"""
Question Manager - MongoDB Version
"""
import os
import logging
import random
import re
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from bson import ObjectId

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

CURRENT_DIR = Path(__file__).parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

logger.info(f"📁 Project root: {PROJECT_ROOT}")


# ============================================
# DATA LOADING
# ============================================

def load_data_files() -> Dict[str, Any]:
    """Load data from files for question generation"""
    data = {
        "topics": [],
        "sectors": [],
        "companies": [],
        "indicators": [],
        "commodities": [],
        "events": [],
        "regions": []
    }
    
    try:
        data_dir = PROJECT_ROOT / "data" / "raw"
        
        # Load from deep_dive_reports.txt
        deep_dive_file = data_dir / "deep_dive_reports.txt"
        if deep_dive_file.exists():
            with open(deep_dive_file, 'r') as f:
                content = f.read()
                topics = re.findall(r'\$\$TOPIC: (.*?)\$\$', content)
                data["topics"] = list(set(topics))
        
        # Load from structured_analysis.txt
        structured_file = data_dir / "structured_analysis.txt"
        if structured_file.exists():
            with open(structured_file, 'r') as f:
                for line in f:
                    if '|' in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 3:
                            category = parts[0].strip()
                            title = parts[2].strip() if len(parts) > 2 else ""
                            if category and category not in ["CATEGORY", "---", ""]:
                                data["topics"].append(f"{category}: {title}")
        
        # Load from quant_financial_data.txt
        quant_file = data_dir / "quant_financial_data.txt"
        if quant_file.exists():
            with open(quant_file, 'r') as f:
                content = f.read()
                
                # Extract sectors
                sector_match = re.search(r'TABLE 1:.*?\n(.*?)\n\n', content, re.DOTALL)
                if sector_match:
                    lines = sector_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'SECTOR' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['SECTOR', '']:
                                data["sectors"].append(parts[0])
                
                # Extract commodities
                commodity_match = re.search(r'TABLE 3:.*?\n(.*?)\n\n', content, re.DOTALL)
                if commodity_match:
                    lines = commodity_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'COMMODITY' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['COMMODITY', '']:
                                data["commodities"].append(parts[0])
                
                # Extract companies
                company_match = re.search(r'TABLE 8:.*?\n(.*?)\n\n', content, re.DOTALL)
                if company_match:
                    lines = company_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'COMPANY' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['COMPANY', '']:
                                data["companies"].append(parts[0])
                
                # Extract indicators
                indicator_match = re.search(r'TABLE 5:.*?\n(.*?)\n\n', content, re.DOTALL)
                if indicator_match:
                    lines = indicator_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'INDICATOR' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['INDICATOR', '']:
                                data["indicators"].append(parts[0])
        
        # Clean up
        data["topics"] = [t for t in data["topics"] if t and len(t) > 5][:50]
        data["sectors"] = list(set([s for s in data["sectors"] if s and len(s) > 2]))[:20]
        data["companies"] = list(set([c for c in data["companies"] if c and len(c) > 2]))[:20]
        data["commodities"] = list(set([c for c in data["commodities"] if c and len(c) > 2]))[:15]
        data["indicators"] = list(set([i for i in data["indicators"] if i and len(i) > 5]))[:20]
        
        # Add regions and events
        data["regions"] = ["Indonesia", "US", "China", "ASEAN", "Europe", "Japan", "India", "Singapore"]
        data["events"] = [
            "BI rate decision", "Fed meeting", "inflation release", "GDP report",
            "trade balance announcement", "earnings season", "IPO pipeline",
            "central bank intervention", "commodity price rally", "market correction"
        ]
        
        logger.info(f"📊 Loaded {len(data['topics'])} topics, {len(data['sectors'])} sectors")
        return data
        
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return data


# Load data once
DATA = load_data_files()


# ============================================
# DATABASE OPERATIONS - Using string annotations
# ============================================

