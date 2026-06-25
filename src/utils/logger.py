"""
Logger - No Emojis, Clean Output
"""
import logging
import sys
from pathlib import Path

def setup_logging(log_level: str = "INFO"):
    """Setup logging without emojis"""
    
    Path("logs").mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/app.log", encoding='utf-8')
        ]
    )
    
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("llama_index").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)