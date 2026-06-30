# main.py
"""
Main FastAPI Application with Data Processing Pipeline
Processes and embeds documents before API startup
"""

import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# ============================================
# FIX PATH BEFORE ANY IMPORTS
# ============================================

# Get the absolute path of the project root
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================
# ENVIRONMENT SETUP
# ============================================

def load_environment():
    """Load environment variables from .env file"""
    env_paths = [
        PROJECT_ROOT / '.env',
        Path.cwd() / '.env',
        Path('.env'),
    ]
    
    for path in env_paths:
        if path.exists():
            load_dotenv(str(path))
            print(f"✅ Loaded .env from: {path}")
            return path
    
    print("⚠️ No .env file found! Using environment variables.")
    return None


# Load environment first
load_environment()

# Now import everything else
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from src.config.database import connect_db, close_db
from src.config.settings import (
    APP_NAME,
    APP_VERSION,
    DEBUG,
    API_HOST,
    API_PORT,
    RELOAD,
    validate_settings
)
from src.middleware.logging_middleware import LoggingMiddleware
from src.middleware.error_middleware import ErrorHandlerMiddleware
from src.utils.logger import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Validate settings
try:
    validate_settings()
except Exception as e:
    logger.error(f"❌ Settings validation failed: {e}")
    raise


# ============================================
# ROUTE LISTING UTILITIES
# ============================================

def get_all_routes(app: FastAPI):
    """Extract all routes from FastAPI app"""
    routes = []
    
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "methods": sorted(list(route.methods or ["GET"])),
                "name": route.name,
                "tags": route.tags or [],
                "summary": route.summary or ""
            })
    
    return sorted(routes, key=lambda x: x["path"])


def print_routes_table(app: FastAPI) -> None:
    """Print all routes in a formatted table"""
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 140)
    logger.info("📋 API ROUTES REGISTRY")
    logger.info("=" * 140)
    
    # Header
    logger.info(f"{'METHOD':<15} {'ENDPOINT':<80} {'SUMMARY':<45}")
    logger.info("-" * 140)
    
    # Group by path
    by_path = {}
    for route in routes:
        path = route["path"]
        if path not in by_path:
            by_path[path] = {"methods": [], "summary": ""}
        by_path[path]["methods"].extend(route["methods"])
        if route["summary"] and not by_path[path]["summary"]:
            by_path[path]["summary"] = route["summary"]
    
    # Print sorted
    for path in sorted(by_path.keys()):
        methods = ", ".join(sorted(set(by_path[path]["methods"])))
        summary = by_path[path]["summary"][:42] if by_path[path]["summary"] else ""
        
        logger.info(f"{methods:<15} {path:<80} {summary:<45}")
    
    logger.info("-" * 140)
    logger.info(f"{'TOTAL ENDPOINTS':<15} {len(by_path):<80}")
    logger.info("=" * 140 + "\n")


def print_routes_by_tag(app: FastAPI) -> None:
    """Print all routes grouped by tag"""
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 140)
    logger.info("📋 API ROUTES BY TAG")
    logger.info("=" * 140)
    
    # Group by tags
    by_tag = {}
    for route in routes:
        tags = route["tags"] or ["default"]
        for tag in tags:
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(route)
    
    # Print by tag
    total_count = 0
    for tag in sorted(by_tag.keys()):
        tag_routes = by_tag[tag]
        total_count += len(tag_routes)
        logger.info(f"\n🏷️  {tag.upper()} ({len(tag_routes)} endpoints)")
        logger.info("-" * 140)
        
        for route in sorted(tag_routes, key=lambda x: x["path"]):
            methods = ", ".join(route["methods"])
            summary = route["summary"][:80] if route["summary"] else ""
            logger.info(f"  {methods:<13} {route['path']:<75} {summary}")
    
    logger.info("\n" + "-" * 140)
    logger.info(f"Total endpoints by tag: {total_count}")
    logger.info("=" * 140 + "\n")


