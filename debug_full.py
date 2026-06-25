# debug_full.py
import sys
import os
import logging

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("=" * 60)
print("FULL DEBUG - AGENT INITIALIZATION")
print("=" * 60)

# Step 1: Check environment
print("\n[1] Checking environment...")
print(f"Current directory: {os.getcwd()}")
print(f"Python path: {sys.path}")

# Step 2: Check .env file
print("\n[2] Checking .env file...")
env_file = ".env"
if os.path.exists(env_file):
    print(f"✅ .env file exists")
    with open(env_file, 'r') as f:
        content = f.read()
        # Show only non-sensitive values
        for line in content.split('\n'):
            if line and not line.startswith('#'):
                if 'API_KEY' in line or 'KEY' in line:
                    parts = line.split('=')
                    if len(parts) > 1:
                        print(f"  {parts[0]}=***hidden***")
                else:
                    print(f"  {line}")
else:
    print(f"❌ .env file not found at {os.path.abspath(env_file)}")

# Step 3: Import config
print("\n[3] Testing config import...")
try:
    from src.config.settings import CONFIG
    print("✅ Config imported successfully")
    print(f"  APP_NAME: {CONFIG.get('APP_NAME')}")
    print(f"  DEBUG: {CONFIG.get('DEBUG')}")
    print(f"  QDRANT_URL: {CONFIG.get('QDRANT_URL')}")
    print(f"  GROQ_API_KEY: {'Set' if CONFIG.get('GROQ_API_KEY') else 'NOT SET'}")
except Exception as e:
    print(f"❌ Config import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Test RAG import
print("\n[4] Testing RAG service import...")
try:
    from src.services.rag_service import initialize_rag, query_rag, get_rag_status
    print("✅ RAG service imported successfully")
    
    # Try to initialize RAG
    print("\n[5] Initializing RAG...")
    try:
        initialize_rag(force_reindex=False)
        print("✅ RAG initialized successfully")
        status = get_rag_status()
        print(f"  RAG Status: {status}")
    except Exception as e:
        print(f"❌ RAG initialization failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n⚠️ Continuing without RAG...")
except Exception as e:
    print(f"❌ RAG import failed: {e}")
    import traceback
    traceback.print_exc()

# Step 5: Test Agent import
print("\n[6] Testing Agent import...")
try:
    from src.services.agent import initialize_agent, get_agent_status, ask_agent
    print("✅ Agent imported successfully")
    
    # Try to initialize Agent
    print("\n[7] Initializing Agent...")
    try:
        initialize_agent(force_reindex=False)
        print("✅ Agent initialized successfully")
        status = get_agent_status()
        print(f"  Agent Status: {status}")
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        import traceback
        traceback.print_exc()
except Exception as e:
    print(f"❌ Agent import failed: {e}")
    import traceback
    traceback.print_exc()

# Step 6: Test the actual ask function
print("\n[8] Testing ask_agent function...")
try:
    import asyncio
    
    async def test_ask():
        try:
            # First check if agent is initialized
            status = get_agent_status()
            print(f"  Status before ask: {status}")
            
            if not status.get('initialized'):
                print("  ⚠️ Agent not initialized, attempting to initialize...")
                initialize_agent()
            
            result = await ask_agent("What is the BI rate?")
            print(f"  Result: {result}")
            return result
        except Exception as e:
            print(f"  ❌ ask_agent failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    result = asyncio.run(test_ask())
    if result:
        print("✅ ask_agent test successful")
    else:
        print("❌ ask_agent test failed")
        
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)