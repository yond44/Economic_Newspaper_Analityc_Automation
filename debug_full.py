# debug_full.py
"""
Comprehensive Debug Script for Agent Initialization
Tests all components and provides detailed diagnostics
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug.log')
    ]
)

logger = logging.getLogger(__name__)

# Color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 70}")
    print(f"{text.center(70)}")
    print(f"{'=' * 70}{Colors.END}\n")


def print_section(text: str):
    """Print section header"""
    print(f"\n{Colors.BLUE}[*] {text}{Colors.END}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")


# ============================================
# STEP 1: ENVIRONMENT CHECKS
# ============================================

def check_environment():
    """Check environment setup"""
    print_header("STEP 1: ENVIRONMENT CHECKS")
    
    checks = {
        "Working Directory": os.getcwd(),
        "Python Version": f"{sys.version.split()[0]}",
        "Platform": sys.platform,
    }
    
    for key, value in checks.items():
        print_info(f"{key}: {value}")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print_error("Python 3.8+ required")
        return False
    
    print_success("Environment checks passed")
    return True


# ============================================
# STEP 2: PROJECT STRUCTURE
# ============================================

def check_project_structure():
    """Check project directory structure"""
    print_header("STEP 2: PROJECT STRUCTURE")
    
    root = Path.cwd()
    required_dirs = [
        "src",
        "src/config",
        "src/services",
        "src/models",
        "src/middleware",
        "data/raw"
    ]
    
    print_info("Checking required directories...")
    
    all_exist = True
    for dir_name in required_dirs:
        dir_path = root / dir_name
        if dir_path.exists():
            print_success(f"  {dir_name}/ exists")
        else:
            print_error(f"  {dir_name}/ NOT FOUND")
            all_exist = False
    
    # Check critical files
    print_info("\nChecking critical files...")
    
    critical_files = [
        ".env",
        "src/__init__.py",
        "src/config/__init__.py",
        "src/services/__init__.py",
    ]
    
    for file_name in critical_files:
        file_path = root / file_name
        if file_path.exists():
            print_success(f"  {file_name} exists")
        else:
            print_warning(f"  {file_name} NOT FOUND")
    
    return all_exist


# ============================================
# STEP 3: ENVIRONMENT VARIABLES
# ============================================

def check_environment_variables():
    """Check .env file and environment variables"""
    print_header("STEP 3: ENVIRONMENT VARIABLES")
    
    env_path = Path.cwd() / ".env"
    
    if not env_path.exists():
        print_error(f".env file not found at {env_path}")
        return False
    
    print_success(f".env file exists at {env_path}")
    
    # Load and check required variables
    required_vars = [
        "GROQ_API_KEY",
        "MONGODB_URI",
        "DATABASE_NAME",
        "CHUNK_SIZE",
        "CACHE_TTL"
    ]
    
    print_info("\nChecking environment variables...")
    
    from dotenv import load_dotenv
    load_dotenv(env_path)
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if "KEY" in var or "SECRET" in var or "PASSWORD" in var:
                print_success(f"  {var}=***hidden***")
            else:
                print_success(f"  {var}={value}")
        else:
            print_warning(f"  {var}=NOT SET")
            missing_vars.append(var)
    
    if missing_vars:
        print_warning(f"\nMissing variables: {', '.join(missing_vars)}")
        print_warning("Some features may not work correctly")
        return len(missing_vars) <= 2  # Allow some missing vars
    
    print_success("All required variables set")
    return True


# ============================================
# STEP 4: DEPENDENCY IMPORTS
# ============================================

def check_dependencies():
    """Check if all required dependencies can be imported"""
    print_header("STEP 4: DEPENDENCY IMPORTS")
    
    dependencies = {
        "fastapi": "FastAPI",
        "pydantic": "Pydantic",
        "sqlalchemy": "SQLAlchemy",
        "motor": "Motor (Async MongoDB)",
        "langchain": "LangChain",
        "llama_index": "LlamaIndex",
        "chromadb": "ChromaDB",
        "dotenv": "Python-dotenv",
        "jwt": "PyJWT",
        "bcrypt": "Bcrypt"
    }
    
    failed_deps = []
    
    for module, name in dependencies.items():
        try:
            __import__(module)
            print_success(f"  {name} imported")
        except ImportError as e:
            print_error(f"  {name} FAILED: {str(e)[:50]}")
            failed_deps.append(name)
    
    if failed_deps:
        print_warning(f"\nFailed imports: {', '.join(failed_deps)}")
        return False
    
    print_success("All dependencies imported successfully")
    return True


# ============================================
# STEP 5: CONFIG IMPORT
# ============================================

def check_config():
    """Test config import"""
    print_header("STEP 5: CONFIG IMPORT")
    
    try:
        from src.config.settings import CONFIG
        print_success("Config imported successfully")
        
        print_info("\nConfig values:")
        config_items = {
            "APP_NAME": CONFIG.get("APP_NAME"),
            "DEBUG": CONFIG.get("DEBUG"),
            "MONGODB_URI": "***" if CONFIG.get("MONGODB_URI") else "NOT SET",
            "CHUNK_SIZE": CONFIG.get("CHUNK_SIZE"),
            "CACHE_TTL": CONFIG.get("CACHE_TTL"),
        }
        
        for key, value in config_items.items():
            if value:
                print_success(f"  {key}: {value}")
            else:
                print_warning(f"  {key}: NOT SET")
        
        return True
        
    except Exception as e:
        print_error(f"Config import failed: {str(e)}")
        logger.exception("Config import error")
        return False


# ============================================
# STEP 6: DATABASE CONNECTION
# ============================================

async def check_database():
    """Test database connection"""
    print_header("STEP 6: DATABASE CONNECTION")
    
    try:
        from src.config.database import get_db
        
        print_info("Testing database connection...")
        
        try:
            db = await get_db()
            
            # Test connection
            server_info = await db.client.server_info()
            print_success("Database connected successfully")
            print_info(f"  Server version: {server_info.get('version', 'Unknown')}")
            
            # Check collections
            collections = await db.list_collection_names()
            print_info(f"  Collections: {', '.join(collections) if collections else 'None'}")
            
            return True
            
        except Exception as e:
            print_error(f"Database connection failed: {str(e)}")
            logger.exception("Database connection error")
            return False
            
    except Exception as e:
        print_error(f"Database import failed: {str(e)}")
        return False


# ============================================
# STEP 7: RAG SYSTEM
# ============================================

def check_rag_system():
    """Test RAG system"""
    print_header("STEP 7: RAG SYSTEM")
    
    try:
        from src.services.rag import (
            initialize_rag,
            get_rag_status,
            query_rag_sync,
            get_cache_stats
        )
        
        print_success("RAG module imported")
        
        # Check RAG status
        print_info("\nChecking RAG status...")
        status = get_rag_status()
        
        if status.get("initialized"):
            print_success("RAG system initialized")
            
            metrics = status.get("metrics", {})
            print_info(f"  Documents: {metrics.get('total_documents', 0)}")
            print_info(f"  Chunks: {metrics.get('total_chunks', 0)}")
            print_info(f"  Models: {status.get('models', {})}")
            
            # Check cache
            print_info("\nCache statistics:")
            cache = get_cache_stats()
            print_info(f"  Cached queries: {cache.get('total_cached_queries', 0)}")
            print_info(f"  Hit rate: {cache.get('hit_rate', 'N/A')}")
            
        else:
            print_warning("RAG system not initialized")
            print_info("Attempting initialization...")
            
            try:
                initialize_rag(force_reindex=False)
                print_success("RAG initialized successfully")
            except Exception as e:
                print_error(f"RAG initialization failed: {str(e)[:100]}")
                return False
        
        return True
        
    except Exception as e:
        print_error(f"RAG system check failed: {str(e)}")
        logger.exception("RAG system error")
        return False


# ============================================
# STEP 8: AGENT SYSTEM
# ============================================

def check_agent_system():
    """Test agent system"""
    print_header("STEP 8: AGENT SYSTEM")
    
    try:
        from src.services.agent import (
            initialize_agent,
            get_agent_status,
            get_graph_app
        )
        
        print_success("Agent module imported")
        
        # Check agent status
        print_info("\nChecking agent status...")
        status = get_agent_status()
        
        if status.get("initialized"):
            print_success("Agent system initialized")
            
            print_info(f"  Graph compiled: {status.get('graph_compiled', False)}")
            print_info(f"  Mode: {status.get('mode', 'Unknown')}")
            print_info(f"  Agents: {len(status.get('agents', {}))}")
            
            # Check features
            features = status.get("features", {})
            print_info(f"\n  Features enabled:")
            for feature, enabled in features.items():
                status_str = "✓" if enabled else "✗"
                print_info(f"    {status_str} {feature}")
            
        else:
            print_warning("Agent system not initialized")
            print_info("Attempting initialization...")
            
            try:
                initialize_agent(force_reindex=False)
                print_success("Agent initialized successfully")
            except Exception as e:
                print_error(f"Agent initialization failed: {str(e)[:100]}")
                return False
        
        return True
        
    except Exception as e:
        print_error(f"Agent system check failed: {str(e)}")
        logger.exception("Agent system error")
        return False


# ============================================
# STEP 9: FUNCTIONAL TESTS
# ============================================

async def check_functionality():
    """Test actual agent functionality"""
    print_header("STEP 9: FUNCTIONAL TESTS")
    
    try:
        from src.services.agent import ask_agent, get_agent_status
        
        # Check if agent is ready
        status = get_agent_status()
        if not status.get("initialized"):
            print_warning("Agent not initialized, skipping functional tests")
            return True
        
        print_info("Testing ask_agent with simple question...")
        
        try:
            result = await ask_agent(
                question="What is the current date?",
                channel="debug"
            )
            
            if result.get("success"):
                print_success("ask_agent test successful")
                print_info(f"  Response type: {result.get('response_type')}")
                print_info(f"  Processing time: {result.get('processing_time', 0):.3f}s")
                print_info(f"  Answer length: {len(result.get('answer', ''))} chars")
            else:
                print_warning("ask_agent returned non-success status")
                print_info(f"  Error: {result.get('error')}")
            
            return result.get("success", True)
            
        except Exception as e:
            print_error(f"ask_agent test failed: {str(e)}")
            logger.exception("ask_agent test error")
            return False
        
    except Exception as e:
        print_error(f"Functionality check failed: {str(e)}")
        logger.exception("Functionality check error")
        return False


# ============================================
# STEP 10: SUMMARY AND RECOMMENDATIONS
# ============================================

def print_summary(results: dict):
    """Print summary and recommendations"""
    print_header("STEP 10: SUMMARY & RECOMMENDATIONS")
    
    total_checks = len(results)
    passed_checks = sum(1 for v in results.values() if v)
    
    print_info(f"Checks passed: {passed_checks}/{total_checks}")
    
    # Determine overall status
    if passed_checks == total_checks:
        print_success("All checks passed! System is ready.")
        status = "READY"
    elif passed_checks >= total_checks - 2:
        print_warning("Most checks passed. Some features may be limited.")
        status = "DEGRADED"
    else:
        print_error("Multiple checks failed. System may not work correctly.")
        status = "CRITICAL"
    
    # Print failed checks
    failed = [k for k, v in results.items() if not v]
    if failed:
        print_warning("\nFailed checks:")
        for check in failed:
            print_warning(f"  • {check}")
    
    # Recommendations
    print_info("\nRecommendations:")
    
    if not results.get("Environment"):
        print_warning("  • Update Python to 3.8+")
    
    if not results.get("Environment Variables"):
        print_warning("  • Check and update .env file")
    
    if not results.get("Dependencies"):
        print_warning("  • Run: pip install -r requirements.txt")
    
    if not results.get("Database"):
        print_warning("  • Verify MongoDB connection")
        print_warning("  • Check MONGODB_URI in .env")
    
    if not results.get("RAG System"):
        print_warning("  • Rerun with --force-reindex flag")
    
    if not results.get("Agent System"):
        print_warning("  • Check RAG system first")
    
    # Print next steps
    print_info("\nNext steps:")
    if status == "READY":
        print_info("  1. Start the API server: uvicorn main:app --reload")
        print_info("  2. Access docs at http://localhost:8000/docs")
        print_info("  3. Try a query: POST /api/agent/ask")
    else:
        print_info("  1. Fix failed checks above")
        print_info("  2. Check debug.log for detailed errors")
        print_info("  3. Rerun this debug script")
    
    print_header(f"OVERALL STATUS: {status}")
    
    return status


# ============================================
# MAIN EXECUTION
# ============================================

async def main():
    """Main debug function"""
    print_header("FULL DEBUG - AGENT INITIALIZATION")
    print_info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # Run all checks
    results["Environment"] = check_environment()
    results["Project Structure"] = check_project_structure()
    results["Environment Variables"] = check_environment_variables()
    results["Dependencies"] = check_dependencies()
    results["Config Import"] = check_config()
    results["RAG System"] = check_rag_system()
    results["Agent System"] = check_agent_system()
    results["Database"] = await check_database()
    results["Functionality"] = await check_functionality()
    
    # Print summary
    status = print_summary(results)
    
    print_info(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Debug log saved to: debug.log")
    
    return 0 if status == "READY" else 1


if __name__ == "__main__":
    import asyncio
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\nDebug interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Fatal error: {str(e)}")
        logger.exception("Fatal error during debug")
        sys.exit(1)