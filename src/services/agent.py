import logging
from typing import Dict, Any, Optional, List, Annotated, Sequence, Literal
import sys
import os
from pathlib import Path
import time
import uuid
import re

from pydantic import BaseModel, Field, validator
from enum import Enum

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.config.prompts import (
    detect_gratitude, get_fallback_response, 
    get_gratitude_response, get_off_topic_response, 
    get_no_data_response, format_response_with_disclaimer,
    format_response_with_sources, get_error_response, detect_greeting,
    detect_language, SYSTEM_PROMPT, DISCLAIMER,
    IntelligentRecommender, format_complete_response,get_rate_limit_response,get_greeting_response,detect_human_expression
)

from src.services.rag import query_rag, initialize_rag, get_rag_status, setup_llm
from src.services.validator import validate_query
from src.services.question_manager import (
    get_next_question, remove_first_question, add_question,
    generate_new_question_from_data, get_all_questions,
    get_question_count, reset_question_queue,
    initialize_question_file, get_archive, get_file_paths
)
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

_is_initialized = False
_graph_app = None
_mongo_db = None


# ============================================
# PYDANTIC MODELS
# ============================================

class ChannelType(str, Enum):
    API = "api"
    WEB = "web"
    MOBILE = "mobile"
    EMAIL = "email"
    BATCH = "batch"
    GRAPH = "graph"
    WEBHOOK = "webhook"      # ← add this
    BATCH_EMAIL = "batch_email"  # ← also add — used in webhook.py line 384"