def print_routes_detailed(app: FastAPI) -> None:
    """Print detailed route information"""
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 140)
    logger.info("📋 DETAILED ROUTES INFORMATION")
    logger.info("=" * 140)
    
    for i, route in enumerate(routes, 1):
        logger.info(f"\n{i}. {route['path']}")
        logger.info(f"   Methods: {', '.join(route['methods'])}")
        if route["summary"]:
            logger.info(f"   Summary: {route['summary']}")
        if route["tags"]:
            logger.info(f"   Tags: {', '.join(route['tags'])}")
        logger.info(f"   Handler: {route['name']}")
    
    logger.info("\n" + "=" * 140 + "\n")


# ============================================
# DATA PROCESSING PIPELINE
# ============================================

class DataProcessingPipeline:
    """Handles document processing and embedding before API startup"""
    
    def __init__(self):
        self.rag_initialized = False
        self.agent_initialized = False
        self.documents_processed = 0
        self.chunks_created = 0
        self.processing_errors = []
    
    async def initialize_rag_system(self) -> bool:
        """Initialize RAG system with document processing"""
        try:
            logger.info("=" * 70)
            logger.info("📚 INITIALIZING RAG SYSTEM")
            logger.info("=" * 70)
            
            # Check if data exists
            data_path = PROJECT_ROOT / "data" / "raw"
            if not data_path.exists():
                logger.warning(f"⚠️ Data directory not found: {data_path}")
                logger.warning("   Create 'data/raw/' directory and add documents")
                return False
            
            doc_files = list(data_path.glob("**/*"))
            if not doc_files:
                logger.warning(f"⚠️ No documents found in {data_path}")
                return False
            
            logger.info(f"📄 Found {len(doc_files)} documents to process")
            
            # Import RAG service
            try:
                from src.services.rag import initialize_rag, get_rag_status
                logger.info("✅ RAG service imported")
            except ImportError as e:
                logger.error(f"❌ Failed to import RAG service: {str(e)}")
                self.processing_errors.append(f"RAG import: {str(e)}")
                return False
            
            # Initialize RAG
            logger.info("🔄 Processing documents...")
            try:
                await asyncio.to_thread(initialize_rag, False)
                logger.info("✅ RAG system initialized successfully")
                self.rag_initialized = True
                
                # Get status
                status = get_rag_status()
                self.documents_processed = status.get("metrics", {}).get("total_documents", 0)
                self.chunks_created = status.get("metrics", {}).get("total_chunks", 0)
                
                logger.info(f"📊 Documents: {self.documents_processed}")
                logger.info(f"📊 Chunks: {self.chunks_created}")
                
                # Log chunk distribution
                chunk_dist = status.get("metrics", {}).get("chunk_distribution", {})
                if chunk_dist:
                    logger.info("📈 Chunk distribution:")
                    for chunk_type, count in chunk_dist.items():
                        logger.info(f"   • {chunk_type}: {count}")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ RAG initialization failed: {str(e)}")
                self.processing_errors.append(f"RAG init: {str(e)}")
                logger.exception("RAG initialization traceback")
                return False
        
        except Exception as e:
            logger.error(f"❌ RAG system initialization error: {str(e)}")
            logger.exception("RAG system traceback")
            self.processing_errors.append(f"RAG system: {str(e)}")
            return False

    async def initialize_agent_system(self) -> bool:
        """Initialize agent system with graph compilation"""
        try:
            logger.info("=" * 70)
            logger.info("🤖 INITIALIZING AGENT SYSTEM")
            logger.info("=" * 70)
            
            # Import agent service
            try:
                from src.services.agent import initialize_agent, get_agent_status
                logger.info("✅ Agent service imported")
            except ImportError as e:
                logger.error(f"❌ Failed to import agent service: {str(e)}")
                self.processing_errors.append(f"Agent import: {str(e)}")
                return False
            
            # Initialize agent
            logger.info("🔄 Compiling agent graph...")
            try:
                await asyncio.to_thread(initialize_agent, False, None)
                logger.info("✅ Agent system initialized successfully")
                self.agent_initialized = True
                
                # Get status
                status = await get_agent_status()
                agents_count = len(status.get("agents", {}))
                
                logger.info(f"🤖 Agents deployed: {agents_count}")
                logger.info(f"✨ Features enabled: {sum(1 for v in status.get('features', {}).values() if v)}")
                
                # List agents
                if status.get("agents"):
                    logger.info("🔧 Agent components:")
                    for agent_name, description in status.get("agents", {}).items():
                        logger.info(f"   • {agent_name}")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Agent initialization failed: {str(e)}")
                self.processing_errors.append(f"Agent init: {str(e)}")
                logger.exception("Agent initialization traceback")
                return False
        
        except Exception as e:
            logger.error(f"❌ Agent system initialization error: {str(e)}")
            logger.exception("Agent system traceback")
            self.processing_errors.append(f"Agent system: {str(e)}")
            return False

    async def initialize_question_system(self) -> bool:
        """Initialize question queue system"""
        try:
            logger.info("=" * 70)
            logger.info("📋 INITIALIZING QUESTION QUEUE SYSTEM")
            logger.info("=" * 70)
            
            try:
                from src.services.question_manager import initialize_question_file, get_question_count
                logger.info("✅ Question manager imported")
            except ImportError as e:
                logger.warning(f"⚠️ Question manager not available: {str(e)}")
                return True  # Non-critical
            
            try:
                # Initialize question file with default questions
                count = await initialize_question_file(db)
                logger.info(f"✅ Question queue initialized with {count} questions")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ Question queue initialization warning: {str(e)}")
                return True  # Non-critical
        
        except Exception as e:
            logger.warning(f"⚠️ Question system warning: {str(e)}")
            return True  # Non-critical
    
    async def run_all_initializations(self) -> bool:
        """Run all initialization tasks in sequence"""
        logger.info("\n" + "=" * 70)
        logger.info("🚀 DATA PROCESSING PIPELINE STARTING")
        logger.info("=" * 70 + "\n")
        
        try:
            # Step 1: RAG System
            rag_ok = await self.initialize_rag_system()
            
            if not rag_ok:
                logger.warning("⚠️ RAG system not ready, some features will be limited")
            
            # Step 2: Agent System
            agent_ok = await self.initialize_agent_system()
            
            if not agent_ok:
                logger.warning("⚠️ Agent system not ready, API will be limited")
            
            # Step 3: Question System
            question_ok = await self.initialize_question_system()
            
            # Summary
            logger.info("\n" + "=" * 70)
            logger.info("📊 PIPELINE SUMMARY")
            logger.info("=" * 70)
            logger.info(f"✅ RAG System: {'Ready' if rag_ok else 'Not Ready'}")
            logger.info(f"✅ Agent System: {'Ready' if agent_ok else 'Not Ready'}")
            logger.info(f"✅ Question System: {'Ready' if question_ok else 'Not Ready'}")
            
            if self.processing_errors:
                logger.warning("\n⚠️ Errors encountered:")
                for error in self.processing_errors:
                    logger.warning(f"   • {error}")
            
            # Overall status
            overall_ok = rag_ok and agent_ok
            logger.info("\n" + "=" * 70)
            if overall_ok:
                logger.info("✅ ALL SYSTEMS READY - API CAN ACCEPT REQUESTS")
            else:
                logger.warning("⚠️ PARTIAL INITIALIZATION - API HAS LIMITED FUNCTIONALITY")
            logger.info("=" * 70 + "\n")
            
            return overall_ok
            
        except Exception as e:
            logger.error(f"❌ Pipeline execution failed: {str(e)}")
            logger.exception("Pipeline traceback")
            return False


