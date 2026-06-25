#!/usr/bin/env python3
# test_webhook.py - Fixed for n8n webhook format

import requests
import json
import sys
import time
import os
from dotenv import load_dotenv


load_dotenv()
# ============================================
# CONFIGURATION
# ============================================

# n8n webhook URL
# N8N_WEBHOOK_URL = "http://localhost:5678/webhook/ask"
N8N_WEBHOOK_URL = "http://localhost:5678/webhook-test/ask"

# Your FastAPI webhook URL (direct test)
API_WEBHOOK_URL = "http://localhost:8000/api/v1/agent/webhook"

# API Key for FastAPI
API_KEY = os.getenv("GROQ_API_KEY")

# ============================================
# TEST FUNCTIONS
# ============================================

def test_n8n_webhook(payload, test_name):
    """Test n8n webhook endpoint"""
    print(f"\n{'='*50}")
    print(f"Test: {test_name}")
    print(f"Endpoint: n8n webhook")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"Response: {response.text[:500]}")
            
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - is n8n running?")
        print("   Start n8n with: docker run -d -p 5678:5678 n8nio/n8n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_api_webhook(payload, test_name):
    """Test FastAPI webhook directly (bypass n8n)"""
    print(f"\n{'='*50}")
    print(f"Test: {test_name}")
    print(f"Endpoint: FastAPI webhook")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(API_WEBHOOK_URL, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"Response: {response.text[:500]}")
            
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - is FastAPI running?")
        print("   Start FastAPI with: python -m src.main")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ============================================
# MAIN TEST SUITE
# ============================================

def main():
    print("🧪 Webhook Test Suite")
    print("=" * 50)
    print(f"n8n Webhook URL: {N8N_WEBHOOK_URL}")
    print(f"API Webhook URL: {API_WEBHOOK_URL}")
    print("=" * 50)
    
    # Test payloads
    test_payloads = [
        {
            "name": "Basic question",
            "payload": {
                "question": "What is BI rate?"
            }
        },
        {
            "name": "Question with email",
            "payload": {
                "question": "What is the current gold price?",
                "email": "test@example.com"
            }
        },
        {
            "name": "Question with body wrapper (n8n style)",
            "payload": {
                "body": {
                    "question": "What is the inflation rate?",
                    "email": "user@example.com"
                }
            }
        },
        {
            "name": "Investment question (should have disclaimer)",
            "payload": {
                "question": "Should I buy Bitcoin now?",
                "email": "investor@example.com"
            }
        },
        {
            "name": "Off-topic question (should be rejected)",
            "payload": {
                "question": "What is the weather today?",
                "email": "test@example.com"
            }
        },
        {
            "name": "Gratitude (should respond nicely)",
            "payload": {
                "question": "Thank you",
                "email": "test@example.com"
            }
        }
    ]
    
    results = []
    
    # Test n8n webhook
    print("\n" + "🔵 TESTING N8N WEBHOOK")
    print("=" * 50)
    print("⚠️ Make sure your n8n workflow is ACTIVE!")
    print("⚠️ The webhook path should be: /ask")
    print("=" * 50)
    
    for test in test_payloads:
        success = test_n8n_webhook(test["payload"], test["name"])
        results.append(("n8n", test["name"], success))
        time.sleep(0.5)  # Small delay between tests
    
    # Test API webhook directly (bypass n8n)
    print("\n" + "🟢 TESTING FASTAPI WEBHOOK (DIRECT)")
    print("=" * 50)
    print("⚠️ Make sure FastAPI is running on port 8000")
    print("=" * 50)
    
    for test in test_payloads:
        success = test_api_webhook(test["payload"], test["name"])
        results.append(("API", test["name"], success))
        time.sleep(0.5)  # Small delay between tests
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    n8n_passed = sum(1 for source, name, success in results if source == "n8n" and success)
    n8n_total = sum(1 for source, name, success in results if source == "n8n")
    api_passed = sum(1 for source, name, success in results if source == "API" and success)
    api_total = sum(1 for source, name, success in results if source == "API" and success)
    
    print(f"\n🔵 n8n Webhook: {n8n_passed}/{n8n_total} passed")
    print(f"🟢 API Webhook: {api_passed}/{api_total} passed")
    
    print("\n📋 Detailed Results:")
    for source, name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - [{source}] {name}")
    
    # Troubleshooting tips
    print("\n" + "=" * 60)
    print("🔧 TROUBLESHOOTING")
    print("=" * 60)
    
    if n8n_passed == 0:
        print("\n❌ n8n webhook is not working. Check:")
        print("  1. Is n8n running?")
        print("     docker ps | grep n8n")
        print("  2. Is the workflow ACTIVE?")
        print("     Go to n8n UI and click 'Activate'")
        print("  3. Is the webhook path correct?")
        print("     Should be: /webhook/ask")
        print("  4. Check n8n logs:")
        print("     docker logs n8n")
    
    if api_passed == 0:
        print("\n❌ API webhook is not working. Check:")
        print("  1. Is FastAPI running?")
        print("     python -m src.main")
        print("  2. Is the API key correct?")
        print(f"     Current API Key: {API_KEY}")
        print("  3. Check FastAPI logs for errors")
    
    if n8n_passed > 0 and api_passed > 0:
        print("\n✅ All tests passed! Your webhook is working!")
    
    print("\n" + "=" * 60)
    
    return 0 if (n8n_passed == n8n_total and api_passed == api_total) else 1


# ============================================
# QUICK TEST FUNCTIONS (for manual testing)
# ============================================

def quick_test_n8n():
    """Quick test for n8n webhook"""
    payload = {"question": "What is the BI rate?"}
    response = requests.post(N8N_WEBHOOK_URL, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
    return response


def quick_test_api():
    """Quick test for API webhook"""
    headers = {"X-API-Key": API_KEY}
    payload = {"question": "What is the BI rate?"}
    response = requests.post(API_WEBHOOK_URL, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response


if __name__ == "__main__":
    # Check for quick test flag
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        print("🚀 Quick Test")
        print("=" * 40)
        print("\nTesting n8n webhook...")
        quick_test_n8n()
        print("\nTesting API webhook...")
        quick_test_api()
        sys.exit(0)
    
    # Run full test suite
    sys.exit(main())