class QueryRequest(BaseModel):
    """Request model for user queries"""
    question: str = Field(..., min_length=1, max_length=2000, description="User's question")
    thread_id: Optional[str] = Field(None, description="Conversation thread identifier")
    channel: Optional[ChannelType] = Field(ChannelType.API, description="Source channel")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    username: Optional[str] = Field(None, description="Optional username")
    language: Optional[str] = Field(default="en", description="Language (en/id)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    
    @validator('question')
    def question_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Question cannot be empty or whitespace')
        return v.strip()
    
    @validator('thread_id', pre=True, always=True)
    def set_thread_id(cls, v):
        return v or str(uuid.uuid4())
    
    @validator('language')
    def validate_language(cls, v):
        if v not in ["en", "id"]:
            raise ValueError('Language must be "en" or "id"')
        return v


class QueryResponse(BaseModel):
    """Response model for queries"""
    question: str = Field(..., description="Original question")
    answer: str = Field(..., description="Generated answer")
    processing_time: float = Field(..., description="Time taken to process in seconds")
    thread_id: str = Field(..., description="Conversation thread identifier")
    language_detected: str = Field(default="en", description="Detected language")
    response_type: str = Field(default="answer", description="Type of response")
    success: bool = Field(default=True, description="Whether processing succeeded")
    validated: bool = Field(default=True, description="Whether query was validated")
    greeting: bool = Field(default=False, description="Whether this was a greeting")
    gratitude: bool = Field(default=False, description="Whether this was gratitude")
    sources: Optional[List[Dict[str, Any]]] = Field(None, description="Referenced sources")
    recommendations: Optional[List[str]] = Field(None, description="Follow-up recommendations")
    queue_info: Optional[Dict[str, Any]] = Field(None, description="Queue information")
    error: Optional[str] = Field(None, description="Error message if applicable")
    user_id: Optional[str] = Field(None, description="User identifier")
    attempts: int = Field(default=1, description="Number of processing attempts")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class BatchEmailRequest(BaseModel):
    """Request model for batch email processing"""
    question: str = Field(..., min_length=1, max_length=2000, description="Question to analyze")
    emails: List[str] = Field(..., min_items=1, max_items=100, description="Email addresses")
    phone: Optional[str] = Field(None, description="Contact phone number")
    subject: Optional[str] = Field(None, description="Email subject line")
    include_pdf: Optional[bool] = Field(False, description="Include PDF report")
    frequency: Optional[str] = Field("once", description="Delivery frequency")
    language: Optional[str] = Field(default="en", description="Language preference")
    
    @validator('emails')
    def validate_emails(cls, v):
        """Validate email format"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for email in v:
            if not re.match(email_pattern, email):
                raise ValueError(f'Invalid email format: {email}')
        return list(set(v))


class ConversationContext(BaseModel):
    """Track conversation context for intelligent recommendations"""
    thread_id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    questions_history: List[str] = Field(default_factory=list, max_items=50)
    topics_discussed: List[str] = Field(default_factory=list)
    user_level: str = Field(default="beginner")
    language: str = Field(default="en")
    channel: ChannelType = Field(default=ChannelType.API)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_interaction: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    interaction_count: int = Field(default=0)


class AgentMetrics(BaseModel):
    """Track agent performance metrics"""
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    total_processing_time: float = 0.0
    avg_processing_time: float = 0.0
    greetings_handled: int = 0
    gratitude_handled: int = 0
    off_topic_rejected: int = 0


from datetime import datetime


# ============================================
# CONVERSATION CONTEXT MANAGER
# ============================================

class ConversationManager:
    """Manages conversation contexts across threads"""
    
    def __init__(self):
        self.contexts: Dict[str, ConversationContext] = {}
        self.metrics = AgentMetrics()
    
    def get_or_create_context(self, request: QueryRequest) -> ConversationContext:
        """Get or create conversation context"""
        thread_id = request.thread_id
        
        if thread_id not in self.contexts:
            self.contexts[thread_id] = ConversationContext(
                thread_id=thread_id,
                user_id=request.user_id,
                username=request.username,
                language=request.language or detect_language(request.question),
                channel=request.channel
            )
        
        context = self.contexts[thread_id]
        context.last_interaction = datetime.utcnow().isoformat()
        context.interaction_count += 1
        
        return context
    
    def update_context(self, context: ConversationContext, question: str, response_type: str, entities: Dict[str, Any]):
        """Update context with new interaction data"""
        context.questions_history.append(question)
        
        if entities.get("companies"):
            context.topics_discussed.extend(["company_analysis"] * len(entities["companies"]))
        if entities.get("sectors"):
            context.topics_discussed.extend(["sector_analysis"] * len(entities["sectors"]))
        if entities.get("assets"):
            context.topics_discussed.extend(entities["assets"])
        
        if len(context.questions_history) > 5:
            context.user_level = IntelligentRecommender.estimate_user_level(context.questions_history)
    
    def get_summary(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation summary"""
        context = self.contexts.get(thread_id)
        
        if not context:
            return None
        
        return {
            "thread_id": thread_id,
            "interaction_count": context.interaction_count,
            "topics": list(set(context.topics_discussed)),
            "user_level": context.user_level,
            "language": context.language,
            "duration": {
                "created_at": context.created_at,
                "last_interaction": context.last_interaction
            },
            "question_count": len(context.questions_history)
        }
    
    def clear_old_contexts(self, max_age_hours: int = 24):
        """Clear old conversation contexts"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        threads_to_remove = []
        
        for thread_id, context in self.contexts.items():
            last_interaction = datetime.fromisoformat(context.last_interaction)
            if last_interaction < cutoff_time:
                threads_to_remove.append(thread_id)
        
        for thread_id in threads_to_remove:
            del self.contexts[thread_id]
        
        return len(threads_to_remove)


# ============================================
# ENTITY EXTRACTION
# ============================================

class EntityExtractor:
    """Extract entities from questions"""
    
    @staticmethod
    def extract(question: str) -> Dict[str, Any]:
        """Extract key entities from question"""
        entities = {
            "companies": [],
            "sectors": [],
            "assets": [],
            "metrics": [],
            "time_periods": []
        }
        
        # Extract tickers
        ticker_pattern = r'\b[A-Z]{1,5}\b'
        tickers = re.findall(ticker_pattern, question)
        entities["companies"] = tickers
        
        # Extract sectors
        sectors = ["tech", "technology", "healthcare", "finance", "financial", "energy",
                   "consumer", "industrial", "real estate", "utilities", "materials"]
        question_lower = question.lower()
        entities["sectors"] = [s for s in sectors if s in question_lower]
        
        # Extract asset types
        assets = {
            "stocks": ["stock", "equity", "share", "company"],
            "crypto": ["crypto", "bitcoin", "ethereum", "blockchain"],
            "commodities": ["gold", "oil", "copper", "commodity"],
            "forex": ["currency", "dollar", "euro", "yen"]
        }
        
        for asset_type, keywords in assets.items():
            if any(kw in question_lower for kw in keywords):
                entities["assets"].append(asset_type)
        
        # Extract metrics
        metrics = ["pe ratio", "revenue", "earnings", "profit", "margin", "dividend", "yield"]
        entities["metrics"] = [m for m in metrics if m in question_lower]
        
        # Extract time periods
        time_periods = ["today", "yesterday", "week", "month", "quarter", "year", "year to date"]
        entities["time_periods"] = [tp for tp in time_periods if tp in question_lower]
        
        return entities


# ============================================
# 1. GRAPH STATE DEFINITION
# ============================================

class AgentState(TypedDict):
    """Tracks the total operational memory of our multi-agent network."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_question: str
    language: str
    is_greeting: bool
    is_gratitude: bool
    is_valid: bool
    validation_reason: str
    retrieved_context: str
    sources: List[Dict[str, Any]]
    analysis_result: str
    recommendations: List[str]
    queue_data: Dict[str, Any]
    next_worker: str
    error: Optional[str]
    db: Optional[AsyncIOMotorDatabase]
    user_id: Optional[str]
    username: Optional[str]
    start_time: float
    response_type: str
    entities: Dict[str, Any]


# ============================================
# 2. DEFINING THE 6 AGENT NODES
# ============================================

def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    Agent #1: The Orchestrator / Router.
    Analyzes current state metrics and directs execution to specialized workers.
    """
    logger.info(f"--- SUPERVISOR AGENT (User: {state.get('username', 'anonymous')}) ---")
    
    # Rule 1: Check for greeting
    if state.get("is_greeting"):
        return {"next_worker": "end"}
    
    # Rule 2: Check for gratitude
    if state.get("is_gratitude"):
        return {"next_worker": "end"}
    
    # Rule 3: Validate if it hasn't been checked yet
    if state.get("is_valid") is None:
        return {"next_worker": "guard"}
    
    # Rule 4: Stop early if the guardrail flagged the query
    if not state.get("is_valid"):
        return {"next_worker": "end"}
    
    # Rule 5: If the user is asking about the queue backlog
    if "queue" in state["current_question"].lower() and not state.get("queue_data"):
        return {"next_worker": "queue"}
    
    # Rule 6: Extract data if no context has been found yet
    if not state.get("retrieved_context"):
        return {"next_worker": "rag"}
    
    # Rule 7: Run final evaluations if context is ready but analysis is pending
    if not state.get("analysis_result"):
        return {"next_worker": "analyst"}
    
    # Everything is handled
    return {"next_worker": "end"}


def greeting_node(state: AgentState) -> Dict[str, Any]:
    """Agent #1.5: Handles greeting messages."""
    logger.info("--- GREETING AGENT ---")
    question = state["current_question"]
    language = state.get("language", "en")
    
    is_greeting = detect_greeting(question)
    
    if is_greeting:
        fallback = get_fallback_response(question, language=language)
        response = fallback if fallback else get_greeting_response(language=language)
        
        return {
            "is_greeting": True,
            "analysis_result": response,
            "response_type": "greeting",
            "messages": [AIMessage(content="Greeting Agent: Greeting message detected and handled.")]
        }
    
    return {
        "is_greeting": False,
        "messages": [AIMessage(content="Greeting Agent: Not a greeting message.")]
    }


def gratitude_node(state: AgentState) -> Dict[str, Any]:
    """Agent #2: Handles gratitude and social messages."""
    logger.info("--- GRATITUDE AGENT ---")
    question = state["current_question"]
    language = state.get("language", "en")
    
    is_gratitude = detect_gratitude(question)
    
    if is_gratitude:
        fallback = get_fallback_response(question, language=language)
        response = fallback if fallback else get_gratitude_response(language=language)
        
        return {
            "is_gratitude": True,
            "analysis_result": response,
            "response_type": "gratitude",
            "messages": [AIMessage(content="Gratitude Agent: Social message detected and handled.")]
        }
    
    return {
        "is_gratitude": False,
        "messages": [AIMessage(content="Gratitude Agent: Not a social message.")]
    }


def guard_node(state: AgentState) -> Dict[str, Any]:
    """Agent #3: Evaluates compliance, safety, and domain alignment."""
    logger.info("--- GUARDRAIL AGENT ---")
    question = state["current_question"]
    
    validation = validate_query(question)
    
    return {
        "is_valid": validation["allowed"],
        "validation_reason": validation.get("reason", ""),
        "response_type": "validation",
        "messages": [AIMessage(content=f"Guardrail Check Completed. Allowed: {validation['allowed']}")]
    }


async def rag_node(state: AgentState) -> Dict[str, Any]:
    """Agent #4: RAG data retrieval agent."""
    logger.info("--- RAG DATA AGENT ---")
    
    result = await query_rag(state["current_question"])
    
    context = ""
    sources = []
    
    if result["success"]:
        sources = result.get("sources", [])
        for s in sources[:3]:
            context += s.get("text", "") + "\n\n"
        cache_status = "🔄 FRESH" if not result.get("from_cache") else "💾 CACHED"
        logger.info(f"{cache_status} - Found {len(sources)} sources")
    else:
        context = "No relevant context found"
    
    return {
        "retrieved_context": context,
        "sources": sources,
        "messages": [AIMessage(content=f"RAG found {len(sources)} chunks")]
    }


def queue_node(state: AgentState) -> Dict[str, Any]:
    """Agent #5: Question queue manager agent."""
    logger.info("--- QUEUE MANAGER AGENT ---")
    
    db = state.get("db")
    
    try:
        count = get_question_count(db=db) if db is not None else 0
        next_q = get_next_question(db=db) if db is not None else None
        all_q = get_all_questions(db=db)[:5] if db is not None else []
    except Exception as e:
        logger.warning(f"Queue fetch error: {str(e)}")
        count = 0
        next_q = None
        all_q = []
    
    data = {
        "total_backlog": count,
        "next_up": next_q,
        "sample_queue": all_q
    }
    
    return {
        "queue_data": data,
        "messages": [AIMessage(content=f"Queue Agent: Synced pipeline. Remaining backlog: {count}")]
    }


def analyst_node(state: AgentState) -> Dict[str, Any]:
    """Agent #6: Financial analyst using LLM synthesis."""
    logger.info("--- FINANCIAL ANALYST AGENT ---")
    
    context = state.get("retrieved_context", "")
    question = state["current_question"]
    language = state.get("language", "en")
    sources = state.get("sources", [])
    
    try:
        llm = setup_llm()
        
        prompt = SYSTEM_PROMPT.format(
            context=context or "No specific data found.",
            question=question
        )
        
        try:
            response = llm.complete(prompt)
            answer = str(response)
        except AttributeError:
            try:
                from llama_index.core.llms import ChatMessage
                messages = [ChatMessage(role="user", content=prompt)]
                response = llm.chat(messages)
                answer = response.message.content
            except Exception as e:
                logger.warning(f"LLM call failed: {str(e)}")
                answer = get_no_data_response(language=language)
        
        # Generate intelligent recommendations
        recommendations_text = IntelligentRecommender.generate_recommendations(
            question,
            user_level="beginner",
            language=language
        )
        
        recommendations = []
        if recommendations_text:
            recommendations = [line.strip("• ").strip() for line in recommendations_text.split("\n") if line.strip("• ")]
        
        return {
            "analysis_result": answer,
            "recommendations": recommendations,
            "response_type": "analysis",
            "messages": [AIMessage(content="Analyst Agent: Business interpretation generation complete.")]
        }
    except Exception as e:
        logger.error(f"Analyst node error: {str(e)}")
        return {
            "analysis_result": get_no_data_response(language=state.get("language", "en")),
            "error": str(e),
            "response_type": "error",
            "messages": [AIMessage(content=f"Analyst Agent Error: {str(e)}")]
        }


# ============================================
# 3. CONDITIONAL ROUTING LOGIC
# ============================================

def router_edge(state: AgentState) -> Literal["greeting", "gratitude", "guard", "rag", "queue", "analyst", "__end__"]:
    """Reads state calculations from Supervisor to decide the true next path node."""
    decision = state.get("next_worker", "end")
    
    # Check greeting first
    if state.get("is_greeting"):
        return "greeting"
    
    # Check gratitude
    if state.get("is_gratitude"):
        return "gratitude"
    
    if decision == "end":
        return END
    
    return decision


# ============================================
# 4. BUILDING AND COMPILING THE LANGGRAPH
# ============================================

def build_economic_advisor_graph():
    """Build and compile the multi-agent LangGraph."""
    workflow = StateGraph(AgentState)
    
    # Register all agent nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("gratitude", gratitude_node)
    workflow.add_node("guard", guard_node)
    workflow.add_node("rag", rag_node)
    workflow.add_node("queue", queue_node)
    workflow.add_node("analyst", analyst_node)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Configure dynamic supervisor distribution connections
    workflow.add_conditional_edges(
        "supervisor",
        router_edge,
        {
            "greeting": "greeting",
            "gratitude": "gratitude",
            "guard": "guard",
            "rag": "rag",
            "queue": "queue",
            "analyst": "analyst",
            "__end__": END
        }
    )
    
    # Worker nodes always report back to the Supervisor
    workflow.add_edge("greeting", "supervisor")
    workflow.add_edge("gratitude", "supervisor")
    workflow.add_edge("guard", "supervisor")
    workflow.add_edge("rag", "supervisor")
    workflow.add_edge("queue", "supervisor")
    workflow.add_edge("analyst", "supervisor")
    
    return workflow.compile()


# ============================================
# 5. INITIALIZATION
# ============================================

conversation_manager = ConversationManager()


def initialize_agent(force_reindex: bool = False, mongo_db=None):
    """Initialize the agent and compile the graph."""
    global _is_initialized, _graph_app, _mongo_db
    
    _mongo_db = mongo_db
    
    try:
        logger.info("🤖 Initializing Multi-Agent Economic Advisor...")
        logger.info(f"📁 Project root: {PROJECT_ROOT}")
        logger.info(f"📁 Question files: {get_file_paths()}")
        
        # Initialize RAG (ChromaDB)
        initialize_rag(force_reindex=force_reindex)
        logger.info("✅ RAG system (ChromaDB) initialized")
        
        # Initialize question manager with MongoDB
        try:
            count = initialize_question_file(db=_mongo_db) if _mongo_db else 0
            logger.info(f"✅ Question queue (MongoDB) initialized with {count} questions")
        except Exception as e:
            logger.warning(f"⚠️ Question queue initialization warning: {str(e)}")
        
        # Build and compile the graph
        _graph_app = build_economic_advisor_graph()
        logger.info("✅ LangGraph multi-agent system compiled")
        
        _is_initialized = True
        logger.info("✅ Multi-Agent Economic Advisor ready!")
        
    except Exception as e:
        logger.error(f"❌ Agent initialization failed: {str(e)}")
        raise


# ============================================
# 6. ENTRYPOINT WRAPPER (Main Interface)
# ============================================

async def ask_agent(
    question: str,
    thread_id: Optional[str] = None,
    db: Optional[AsyncIOMotorDatabase] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    language: Optional[str] = None,
    channel: str = "api"
) -> dict:
    """
    Main entry point for agent queries.
    Routes through multi-agent LangGraph system with intelligent context management.
    
    **Parameters:**
    - question: The user's question
    - thread_id: Optional conversation thread ID
    - db: MongoDB database connection
    - user_id: User identifier
    - username: User's username
    - language: Response language ("en" or "id")
    - channel: Request source channel
    
    **Returns:**
    - Dictionary with complete metadata
    """
    global _is_initialized, _graph_app, _mongo_db
    
    start_time = time.time()
    
    # Use passed db or fall back to global
    if db is not None:
        _mongo_db = db
    
    if not _is_initialized or _graph_app is None:
        initialize_agent(mongo_db=_mongo_db)
    
    try:
        # Validate request
        request = QueryRequest(
            question=question,
            thread_id=thread_id,
            user_id=user_id,
            username=username,
            language=language or detect_language(question),
            channel=ChannelType(channel)
        )
        
        detected_language = request.language
        user_context = f"{username or user_id or 'anonymous'}"
        logger.info(f"📨 Processing question from {user_context}: {question[:100]}... (Language: {detected_language})")
        
        # ============================================
        # ✅ EARLY EXIT FOR NON-TECHNICAL EXPRESSIONS
        # ============================================
        
        # 1. Detect greeting
        if detect_greeting(question):
            answer = get_greeting_response(detected_language)
            processing_time = time.time() - start_time
            conversation_manager.metrics.greetings_handled += 1
            logger.info(f"✅ Greeting detected and handled")
            
            return {
                "question": question,
                "answer": answer,
                "processing_time": processing_time,
                "thread_id": request.thread_id,
                "language_detected": detected_language,
                "response_type": "greeting",
                "success": True,
                "validated": True,
                "greeting": True,
                "gratitude": False,
                "sources": [],
                "recommendations": [],
                "user_id": user_id,
                "error": None,
                "attempts": 1
            }
        
        # 2. Detect gratitude
        if detect_gratitude(question):
            answer = get_gratitude_response(detected_language)
            processing_time = time.time() - start_time
            conversation_manager.metrics.gratitude_handled += 1
            logger.info(f"✅ Gratitude detected and handled")
            
            return {
                "question": question,
                "answer": answer,
                "processing_time": processing_time,
                "thread_id": request.thread_id,
                "language_detected": detected_language,
                "response_type": "gratitude",
                "success": True,
                "validated": True,
                "greeting": False,
                "gratitude": True,
                "sources": [],
                "recommendations": [],
                "user_id": user_id,
                "error": None,
                "attempts": 1
            }
        
        # 3. Detect other human expressions (apologies, complaints, feedback, etc.)
        human_expression_result = detect_human_expression(question, detected_language)
        if human_expression_result:
            processing_time = time.time() - start_time
            conversation_manager.metrics.human_expressions_handled += 1
            logger.info(f"✅ Human expression detected: {human_expression_result['type']}")
            
            return {
                "question": question,
                "answer": human_expression_result['response'],
                "processing_time": processing_time,
                "thread_id": request.thread_id,
                "language_detected": detected_language,
                "response_type": human_expression_result['type'],
                "success": True,
                "validated": True,
                "greeting": False,
                "gratitude": False,
                "sources": [],
                "recommendations": [],
                "user_id": user_id,
                "error": None,
                "attempts": 1
            }
        
        # ============================================
        # Now process actual business questions
        # ============================================
        
        # Get or create conversation context
        context = conversation_manager.get_or_create_context(request)
        
        # Extract entities
        entities = EntityExtractor.extract(question)
        
        # Initialize state for graph
        initial_state = {
            "messages": [HumanMessage(content=question)],
            "current_question": question,
            "language": request.language,
            "is_greeting": False,  # Already handled
            "is_gratitude": False,  # Already handled
            "is_valid": None,
            "validation_reason": "",
            "retrieved_context": "",
            "sources": [],
            "analysis_result": "",
            "recommendations": [],
            "queue_data": {},
            "next_worker": "supervisor",
            "error": None,
            "db": _mongo_db,
            "user_id": user_id,
            "username": username,
            "start_time": start_time,
            "response_type": "initial",
            "entities": entities
        }
        
        # Run graph execution
        logger.info("🔄 Starting multi-agent graph execution...")
        final_state = await _graph_app.ainvoke(initial_state)
        
        processing_time = time.time() - start_time
        
        # Update conversation context
        response_type = final_state.get("response_type", "answer")
        conversation_manager.update_context(context, question, response_type, entities)
        
        # Check if question is off-topic
        if not final_state.get("is_valid"):
            answer = get_off_topic_response(language=request.language)
            conversation_manager.metrics.off_topic_rejected += 1
            
            logger.warning(f"❌ Off-topic query rejected: {question[:50]}...")
            return {
                "question": question,
                "answer": answer,
                "processing_time": processing_time,
                "thread_id": request.thread_id,
                "language_detected": request.language,
                "response_type": "off-topic",
                "success": False,
                "validated": False,
                "greeting": False,
                "gratitude": False,
                "sources": [],
                "recommendations": [],
                "user_id": user_id,
                "error": final_state.get("validation_reason"),
                "attempts": 1
            }
        
        # Check for errors
        if final_state.get("error"):
            logger.error(f"❌ Error in graph execution: {final_state.get('error')}")
            conversation_manager.metrics.failed_queries += 1
            
            return {
                "question": question,
                "answer": get_error_response(language=request.language),
                "processing_time": processing_time,
                "thread_id": request.thread_id,
                "language_detected": request.language,
                "response_type": "error",
                "success": False,
                "validated": True,
                "greeting": False,
                "gratitude": False,
                "sources": [],
                "recommendations": [],
                "user_id": user_id,
                "error": final_state.get("error"),
                "attempts": len(final_state.get("messages", []))
            }
        
        # Success response
        answer = final_state.get("analysis_result", get_no_data_response(language=request.language))
        answer = format_response_with_disclaimer(answer, language=request.language)
        answer = format_response_with_sources(answer, final_state.get("sources", []))
        
        conversation_manager.metrics.successful_queries += 1
        conversation_manager.metrics.total_processing_time += processing_time
        conversation_manager.metrics.total_queries += 1
        
        logger.info(f"✅ Successfully processed question in {request.language}")
        
        return {
            "question": question,
            "answer": answer,
            "processing_time": processing_time,
            "thread_id": request.thread_id,
            "language_detected": request.language,
            "response_type": final_state.get("response_type", "answer"),
            "success": True,
            "validated": True,
            "sources": final_state.get("sources", []),
            "recommendations": final_state.get("recommendations", []),
            "queue_info": final_state.get("queue_data", {}),
            "greeting": False,
            "gratitude": False,
            "attempts": len(final_state.get("messages", [])),
            "user_id": user_id,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ Multi-Agent Graph execution failed: {str(e)}")
        conversation_manager.metrics.failed_queries += 1
        
        detected_language = detect_language(question) if question else "en"
        
        return {
            "question": question,
            "answer": get_error_response(language=detected_language),
            "processing_time": time.time() - start_time,
            "thread_id": thread_id or str(uuid.uuid4()),
            "language_detected": detected_language,
            "response_type": "error",
            "success": False,
            "validated": True,
            "greeting": False,
            "gratitude": False,
            "sources": [],
            "recommendations": [],
            "user_id": user_id,
            "error": str(e),
            "attempts": 1
        }
# ============================================
# 7. STATUS AND UTILITY FUNCTIONS
# ============================================

async def get_agent_status(db=None) -> Dict[str, Any]:
    """Get comprehensive agent status."""
    rag_status = get_rag_status()
    
    question_count = 0
    questions = []
    file_paths = []
    
    if db is not None:
        try:
            question_count = await db.questions.count_documents({})
            cursor = db.questions.find({}).limit(5)
            questions = await cursor.to_list(length=5)
            file_paths = []
        except Exception as e:
            logger.error(f"Error getting question data: {e}")
    
    avg_processing_time = (
        conversation_manager.metrics.total_processing_time / 
        conversation_manager.metrics.total_queries
    ) if conversation_manager.metrics.total_queries > 0 else 0
    
    return {
        "initialized": _is_initialized,
        "graph_compiled": _graph_app is not None,
        "rag": rag_status,
        "question_queue": {
            "total": question_count,
            "questions": questions,
            "file_paths": file_paths
        },
        "metrics": {
            "total_queries": conversation_manager.metrics.total_queries,
            "successful_queries": conversation_manager.metrics.successful_queries,
            "failed_queries": conversation_manager.metrics.failed_queries,
            "greetings_handled": conversation_manager.metrics.greetings_handled,
            "gratitude_handled": conversation_manager.metrics.gratitude_handled,
            "off_topic_rejected": conversation_manager.metrics.off_topic_rejected,
            "avg_processing_time": round(avg_processing_time, 3)
        },
        "mode": "Multi-Agent Business, Investment, Economy Advisor",
        "agents": {
            "supervisor": "Orchestrator - Routes requests to specialized workers",
            "greeting": "Greeting handler",
            "gratitude": "Social message handler",
            "guard": "Query validation and compliance",
            "rag": "Vector database retrieval",
            "queue": "Question backlog manager",
            "analyst": "LLM-based analysis and synthesis"
        },
        "features": {
            "multi_agent_routing": True,
            "greeting_detection": True,
            "gratitude_detection": True,
            "query_validation": True,
            "rag_retrieval": True,
            "queue_management": True,
            "llm_synthesis": True,
            "source_citation": True,
            "intelligent_recommendations": True,
            "conversation_context": True,
            "bilingual_support": True,
            "disclaimer": True
        },
        "conversation_contexts": len(conversation_manager.contexts)
    }


def reset_question_system(db=None) -> Dict[str, Any]:
    """Reset the question queue system."""
    global _mongo_db
    
    if db is not None:
        _mongo_db = db
    
    try:
        count = reset_question_queue(db=_mongo_db) if _mongo_db else 0
    except Exception as e:
        logger.warning(f"Reset error: {str(e)}")
        count = 0
    
    return {
        "status": "success",
        "message": f"Question queue reset with {count} questions",
        "file_paths": get_file_paths()
    }


def get_graph_app():
    """Get the compiled graph application."""
    global _graph_app
    if _graph_app is None:
        initialize_agent()
    return _graph_app


def get_conversation_summary(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get conversation summary for a thread."""
    return conversation_manager.get_summary(thread_id)


def clear_old_conversations(max_age_hours: int = 24) -> int:
    """Clear old conversation contexts."""
    return conversation_manager.clear_old_contexts(max_age_hours)


# ============================================
# UTILITY: Batch Email Processor
# ============================================

class BatchEmailProcessor:
    """Process batch email requests"""
    
    def __init__(self):
        pass
    
    async def process_batch(
        self, 
        request: BatchEmailRequest, 
        db: Optional[AsyncIOMotorDatabase] = None,   # ← ADD this parameter
    ) -> Dict[str, Any]:
        
        """Process batch email request: ask agent, send via SMTP, and log to history."""
        from src.services.email_sender import send_batch_emails
        from src.services.history_manager import create_history_entry as create_history
        from src.models.history import SentHistoryCreate, ChannelType as HistoryChannel, DeliveryStatus
        
        batch_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        
        # Fall back to module-level global if no db passed
        effective_db = db if db is not None else _mongo_db
        
        # Process the question through the agent (pass db so it routes correctly too)
        response = await ask_agent(
            question=request.question,
            thread_id=thread_id,
            db=effective_db,                # ← pass db here too
            language=request.language,
        )
        
        answer = response.get("answer", "")
        
        # Build the newspaper HTML email body
        email_content = self._prepare_email_content(
            request.question,
            response,
            request.subject,
        )
        
        # Plain-text fallback for clients that prefer it
        plain_text_fallback = (
            f"Question: {request.question}\n\n"
            f"{answer}\n\n"
            f"-- The Jojoba Economic Review"
        )
        
        subject = request.subject or f"Economic Analysis: {request.question[:60]}"
        
        # ✅ Send via SMTP with HTML in html_body so it isn't mangled by .replace("\n","<br>")
        send_result = await send_batch_emails(
            to_emails=request.emails,
            subject=subject,
            body=plain_text_fallback,
            html_body=email_content,
        )
        
        sent_count = send_result.get("sent_count", 0)
        failed_emails = send_result.get("failed_emails", [])
        simulated = send_result.get("simulated", False)
        smtp_error = send_result.get("error")
        
        # Determine overall status
        if simulated:
            overall_status = "simulated"
            delivery_status = DeliveryStatus.PENDING
        elif sent_count > 0 and not failed_emails:
            overall_status = "sent"
            delivery_status = DeliveryStatus.SENT
        elif sent_count > 0 and failed_emails:
            overall_status = "partial"
            delivery_status = DeliveryStatus.SENT
        else:
            overall_status = "failed"
            delivery_status = DeliveryStatus.FAILED
        
        logger.info(f"📧 Batch {batch_id}: {overall_status} - sent {sent_count}/{len(request.emails)}")
        
        # ✅ Log to history collection so the Sent History UI picks it up
        try:
            history_payload = SentHistoryCreate(
                question=request.question,
                answer=answer or "(no answer generated)",
                channel=HistoryChannel.BATCH,
                status=delivery_status,
                processing_time=response.get("processing_time", 0),
                iterations=response.get("attempts", 1),
                response_type=response.get("response_type", "answer"),
                language=request.language or "en",
                recipients=request.emails,
                recipient_count=len(request.emails),
                sources=response.get("sources", []),
                thread_id=thread_id,
                metadata={
                    "batch_id": batch_id,
                    "subject": subject,
                    "frequency": request.frequency,
                    "include_pdf": request.include_pdf,
                    "sent_count": sent_count,
                    "failed_emails": failed_emails,
                    "simulated": simulated,
                    "smtp_error": smtp_error,
                },
            )
            
            history_id = await create_history(
                db=effective_db, 
                history_data=history_payload,
                user_id=getattr(self, "_current_user_id", None),
                username=getattr(self, "_current_username", None),
            )
            logger.info(f"📝 History logged: {history_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to log batch history: {str(e)}")
            history_id = None
        
        return {
            "batch_id": batch_id,
            "history_id": history_id,
            "thread_id": thread_id,
            "status": overall_status,
            "email_count": len(request.emails),
            "sent_count": sent_count,
            "failed_count": len(failed_emails),
            "failed_emails": failed_emails,
            "emails": request.emails,
            "question": request.question,
            "response_preview": answer[:500] if answer else "",
            "frequency": request.frequency,
            "include_pdf": request.include_pdf,
            "created_at": datetime.utcnow().isoformat(),
            "simulated": simulated,
            "error": smtp_error,
        }
    
    def _prepare_email_content(self, question: str, response: Dict[str, Any], subject: Optional[str] = None) -> str:
        """Prepare email content in newspaper-style HTML format (email-client safe)."""
        
        # Extract fields from response dict
        answer = response.get("answer", "No analysis available at the time of publication.")
        processing_time = response.get("processing_time", 0)
        response_type = response.get("response_type", "answer")
        recommendations = response.get("recommendations") or []
        sources = response.get("sources") or []
        language = response.get("language_detected", "en")
        
        # Formatted timestamp
        now = datetime.utcnow()
        date_long = now.strftime("%A, %d %B %Y")
        time_short = now.strftime("%H:%M")
        
        # Format answer into paragraphs (split on double newline)
        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [answer]
        
        # Build paragraphs HTML, with drop cap on the first one
        para_html_parts = []
        for i, para in enumerate(paragraphs):
            # Convert single newlines inside paragraphs to <br/>
            para_clean = para.replace("\n", "<br/>")
            if i == 0 and para_clean:
                first_char = para_clean[0]
                rest = para_clean[1:]
                para_html_parts.append(
                    f'<p style="margin:0 0 14px 0;font-family:Georgia,\'Times New Roman\',serif;font-size:16px;line-height:1.75;color:#1a1a1a;">'
                    f'<span style="font-family:Georgia,serif;font-size:52px;font-weight:700;float:left;line-height:0.9;margin:6px 8px 0 0;color:#8b6914;">{first_char}</span>'
                    f'{rest}</p>'
                )
            else:
                para_html_parts.append(
                    f'<p style="margin:0 0 14px 0;font-family:Georgia,\'Times New Roman\',serif;font-size:16px;line-height:1.75;color:#1a1a1a;">{para_clean}</p>'
                )
        article_body = "\n".join(para_html_parts)
        
        # Build recommendations block (if any)
        recs_html = ""
        if recommendations:
            rec_lines = "<br/>".join([f"&bull; {rec}" for rec in recommendations[:5]])
            recs_html = f"""
  <tr>
    <td style="padding:0 32px 24px 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f5f1e3" style="background-color:#f5f1e3;border-left:4px solid #8b6914;">
        <tr>
          <td style="padding:14px 18px;">
            <div style="font-family:Georgia,serif;font-size:10px;text-transform:uppercase;letter-spacing:2px;color:#8b6914;font-weight:700;margin-bottom:8px;">
              &#128204; Further Reading &middot; Suggested Questions
            </div>
            <div style="font-family:Georgia,serif;font-size:14px;font-style:italic;color:#4a4233;line-height:1.7;">
              {rec_lines}
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>"""
        
        sources_count = len(sources)
        sources_label = f"{sources_count} source{'s' if sources_count != 1 else ''} consulted" if sources_count else "Synthesized analysis"
        
        # Clean headline (remove trailing punctuation, escape HTML)
        headline_text = question.strip().rstrip("?.!") if question else "Market Analysis"
        # Basic HTML escape for headline
        headline_text = headline_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>The Jojoba Economic Review</title>
</head>
<body style="margin:0;padding:0;background-color:#e8e4d8;font-family:Georgia,'Times New Roman',Times,serif;color:#1a1a1a;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#e8e4d8" style="background-color:#e8e4d8;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" bgcolor="#fdfcf7" style="max-width:640px;width:100%;background-color:#fdfcf7;border:1px solid #c8c2b0;">

  <tr>
    <td style="padding:18px 32px 0 32px;border-bottom:1px solid #d4cdb5;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="left" style="font-family:Georgia,serif;font-size:10px;text-transform:uppercase;letter-spacing:2px;color:#6b5d3f;font-weight:700;padding-bottom:10px;">Vol. I &mdash; Reader Edition</td>
          <td align="center" style="font-family:Georgia,serif;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6b5d3f;font-style:italic;padding-bottom:10px;">Est. MMXXVI</td>
          <td align="right" style="font-family:Georgia,serif;font-size:10px;text-transform:uppercase;letter-spacing:2px;color:#6b5d3f;font-weight:700;padding-bottom:10px;">On-Demand</td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td align="center" style="padding:18px 32px 6px 32px;background-color:#fdfcf7;">
      <div style="font-family:Georgia,'Times New Roman',serif;font-size:42px;font-weight:900;letter-spacing:-1px;line-height:1;color:#0d0d0d;">
        The Jojoba <span style="color:#8b6914;font-style:italic;">Economic</span> Review
      </div>
    </td>
  </tr>

  <tr>
    <td align="center" style="padding:0 32px 18px 32px;border-bottom:3px solid #1a1a1a;">
      <div style="font-family:Georgia,serif;font-style:italic;font-size:13px;color:#5a4f3a;letter-spacing:0.5px;">
        &mdash; Intelligence for the Discerning Investor &mdash;
      </div>
    </td>
  </tr>

  <tr>
    <td style="padding:2px 32px 0 32px;border-bottom:1px solid #1a1a1a;font-size:0;line-height:0;">&nbsp;</td>
  </tr>

  <tr>
    <td bgcolor="#1a1a1a" style="background-color:#1a1a1a;padding:10px 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="left" style="font-family:Georgia,serif;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#fdfcf7;">{date_long}</td>
          <td align="center" style="font-family:Georgia,serif;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#d4a542;font-weight:700;">&#9733; AI Edition &#9733;</td>
          <td align="right" style="font-family:Georgia,serif;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#fdfcf7;">{time_short} WIB</td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding:28px 32px 0 32px;">
      <div style="font-family:Georgia,serif;font-size:11px;text-transform:uppercase;letter-spacing:2.5px;color:#8b6914;font-weight:700;padding-bottom:6px;border-bottom:1px solid #d4cdb5;">
        Reader Inquiry &middot; Economic Intelligence
      </div>
    </td>
  </tr>

  <tr>
    <td style="padding:8px 32px 0 32px;">
      <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:30px;line-height:1.15;font-weight:700;color:#0d0d0d;letter-spacing:-0.3px;">
        {headline_text}
      </h1>
    </td>
  </tr>

  <tr>
    <td style="padding:12px 32px 14px 32px;border-bottom:1px solid #d4cdb5;">
      <p style="margin:0;font-family:Georgia,serif;font-size:15px;line-height:1.5;font-style:italic;color:#4a4233;">
        An AI-assisted analysis prepared in response to a reader's inquiry, drawing on current economic data, sector indicators, and contextual market intelligence.
      </p>
    </td>
  </tr>

  <tr>
    <td style="padding:14px 32px 18px 32px;">
      <div style="font-family:Georgia,serif;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#6b5d3f;">
        <span style="font-weight:700;color:#1a1a1a;">By Jojoba AI Desk</span>
        &nbsp;|&nbsp; Filed {time_short} WIB
        &nbsp;|&nbsp; {processing_time:.2f}s analysis
        &nbsp;|&nbsp; {sources_label}
      </div>
    </td>
  </tr>

  <tr>
    <td style="padding:0 32px 8px 32px;">
      {article_body}
    </td>
  </tr>

  <tr>
    <td style="padding:8px 32px 8px 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td style="border-top:2px solid #1a1a1a;font-size:0;line-height:0;">&nbsp;</td></tr>
        <tr>
          <td align="center" style="padding:14px 24px;font-family:Georgia,serif;font-style:italic;font-size:18px;line-height:1.4;color:#4a4233;">
            &ldquo;Read the data. Question the narrative. Decide for yourself.&rdquo;
          </td>
        </tr>
        <tr><td style="border-top:1px solid #1a1a1a;font-size:0;line-height:0;">&nbsp;</td></tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding:16px 32px 24px 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #1a1a1a;border-bottom:1px solid #1a1a1a;">
        <tr>
          <td align="center" width="25%" style="padding:14px 4px;border-right:1px solid #d4cdb5;font-family:Georgia,serif;">
            <div style="font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:#6b5d3f;margin-bottom:4px;">Processing</div>
            <div style="font-size:18px;font-weight:700;color:#0d0d0d;">{processing_time:.2f}s</div>
          </td>
          <td align="center" width="25%" style="padding:14px 4px;border-right:1px solid #d4cdb5;font-family:Georgia,serif;">
            <div style="font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:#6b5d3f;margin-bottom:4px;">Sources</div>
            <div style="font-size:18px;font-weight:700;color:#0d0d0d;">{sources_count}</div>
          </td>
          <td align="center" width="25%" style="padding:14px 4px;border-right:1px solid #d4cdb5;font-family:Georgia,serif;">
            <div style="font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:#6b5d3f;margin-bottom:4px;">Type</div>
            <div style="font-size:13px;font-weight:700;color:#0d0d0d;text-transform:uppercase;">{response_type}</div>
          </td>
          <td align="center" width="25%" style="padding:14px 4px;font-family:Georgia,serif;">
            <div style="font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:#6b5d3f;margin-bottom:4px;">Language</div>
            <div style="font-size:15px;font-weight:700;color:#0d0d0d;text-transform:uppercase;">{language}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
{recs_html}
  <tr>
    <td bgcolor="#1a1a1a" style="background-color:#1a1a1a;padding:20px 32px;text-align:center;">
      <div style="font-family:Georgia,serif;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#d4a542;font-style:italic;font-weight:700;margin-bottom:8px;">
        &#9888; Not Financial Advice &middot; For Educational Purposes Only
      </div>
      <div style="font-family:Georgia,serif;font-size:11px;line-height:1.5;color:#c8c2b0;">
        Always consult a licensed financial advisor before making investment decisions. Past performance is not indicative of future results.
      </div>
      <div style="font-family:Georgia,serif;font-size:10px;letter-spacing:0.5px;color:#8a8270;margin-top:10px;padding-top:10px;border-top:1px solid #4a4233;">
        The Jojoba Economic Review &middot; Published by Jojoba AI &middot; Reader-Requested Edition
      </div>
    </td>
  </tr>

</table>

</td></tr>
</table>

</body>
</html>"""
        
        return html


batch_processor = BatchEmailProcessor()
