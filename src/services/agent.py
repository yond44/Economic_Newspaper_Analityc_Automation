import logging
from typing import Dict, Any, Optional, List
import sys
from pathlib import Path

# Add project root to path if needed
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.rag import query_rag, initialize_rag, get_rag_status
from src.config.prompts import (
    SYSTEM_PROMPT, 
    NO_DATA_RESPONSE, 
    DISCLAIMER,
    detect_gratitude,
    get_gratitude_response,
    get_fallback_response,
    format_response_with_sources,
    format_response_with_disclaimer,
    get_no_data_response
)
from src.services.validator import validate_query
from src.services.question_manager import (
    get_next_question,
    remove_first_question,
    add_question,
    generate_new_question_from_data,
    get_all_questions,
    get_question_count,
    reset_question_queue,
    initialize_question_file,
    get_archive,
    get_file_paths
)
from dotenv import load_dotenv


# Load .env from project root
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


logger = logging.getLogger(__name__)

_is_initialized = False


def initialize_agent(force_reindex: bool = False):
    global _is_initialized
    
    try:
        logger.info("Initializing Economic Advisor...")
        logger.info(f"📁 Project root: {PROJECT_ROOT}")
        logger.info(f"📁 Question files: {get_file_paths()}")
        
        initialize_rag(force_reindex=force_reindex)
        
        count = initialize_question_file()
        logger.info(f"Question queue initialized with {count} questions")
        
        _is_initialized = True
        logger.info("Economic Advisor initialized")
    except Exception as e:
        logger.error(f"Agent initialization failed: {str(e)}")
        raise


async def ask_agent(question: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    global _is_initialized
    
    if not _is_initialized:
        initialize_agent()
    
    try:
        # STEP 1: Check for gratitude/social messages
        if detect_gratitude(question):
            fallback_response = get_fallback_response(question)
            if fallback_response:
                return {
                    "answer": fallback_response,
                    "success": True,
                    "validated": True,
                    "gratitude": True,
                    "attempts": 0
                }
            return {
                "answer": get_gratitude_response(),
                "success": True,
                "validated": True,
                "gratitude": True,
                "attempts": 0
            }
        
        # STEP 2: Validate the question
        validation = validate_query(question)
        if not validation["allowed"]:
            logger.warning(f"Question rejected: {validation['reason']}")
            return {
                "answer": validation["response"],
                "success": False,
                "validated": False,
                "reason": validation["reason"]
            }
        
        # STEP 3: Query RAG
        result = query_rag(question)
        
        if not result["success"]:
            return {
                "answer": get_no_data_response(),
                "success": False,
                "validated": True,
                "error": result.get("error", "Search failed")
            }
        
        # STEP 4: Build context from sources
        sources = result.get("sources", [])
        context_text = ""
        for s in sources[:3]:
            context_text += s.get("text", "") + "\n\n"
        
        # STEP 5: Use system prompt with your data
        full_prompt = SYSTEM_PROMPT.format(
            context=context_text or "No specific data found.",
            question=question
        )
        
        # STEP 6: Get response from LLM
        from src.services.rag import setup_llm
        llm = setup_llm()
        
        try:
            response = llm.complete(full_prompt)
            answer = str(response)
        except AttributeError:
            try:
                from llama_index.core.llms import ChatMessage
                messages = [ChatMessage(role="user", content=full_prompt)]
                response = llm.chat(messages)
                answer = response.message.content
            except Exception as e:
                logger.warning(f"LLM call failed: {str(e)}")
                answer = "I encountered an error processing your question. Please try again."
        
        # STEP 7: Add disclaimer and sources
        answer = format_response_with_disclaimer(answer)
        answer = format_response_with_sources(answer, sources)
        
        return {
            "answer": answer,
            "success": True,
            "validated": True,
            "sources": sources,
            "attempts": result.get("attempts", 0),
            "gratitude": False,
            "question": question
        }
        
    except Exception as e:
        logger.error(f"Agent error: {str(e)}")
        return {
            "answer": f"An error occurred: {str(e)}",
            "success": False,
            "validated": True,
            "error": str(e)
        }


def get_agent_status() -> Dict[str, Any]:
    rag_status = get_rag_status()
    return {
        "initialized": _is_initialized,
        "rag": rag_status,
        "question_queue": {
            "total": get_question_count(),
            "questions": get_all_questions()[:5], 
            "file_paths": get_file_paths()
        },
        "mode": "Business, Investment, Economy Advisor",
        "features": {
            "gratitude_detection": True,
            "multi_language": True,
            "source_citation": True,
            "disclaimer": True,
            "auto_question_management": True
        },
        "limitations": {
            "topic": "Business, Economy, Investment only",
            "knowledge": "Knowledge base only",
            "disclaimer": "Not financial advice"
        }
    }


def reset_question_system() -> Dict[str, Any]:
    count = reset_question_queue()
    return {
        "status": "success",
        "message": f"Question queue reset with {count} questions",
        "file_paths": get_file_paths()
    }