async def initialize_question_file(db: "AsyncIOMotorDatabase") -> int:
    """Initialize question collection with default questions"""
    collection = db["questions"]
    
    # Check if collection already has questions
    count = await collection.count_documents({"status": "pending"})
    if count > 0:
        logger.info(f"📄 Question collection exists with {count} pending questions")
        return count
    
    default_questions = [
        "What is the current BI rate and what is its impact on the Rupiah exchange rate?",
        "What is the latest core inflation rate in Indonesia and how does it compare to BI's target?",
        "What is the current GDP growth forecast for Indonesia and key drivers?",
        "What are the latest policy signals from Bank Indonesia regarding future rates?",
        "What is the Federal Reserve's latest stance on interest rates and inflation?",
        "What is the current US inflation rate and its impact on global markets?",
        "What is the latest ECB policy decision and its effect on the Euro?",
        "What is the Bank of Japan's current monetary policy stance?",
        "What is the latest JCI (IDX Composite) performance and key movers?",
        "What are the top 5 performing stocks on IDX this week?",
        "What is the current foreign flow into Indonesian stock market?",
        "What are the latest earnings reports from major Indonesian banks?"
    ]
    
    questions_to_insert = [
        {
            "text": q,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "answered_at": None,
            "answer": None,
            "source": "default",
            "attempts": 0
        }
        for q in default_questions
    ]
    
    result = await collection.insert_many(questions_to_insert)
    logger.info(f"✅ Initialized {len(result.inserted_ids)} default questions")
    return len(result.inserted_ids)


async def get_question_count(db: "AsyncIOMotorDatabase") -> int:
    """Get count of pending questions"""
    collection = db["questions"]
    return await collection.count_documents({"status": "pending"})


async def get_next_question(db: "AsyncIOMotorDatabase") -> Optional[Dict[str, Any]]:
    """Get next pending question from database"""
    collection = db["questions"]
    
    question = await collection.find_one({"status": "pending"})
    
    if question:
        question["_id"] = str(question["_id"])
        logger.info(f"📨 Retrieved question: {question['text'][:50]}...")
        return question
    
    logger.warning("❌ No pending questions found")
    return None


async def add_question(db: "AsyncIOMotorDatabase", question: str, source: str = "manual") -> Optional[str]:
    """Add new question to database"""
    if not question or not question.strip():
        return None
    
    question = question.strip()
    if not question.endswith('?'):
        question += '?'
    
    collection = db["questions"]
    
    question_doc = {
        "text": question,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "answered_at": None,
        "answer": None,
        "source": source,
        "attempts": 0
    }
    
    result = await collection.insert_one(question_doc)
    logger.info(f"➕ Added question: {question[:50]}...")
    return str(result.inserted_id)


async def remove_first_question(db: "AsyncIOMotorDatabase") -> bool:
    """Remove and archive first pending question"""
    collection = db["questions"]
    
    question = await collection.find_one({"status": "pending"})
    if not question:
        return False
    
    # Archive it
    await archive_question(db, str(question["_id"]), question["text"])
    
    # Update status
    await collection.update_one(
        {"_id": question["_id"]},
        {"$set": {"status": "archived", "answered_at": datetime.utcnow()}}
    )
    
    logger.info(f"🗑️ Archived question: {question['text'][:50]}...")
    return True


async def archive_question(
    db: "AsyncIOMotorDatabase",
    question_id: str,
    text: str
) -> bool:
    """Archive a question"""
    archive_collection = db["question_archive"]
    
    archive_doc = {
        "question_id": ObjectId(question_id) if ObjectId.is_valid(question_id) else question_id,
        "text": text,
        "archived_at": datetime.utcnow()
    }
    
    result = await archive_collection.insert_one(archive_doc)
    logger.info(f"📦 Archived: {text[:50]}...")
    return bool(result.inserted_id)


