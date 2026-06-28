"""Agent Webhook Routes - Enhanced with n8n Integration and Advanced Features"""
import json
import time
import logging
from fastapi import APIRouter, Depends, Request, HTTPException, Query as QueryParam
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.middleware.rate_limiter import check_rate_limit
from src.middleware.auth import get_current_user
from src.config.database import get_db
from src.models.user import UserInDB
from src.models.agent import BatchEmailRequest
from src.services.agent import ask_agent, get_agent_status, batch_processor
from src.services.email_manager import get_all_emails
from src.services.question_manager import (
    get_question_count,
    get_next_question,
    remove_first_question,
    add_question,
    generate_new_question_from_data,
    get_default_fallback_questions
)
from src.utils.question_logger import log_question

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhook", tags=["webhook"])


# ============================================
# HELPER FUNCTIONS
# ============================================

def validate_webhook_secret(request: Request, expected_secret: Optional[str] = None) -> bool:
    """Validate webhook secret if configured"""
    if not expected_secret:
        return True
    secret = request.headers.get("X-Webhook-Secret")
    return secret == expected_secret


def extract_question_text(question: Any) -> str:
    """Extract question text from various formats"""
    if isinstance(question, str):
        return question
    elif isinstance(question, dict):
        return question.get("text", question.get("question", str(question)))
    elif hasattr(question, "text"):
        return question.text
    elif hasattr(question, "question"):
        return question.question
    else:
        return str(question)


async def get_recipient_emails(db, provided_emails: Optional[List[str]] = None) -> List[str]:
    """Get recipient emails from provided list or database"""
    if provided_emails and isinstance(provided_emails, list):
        return [e.strip() for e in provided_emails if isinstance(e, str) and e.strip()]
    
    try:
        contacts = await get_all_emails(db)
        emails = [c.get("email") for c in contacts if c.get("email")]
        logger.info(f"📧 Retrieved {len(emails)} emails from database")
        return emails
    except Exception as e:
        logger.warning(f"⚠️ Error retrieving emails: {str(e)}")
        return []


# ============================================
# GENERIC WEBHOOK
# ============================================

