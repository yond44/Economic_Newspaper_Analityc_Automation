import os
import sys
import uvicorn
from dotenv import load_dotenv


env_paths = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),  # Project root
    os.path.join(os.getcwd(), '.env'),  # Current directory
    '.env'  # Same directory
]

for path in env_paths:
    if os.path.exists(path):
        load_dotenv(path)
        print(f"✅ Loaded .env from: {path}")
        break
else:
    print("⚠️ No .env file found! Using environment variables.")


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================
# IMPORTS WORK
# ============================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from src.services.agent import initialize_agent, get_agent_status
from src.middleware.logging_middleware import LoggingMiddleware
from src.middleware.error_middleware import global_exception_handler
from src.utils.logger import setup_logging
from src.routes import agent_router, health_router

setup_logging()
logger = logging.getLogger(__name__)

# ============================================
# CONFIG (Read from environment)
# ============================================
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Check if GROQ_API_KEY is loaded
if GROQ_API_KEY:
    logger.info(f"✅ GROQ_API_KEY loaded: {GROQ_API_KEY[:20]}...")
else:
    logger.error("❌ GROQ_API_KEY NOT found in environment!")
    logger.info("📝 Current working directory: " + os.getcwd())
    logger.info("📝 .env file exists? " + str(os.path.exists(".env")))

# ============================================
# LIFESPAN
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting application...")
    
    # Check environment variables
    if not os.getenv("GROQ_API_KEY"):
        logger.error("❌ GROQ_API_KEY not set! Check your .env file.")
        logger.info(f"📂 .env path: {os.path.join(os.getcwd(), '.env')}")
    
    try:
        initialize_agent()
        logger.info("✅ Agent initialized")
    except Exception as e:
        logger.error(f"❌ Agent initialization failed: {str(e)}")
    
    yield
    logger.info("👋 Shutting down...")

# ============================================
# CREATE APP
# ============================================
app = FastAPI(
    title="Economic Analysis API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_exception_handler(Exception, global_exception_handler)

# ============================================
# INCLUDE ROUTERS
# ============================================
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])

# ============================================
# ROOT ENDPOINT
# ============================================
@app.get("/")
async def root():
    status = get_agent_status()
    return {
        "name": "Economic Analysis API",
        "version": "1.0.0",
        "status": "running",
        "agent_ready": status.get("initialized", False),
        "env": {
            "groq_loaded": bool(os.getenv("GROQ_API_KEY")),
            "cwd": os.getcwd()
        },
        "endpoints": {
            "ask": "/api/v1/agent/ask",
            "webhook": "/api/v1/agent/webhook",
            "webhook_batch": "/api/v1/agent/webhook/batch",
            "webhook_flexible": "/api/v1/agent/webhook/flexible",
            "status": "/api/v1/agent/status",
            "health": "/api/v1/health",
            "docs": "/docs" if DEBUG else "Disabled"
        }
    }

# ============================================
# RUN THE APP
# ============================================
if __name__ == "__main__":
  
    
    if not os.getenv("GROQ_API_KEY"):
        print("\n" + "="*60)
        print("❌ ERROR: GROQ_API_KEY not found!")
        print(f"📂 Current directory: {os.getcwd()}")
        print(f"📂 .env exists? {os.path.exists('.env')}")
        print("="*60 + "\n")
    
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=os.getenv("DEBUG", "True").lower() == "False"
    )