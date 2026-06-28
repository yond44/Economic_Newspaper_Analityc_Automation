"""
Application Settings Configuration
"""
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# ============================================
# APPLICATION SETTINGS
# ============================================

APP_NAME = os.getenv("APP_NAME", "LLM Economic Analysis System")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
RELOAD = os.getenv("RELOAD", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ============================================
# DATABASE
# ============================================

MONGO_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
MONGO_URL_PROD = os.getenv("MONGO_URL_2", MONGO_URL)
DB_NAME = os.getenv("DB_NAME", "llmautomationai")

# Use MONGO_URL_PROD if in production
if ENVIRONMENT == "production" and MONGO_URL_PROD:
    MONGO_URL = MONGO_URL_PROD

# ============================================
# API SECURITY
# ============================================

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
API_KEY = os.getenv("GROQ_API_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# ============================================
# LLM CONFIGURATION
# ============================================

GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")

# ============================================
# QDRANT VECTOR DATABASE
# ============================================

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "economic_data")

# ============================================
# DATA PROCESSING
# ============================================

DATA_DIR = os.getenv("DATA_DIR", "data/raw")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# ============================================
# RATE LIMITING
# ============================================

RATE_LIMIT = int(os.getenv("RATE_LIMIT", "100"))
RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", "60"))

# ============================================
# EMAIL CONFIGURATION
# ============================================

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")

# ============================================
# WAHA WHATSAPP CONFIGURATION
# ============================================

WAHA_ENABLED = os.getenv("WAHA_ENABLED", "false").lower() == "true"
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "admin")
WHATSAPP_VERIFY_TOKEN: Optional[str] = os.getenv("WHATSAPP_VERIFY_TOKEN")

# ============================================
# N8N WEBHOOK
# ============================================

N8N_WEBHOOK_URL: Optional[str] = os.getenv("N8N_WEBHOOK_URL")

# ============================================
# CORS CONFIGURATION
# ============================================

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]

# ============================================
# VALIDATION
# ============================================

def validate_settings() -> bool:
    """Validate critical settings"""
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Required settings
    required_settings = {
        "GROQ_API_KEY": GROQ_API_KEY,
    }
    
    missing = [key for key, value in required_settings.items() if not value]
    
    # Conditional requirements
    if EMAIL_ENABLED and not SMTP_USER:
        missing.append("SMTP_USER (required when EMAIL_ENABLED=true)")
    if EMAIL_ENABLED and not SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD (required when EMAIL_ENABLED=true)")
    
    if WAHA_ENABLED and not WHATSAPP_VERIFY_TOKEN:
        missing.append("WHATSAPP_VERIFY_TOKEN (required when WAHA_ENABLED=true)")
    
    if missing:
        logger.warning(f"⚠️ Missing environment variables: {', '.join(missing)}")
        return len(missing) == 0
    
    logger.info(f"✓ Settings validated successfully (Environment: {ENVIRONMENT})")
    return True


# ============================================
# ENVIRONMENT INFO
# ============================================

def get_settings_summary() -> dict:
    """Get a summary of current settings (safe for logging)"""
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "environment": ENVIRONMENT,
        "debug": DEBUG,
        "database": DB_NAME,
        "api_host": API_HOST,
        "api_port": API_PORT,
        "email_enabled": EMAIL_ENABLED,
        "waha_enabled": WAHA_ENABLED,
        "llm_configured": bool(GROQ_API_KEY),
        "vector_db_url": QDRANT_URL,
    }