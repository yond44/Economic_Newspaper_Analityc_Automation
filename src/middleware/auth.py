"""
Auth Middleware - Functions Only
"""
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GROQ_API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(api_key: str = Security(api_key_header)): 
    if not API_KEY:
        logger.error("❌ GROQ_API_KEY not set in environment variables")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key not set"
        )
    
    if not api_key:
        logger.warning("❌ Missing API key in request")
        raise HTTPException(
            status_code=401,
            detail="Missing API Key. Provide X-API-Key header."
        )
    
    if api_key != API_KEY:
        logger.warning(f"❌ Invalid API key attempt: {api_key[:10]}...")
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )
    
    return True