"""
MongoDB Database Configuration
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

MONGODB_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
DATABASE_NAME = os.getenv("DB_NAME", "llmautomationai")

# Global database instance
_db: AsyncIOMotorDatabase = None


# ============================================
# CONNECTION FUNCTIONS
# ============================================

async def connect_db():
    """Connect to MongoDB"""
    global _db
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        _db = client[DATABASE_NAME]
        
        # Verify connection
        await client.admin.command('ping')
        logger.info(f"✅ Connected to MongoDB: {DATABASE_NAME}")
        logger.info(f"📍 URL: {MONGODB_URL}")
        
        # Create indexes
        await create_indexes(_db)
        
        return _db
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {str(e)}")
        raise


async def close_db():
    """Close MongoDB connection"""
    global _db
    if _db:
        _db.client.close()
        logger.info("👋 Disconnected from MongoDB")


async def create_indexes(db: AsyncIOMotorDatabase):
    """Create database indexes"""
    try:
        # Users collection indexes
        users_collection = db["users"]
        await users_collection.create_index("email", unique=True)
        await users_collection.create_index("username", unique=True)
        await users_collection.create_index("created_at")
        
        # Login history indexes
        login_history = db["login_history"]
        await login_history.create_index("user_id")
        await login_history.create_index("login_at")
        
        # Emails collection indexes
        emails_collection = db["emails"]
        await emails_collection.create_index("email", unique=True)
        await emails_collection.create_index("name")
        await emails_collection.create_index("created_at")
        
        logger.info("✅ Database indexes created")
        
        question_logs = db["question_logs"]
        await question_logs.create_index("logged_at")
        await question_logs.create_index("success")
        await question_logs.create_index("channel")
        await question_logs.create_index("thread_id")
        await question_logs.create_index("user_id")
        await question_logs.create_index([("user_id", 1), ("logged_at", -1)])
        await question_logs.create_index([("user_id", 1), ("channel", 1)])
        
        logger.info("✅ Indexes created")
        
                # User emails indexes
        user_emails = db["user_emails"]
        await user_emails.create_index("user_id")
        await user_emails.create_index([("user_id", 1), ("email", 1)], unique=True)
        await user_emails.create_index([("user_id", 1), ("created_at", -1)])
    except Exception as e:
        logger.warning(f"⚠️ Index creation warning: {str(e)}")


def get_db() -> AsyncIOMotorDatabase:
    """Get database instance"""
    global _db
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _db