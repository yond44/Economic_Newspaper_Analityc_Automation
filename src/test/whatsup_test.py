import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

# WAHA API URL (your WhatsApp gateway)
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "admin")

# Your FastAPI URL
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "your-secret-api-key-12345")

# Test phone number (WITHOUT + sign)
TEST_PHONE = "6281238983961"


# ============================================
# TEST FUNCTIONS
# ============================================

def test_waha_connection():
    """Test if WAHA is running"""
    print("🔍 Testing WAHA connection...")
    
    try:
        response = requests.get(f"{WAHA_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ WAHA is running: {response.json()}")
            return True
        else:
            print(f"❌ WAHA returned: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ WAHA not reachable at {WAHA_URL}")
        print("   Start WAHA with: docker run -d -p 3000:3000 devlikeapro/waha-core:latest")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_waha_send_direct():
    """Test sending directly to WAHA (bypass FastAPI)"""
    print("\n📤 Testing WAHA direct send...")
    
    url = f"{WAHA_URL}/api/send/text"
    headers = {
        "X-API-Key": WAHA_API_KEY,
        "Content-Type": "application/json"
    }
    
    # WAHA expects "chatId" with @c.us suffix
    payload = {
        "chatId": f"{TEST_PHONE}@c.us",
        "text": "Hello from WAHA test! 🚀"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            print(f"✅ WAHA send successful: {response.json()}")
            return True
        else:
            print(f"❌ WAHA send failed: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to WAHA")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_whatsapp_manual():
    """Test WhatsApp via your FastAPI endpoint"""
    print("\n📤 Testing WhatsApp via FastAPI...")
    
    url = f"{API_URL}/api/v1/agent/whatsapp"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    payload = {
        "phone": TEST_PHONE,
        "question": "What is the BI rate?"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to FastAPI at {API_URL}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_whatsapp_webhook():
    """Test the WhatsApp incoming webhook (simulate WAHA)"""
    print("\n📥 Testing WhatsApp webhook...")
    
    url = f"{API_URL}/api/v1/agent/whatsapp/webhook"
    headers = {"Content-Type": "application/json"}
    
    # Simulate WAHA incoming message
    payload = {
        "event": "message",
        "session": "default",
        "data": {
            "from": f"{TEST_PHONE}@c.us",
            "body": "What is the gold price?",
            "id": "test_12345"
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Webhook response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Webhook failed: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to FastAPI at {API_URL}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_whatsapp_status():
    """Check WhatsApp connection status"""
    print("\n📊 Checking WhatsApp status...")
    
    url = f"{API_URL}/api/v1/agent/whatsapp/status"
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Status check failed: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to FastAPI at {API_URL}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ============================================
# MAIN
# ============================================

def main():
    print("=" * 60)
    print("📱 WhatsApp Integration Test Suite")
    print("=" * 60)
    print(f"WAHA URL: {WAHA_URL}")
    print(f"FastAPI URL: {API_URL}")
    print(f"Test Phone: {TEST_PHONE}")
    print("=" * 60)
    
    results = []
    
    # Test 1: WAHA Connection
    results.append(("WAHA Connection", test_waha_connection()))
    
    # Test 2: WAHA Direct Send
    results.append(("WAHA Direct Send", test_waha_send_direct()))
    
    # Test 3: WhatsApp via FastAPI
    results.append(("WhatsApp Manual (FastAPI)", test_whatsapp_manual()))
    
    # Test 4: WhatsApp Webhook
    results.append(("WhatsApp Webhook", test_whatsapp_webhook()))
    
    # Test 5: WhatsApp Status
    results.append(("WhatsApp Status", test_whatsapp_status()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if success:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} passed")
    
    # Troubleshooting
    if passed < len(results):
        print("\n🔧 TROUBLESHOOTING:")
        if not results[0][1]:  # WAHA Connection failed
            print("  ❌ WAHA is not running. Start it with:")
            print("     docker run -d -p 3000:3000 devlikeapro/waha-core:latest")
            print("     Then open http://localhost:3000 and scan QR code")
        
        if results[0][1] and not results[1][1]:  # WAHA running but send failed
            print("  ❌ WhatsApp not connected. Check:")
            print("     - QR code scanned in WAHA dashboard (http://localhost:3000)")
            print("     - WAHA_API_KEY matches in .env")
    
    print("=" * 60)


if __name__ == "__main__":
    main()