# ============================================
# LIFESPAN
# ============================================

pipeline = DataProcessingPipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    logger.info("\n" + "=" * 70)
    logger.info("🚀 APPLICATION STARTUP")
    logger.info("=" * 70 + "\n")
    
    logger.info(f"📝 App: {APP_NAME} v{APP_VERSION}")
    logger.info(f"🔧 Debug: {DEBUG}")
    logger.info(f"🌍 Host: {API_HOST}:{API_PORT}")
    logger.info(f"📁 Project Root: {PROJECT_ROOT}")
    
    # Connect database
    try:
        await connect_db()
        logger.info("✅ Database connected")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        raise
    
    
    # Initialize automation settings (default off untuk semua)
    try:
        from src.config.database import get_database
        from src.services.automation_manager import ensure_default_settings
        db = get_database()
        await ensure_default_settings(db)
        logger.info("✅ Automation settings initialized")
    except Exception as e:
        logger.warning(f"⚠️ Could not init automation settings: {str(e)}")
        
    # Run data processing pipeline
    try:
        pipeline_ok = await pipeline.run_all_initializations()
        
        if not pipeline_ok:
            logger.warning("⚠️ API starting with limited functionality")
            logger.warning("   Some endpoints may not work correctly")
        
        # Store pipeline status in app state
        app.state.pipeline_status = pipeline_ok
        app.state.rag_ready = pipeline.rag_initialized
        app.state.agent_ready = pipeline.agent_initialized
        
    except Exception as e:
        logger.error(f"❌ Pipeline initialization failed: {str(e)}")
        logger.warning("⚠️ Continuing without full initialization")
        app.state.pipeline_status = False
        app.state.rag_ready = False
        app.state.agent_ready = False
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ APPLICATION READY")
    logger.info("=" * 70 + "\n")
    
    yield
    
    # Shutdown
    logger.info("\n👋 Shutting down...")
    await close_db()
    logger.info("✅ Shutdown complete")


