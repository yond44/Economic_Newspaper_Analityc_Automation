"""
Configuration - Plain dict, no classes
"""
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Config dictionary
CONFIG = {
    "APP_NAME": os.getenv("APP_NAME", "Economic Analysis System"),
    "APP_VERSION": "1.0.0",
    "DEBUG": os.getenv("DEBUG", "True").lower() == "true",
    "API_HOST": os.getenv("API_HOST", "0.0.0.0"),
    "API_PORT": int(os.getenv("API_PORT", 8000)),
    "API_KEY": os.getenv("API_KEY", "your-secret-api-key-12345"),
    "ALLOWED_ORIGINS": ["http://localhost:3000", "http://localhost:5678"],
    
    # Groq
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
    "OLLAMA_URL": os.getenv("OLLAMA_URL", "http://localhost:11434"),
    
    # Qdrant
    "QDRANT_URL": os.getenv("QDRANT_URL", "http://localhost:6333"),
    "QDRANT_COLLECTION": os.getenv("QDRANT_COLLECTION", "economic_data"),
    
    # Data
    "DATA_DIR": os.getenv("DATA_DIR", "data/raw"),
    "CHUNK_SIZE": int(os.getenv("CHUNK_SIZE", 1024)),
    "CHUNK_OVERLAP": int(os.getenv("CHUNK_OVERLAP", 200)),
    
    # Rate Limiting
    "RATE_LIMIT": int(os.getenv("RATE_LIMIT", 50)),
    "RATE_LIMIT_PERIOD": int(os.getenv("RATE_LIMIT_PERIOD", 60)),
}