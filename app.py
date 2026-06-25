import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
import socket
import subprocess
import logging

logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)

PROJECT_ROOT = Path(__file__).parent
STREAMLIT_APP = PROJECT_ROOT / "src" / "streamlit" / "streamlit_app.py"

def run_fastapi():
    subprocess.run(
        ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "error"],
        cwd=str(PROJECT_ROOT)
    )

def wait_for_api(max_retries=30, delay=2):
    print("⏳ Waiting for FastAPI to start...")
    for i in range(max_retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 8000))
            sock.close()
            if result == 0:
                print("✅ FastAPI ready!")
                time.sleep(1)
                return True
        except:
            pass
        if i % 5 == 0 and i > 0:
            print(f"⏳ Still waiting... ({i+1}/{max_retries})")
        time.sleep(delay)
    print("❌ FastAPI failed to start")
    return False

def run_streamlit():
    if wait_for_api():
        print("🚀 Starting Streamlit...")
        subprocess.run(
            ["streamlit", "run", str(STREAMLIT_APP), "--server.port", "8501", "--logger.level", "error"],
            cwd=str(PROJECT_ROOT)
        )
    else:
        sys.exit(1)

if __name__ == "__main__":
    print("="*50)
    print("🚀 Jojoba Economic News Platform")
    print("="*50)
    print("📊 FastAPI: http://localhost:8000")
    print("📊 Streamlit: http://localhost:8501")
    print("="*50)
    
    try:
        import streamlit
    except ImportError:
        print("📦 Installing streamlit...")
        subprocess.run(["pip", "install", "streamlit", "-q"])

    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    
    run_streamlit()