# ============================================
# CREATE APP
# ============================================

def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="Multi-agent Economic & Investment Advisor with RAG",
        lifespan=lifespan,
        docs_url="/docs" if DEBUG else None,
        openapi_url="/openapi.json" if DEBUG else None,
    )
    
    # ============================================
    # MIDDLEWARE
    # ============================================
    
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if DEBUG else ["http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
    
    # ============================================
    # DEBUG: ROUTE LISTING
    # ============================================
    
    @app.get("/api/routes", tags=["debug"])
    async def list_routes():
        """List all registered routes (DEBUG ONLY)"""
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                routes.append({
                    "path": route.path,
                    "methods": list(route.methods) if route.methods else ["GET"]
                })
        return {
            "total": len(routes),
            "routes": sorted(routes, key=lambda x: x['path'])
        }
    
    # ============================================
    # ROUTES - Import directly
    # ============================================
    
    logger.info("\n" + "="*70)
    logger.info("📋 REGISTERING ROUTES")
    logger.info("="*70)
    
    # Agent routes
    try:
        from src.routes.agent import router as agent_router
        
        logger.info(f"Agent router details:")
        logger.info(f"  • Prefix: {agent_router.prefix}")
        logger.info(f"  • Total routes: {len(agent_router.routes)}")
        for route in agent_router.routes:
            if hasattr(route, 'path'):
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ["GET"]
                logger.info(f"    - {route.path} {methods}")
        
        app.include_router(agent_router, prefix="/api/v1")
        logger.info("✅ Included: agent_router → /api/v1/agent/*")
        
    except Exception as e:
        logger.error(f"❌ Agent router error: {type(e).__name__}")
        logger.exception("Full traceback:")
    
    # Webhook routes
    try:
        from src.routes.agent.webhook import router as webhook_router
        # webhook_router already has /api/webhook prefix
        app.include_router(webhook_router)
        logger.info("✅ Included: webhook_router → /api/webhook/*")
        
        # Log webhook routes
        for route in webhook_router.routes:
            if hasattr(route, 'path'):
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ["GET"]
                logger.info(f"    - {route.path} {methods}")
        
    except Exception as e:
        logger.warning(f"⚠️ Webhook router: {type(e).__name__}")
        logger.exception("Webhook router traceback:")
    
    # User routes
    try:
        from src.routes.user import router as user_router
        app.include_router(user_router, prefix="/api/v1")
        logger.info("✅ Included: user_router")
    except Exception as e:
        logger.warning(f"⚠️ User router: {type(e).__name__}")
    
    # Auth routes
    try:
        from src.routes.auth_routes import router as auth_router
        app.include_router(auth_router, prefix="/api/v1")
        logger.info("✅ Included: auth_router")
    except Exception as e:
        logger.warning(f"⚠️ Auth router: {type(e).__name__}")
    
    # Email routes
    try:
        from src.routes.email_routes import router as email_router
        app.include_router(email_router, prefix="/api/v1")
        logger.info("✅ Included: email_router")
    except Exception as e:
        logger.warning(f"⚠️ Email router: {type(e).__name__}")
    
    # Question routes - now with n8n endpoints
    try:
        from src.routes.question_router import router as question_router
        app.include_router(question_router, prefix="/api/v1")
        logger.info("✅ Included: question_router → /api/v1/questions/*")
        
        # Log question routes
        for route in question_router.routes:
            if hasattr(route, 'path'):
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ["GET"]
                logger.info(f"    - {route.path} {methods}")
        
    except Exception as e:
        logger.warning(f"⚠️ Question router: {type(e).__name__}")
        logger.exception("Question router traceback:")
    
    # ✅ History routes - ADD THIS
    try:
        from src.routes.history_routes import router as history_router
        app.include_router(history_router, prefix="/api/v1")
        logger.info("✅ Included: history_router → /api/v1/history/*")
        
        # Log history routes
        for route in history_router.routes:
            if hasattr(route, 'path'):
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ["GET"]
                logger.info(f"    - {route.path} {methods}")
        
    except Exception as e:
        logger.warning(f"⚠️ History router: {type(e).__name__}")
        logger.exception("History router traceback:")
        
        
        # ✅ Automation routes - toggle Aktif/Jeda
    try:
        from src.routes.automation_routes import router as automation_router
        app.include_router(automation_router, prefix="/api/v1")
        logger.info("✅ Included: automation_router → /api/v1/automation/*")
        
        for route in automation_router.routes:
            if hasattr(route, 'path'):
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ["GET"]
                logger.info(f"    - {route.path} {methods}")
        
    except Exception as e:
        logger.warning(f"⚠️ Automation router: {type(e).__name__}")
        logger.exception("Automation router traceback:")
    
    # Health routes
    try:
        from src.routes.health_routes import router as health_router
        app.include_router(health_router, prefix="/api/v1")
        logger.info("✅ Included: health_router")
    except Exception as e:
        logger.warning(f"⚠️ Health router: {type(e).__name__}")
    
    logger.info("="*70 + "\n")
    
    # ============================================
    # PRINT ROUTES IN MULTIPLE FORMATS
    # ============================================
    
    # Print simple table format (recommended)
    print_routes_table(app)
    
    # Uncomment below for additional formats:
    # print_routes_by_tag(app)
    # print_routes_detailed(app)
    
    # ============================================
    # ROOT ENDPOINTS
    # ============================================
    
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint - API status"""
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "status": "running",
            "debug": DEBUG,
            "pipeline_status": {
                "ready": getattr(app.state, 'pipeline_status', False),
                "rag": getattr(app.state, 'rag_ready', False),
                "agent": getattr(app.state, 'agent_ready', False),
                "documents_processed": pipeline.documents_processed,
                "chunks_created": pipeline.chunks_created,
            }
        }
    
    @app.get("/health", tags=["health"])
    async def health():
        """Quick health check"""
        pipeline_ok = getattr(app.state, 'pipeline_status', False)
        return {
            "status": "healthy" if pipeline_ok else "degraded",
            "app": APP_NAME,
            "version": APP_VERSION
        }
    
    return app


app = create_app()


# ============================================
# MAIN
# ============================================

def main():
    """Main entry point"""
    import uvicorn
    
    logger.info("=" * 70)
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION}")
    logger.info("=" * 70)
    logger.info(f"Host: {API_HOST}:{API_PORT}")
    logger.info(f"Debug: {DEBUG}")
    logger.info(f"Reload: {RELOAD}")
    logger.info(f"Project Root: {PROJECT_ROOT}")
    logger.info("=" * 70)
    
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        reload=RELOAD,
        log_level="debug" if DEBUG else "info",
    )


if __name__ == "__main__":
    main()