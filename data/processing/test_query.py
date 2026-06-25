from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.groq import Groq
from llama_index.core.node_parser import SimpleNodeParser
import chromadb
from pathlib import Path
import os
import time
os.environ["GROQ_API_KEY"] = ""  

Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
    embed_batch_size=2,  
    timeout=120,
)

Settings.llm = Groq(
    model="llama-3.3-70b-versatile",  
    api_key=os.getenv("GROQ_API_KEY"), 
)


chroma_client = chromadb.PersistentClient(path="./chroma_db") 
collection = chroma_client.get_or_create_collection("my_collection")
vector_store = ChromaVectorStore(chroma_collection=collection)


parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=10)

current_dir = Path(__file__).parent
raw_dir = current_dir.parent.parent / "data" / "raw"

print(f"📂 Loading documents from: {raw_dir}")
documents = SimpleDirectoryReader(str(raw_dir)).load_data()
print(f"✅ Loaded {len(documents)} documents")


print("🔄 Creating vector index (one doc at a time)...")
storage_context = StorageContext.from_defaults(vector_store=vector_store)


index = VectorStoreIndex.from_documents(
    documents,
    storage_context=storage_context,
    transformations=[parser],
    show_progress=True,
)


query_engine = index.as_query_engine(
    similarity_top_k=1,  
    response_mode="compact",
)

question = "What is the BI rate?"
print(f"\n❓ Question: {question}")

for attempt in range(3):
    try:
        response = query_engine.query(question)
        print(f"💡 Answer: {response}")
        break
    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        if attempt < 2:
            time.sleep(5)