@router.post("/ask")
async def webhook_ask(
    request: Request,
    rate_limit: bool = Depends(check_rate_limit),
    db = Depends(get_db)
):
    """Generic webhook endpoint to ask agent a question"""
    
    if not rate_limit:
        logger.warning("⚠️ Rate limit exceeded on webhook")
        raise HTTPException(status_code=429, detail="Too many requests")
    
    status_data = await get_agent_status()
    if not status_data.get("initialized"):
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        start_time = time.time()
        
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"❌ Invalid JSON: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        question = (
            body.get("question") or 
            body.get("message") or 
            body.get("text") or 
            body.get("prompt")
        )
        
        if not question or not isinstance(question, str) or not question.strip():
            return {
                "status": "error",
                "message": "No question provided",
                "received_keys": list(body.keys()) if isinstance(body, dict) else [],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        question = question.strip()
        logger.info(f"📨 Webhook question: {question[:100]}...")
        
        language = body.get("language", "en")
        thread_id = body.get("thread_id")
        send_email = body.get("send_email", False)
        phone = body.get("phone")
        
        emails = []
        if body.get("email"):
            email_value = body["email"]
            if isinstance(email_value, str):
                emails = [e.strip() for e in email_value.split(",") if e.strip()]
            elif isinstance(email_value, list):
                emails = [e for e in email_value if isinstance(e, str) and e.strip()]
        
        if send_email and not emails:
            emails = await get_recipient_emails(db)
        
        result = await ask_agent(
            question=question,
            thread_id=thread_id,
            db=db,
            language=language
        )
        
        processing_time = time.time() - start_time
        
        try:
            await log_question(
                db,
                question=question,
                answer=result.get("answer", ""),
                processing_time=processing_time,
                thread_id=thread_id,
                channel="webhook",
                language=language,
                success=result.get("success", False),
                error=result.get("error")
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to log question: {str(e)}")
        
        email_result = None
        if send_email and emails:
            try:
                from src.services.email_sender import send_batch_emails
                logger.info(f"📧 Sending to {len(emails)} recipients...")
                email_result = await send_batch_emails(
                    to_emails=emails,
                    subject=f"Economic Analysis: {question[:50]}...",
                    body=result.get("answer", "No answer generated"),
                    html_body=None
                )
                logger.info(f"✅ Sent to {email_result.get('sent_count', 0)} recipients")
            except Exception as e:
                logger.error(f"❌ Email error: {str(e)}")
                email_result = {"status": "error", "message": str(e)}
        
        logger.info(f"✅ Webhook processed in {processing_time:.2f}s")
        
        return {
            "status": "success" if result.get("success") else "error",
            "timestamp": datetime.utcnow().isoformat(),
            "question": question,
            "answer": result.get("answer", ""),
            "processing_time_seconds": round(processing_time, 3),
            "iterations": result.get("attempts", 1),
            "response_type": result.get("response_type", "answer"),
            "language_detected": result.get("language_detected", language),
            "sources_count": len(result.get("sources", [])),
            "recipients": len(emails) if emails else 0,
            "emails": emails if send_email else None,
            "email_result": email_result if send_email else None,
            "phone": phone,
            "thread_id": thread_id,
            "error": result.get("error")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ============================================
# QUEUE PROCESSING WEBHOOK
# ============================================

@router.post("/process-next")
async def webhook_process_next(
    rate_limit: bool = Depends(check_rate_limit),
    db = Depends(get_db),
    send_email: bool = QueryParam(False),
    language: str = QueryParam("en")
):
    """Process next question in queue and optionally send via email"""
    
    if not rate_limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    status_data = await get_agent_status()
    if not status_data.get("initialized"):
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        start_time = time.time()
        
        # Get next question - this might be a string or a dict
        question = await get_next_question(db)
        
        # Extract question text if it's a dict or object
        question_text = extract_question_text(question) if question else None
        
        # If queue empty, generate new question
        if not question_text:
            logger.info("📭 Queue empty, generating new question...")
            new_q = await generate_new_question_from_data(db)
            
            if not new_q:
                fallbacks = get_default_fallback_questions()
                for fb in fallbacks:
                    await add_question(db, fb)
                new_q = await get_next_question(db)
            
            if new_q:
                await add_question(db, new_q)
                question = await get_next_question(db)
                question_text = extract_question_text(question) if question else None
        
        if not question_text:
            return {
                "status": "error",
                "message": "No questions available in queue or from generation",
                "queue_size": await get_question_count(db),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Log with truncated text
        preview = question_text[:100] + "..." if len(question_text) > 100 else question_text
        logger.info(f"📝 Processing queue question: {preview}")
        
        # Process the question using the text
        result = await ask_agent(
            question=question_text,
            db=db,
            language=language,
            channel="webhook"
        )
        
        processing_time = time.time() - start_time
        
        try:
            await log_question(
                db,
                question=question_text,
                answer=result.get("answer", ""),
                processing_time=processing_time,
                channel="webhook_queue",
                language=language,
                success=result.get("success", False)
            )
        except Exception as e:
            logger.warning(f"⚠️ Log error: {str(e)}")
        
        try:
            removed = await remove_first_question(db)
            if removed:
                logger.info(f"✅ Removed from queue")
        except Exception as e:
            logger.warning(f"⚠️ Remove error: {str(e)}")
        
        try:
            new_question = await generate_new_question_from_data(db)
            if new_question:
                await add_question(db, new_question)
                new_text = extract_question_text(new_question)
                preview = new_text[:50] + "..." if len(new_text) > 50 else new_text
                logger.info(f"✨ Generated and added: {preview}")
            else:
                fallbacks = get_default_fallback_questions()
                if fallbacks:
                    await add_question(db, fallbacks[0])
        except Exception as e:
            logger.warning(f"⚠️ Generation error: {str(e)}")
        
        email_data = None
        if send_email:
            try:
                emails = await get_recipient_emails(db)
                if emails:
                    from src.services.email_sender import send_batch_emails
                    email_result = await send_batch_emails(
                        to_emails=emails,
                        subject=f"Daily Economic Analysis: {question_text[:50]}...",
                        body=result.get("answer", ""),
                        html_body=None
                    )
                    email_data = {
                        "sent": True,
                        "recipients": len(emails),
                        "sent_count": email_result.get("sent_count", 0),
                        "failed_emails": email_result.get("failed_emails", [])
                    }
                    logger.info(f"📧 Sent to {email_data['sent_count']} recipients")
            except Exception as e:
                logger.error(f"❌ Email error: {str(e)}")
                email_data = {"sent": False, "error": str(e)}
        
        logger.info(f"✅ Queue processing complete in {processing_time:.2f}s")
        
        # Get next question for response
        next_q = await get_next_question(db)
        next_text = extract_question_text(next_q) if next_q else None
        
        return {
            "status": "success" if result.get("success") else "error",
            "timestamp": datetime.utcnow().isoformat(),
            "question": question_text,
            "answer": result.get("answer", ""),
            "processing_time_seconds": round(processing_time, 3),
            "iterations": result.get("attempts", 1),
            "response_type": result.get("response_type", "answer"),
            "queue_remaining": await get_question_count(db),
            "next_question": next_text,
            "email": email_data,
            "error": result.get("error")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Queue processing error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# BATCH EMAIL WEBHOOK
# ============================================

@router.post("/send-batch")
async def webhook_send_batch(
    request: BatchEmailRequest,
    rate_limit: bool = Depends(check_rate_limit),
    db = Depends(get_db)
):
    """Process question and send batch emails"""
    
    if not rate_limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    status_data = await get_agent_status()
    if not status_data.get("initialized"):
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        start_time = time.time()
        
        if not request.question or not request.emails:
            raise HTTPException(status_code=400, detail="Missing question or emails")
        
        logger.info(f"📧 Batch email request: {len(request.emails)} recipients")
        logger.info(f"❓ Question: {request.question[:100]}...")
        
        result = await ask_agent(
            question=request.question,
            db=db,
            language=request.language or "en",
            channel="batch_email"
        )
        
        processing_time = time.time() - start_time
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process question: {result.get('error')}"
            )
        
        answer = result.get("answer", "")
        
        try:
            await log_question(
                db,
                question=request.question,
                answer=answer,
                processing_time=processing_time,
                channel="batch_email",
                language=request.language or "en",
                success=True,
                recipient_count=len(request.emails)
            )
        except Exception as e:
            logger.warning(f"⚠️ Log error: {str(e)}")
        
        email_result = None
        try:
            from src.services.email_sender import send_batch_emails
            from src.utils.email_html import generate_economic_news_email
            
            logger.info(f"📧 Sending to {len(request.emails)} recipients...")
            
            html_body = generate_economic_news_email(
                question=request.question,
                answer=answer,
                processing_time=processing_time,
                iterations=result.get("attempts", 1),
                sources_count=len(result.get("sources", []))
            )
            
            email_result = await send_batch_emails(
                to_emails=request.emails,
                subject=request.subject or f"Economic Analysis: {request.question[:50]}...",
                body=answer,
                html_body=html_body
            )
            
            logger.info(f"✅ Sent to {email_result.get('sent_count', 0)} recipients")
            
        except Exception as e:
            logger.error(f"❌ Email sending error: {str(e)}")
            email_result = {
                "status": "error",
                "message": str(e),
                "sent_count": 0
            }
        
        logger.info(f"✅ Batch email complete in {processing_time:.2f}s")
        
        return {
            "status": "success" if email_result and email_result.get("sent_count", 0) > 0 else "partial",
            "timestamp": datetime.utcnow().isoformat(),
            "question": request.question,
            "answer_preview": answer[:500] + ("..." if len(answer) > 500 else ""),
            "total_recipients": len(request.emails),
            "sent_count": email_result.get("sent_count", 0) if email_result else 0,
            "failed_emails": email_result.get("failed_emails", []) if email_result else [],
            "processing_time_seconds": round(processing_time, 3),
            "iterations": result.get("attempts", 1),
            "simulated": email_result.get("simulated", False) if email_result else False,
            "error": email_result.get("message") if email_result and email_result.get("status") == "error" else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Batch email error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# WEBHOOK VALIDATION & TESTING
# ============================================

@router.post("/test")
async def test_webhook(
    request: Request,
    db = Depends(get_db)
):
    """Test webhook connectivity and agent status"""
    
    try:
        logger.info("🧪 Webhook test initiated")
        status = await get_agent_status()
        
        return {
            "status": "operational" if status.get("initialized") else "degraded",
            "agent_ready": status.get("initialized", False),
            "graph_compiled": status.get("graph_compiled", False),
            "queue_size": await get_question_count(db),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Test error: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, 500


@router.get("/health")
async def webhook_health():
    """Webhook health check"""
    
    try:
        status_data = await get_agent_status()
        ready = status_data.get("initialized", False)
        
        response = {
            "status": "healthy" if ready else "degraded",
            "ready": ready,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return response if ready else (response, 503)
        
    except Exception as e:
        logger.error(f"❌ Health check error: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }, 503