async def get_all_questions(db: "AsyncIOMotorDatabase", limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all questions with optional status filter"""
    collection = db["questions"]
    
    # Build filter
    filter_query = {}
    if status:
        filter_query["status"] = status
    else:
        filter_query["status"] = {"$ne": "archived"}  # Exclude archived by default
    
    questions = []
    cursor = collection.find(filter_query).sort("created_at", -1).limit(limit)
    
    async for question in cursor:
        question["_id"] = str(question["_id"])
        questions.append(question)
    
    return questions


async def get_question_by_id(db: "AsyncIOMotorDatabase", question_id: str) -> Optional[Dict[str, Any]]:
    """Get a question by ID"""
    try:
        collection = db["questions"]
        if not ObjectId.is_valid(question_id):
            return None
        
        doc = await collection.find_one({"_id": ObjectId(question_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None
    except Exception as e:
        logger.error(f"Error getting question by ID: {str(e)}")
        return None


async def get_archive(db: "AsyncIOMotorDatabase", limit: int = 100) -> List[Dict[str, Any]]:
    """Get archived questions"""
    collection = db["question_archive"]
    
    archive = []
    cursor = collection.find({}).sort("archived_at", -1).limit(limit)
    
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        archive.append(doc)
    
    return archive


async def reset_question_queue(db: "AsyncIOMotorDatabase") -> int:
    """Reset question queue - delete all and reinitialize"""
    collection = db["questions"]
    archive_collection = db["question_archive"]
    
    await collection.delete_many({})
    await archive_collection.delete_many({})
    
    count = await initialize_question_file(db)
    logger.info(f"🔄 Queue reset with {count} questions")
    return count


async def generate_new_question_from_data(db: "AsyncIOMotorDatabase") -> Optional[str]:
    """Generate new question from loaded data"""
    try:
        # Pick random elements
        topic = random.choice(DATA["topics"]) if DATA["topics"] else "Indonesian economy"
        sector = random.choice(DATA["sectors"]) if DATA["sectors"] else "banking"
        company = random.choice(DATA["companies"]) if DATA["companies"] else "companies"
        commodity = random.choice(DATA["commodities"]) if DATA["commodities"] else "commodities"
        indicator = random.choice(DATA["indicators"]) if DATA["indicators"] else "economic indicators"
        region = random.choice(DATA["regions"]) if DATA["regions"] else "Indonesia"
        event = random.choice(DATA["events"]) if DATA["events"] else "market developments"
        
        # Question templates
        templates = [
            f"What are the latest trends in {topic} and what are the implications for Indonesia's economy?",
            f"How is {indicator} performing in {region} and what does it signal for monetary policy?",
            f"What is the current valuation and outlook for the {sector} sector in Indonesia?",
            f"What are the latest earnings and performance of {company}?",
            f"What is the current price and outlook for {commodity}?",
            f"How are {region} market developments affecting Indonesian stocks?",
            f"What is the impact of {event} on the markets?",
            f"What are the top investment opportunities in {sector}?",
            f"How will {topic} impact {region}'s economy?",
            f"What is the market sentiment toward {sector} right now?"
        ]
        
        question = random.choice(templates).strip()
        if not question.endswith('?'):
            question += '?'
        
        # Check for duplicates
        existing = await get_all_questions(db, limit=20)
        if await is_duplicate_question(question, existing):
            logger.warning("⚠️ Generated duplicate question, trying again...")
            return await get_random_fallback_question_async(db)
        
        # Add to database
        await add_question(db, question, source="generated")
        logger.info(f"✨ Generated: {question[:60]}...")
        return question
        
    except Exception as e:
        logger.error(f"Error generating question: {e}")
        return await get_random_fallback_question_async(db)


async def is_duplicate_question(
    new_question: str,
    existing_questions: List[Dict[str, Any]],
    threshold: float = 0.6
) -> bool:
    """Check if question is duplicate"""
    if not existing_questions:
        return False
    
    stop_words = {
        'what', 'is', 'are', 'the', 'of', 'to', 'for', 'on', 'at', 'from',
        'by', 'in', 'with', 'and', 'or', 'but', 'nor', 'into', 'through'
    }
    
    new_words = set([
        w.lower() for w in new_question.split()
        if w.lower() not in stop_words and len(w) > 3
    ])
    
    for existing in existing_questions[-15:]:
        existing_text = existing.get("text", "")
        existing_words = set([
            w.lower() for w in existing_text.split()
            if w.lower() not in stop_words and len(w) > 3
        ])
        
        if not new_words or not existing_words:
            continue
        
        overlap = len(new_words.intersection(existing_words)) / len(new_words.union(existing_words))
        
        if overlap > threshold:
            return True
    
    return False


async def get_random_fallback_question_async(db: "AsyncIOMotorDatabase") -> str:
    """Get random fallback question"""
    fallbacks = [
        "What is the current Rupiah exchange rate against USD and what are the key drivers?",
        "What is the latest JCI performance and which sectors are leading the market?",
        "What is the current oil price and how does it impact Indonesia's trade balance?",
        "What are the latest earnings from major Indonesian banks?",
        "What is the current inflation rate and how is BI responding?",
        "What are the latest foreign investment trends in Indonesia?",
        "What is the outlook for commodity prices and their impact on Indonesia?",
        "What are the most promising sectors for investment in Indonesia right now?",
        "What is the impact of global supply chain disruptions on Indonesia?",
        "What are the key themes driving the Indonesian market this quarter?"
    ]
    question = random.choice(fallbacks)
    await add_question(db, question, source="fallback")
    return question


def get_default_fallback_questions() -> List[str]:
    """Get default fallback questions"""
    return [
        "What is the current Rupiah exchange rate against USD and what are the key drivers?",
        "What is the latest JCI performance and which sectors are leading the market?",
        "What is the current oil price and how does it impact Indonesia's trade balance?",
        "What are the latest earnings from major Indonesian banks?",
        "What is the current inflation rate and how is BI responding?",
        "What are the latest foreign investment trends in Indonesia?",
        "What is the outlook for commodity prices and their impact on Indonesia?",
        "What are the most promising sectors for investment in Indonesia right now?",
        "What is the impact of global supply chain disruptions on Indonesia?",
        "What are the key themes driving the Indonesian market this quarter?"
    ]


# ============================================
# N8N LLM QUESTION GENERATION
# ============================================

async def n8n_generate_questions_with_llm(
    db: "AsyncIOMotorDatabase",
    topic: Optional[str] = None,
    complexity: str = "medium",
    num_questions: int = 1
) -> List[str]:
    """
    N8N: Generate intelligent questions using LLM based on data context
    
    This uses the agent/LLM to generate context-aware questions
    based on your economic data, documents, and previous context.
    """
    try:
        # Import agent services
        from src.services.agent import ask_agent
        
        # Get context from data
        context = _get_data_context_for_questions()
        
        # Build prompt for question generation
        prompt = _build_question_generation_prompt(
            context=context,
            topic=topic,
            complexity=complexity,
            num_questions=num_questions
        )
        
        # Use agent to generate questions
        result = await ask_agent(
            question=prompt,
            db=db,
            language="en",
            channel="api" 
        )
        
        if not result.get("success"):
            logger.error(f"Failed to generate questions: {result.get('error')}")
            return _get_fallback_questions(num_questions)
        
        # Parse the generated questions
        answer = result.get("answer", "")
        questions = _parse_generated_questions(answer)
        
        if not questions:
            logger.warning("No questions parsed from LLM response, using fallback")
            return _get_fallback_questions(num_questions)
        
        # Limit to requested number
        questions = questions[:num_questions]
        
        logger.info(f"✨ Generated {len(questions)} questions using LLM")
        return questions
        
    except Exception as e:
        logger.error(f"Error generating questions with LLM: {str(e)}")
        return _get_fallback_questions(num_questions)


def _get_data_context_for_questions() -> str:
    """Get context from loaded data for question generation"""
    try:
        context_parts = []
        
        # Add topics
        if DATA.get("topics"):
            topics_sample = random.sample(DATA["topics"], min(10, len(DATA["topics"])))
            context_parts.append(f"Key topics: {', '.join(topics_sample)}")
        
        # Add sectors
        if DATA.get("sectors"):
            sectors_sample = random.sample(DATA["sectors"], min(8, len(DATA["sectors"])))
            context_parts.append(f"Key sectors: {', '.join(sectors_sample)}")
        
        # Add companies
        if DATA.get("companies"):
            companies_sample = random.sample(DATA["companies"], min(5, len(DATA["companies"])))
            context_parts.append(f"Key companies: {', '.join(companies_sample)}")
        
        # Add indicators
        if DATA.get("indicators"):
            indicators_sample = random.sample(DATA["indicators"], min(8, len(DATA["indicators"])))
            context_parts.append(f"Economic indicators: {', '.join(indicators_sample)}")
        
        # Add commodities
        if DATA.get("commodities"):
            commodities_sample = random.sample(DATA["commodities"], min(5, len(DATA["commodities"])))
            context_parts.append(f"Commodities: {', '.join(commodities_sample)}")
        
        return "\n".join(context_parts) if context_parts else "Indonesian economy and financial markets"
        
    except Exception as e:
        logger.error(f"Error getting data context: {str(e)}")
        return "Indonesian economy and financial markets"


def _build_question_generation_prompt(
    context: str,
    topic: Optional[str],
    complexity: str,
    num_questions: int
) -> str:
    """Build prompt for LLM question generation"""
    
    complexity_instructions = {
        "simple": "simple, straightforward questions about current economic conditions",
        "medium": "moderately complex questions that require analysis and synthesis of economic data",
        "complex": "advanced, strategic questions that require deep analysis and forecasting"
    }
    
    instruction = complexity_instructions.get(complexity, complexity_instructions["medium"])
    
    prompt = f"""Based on the following economic data and context, generate {num_questions} relevant, insightful questions.

Data Context:
{context}

{f"Focus on the topic: {topic}" if topic else "Generate questions covering various aspects of the economy."}

Requirements:
1. Questions should be {instruction}
2. Questions should be specific and data-driven
3. Questions should be relevant for investment/economic analysis
4. Each question should be a complete sentence ending with a question mark

Generate {num_questions} questions, one per line, numbered or separated by newlines:

Questions:
"""
    
    return prompt.strip()


def _parse_generated_questions(answer: str) -> List[str]:
    """Parse questions from LLM response"""
    questions = []
    
    # Try to extract numbered questions
    lines = answer.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Remove numbering (e.g., "1. ", "2. ", "Q1: ", etc.)
        cleaned = re.sub(r'^[\d\s\.]+[\.\:]\s*', '', line)
        cleaned = re.sub(r'^Q[\d]+\s*[:\.]\s*', '', cleaned, flags=re.IGNORECASE)
        
        # Check if it ends with a question mark
        if cleaned.endswith('?'):
            questions.append(cleaned)
        elif cleaned and not cleaned.endswith('.'):
            # Add question mark if missing
            questions.append(cleaned + '?')
    
    # If no questions found, try to extract by sentence boundaries
    if not questions:
        sentences = answer.split('. ')
        for sent in sentences:
            sent = sent.strip()
            if '?' in sent:
                # Split by question marks
                parts = sent.split('?')
                for part in parts:
                    if part.strip():
                        questions.append(part.strip() + '?')
    
    return questions


def _get_fallback_questions(num_questions: int) -> List[str]:
    """Get fallback questions if LLM generation fails"""
    fallbacks = get_default_fallback_questions()
    
    # Return random selection
    if len(fallbacks) <= num_questions:
        return fallbacks[:num_questions]
    
    return random.sample(fallbacks, num_questions)


# ============================================
# QUESTION STATS
# ============================================

async def get_question_stats(db: "AsyncIOMotorDatabase") -> Dict[str, Any]:
    """Get statistics on questions"""
    collection = db["questions"]
    archive_collection = db["question_archive"]
    
    pending = await collection.count_documents({"status": "pending"})
    archived = await archive_collection.count_documents({})
    total = pending + archived
    
    return {
        "pending_questions": pending,
        "archived_questions": archived,
        "total": total,
        "data_summary": {
            "topics_count": len(DATA.get("topics", [])),
            "sectors_count": len(DATA.get("sectors", [])),
            "companies_count": len(DATA.get("companies", [])),
            "commodities_count": len(DATA.get("commodities", [])),
            "indicators_count": len(DATA.get("indicators", []))
        }
    }


# ============================================
# SYNC WRAPPERS (For backward compatibility)
# ============================================

def get_question_count_sync(db: "AsyncIOMotorDatabase") -> int:
    """Sync wrapper"""
    return asyncio.run(get_question_count(db))


def get_next_question_sync(db: "AsyncIOMotorDatabase") -> Optional[Dict[str, Any]]:
    """Sync wrapper"""
    return asyncio.run(get_next_question(db))


def get_all_questions_sync(db: "AsyncIOMotorDatabase") -> List[Dict[str, Any]]:
    """Sync wrapper"""
    return asyncio.run(get_all_questions(db))


# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_file_paths() -> dict:
    """Get project file paths"""
    return {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(PROJECT_ROOT / "data" / "raw")
    }


def get_data_summary() -> dict:
    """Get summary of loaded data"""
    return {
        "topics_count": len(DATA["topics"]),
        "sectors_count": len(DATA["sectors"]),
        "companies_count": len(DATA["companies"]),
        "commodities_count": len(DATA["commodities"]),
        "indicators_count": len(DATA["indicators"]),
        "sample_topics": DATA["topics"][:5],
        "sample_sectors": DATA["sectors"][:5]
    }


async def log_question(
    db: "AsyncIOMotorDatabase",
    question: str,
    answer: str,
    processing_time: float,
    iterations: int,
    thread_id: Optional[str] = None,
    channel: Optional[str] = "api",
    success: bool = True
) -> bool:
    """Log question and answer to MongoDB"""
    try:
        collection = db["question_logs"]
        
        log_doc = {
            "question": question,
            "answer": answer,
            "processing_time": processing_time,
            "iterations": iterations,
            "thread_id": thread_id or "anonymous",
            "channel": channel,
            "success": success,
            "logged_at": datetime.utcnow()
        }
        
        result = await collection.insert_one(log_doc)
        logger.info(f"📝 Question logged: {result.inserted_id}")
        return bool(result.inserted_id)
    except Exception as e:
        logger.error(f"❌ Error logging question: {str(e)}")
        return False


async def get_question_logs(
    db: "AsyncIOMotorDatabase",
    limit: int = 100,
    success_only: bool = False
) -> List[Dict[str, Any]]:
    """Get question logs from MongoDB"""
    try:
        collection = db["question_logs"]
        
        query = {}
        if success_only:
            query["success"] = True
        
        logs = []
        cursor = collection.find(query).sort("logged_at", -1).limit(limit)
        
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(log)
        
        logger.info(f"📋 Retrieved {len(logs)} question logs")
        return logs
    except Exception as e:
        logger.error(f"❌ Error getting logs: {str(e)}")
        return []


async def get_question_log_stats(
    db: "AsyncIOMotorDatabase"
) -> Dict[str, Any]:
    """Get statistics on question logs"""
    try:
        collection = db["question_logs"]
        
        total = await collection.count_documents({})
        successful = await collection.count_documents({"success": True})
        failed = await collection.count_documents({"success": False})
        
        # Get average processing time
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "avg_time": {"$avg": "$processing_time"},
                    "avg_iterations": {"$avg": "$iterations"}
                }
            }
        ]
        
        avg_stats = []
        async for doc in collection.aggregate(pipeline):
            avg_stats.append(doc)
        
        return {
            "total_questions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "avg_processing_time": avg_stats[0]["avg_time"] if avg_stats else 0,
            "avg_iterations": avg_stats[0]["avg_iterations"] if avg_stats else 0
        }
    except Exception as e:
        logger.error(f"❌ Error getting stats: {str(e)}")
        return {}


async def clear_question_logs(db: "AsyncIOMotorDatabase") -> bool:
    """Clear all question logs (DESTRUCTIVE)"""
    try:
        collection = db["question_logs"]
        result = await collection.delete_many({})
        logger.warning(f"🗑️ Cleared {result.deleted_count} question logs")
        return True
    except Exception as e:
        logger.error(f"❌ Error clearing logs: {str(e)}")
        return False


async def export_question_logs(
    db: "AsyncIOMotorDatabase",
    format: str = "json"
) -> Optional[str]:
    """Export question logs"""
    try:
        import json
        
        logs = await get_question_logs(db, limit=10000)
        
        if format == "json":
            return json.dumps(logs, indent=2, default=str)
        elif format == "csv":
            if not logs:
                return "question,answer,processing_time,iterations,thread_id,channel,success,logged_at"
            
            lines = ["question,answer,processing_time,iterations,thread_id,channel,success,logged_at"]
            for log in logs:
                question = log.get("question", "").replace(",", ";")
                answer = log.get("answer", "")[:100].replace(",", ";")
                processing_time = log.get("processing_time", 0)
                iterations = log.get("iterations", 0)
                thread_id = log.get("thread_id", "")
                channel = log.get("channel", "")
                success = log.get("success", False)
                logged_at = log.get("logged_at", "")
                
                lines.append(
                    f"{question},{answer},{processing_time},{iterations},{thread_id},{channel},{success},{logged_at}"
                )
            
            return "\n".join(lines)
        
        return None
    except Exception as e:
        logger.error(f"❌ Error exporting logs: {str(e)}")
        return None