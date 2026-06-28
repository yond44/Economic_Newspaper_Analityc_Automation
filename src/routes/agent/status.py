"""Agent Status Routes - Enhanced with Comprehensive Monitoring"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Dict, Any

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.models.user import UserInDB
from src.services.agent import (
    get_agent_status,
    conversation_manager,
    get_graph_app
)
from src.services.question_manager import get_question_count, get_archive
from src.services.rag import get_rag_status, get_cache_stats
from src.services.email_manager import get_email_count

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/status", tags=["status"])


# ============================================
# SYSTEM STATUS
# ============================================

@router.get("/system")
async def get_system_status(
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Get comprehensive system status
    
    **Returns:**
    - `agent`: Agent system status
    - `rag`: RAG/Vector DB status
    - `queue`: Question queue status
    - `cache`: Caching statistics
    - `database`: Database connection status
    - `overall`: Overall system health
    
    **Example Response:**
    ```json
    {
        "overall": "healthy",
        "agent": {
            "initialized": true,
            "graph_compiled": true,
            "agents": 7
        },
        "rag": {
            "initialized": true,
            "documents": 45,
            "chunks": 1250
        },
        "timestamp": "2024-01-20T15:30:45.123456"
    }
    ```
    """
    
    try:
        logger.info(f"🔍 System status check by {current_user.username}")
        
        # Get all status information
        agent_status = await get_agent_status(db=db)
        rag_status = get_rag_status()
        cache_stats = get_cache_stats()
        queue_count = get_question_count()
        archive_count = len(get_archive())
        email_count = await get_email_count(db) if db else 0
        
        # Determine overall health
        overall_health = "healthy"
        
        if not agent_status.get("initialized"):
            overall_health = "degraded"
        
        if not rag_status.get("initialized"):
            overall_health = "critical"
        
        if cache_stats.get("cache_hit_rate", "0%").rstrip("%").startswith("0"):
            overall_health = "warning" if overall_health == "healthy" else overall_health
        
        return {
            "overall_status": overall_health,
            "agent": {
                "initialized": agent_status.get("initialized"),
                "graph_compiled": agent_status.get("graph_compiled"),
                "agents_count": 7,
                "agents": agent_status.get("agents", {}),
                "conversation_contexts": agent_status.get("conversation_contexts", 0),
                "features": agent_status.get("features", {}),
                "mode": agent_status.get("mode", "Unknown")
            },
            "rag": {
                "initialized": rag_status.get("initialized"),
                "collection": rag_status.get("collection"),
                "documents": rag_status.get("metrics", {}).get("total_documents", 0),
                "chunks": rag_status.get("metrics", {}).get("total_chunks", 0),
                "models": rag_status.get("models", {}),
                "strategies": rag_status.get("chunking_strategies", [])
            },
            "cache": {
                "total_queries": cache_stats.get("total_cached_queries"),
                "hit_rate": cache_stats.get("hit_rate"),
                "size_mb": cache_stats.get("total_size_mb"),
                "max_size_mb": cache_stats.get("max_size_mb"),
                "entries": {
                    "valid": cache_stats.get("valid_entries"),
                    "expired": cache_stats.get("expired_entries")
                }
            },
            "queue": {
                "current": queue_count,
                "archived": archive_count,
                "total_processed": queue_count + archive_count
            },
            "database": {
                "connected": db is not None,
                "email_count": email_count
            },
            "metrics": agent_status.get("metrics", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ System status error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================
# AGENT STATUS
# ============================================

@router.get("/agent")
async def get_agent_detailed_status(
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Get detailed agent system status
    
    **Returns:**
    - `initialized`: Whether agent is initialized
    - `agents`: Information about each agent
    - `features`: Available features
    - `metrics`: Performance metrics
    - `conversation_contexts`: Active conversations
    """
    
    try:
        logger.debug(f"📊 Agent status requested by {current_user.username}")
        
        status = await get_agent_status(db=db)
        
        return {
            "status": "operational",
            "initialized": status.get("initialized"),
            "graph_compiled": status.get("graph_compiled"),
            "agents": status.get("agents", {}),
            "features": status.get("features", {}),
            "agents_count": len(status.get("agents", {})),
            "active_conversations": status.get("conversation_contexts", 0),
            "metrics": {
                "total_queries": status.get("metrics", {}).get("total_queries", 0),
                "successful_queries": status.get("metrics", {}).get("successful_queries", 0),
                "failed_queries": status.get("metrics", {}).get("failed_queries", 0),
                "success_rate": status.get("metrics", {}).get("success_rate", "N/A"),
                "avg_processing_time_ms": status.get("metrics", {}).get("avg_processing_time_ms", "N/A"),
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Agent status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# RAG STATUS
# ============================================

@router.get("/rag")
async def get_rag_detailed_status(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get detailed RAG system status
    
    **Returns:**
    - `initialized`: Whether RAG is initialized
    - `collection`: Vector DB collection info
    - `documents`: Document statistics
    - `models`: LLM and embedding models
    - `cache`: Cache statistics
    - `performance`: Performance metrics
    """
    
    try:
        logger.debug(f"📚 RAG status requested by {current_user.username}")
        
        rag_status = get_rag_status()
        cache_stats = get_cache_stats()
        
        return {
            "status": "operational" if rag_status.get("initialized") else "not_initialized",
            "initialized": rag_status.get("initialized"),
            "collection": rag_status.get("collection"),
            "database": rag_status.get("db_path"),
            "documents": {
                "total": rag_status.get("metrics", {}).get("total_documents", 0),
                "chunks": rag_status.get("metrics", {}).get("total_chunks", 0),
                "distribution": rag_status.get("metrics", {}).get("chunk_distribution", {})
            },
            "configuration": rag_status.get("configuration", {}),
            "models": rag_status.get("models", {}),
            "cache": cache_stats,
            "performance": {
                "total_queries": rag_status.get("metrics", {}).get("total_queries", 0),
                "cache_hit_rate": rag_status.get("metrics", {}).get("cache_hit_rate", "0%"),
                "success_rate": rag_status.get("metrics", {}).get("success_rate", "0%"),
                "avg_response_time_ms": rag_status.get("metrics", {}).get("avg_response_time_ms", "N/A"),
                "total_processing_time_s": rag_status.get("metrics", {}).get("total_processing_time_s", "N/A"),
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ RAG status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# QUEUE STATUS
# ============================================

@router.get("/queue")
async def get_queue_status(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get question queue status
    
    **Returns:**
    - `current`: Current queue size
    - `archived`: Number of archived questions
    - `total_processed`: Total questions processed
    - `health`: Queue health status
    """
    
    try:
        logger.debug(f"📋 Queue status requested by {current_user.username}")
        
        current = get_question_count()
        archived = len(get_archive())
        
        health = "healthy"
        if current == 0:
            health = "empty"
        elif current > 5000:
            health = "warning"
        elif current > 10000:
            health = "critical"
        
        return {
            "status": health,
            "queue": {
                "current": current,
                "archived": archived,
                "total_processed": current + archived
            },
            "health": health,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Queue status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CACHE STATUS
# ============================================

@router.get("/cache")
async def get_cache_status(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Get cache system status
    
    **Returns:**
    - `statistics`: Cache statistics
    - `hit_rate`: Cache hit rate percentage
    - `memory`: Memory usage
    - `top_queries`: Most frequently cached queries
    """
    
    try:
        logger.debug(f"💾 Cache status requested by {current_user.username}")
        
        stats = get_cache_stats()
        
        return {
            "status": "operational",
            "statistics": {
                "total_cached": stats.get("total_cached_queries"),
                "valid_entries": stats.get("valid_entries"),
                "expired_entries": stats.get("expired_entries")
            },
            "performance": {
                "hit_rate": stats.get("hit_rate"),
                "total_hits": stats.get("total_hits"),
                "total_misses": stats.get("total_misses")
            },
            "memory": {
                "used_mb": stats.get("total_size_mb"),
                "max_mb": stats.get("max_size_mb"),
                "ttl_seconds": stats.get("cache_ttl_seconds")
            },
            "top_queries": stats.get("top_cached_queries", []),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Cache status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# HEALTH CHECK
# ============================================

@router.get("/health")
async def health_check(
    db = Depends(get_db)
):
    """
    Quick health check endpoint
    
    **Returns:**
    - `status`: Overall system status (healthy/degraded/unhealthy)
    - `checks`: Individual component health
    - `timestamp`: Check timestamp
    
    **Status Codes:**
    - 200: Healthy
    - 503: Unhealthy/Degraded
    """
    
    try:
        logger.debug("🏥 Health check initiated")
        
        checks = {
            "agent": False,
            "rag": False,
            "queue": False,
            "database": False
        }
        
        # Check agent
        try:
            agent_status = await get_agent_status(db=db)
            checks["agent"] = agent_status.get("initialized", False)
        except Exception as e:
            logger.warning(f"⚠️ Agent check failed: {str(e)}")
        
        # Check RAG
        try:
            rag_status = get_rag_status()
            checks["rag"] = rag_status.get("initialized", False)
        except Exception as e:
            logger.warning(f"⚠️ RAG check failed: {str(e)}")
        
        # Check queue
        try:
            queue_count = get_question_count()
            checks["queue"] = queue_count >= 0
        except Exception as e:
            logger.warning(f"⚠️ Queue check failed: {str(e)}")
        
        # Check database
        checks["database"] = db is not None
        
        # Determine overall status
        healthy_checks = sum(1 for v in checks.values() if v)
        total_checks = len(checks)
        
        if healthy_checks == total_checks:
            overall_status = "healthy"
            status_code = 200
        elif healthy_checks >= total_checks - 1:
            overall_status = "degraded"
            status_code = 200
        else:
            overall_status = "unhealthy"
            status_code = 503
        
        logger.info(f"✅ Health check: {overall_status} ({healthy_checks}/{total_checks} components)")
        
        response = {
            "status": overall_status,
            "checks": checks,
            "healthy_components": healthy_checks,
            "total_components": total_checks,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if status_code != 200:
            return response, status_code
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, 503


# ============================================
# READINESS CHECK
# ============================================

@router.get("/ready")
async def readiness_check(
    db = Depends(get_db)
):
    """
    Readiness check - indicates if system can accept requests
    
    **Returns:**
    - `ready`: Whether system is ready
    - `timestamp`: Check timestamp
    
    **Status Codes:**
    - 200: Ready to accept requests
    - 503: Not ready
    """
    
    try:
        logger.debug("🚀 Readiness check initiated")
        
        # Critical checks
        agent_ok = False
        rag_ok = False
        db_ok = db is not None
        
        try:
            agent_status = await get_agent_status(db=db)
            agent_ok = agent_status.get("initialized", False) and agent_status.get("graph_compiled", False)
        except:
            pass
        
        try:
            rag_status = get_rag_status()
            rag_ok = rag_status.get("initialized", False)
        except:
            pass
        
        ready = agent_ok and rag_ok and db_ok
        
        response = {
            "ready": ready,
            "checks": {
                "agent": agent_ok,
                "rag": rag_ok,
                "database": db_ok
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if not ready:
            return response, 503
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Readiness check failed: {str(e)}")
        return {
            "ready": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, 503


# ============================================
# LIVENESS CHECK
# ============================================

@router.get("/live")
async def liveness_check():
    """
    Liveness check - indicates if service is running
    
    **Returns:**
    - `alive`: Service is running
    - `timestamp`: Check timestamp
    
    **Status Codes:**
    - 200: Service is alive
    - 503: Service is down
    """
    
    try:
        return {
            "alive": True,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "Economic Advisor API"
        }
    except Exception as e:
        logger.error(f"❌ Liveness check failed: {str(e)}")
        return {
            "alive": False,
            "error": str(e)
        }, 503


# ============================================
# DETAILED DIAGNOSTICS
# ============================================

@router.get("/diagnostics")
async def get_diagnostics(
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Get detailed system diagnostics
    
    **Returns:**
    - `system`: Full system status
    - `diagnostics`: Detailed diagnostic information
    - `recommendations`: System recommendations
    
    **Requires:** User authentication
    """
    
    try:
        logger.info(f"🔧 Diagnostics requested by {current_user.username}")
        
        # Gather all diagnostic data
        agent_status = await get_agent_status(db=db)
        rag_status = get_rag_status()
        cache_stats = get_cache_stats()
        queue_count = get_question_count()
        archive_count = len(get_archive())
        
        # Generate recommendations
        recommendations = []
        
        if cache_stats.get("cache_hit_rate", "0%").rstrip("%").startswith("0"):
            recommendations.append("⚠️ Low cache hit rate - consider checking query patterns")
        
        if queue_count > 5000:
            recommendations.append("⚠️ Large queue size - consider processing more questions")
        
        if not rag_status.get("initialized"):
            recommendations.append("❌ RAG system not initialized - reinitialize required")
        
        if not agent_status.get("initialized"):
            recommendations.append("❌ Agent not initialized - restart required")
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "agent": agent_status,
                "rag": rag_status,
                "cache": cache_stats,
                "queue": {
                    "current": queue_count,
                    "archived": archive_count
                }
            },
            "recommendations": recommendations if recommendations else ["✅ System running optimally"],
            "diagnostics": {
                "agent_health": "good" if agent_status.get("initialized") else "failed",
                "rag_health": "good" if rag_status.get("initialized") else "failed",
                "cache_health": "good" if cache_stats.get("cache_hit_rate", "0%") != "0%" else "poor",
                "queue_health": "good" if queue_count < 5000 else "warning"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Diagnostics error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))