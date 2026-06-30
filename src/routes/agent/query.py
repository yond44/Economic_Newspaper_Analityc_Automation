# src/routes/agent/query.py
"""Agent Query Routes - Updated with Enhanced Features"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Query as QueryParam
import time
from datetime import datetime
from typing import Optional, Dict, Any

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.middleware.rate_limiter import check_rate_limit
from src.services.agent import (
    ask_agent, 
    get_agent_status,
    get_conversation_summary,
    clear_old_conversations,
    get_graph_app
)
from src.models.agent import (
    QueryRequest, 
    QueryResponse, 
    BatchEmailRequest,
    ConversationContext
)
from src.models.user import UserInDB
from src.services.user_queries import (
    log_user_query,
    get_user_queries,
    get_user_query_stats,
    delete_user_query,
    export_user_queries,
    search_user_queries  # ⬅️ ADD THIS
)
from src.services.rag import get_rag_status, get_cache_stats, clear_query_cache

logger = logging.getLogger(__name__)

# ⚠️ CHANGED: Remove /api/agent prefix - it's added by parent router
router = APIRouter(prefix="", tags=["agent"])


# ============================================
# QUERY ENDPOINTS
# ============================================

@router.post("/ask", response_model=QueryResponse)
async def ask(
    request: QueryRequest,
    http_request: Request,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
    rate_limit: bool = Depends(check_rate_limit),
):
    """
    Ask the agent a question with full context management
    
    **Parameters:**
    - `question`: The question to ask (required)
    - `thread_id`: Optional conversation thread ID for context
    - `channel`: Source channel (api, web, mobile, batch)
    - `metadata`: Optional additional context
    
    **Returns:**
    - `answer`: The agent's response
    - `processing_time`: Time taken to process (seconds)
    - `sources`: Retrieved context sources
    - `recommendations`: Suggested follow-up questions
    - `success`: Whether the query was successful
    - `validated`: Whether the query passed validation
    
    **Rate Limits:** 10 requests per minute per user
    
    **Example:**
    ```json
    {
        "question": "What are the current trends in tech stocks?",
        "thread_id": "conv-123",
        "channel": "api"
    }
    ```
    """
    
    if not rate_limit:
        logger.warning(f"⚠️ Rate limit exceeded for user {current_user.username}")
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Maximum 10 requests per minute."
        )
    
    try:
        client_ip = http_request.client.host if http_request.client else "unknown"
        logger.info(f"👤 User: {current_user.username} ({current_user.id}) | IP: {client_ip}")
        logger.info(f"❓ Question: {request.question[:100]}...")
        logger.info(f"🔗 Thread: {request.thread_id}")
        
        start_time = time.time()
        
        # Validate request
        try:
            request_validated = QueryRequest(**request.dict())
        except Exception as e:
            logger.error(f"❌ Request validation failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
        
        # Call agent with enhanced parameters
        result = await ask_agent(
            question=request_validated.question,
            thread_id=request_validated.thread_id,
            db=db,
            user_id=str(current_user.id),
            username=current_user.username,
            language=request_validated.metadata.get("language", "en") if request_validated.metadata else "en",
            channel=request_validated.channel.value if request_validated.channel else "api"
        )
        
        processing_time = time.time() - start_time
        
        # ✅ FIXED: result is now a dict, so .get() works
        logger.info(f"✅ Processed in {processing_time:.3f}s")
        logger.info(f"📊 Type: {result.get('response_type')} | Success: {result.get('success')}")
        logger.info(f"📚 Sources: {len(result.get('sources', []))} | Recommendations: {len(result.get('recommendations', []))}")
        
        # Log query to database
        try:
            await log_user_query(
                db=db,
                user_id=str(current_user.id),
                question=request_validated.question,
                answer=result.get("answer", ""),
                processing_time=processing_time,
                attempts=result.get("attempts", 1),
                thread_id=request_validated.thread_id,
                channel=request_validated.channel.value if request_validated.channel else "api",
                success=result.get("success", False),
                validated=result.get("validated", False),
                sources_count=len(result.get("sources", [])),
                error=result.get("error"),
                response_type=result.get("response_type", "answer"),  # ✅ ADD THIS
                language_detected=result.get("language_detected", "en")  # ✅ ADD THIS
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to log query: {str(e)}")
        
        # Build response
        response = QueryResponse(
            question=request_validated.question,
            answer=result["answer"],
            processing_time=processing_time,
            thread_id=request_validated.thread_id,
            language_detected=result.get("language_detected", "en"),
            response_type=result.get("response_type", "answer"),
            success=result.get("success", False),
            validated=result.get("validated", False),
            greeting=result.get("greeting", False),
            gratitude=result.get("gratitude", False),
            sources=result.get("sources", []),
            recommendations=result.get("recommendations", []),
            error=result.get("error"),
            user_id=str(current_user.id),
            attempts=result.get("attempts", 1)
        )
        
        logger.info(f"✅ Response sent to {current_user.username}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Query error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@router.post("/batch-email")
async def batch_email(
    request: BatchEmailRequest,
    http_request: Request,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
):
    """
    Send analysis to multiple email addresses
    """
    
    try:
        logger.info(f"📧 Batch email request from {current_user.username}")
        logger.info(f"   Recipients: {len(request.emails)} | Frequency: {request.frequency}")
        
        from src.services.agent import batch_processor
        
        # ✅ Attach the requesting user so history is tagged correctly
        batch_processor._current_user_id = str(current_user.id)
        batch_processor._current_username = current_user.username
        
        try:
            result = await batch_processor.process_batch(request, db=db)
        finally:
            # Clear so a subsequent request without auth context doesn't reuse stale values
            batch_processor._current_user_id = None
            batch_processor._current_username = None
        
        logger.info(f"✅ Batch {result['batch_id']} created with status: {result.get('status')}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Batch email error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing batch: {str(e)}")

@router.get("/conversation/{thread_id}")
async def get_conversation(
    thread_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get conversation summary for a thread"""
    
    try:
        logger.info(f"📖 Fetching conversation {thread_id} for {current_user.username}")
        
        summary = get_conversation_summary(thread_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "success": True,
            "data": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_query_history(
    skip: int = QueryParam(0, ge=0),
    limit: int = QueryParam(10, ge=1, le=100),
    days: Optional[int] = QueryParam(None, ge=1, le=365),
    response_type: Optional[str] = QueryParam(None),
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's query history with filtering and pagination"""
    
    try:
        logger.info(f"📜 Fetching query history for {current_user.username}")
        
        queries, total = await get_user_queries(
            db=db,
            user_id=str(current_user.id),
            skip=skip,
            limit=limit,
            days=days,
            response_type=response_type
        )
        
        logger.info(f"✅ Retrieved {len(queries)} of {total} queries")
        
        return {
            "user_id": str(current_user.id),
            "username": current_user.username,
            "queries": queries,
            "pagination": {
                "total": total,
                "skip": skip,
                "limit": limit,
                "remaining": max(0, total - skip - limit)
            },
            "filters": {
                "days": days,
                "response_type": response_type
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching query history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_query_stats(
    days: int = QueryParam(30, ge=1, le=365),
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's query statistics"""
    
    try:
        logger.info(f"📊 Computing stats for {current_user.username}")
        
        stats = await get_user_query_stats(
            db=db,
            user_id=str(current_user.id),
            days=days
        )
        
        logger.info(f"✅ Stats computed")
        
        return {
            "user_id": str(current_user.id),
            "username": current_user.username,
            "period_days": days,
            "computed_at": datetime.utcnow().isoformat(),
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching query stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_queries(
    q: str = QueryParam(..., min_length=1, max_length=200),
    skip: int = QueryParam(0, ge=0),
    limit: int = QueryParam(10, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Search user's query history"""
    
    try:
        logger.info(f"🔍 Searching queries for {current_user.username}")
        
        results, total = await search_user_queries(
            db=db,
            user_id=str(current_user.id),
            search_term=q,
            skip=skip,
            limit=limit
        )
        
        logger.info(f"✅ Found {total} matching queries")
        
        return {
            "search_query": q,
            "results": results,
            "total": total,
            "pagination": {
                "skip": skip,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_queries(
    format: str = QueryParam("json", pattern="^(json|csv)$"),
    days: Optional[int] = QueryParam(None, ge=1, le=365),
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Export user's query history"""
    
    try:
        logger.info(f"📥 Exporting queries for {current_user.username}")
        
        exported_data = await export_user_queries(
            db=db,
            user_id=str(current_user.id),
            format=format,
            days=days
        )
        
        logger.info(f"✅ Export completed")
        
        return {
            "success": True,
            "format": format,
            "data": exported_data,
            "exported_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Export error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/query/{query_id}")
async def delete_query(
    query_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete a specific query"""
    
    try:
        logger.info(f"🗑️ Delete request for query {query_id}")
        
        success = await delete_user_query(
            db=db,
            query_id=query_id,
            user_id=str(current_user.id)
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Query not found")
        
        logger.info(f"✅ Query deleted")
        
        return {
            "success": True,
            "message": "Query deleted successfully",
            "query_id": query_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get comprehensive agent system status"""
    
    try:
        logger.info(f"📊 Status check")
        
        agent_status = await get_agent_status(db=db)
        rag_status = get_rag_status()
        cache_stats = get_cache_stats()
        
        return {
            "agent": agent_status,
            "rag": rag_status,
            "cache": cache_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/maintenance/clear-cache")
async def clear_cache(
    current_user: UserInDB = Depends(get_current_user),
):
    """Clear RAG query cache (admin only)"""
    
    try:
        if not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code=403, detail="Admin only")
        
        logger.info(f"🧹 Cache clear requested")
        
        old_stats = get_cache_stats()
        clear_query_cache()
        
        logger.info(f"✅ Cache cleared")
        
        return {
            "success": True,
            "message": "Cache cleared",
            "previous_entries": old_stats.get("total_cached_queries")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0"
        }
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return {
            "status": "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }, 503