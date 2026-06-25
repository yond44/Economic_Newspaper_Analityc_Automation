import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Use the same API key that your auth.py expects
API_KEY = os.getenv("GROQ_API_KEY")  # This matches your auth.py

questions = [
    # Normal questions
    "What is the BI rate?",
    "What is the gold price?",
    
    # Gratitude
    "Thank you",
    "Thanks a lot!",
    "Great, thank you!",
    
    # Off-topic
    "What is the weather?",
    "How to cook rice?",
    
    # No data
    "What is the price of Tesla stock?"
]

# Check if API key is set
if not API_KEY:
    print("❌ GROQ_API_KEY not found in .env file!")
    print("Please add GROQ_API_KEY=your-key-here to .env")
    exit(1)

for q in questions:
    url = "http://localhost:8000/api/v1/agent/ask"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY  # Use the key from .env
    }
    data = {
        "question": q
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Question: {q}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Answer: {result.get('answer', 'No answer')}")
            print(f"Processing time: {result.get('processing_time', 0)}s")
        else:
            print(f"Error: {response.text}")
        print("-" * 50)
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection error - is FastAPI running?")
        print("   Start with: python -m src.main")
        break
    except Exception as e:
        print(f"❌ Error: {e}")
        break