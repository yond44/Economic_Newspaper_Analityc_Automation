"""Agent Queue Routes - Enhanced with Admin Controls and Analytics"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from datetime import datetime
from typing import Optional

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.models.user import UserInDB
from src.services.question_manager import (
    get_question_count,
    get_all_questions,
    get_next_question,
    add_question,
    remove_first_question,
    generate_new_question_from_data,
    get_archive,
    get_file_paths,
    get_data_summary,
    reset_question_queue,
    initialize_question_file
)
from src.services.agent import reset_question_system

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/queue", tags=["queue"])


# ============================================
# MIDDLEWARE - ADMIN CHECK
# ============================================

async def check_admin(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Verify user is admin"""
    if not getattr(current_user, 'is_admin', False):
        logger.warning(f"⚠️ Unauthorized queue access attempt by {current_user.username}")
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access queue management endpoints"
        )
    return current_user


# ============================================
# QUEUE OVERVIEW
# ============================================

@router.get("")
async def get_queue(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get current question queue status
    
    **Returns:**
    - `total`: Total questions in queue
    - `questions`: List of all queued questions
    - `next`: Next question to be processed
    - `metrics`: Queue metrics and statistics
    
    **Example Response:**
    ```json
    {
        "status": "success",
        "total": 45,
        "next_question": "What are...",
        "questions": [...],
        "metrics": {
            "average_length": 85,
            "oldest_date": "2024-01-15T10:30:00",
            "newest_date": "2024-01-20T15:45:00"
        }
    }
    ```
    """
    try:
        questions = get_all_questions()
        next_question = get_next_question()
        
        logger.info(f"📊 Queue status retrieved by {current_user.username}")
        
        # Calculate metrics
        metrics = {
            "total": len(questions),
            "average_length": int(sum(len(q) for q in questions) / len(questions)) if questions else 0,
            "min_length": min(len(q) for q in questions) if questions else 0,
            "max_length": max(len(q) for q in questions) if questions else 0,
            "processing_order": "FIFO" if next_question else "empty"
        }
        
        return {
            "status": "success",
            "total": len(questions),
            "next_question": next_question,
            "questions": questions,
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error retrieving queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/count")
async def get_queue_count(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get quick queue count
    
    **Returns:**
    - `count`: Number of questions in queue
    - `archive_count`: Number of archived questions
    """
    
    try:
        count = get_question_count()
        archive_count = len(get_archive())
        
        logger.debug(f"📈 Queue count: {count} | Archive: {archive_count}")
        
        return {
            "status": "success",
            "queue_count": count,
            "archive_count": archive_count,
            "total_processed": count + archive_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/next")
async def peek_next_question(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Peek at the next question without removing it
    
    **Returns:**
    - `question`: Next question in queue
    - `position`: Position in queue (always 1)
    """
    
    try:
        next_q = get_next_question()
        
        if not next_q:
            logger.info(f"📭 Queue is empty - checked by {current_user.username}")
            return {
                "status": "empty",
                "message": "No questions in queue"
            }
        
        logger.debug(f"👀 Peeked next question")
        
        return {
            "status": "success",
            "question": next_q,
            "position": 1,
            "queue_size": get_question_count()
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ARCHIVE MANAGEMENT
# ============================================

@router.get("/archive")
async def get_archive_questions(
    skip: int = QueryParam(0, ge=0),
    limit: int = QueryParam(20, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get archived (processed) questions
    
    **Parameters:**
    - `skip`: Number of records to skip
    - `limit`: Maximum records to return (max: 100)
    
    **Returns:**
    - `archive`: List of archived questions
    - `total`: Total archived questions
    - `pagination`: Pagination info
    """
    
    try:
        archive = get_archive()
        total = len(archive)
        
        # Apply pagination (most recent first)
        paginated = list(reversed(archive))[skip:skip + limit]
        
        logger.info(f"📜 Archive retrieved by {current_user.username} (skip={skip}, limit={limit})")
        
        return {
            "status": "success",
            "total": total,
            "archive": paginated,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "remaining": max(0, total - skip - limit)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error retrieving archive: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/search")
async def search_archive(
    q: str = QueryParam(..., min_length=1, max_length=200),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Search archived questions
    
    **Parameters:**
    - `q`: Search query (required)
    
    **Returns:**
    - `results`: Matching archived questions
    - `total`: Number of matches
    """
    
    try:
        archive = get_archive()
        query_lower = q.lower()
        
        results = [item for item in archive if query_lower in item.lower()]
        
        logger.info(f"🔍 Archive search by {current_user.username}: '{q}' - {len(results)} matches")
        
        return {
            "status": "success",
            "query": q,
            "results": results,
            "total": len(results)
        }
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# QUEUE MANAGEMENT (ADMIN ONLY)
# ============================================

@router.post("/add")
async def add_question_to_queue(
    question: str = QueryParam(..., min_length=5, max_length=2000),
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Add a question to the queue
    
    **Parameters:**
    - `question`: Question text to add (5-2000 chars)
    
    **Returns:**
    - `message`: Confirmation message
    - `queue_size`: New queue size
    
    **Requires:** Admin privileges
    """
    
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        add_question(question.strip())
        new_count = get_question_count()
        
        logger.warning(f"➕ Question added by {admin.username}: {question[:50]}...")
        logger.info(f"   Queue size is now: {new_count}")
        
        return {
            "status": "success",
            "message": "Question added to queue",
            "question": question[:100],
            "queue_size": new_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error adding question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-bulk")
async def add_bulk_questions(
    questions: list,
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Add multiple questions to the queue
    
    **Parameters:**
    - `questions`: List of question strings
    
    **Returns:**
    - `added_count`: Number of questions added
    - `failed_count`: Number of failures
    - `queue_size`: New queue size
    
    **Requires:** Admin privileges
    """
    
    if not questions or not isinstance(questions, list):
        raise HTTPException(status_code=400, detail="Expected list of questions")
    
    try:
        added = 0
        failed = 0
        errors = []
        
        for q in questions:
            if q and isinstance(q, str) and len(q.strip()) >= 5:
                try:
                    add_question(q.strip())
                    added += 1
                except Exception as e:
                    failed += 1
                    errors.append({"question": q[:50], "error": str(e)})
            else:
                failed += 1
        
        new_count = get_question_count()
        
        logger.warning(f"➕ Bulk add by {admin.username}: {added} added, {failed} failed")
        
        return {
            "status": "success" if added > 0 else "partial",
            "added": added,
            "failed": failed,
            "errors": errors if errors else None,
            "queue_size": new_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Bulk add error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
async def process_next_question(
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Process (remove) the next question from queue
    
    **Returns:**
    - `processed_question`: The question that was processed
    - `queue_size`: New queue size
    
    **Requires:** Admin privileges
    """
    
    try:
        next_q = get_next_question()
        
        if not next_q:
            logger.warning(f"⚠️ Process attempted on empty queue by {admin.username}")
            raise HTTPException(status_code=404, detail="Queue is empty")
        
        # Remove it (archive)
        remove_first_question()
        new_count = get_question_count()
        
        logger.warning(f"✅ Processed by {admin.username}: {next_q[:50]}...")
        logger.info(f"   Remaining in queue: {new_count}")
        
        return {
            "status": "success",
            "processed_question": next_q,
            "remaining_count": new_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Process error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_new_question(
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Generate and add a new question from data
    
    **Returns:**
    - `question`: The generated question
    - `queue_size`: New queue size
    
    **Requires:** Admin privileges
    """
    
    try:
        new_q = generate_new_question_from_data()
        
        if not new_q:
            logger.warning(f"⚠️ Could not generate question - by {admin.username}")
            raise HTTPException(
                status_code=500,
                detail="Could not generate question from available data"
            )
        
        add_question(new_q)
        new_count = get_question_count()
        
        logger.warning(f"✨ Generated by {admin.username}: {new_q[:50]}...")
        logger.info(f"   Queue size is now: {new_count}")
        
        return {
            "status": "success",
            "message": "Question generated and added to queue",
            "question": new_q,
            "queue_size": new_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# QUEUE MAINTENANCE (ADMIN ONLY)
# ============================================

@router.post("/reset")
async def reset_queue(
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Reset the entire question queue
    
    **Returns:**
    - `message`: Confirmation
    - `reinitialized_count`: Number of questions in new queue
    
    **Requires:** Admin privileges
    **⚠️ WARNING:** This will clear all questions and archive!
    """
    
    try:
        logger.warning(f"🔄 QUEUE RESET initiated by {admin.username}")
        
        result = reset_question_system(db=db)
        
        logger.warning(f"✅ Queue reset completed by {admin.username}")
        
        return {
            "status": "success",
            "message": "Queue reset successfully",
            **result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Reset error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reinitialize")
async def reinitialize_queue(
    admin: UserInDB = Depends(check_admin),
    db = Depends(get_db)
):
    """
    Reinitialize question queue from data files
    
    **Returns:**
    - `initialized_count`: Number of questions loaded
    - `message`: Confirmation
    
    **Requires:** Admin privileges
    """
    
    try:
        logger.warning(f"🔁 Queue reinitialization initiated by {admin.username}")
        
        count = initialize_question_file(db=db)
        
        logger.warning(f"✅ Queue reinitialized by {admin.username}: {count} questions")
        
        return {
            "status": "success",
            "message": "Queue reinitialized from source files",
            "initialized_count": count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Reinitialization error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# QUEUE INFORMATION
# ============================================

@router.get("/files")
async def get_queue_files(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get queue file paths and metadata
    
    **Returns:**
    - `paths`: File paths being used
    - `question_count`: Current queue size
    - `archive_count`: Archived questions
    - `file_sizes`: Size information
    """
    
    try:
        paths = get_file_paths()
        question_count = get_question_count()
        archive_count = len(get_archive())
        
        logger.debug(f"📁 File info retrieved by {current_user.username}")
        
        return {
            "status": "success",
            "paths": paths,
            "question_count": question_count,
            "archive_count": archive_count,
            "total_processed": question_count + archive_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-summary")
async def get_data_summary_endpoint(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get comprehensive data summary
    
    **Returns:**
    - `data`: Data statistics and summary
    - `source_count`: Number of data sources
    - `timestamp`: When generated
    """
    
    try:
        summary = get_data_summary()
        
        logger.info(f"📊 Data summary retrieved by {current_user.username}")
        
        return {
            "status": "success",
            "data": summary,
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_queue_statistics(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get detailed queue statistics
    
    **Returns:**
    - `queue_stats`: Statistics about current queue
    - `archive_stats`: Statistics about archived questions
    - `health`: Queue health metrics
    """
    
    try:
        questions = get_all_questions()
        archive = get_archive()
        
        queue_stats = {
            "total": len(questions),
            "average_length": int(sum(len(q) for q in questions) / len(questions)) if questions else 0,
            "min_length": min(len(q) for q in questions) if questions else 0,
            "max_length": max(len(q) for q in questions) if questions else 0,
        }
        
        archive_stats = {
            "total": len(archive),
            "average_length": int(sum(len(q) for q in archive) / len(archive)) if archive else 0,
        }
        
        health = {
            "queue_utilization": len(questions),
            "processing_rate": "unknown",
            "status": "healthy" if len(questions) < 1000 else "warning" if len(questions) < 5000 else "critical"
        }
        
        logger.debug(f"📈 Stats retrieved by {current_user.username}")
        
        return {
            "status": "success",
            "queue_stats": queue_stats,
            "archive_stats": archive_stats,
            "health": health,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# HEALTH CHECK
# ============================================

@router.get("/health")
async def queue_health():
    """
    Queue system health check
    
    **Returns:**
    - `status`: Queue system status
    - `queue_size`: Current queue size
    - `is_operational`: Whether queue is operational
    """
    
    try:
        count = get_question_count()
        
        is_operational = True
        status = "healthy"
        
        if count == 0:
            status = "empty"
        elif count > 5000:
            status = "warning"
            is_operational = True
        
        return {
            "status": status,
            "queue_size": count,
            "is_operational": is_operational,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return {
            "status": "error",
            "is_operational": False,
            "error": str(e)
        }, 503