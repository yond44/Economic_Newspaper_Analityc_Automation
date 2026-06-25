from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
import logging
import time
import json

from src.utils.email_html import generate_economic_news_email
from src.middleware.auth import validate_api_key
from src.middleware.rate_limiter import check_rate_limit
from src.services.agent import (
    ask_agent, 
    get_agent_status,
    reset_question_system
)
from src.services.question_manager import (
    get_next_question,
    remove_first_question,
    add_question,
    generate_new_question_from_data,
    get_all_questions,
    get_question_count,
    get_archive,
    initialize_question_file,
    reset_question_queue,
    get_file_paths
)

from src.services.email_manager import (
    get_all_emails,
    get_email_by_id,
    add_email,
    update_email,
    delete_email,
    get_email_string,
    get_email_count,
    reset_email_file,
    initialize_email_file
)


logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# MODELS
# ============================================

class QueryRequest(BaseModel):
    question: str
    thread_id: Optional[str] = None
    channel: Optional[str] = "api"


class QueryResponse(BaseModel):
    question: str
    answer: str
    processing_time: float
    iterations: int
    thread_id: Optional[str] = "anonymous"


class BatchEmailRequest(BaseModel):
    question: str
    emails: List[str]
    phone: Optional[str] = None


# ============================================
# ROUTE FUNCTIONS
# ============================================

@router.post("/ask", response_model=QueryResponse)
async def ask(
    request: QueryRequest,
    api_key: str = Depends(validate_api_key),
    rate_limit: bool = Depends(check_rate_limit)
):
    """Ask a specific question"""
    
    status = get_agent_status()
    if not status["initialized"]:
        raise HTTPException(status_code=503, detail="Agent not ready")
    
    try:
        start_time = time.time()
        result = await ask_agent(request.question)
        processing_time = time.time() - start_time
        
        return QueryResponse(
            question=request.question,
            answer=result["answer"],
            processing_time=processing_time,
            iterations=result.get("attempts", 0),
            thread_id=request.thread_id or "anonymous"
        )
    
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-batch")
async def send_batch_email(
    request: BatchEmailRequest,
    api_key: str = Depends(validate_api_key),
    rate_limit: bool = Depends(check_rate_limit)
):
    status = get_agent_status()
    if not status["initialized"]:
        raise HTTPException(status_code=503, detail="Agent not ready")
    
    try:
        from src.services.email_sender import send_batch_emails
        from datetime import datetime
        
        result = await ask_agent(request.question)
        
        if not result.get("success", False):
            return {
                "status": "error",
                "message": "Failed to generate answer",
                "error": result.get("error", "Unknown error")
            }
        
        answer = result.get("answer", "No answer generated")
        question = request.question
        processing_time = result.get("processing_time", 0)
        iterations = result.get("attempts", 0)
        email_count = len(request.emails)
        
        queue_remaining = get_question_count()
        next_question = get_next_question()
        
        html_body = generate_economic_news_email(
            question=question,
            answer=answer,
            processing_time=processing_time,
            iterations=iterations,
            queue_remaining=queue_remaining,
            next_question=next_question,
            email_count=email_count
        )
        logger.info(f"📧 Sending to {len(request.emails)} recipients")
        email_result = await send_batch_emails(
            to_emails=request.emails,
            subject=f"Jojoba Economic News - {question[:50]}...",
            body=answer,
            html_body=html_body  
        )
        
        return {
            "status": "success",
            "question": request.question,
            "answer": answer[:500] + "..." if len(answer) > 500 else answer,
            "total_recipients": len(request.emails),
            "sent_count": email_result.get("sent_count", 0),
            "failed_emails": email_result.get("failed_emails", []),
            "simulated": email_result.get("simulated", False),
            "message": email_result.get("message", "Emails processed"),
            "iterations": result.get("attempts", 0)
        }
        
    except Exception as e:
        logger.error(f"Batch email error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook/next")
async def webhook_next(
    api_key: str = Depends(validate_api_key),
    rate_limit: bool = Depends(check_rate_limit)
):
    status = get_agent_status()
    if not status["initialized"]:
        return {"status": "error", "message": "Agent not ready"}
    
    try:
        question = get_next_question()
        
        if not question:
            new_q = generate_new_question_from_data()
            if new_q:
                add_question(new_q)
                question = get_next_question()
            
            if not question:
                from src.services.question_manager import get_default_fallback_questions
                fallbacks = get_default_fallback_questions()
                for q in fallbacks:
                    add_question(q)
                question = get_next_question()
        
        if not question:
            return {
                "status": "error",
                "message": "No questions available. Please add questions to the queue.",
                "queue_size": get_question_count()
            }
        
        logger.info(f"📝 Processing question: {question[:50]}...")
        
        # STEP 2: Process the question
        start_time = time.time()
        result = await ask_agent(question)
        processing_time = time.time() - start_time
        
        # STEP 3: Remove the processed question (index 0)
        removed = remove_first_question()
        if removed:
            logger.info(f"✅ Removed question from queue")
        
        # STEP 4: Generate a new question and add it to the end
        new_question = generate_new_question_from_data()
        if new_question:
            add_question(new_question)
            logger.info(f"✨ Added new question: {new_question[:50]}...")
        else:
            # If generation fails, add a fallback
            from src.services.question_manager import get_default_fallback_questions
            fallbacks = get_default_fallback_questions()
            add_question(fallbacks[0] if fallbacks else "What is the current market outlook?")
            logger.info("📌 Added fallback question")
        
        # STEP 5: Get email list from database
        contacts = get_all_emails()
        email_list = [contact.get("email") for contact in contacts if contact.get("email")]
        email_string = ", ".join(email_list)
        
        remaining = get_question_count()
        
        return {
            "status": "success" if result.get("success", False) else "error",
            "question": question,
            "response": result.get("answer", "No answer generated"),
            "processing_time": round(processing_time, 2),
            "iterations": result.get("attempts", 0),
            "queue_remaining": remaining,
            "next_question": get_next_question(),
            "emails": email_list,
            "email_string": email_string,
            "email_count": len(email_list)
        }
        
    except Exception as e:
        logger.error(f"❌ Next webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/webhook")
async def webhook(
    request: Request,
    api_key: str = Depends(validate_api_key),
    rate_limit: bool = Depends(check_rate_limit)
):
    status = get_agent_status()
    if not status["initialized"]:
        return {"status": "error", "message": "Agent not ready"}
    
    try:
        body = await request.json()
        logger.info(f"Received webhook body: {json.dumps(body, indent=2)[:500]}")
        
        question = None
        emails = []
        phone = None
        
        if isinstance(body, dict):
            if "question" in body:
                question = body["question"]
            elif "message" in body:
                question = body["message"]
            elif "text" in body:
                question = body["text"]
            
            if "email" in body:
                email_value = body["email"]
                if isinstance(email_value, str):
                    emails = [e.strip() for e in email_value.split(",") if e.strip()]
                elif isinstance(email_value, list):
                    emails = email_value
            
            # Extract phone
            if "phone" in body:
                phone = body["phone"]
        
        if not question:
            return {
                "status": "error",
                "message": "No question found",
                "received_keys": list(body.keys()) if isinstance(body, dict) else []
            }
        
        if not emails:
            contacts = get_all_emails()
            emails = [contact.get("email") for contact in contacts if contact.get("email")]
            logger.info(f"📧 Using {len(emails)} emails from database")
        
        result = await ask_agent(question)
        
        email_result = None
        if emails:
            from src.services.email_sender import send_batch_emails
            logger.info(f"📧 Sending to {len(emails)} recipients via webhook")
            email_result = await send_batch_emails(
                to_emails=emails,
                subject=f"Economic Analysis: {question[:50]}...",
                body=result.get("answer", "No answer generated")
            )
        
        return {
            "status": "success" if result.get("success", False) else "error",
            "question": question,
            "response": result.get("answer", "No answer generated"),
            "recipients": emails,
            "email_result": email_result,
            "phone": phone if phone else None,
            "iterations": result.get("attempts", 0),
            "processed": True
        }
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.get("/emails")
async def get_emails(
    api_key: str = Depends(validate_api_key)
):
    """Get all email contacts"""
    return {
        "status": "success",
        "count": get_email_count(),
        "emails": get_all_emails()
    }


@router.get("/emails/{email_id}")
async def get_email(
    email_id: int,
    api_key: str = Depends(validate_api_key)
):
    """Get a single email contact by ID"""
    email = get_email_by_id(email_id)
    if not email:
        return {"status": "error", "message": "Email contact not found"}
    return {"status": "success", "email": email}


@router.post("/emails")
async def create_email(
    name: str,
    email: str,
    api_key: str = Depends(validate_api_key)
):
    """Add a new email contact"""
    if not name or not email:
        return {"status": "error", "message": "Name and email are required"}
    
    new_contact = add_email(name, email)
    return {
        "status": "success",
        "message": "Email contact added",
        "email": new_contact
    }


@router.put("/emails/{email_id}")
async def update_email_contact(
    email_id: int,
    name: str,
    email: str,
    api_key: str = Depends(validate_api_key)
):
    """Update an email contact"""
    if not name or not email:
        return {"status": "error", "message": "Name and email are required"}
    
    updated = update_email(email_id, name, email)
    if not updated:
        return {"status": "error", "message": "Email contact not found"}
    
    return {
        "status": "success",
        "message": "Email contact updated",
        "email": updated
    }


@router.delete("/emails/{email_id}")
async def delete_email_contact(
    email_id: int,
    api_key: str = Depends(validate_api_key)
):
    deleted = delete_email(email_id)
    if not deleted:
        return {"status": "error", "message": "Email contact not found"}
    
    return {
        "status": "success",
        "message": "Email contact deleted"
    }


@router.get("/emails/string")
async def get_emails_string(
    api_key: str = Depends(validate_api_key)
):
    return {
        "status": "success",
        "email_string": get_email_string(),
        "count": get_email_count()
    }


@router.post("/emails/reset")
async def reset_emails(
    api_key: str = Depends(validate_api_key)
):
    emails = reset_email_file()
    return {
        "status": "success",
        "message": "Email contacts reset",
        "emails": emails
    }


@router.get("/status")
async def get_status(
    api_key: str = Depends(validate_api_key)
):
    return get_agent_status()


@router.get("/queue")
async def get_queue(
    api_key: str = Depends(validate_api_key)
):
    return {
        "total": get_question_count(),
        "questions": get_all_questions(),
        "next": get_next_question()
    }


@router.get("/archive")
async def get_archive_questions(
    api_key: str = Depends(validate_api_key)
):
    return {
        "total": len(get_archive()),
        "archive": get_archive()[-50:]  # Last 50
    }


@router.post("/queue/add")
async def add_question_to_queue(
    question: str,
    api_key: str = Depends(validate_api_key)
):
    if not question or not question.strip():
        return {"status": "error", "message": "Question cannot be empty"}
    
    add_question(question)
    return {
        "status": "success",
        "message": "Question added to queue",
        "queue_size": get_question_count()
    }


@router.post("/queue/reset")
async def reset_queue(
    api_key: str = Depends(validate_api_key)
):
    return reset_question_system()


@router.post("/queue/generate")
async def generate_question(
    api_key: str = Depends(validate_api_key)
):
    new_q = generate_new_question_from_data()
    if new_q:
        add_question(new_q)
        return {
            "status": "success",
            "question": new_q,
            "queue_size": get_question_count()
        }
    else:
        return {
            "status": "error",
            "message": "Could not generate question"
        }


@router.get("/queue/files")
async def get_queue_files(
    api_key: str = Depends(validate_api_key)
):
    return {
        "status": "success",
        "paths": get_file_paths(),
        "question_count": get_question_count(),
        "archive_count": len(get_archive())
    }


@router.get("/queue/data-summary")
async def get_data_summary(
    api_key: str = Depends(validate_api_key)
):
    from src.services.question_manager import get_data_summary
    return {
        "status": "success",
        "data": get_data_summary()
    }