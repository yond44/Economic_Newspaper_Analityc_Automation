import os
import time
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import asyncio
from functools import lru_cache

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.llms.groq import Groq
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core import Document
import chromadb
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================
# GLOBAL STATE
# ============================================

_query_engine = None
_is_initialized = False
_index = None
_query_cache = {}  # {hash: {answer, timestamp, ttl}}
_embedding_cache = {}  # {doc_hash: embedded_doc}

# Configuration from .env
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "128"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default
SIMILARITY_TOP_K = int(os.getenv("SIMILARITY_TOP_K", "8"))
DATA_HASH_FILE = "./chroma_db/.data_hash"


# ============================================
# CACHING UTILITIES
# ============================================

def _hash_query(question: str) -> str:
    """Create a hash of the query for caching"""
    return hashlib.md5(question.lower().strip().encode()).hexdigest()


def _is_cache_valid(timestamp: float, ttl: int) -> bool:
    """Check if cache entry is still valid"""
    return (time.time() - timestamp) < ttl


def _get_cached_query(question: str) -> Optional[Dict[str, Any]]:
    """Get query from cache if available and valid"""
    query_hash = _hash_query(question)

    if query_hash in _query_cache:
        cache_entry = _query_cache[query_hash]
        if _is_cache_valid(cache_entry["timestamp"], cache_entry["ttl"]):
            logger.info(f"✅ Cache HIT: {question[:50]}...")
            return cache_entry["data"]
        else:
            del _query_cache[query_hash]
            logger.info(f"⏰ Cache EXPIRED: {question[:50]}...")

    return None


def _set_cached_query(question: str, data: Dict[str, Any]):
    """Store query result in cache"""
    query_hash = _hash_query(question)
    _query_cache[query_hash] = {
        "data": data,
        "timestamp": time.time(),
        "ttl": CACHE_TTL
    }
    logger.info(f"💾 Cached query: {question[:50]}...")


def clear_query_cache():
    """Clear all query cache"""
    global _query_cache
    _query_cache.clear()
    logger.info("🧹 Query cache cleared")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    valid_entries = sum(
        1 for entry in _query_cache.values()
        if _is_cache_valid(entry["timestamp"], entry["ttl"])
    )

    return {
        "total_cached_queries": len(_query_cache),
        "valid_entries": valid_entries,
        "expired_entries": len(_query_cache) - valid_entries,
        "cache_ttl_seconds": CACHE_TTL,
        "approximate_memory_kb": len(str(_query_cache)) / 1024
    }


# ============================================
# DATA CHANGE DETECTION
# ============================================

def _hash_data_directory(data_dir: Path) -> str:
    """Hash all files in data directory to detect changes"""
    hasher = hashlib.sha256()
    for filepath in sorted(data_dir.glob("*")):
        if filepath.is_file():
            hasher.update(filepath.name.encode())
            hasher.update(str(filepath.stat().st_size).encode())
            hasher.update(str(filepath.stat().st_mtime).encode())
    return hasher.hexdigest()


def _data_has_changed(data_dir: Path) -> bool:
    """Check if data files have changed since last indexing"""
    current_hash = _hash_data_directory(data_dir)
    hash_file = Path(DATA_HASH_FILE)

    if hash_file.exists():
        stored_hash = hash_file.read_text().strip()
        if stored_hash == current_hash:
            logger.info("📦 Data files unchanged — skipping reindex")
            return False

    logger.info("🔄 Data files changed — reindex required")
    return True


def _save_data_hash(data_dir: Path):
    """Save current data hash after successful indexing"""
    current_hash = _hash_data_directory(data_dir)
    hash_file = Path(DATA_HASH_FILE)
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(current_hash)
    logger.info("💾 Data hash saved")


# ============================================
# SETUP FUNCTIONS
# ============================================

def setup_llm():
    """Setup Groq LLM"""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found")

    return Groq(
        model="llama-3.3-70b-versatile",
        api_key=api_key,
    )


def setup_embeddings():
    """Setup embedding model"""
    return FastEmbedEmbedding(
        model_name="BAAI/bge-small-en-v1.5",
    )


def setup_vector_store(force_clear: bool = False):
    """Setup ChromaDB vector store, optionally clearing old data"""
    chroma_client = chromadb.PersistentClient(path="./chroma_db")

    if force_clear:
        try:
            chroma_client.delete_collection("my_collection")
            logger.info("🗑️ Cleared old ChromaDB collection")
        except Exception:
            pass  # Collection didn't exist

    collection = chroma_client.get_or_create_collection("my_collection")
    logger.info(f"📊 ChromaDB collection has {collection.count()} existing vectors")
    return ChromaVectorStore(chroma_collection=collection)


def setup_node_parser():
    """Setup document parser with optimized chunk sizes"""
    return SimpleNodeParser.from_defaults(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )


# ============================================
# INTELLIGENT CHUNKING STRATEGIES
# ============================================

def chunk_documents_by_type(documents: List[Document]) -> List[Document]:
    """Route documents to appropriate chunking strategy based on MASTER file names"""
    chunked_docs = []

    for doc in documents:
        file_name = doc.metadata.get('file_name', '').lower()

        if 'qa_pairs' in file_name:
            chunks = chunk_qa_document(doc)
        elif 'glossary' in file_name:
            chunks = chunk_glossary_document(doc)
        elif 'scenario_playbooks' in file_name:
            chunks = chunk_scenario_document(doc)
        elif 'structured_analysis' in file_name:
            chunks = chunk_structured_document(doc)
        elif 'deep_dive' in file_name:
            chunks = chunk_deep_document(doc)
        elif 'quant' in file_name or 'financial_data' in file_name:
            chunks = chunk_quant_document(doc)
        else:
            chunks = chunk_default_document(doc)

        chunked_docs.extend(chunks)
        logger.info(f"  📄 {file_name}: {len(chunks)} chunks")

    return chunked_docs


def chunk_qa_document(doc: Document) -> List[Document]:
    """Chunk QA pairs — each Q&A pair stays together as one chunk"""
    chunks = []
    text = doc.text
    # Split on "Q: " at the start of a line
    pairs = text.split('\nQ: ')

    for i, pair in enumerate(pairs):
        pair = pair.strip()
        if not pair:
            continue

        # Re-add the "Q: " prefix that was removed by split (except first if it starts with Q:)
        if not pair.startswith('Q:'):
            pair = 'Q: ' + pair

        if len(pair) > 50:  # Skip empty/junk pairs
            chunks.append(
                Document(
                    text=pair,
                    metadata={
                        **doc.metadata,
                        "chunk_type": "qa_pair",
                        "pair_index": i
                    }
                )
            )

    return chunks if chunks else [doc]


def chunk_glossary_document(doc: Document) -> List[Document]:
    """Chunk glossary — each definition is its own chunk"""
    chunks = []
    text = doc.text
    lines = text.split('\n')

    current_entry = []
    for line in lines:
        # New glossary entry starts with an ALL-CAPS term followed by colon or parenthesis
        # Or a section header starting with #
        stripped = line.strip()
        if not stripped:
            continue

        # Detect new entry: line starts with uppercase word(s) followed by ( or :
        is_new_entry = False
        if stripped and stripped[0].isupper() and (':' in stripped[:80] or '(' in stripped[:80]):
            # Check it's not a continuation sentence
            words_before_colon = stripped.split(':')[0].split('(')[0].strip()
            if words_before_colon.isupper() or words_before_colon.replace(' ', '').replace('-', '').replace('/', '').isupper():
                is_new_entry = True

        if is_new_entry and current_entry:
            entry_text = '\n'.join(current_entry)
            if len(entry_text) > 30:
                chunks.append(
                    Document(
                        text=entry_text,
                        metadata={
                            **doc.metadata,
                            "chunk_type": "glossary_entry",
                        }
                    )
                )
            current_entry = [stripped]
        elif stripped.startswith('#'):
            # Section header — save current, skip header
            if current_entry:
                entry_text = '\n'.join(current_entry)
                if len(entry_text) > 30:
                    chunks.append(
                        Document(
                            text=entry_text,
                            metadata={
                                **doc.metadata,
                                "chunk_type": "glossary_entry",
                            }
                        )
                    )
                current_entry = []
        else:
            current_entry.append(stripped)

    # Save last entry
    if current_entry:
        entry_text = '\n'.join(current_entry)
        if len(entry_text) > 30:
            chunks.append(
                Document(
                    text=entry_text,
                    metadata={
                        **doc.metadata,
                        "chunk_type": "glossary_entry",
                    }
                )
            )

    return chunks if chunks else [doc]


def chunk_scenario_document(doc: Document) -> List[Document]:
    """Chunk scenario playbooks — each full scenario (base+bull+bear+positioning) stays together"""
    chunks = []
    text = doc.text
    # Split on the scenario marker
    scenarios = text.split('[SCENARIO PLAYBOOK]')

    for i, scenario in enumerate(scenarios):
        scenario = scenario.strip()
        if not scenario or len(scenario) < 100:
            continue

        # Re-add marker for context
        scenario_text = '[SCENARIO PLAYBOOK] ' + scenario

        chunks.append(
            Document(
                text=scenario_text,
                metadata={
                    **doc.metadata,
                    "chunk_type": "scenario_playbook",
                    "scenario_index": i
                }
            )
        )

    return chunks if chunks else [doc]


def chunk_structured_document(doc: Document) -> List[Document]:
    """Chunk structured analysis — each row with its header as context"""
    chunks = []
    text = doc.text
    lines = text.split('\n')

    # Find the header line (CATEGORY | DATE | TITLE | ...)
    header = ""
    for line in lines:
        if 'CATEGORY' in line and 'DATE' in line and '|' in line:
            header = line
            break

    # Each data row becomes a chunk with header
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line == header:
            continue
        if line.startswith('#') or line.startswith('='):
            continue

        if '|' in line and 'CATEGORY' not in line:
            # Parse the category and title for better metadata
            parts = [p.strip() for p in line.split('|')]
            category = parts[0] if len(parts) > 0 else "unknown"
            title = parts[2] if len(parts) > 2 else "unknown"

            chunk_text = f"{header}\n{line}"
            chunks.append(
                Document(
                    text=chunk_text,
                    metadata={
                        **doc.metadata,
                        "chunk_type": "structured_row",
                        "category": category,
                        "title": title[:100],
                        "row_index": i
                    }
                )
            )

    return chunks if chunks else [doc]


def chunk_deep_document(doc: Document) -> List[Document]:
    """Chunk deep dive reports — each report (marked by [DATE:]) stays together"""
    chunks = []
    text = doc.text
    # Split on report markers
    reports = text.split('[DATE:')

    for i, report in enumerate(reports):
        report = report.strip()
        if not report or len(report) < 100:
            continue

        # Re-add marker
        report_text = '[DATE: ' + report

        # Extract topic for metadata
        topic = "unknown"
        if '[TOPIC:' in report_text:
            try:
                topic = report_text.split('[TOPIC:')[1].split(']')[0].strip()
            except IndexError:
                pass

        chunks.append(
            Document(
                text=report_text,
                metadata={
                    **doc.metadata,
                    "chunk_type": "deep_dive_report",
                    "topic": topic[:100],
                    "report_index": i
                }
            )
        )

    return chunks if chunks else [doc]


def chunk_quant_document(doc: Document) -> List[Document]:
    """Chunk quantitative data — each TABLE stays together as one chunk"""
    chunks = []
    text = doc.text

    # Split by table headers (lines of ========)
    sections = []
    current_section = []
    current_title = ""

    for line in text.split('\n'):
        if '=' * 20 in line:
            # This is a separator line — could be start or end of a table title
            if current_section:
                # Check if previous section has meaningful content
                content = '\n'.join(current_section)
                if len(content.strip()) > 50 and '|' in content:
                    sections.append((current_title, content))
                current_section = []
                current_title = ""
            continue

        stripped = line.strip()
        if stripped.startswith('TABLE') or stripped.startswith('#'):
            current_title = stripped
            continue

        if stripped:
            current_section.append(line)

    # Save last section
    if current_section:
        content = '\n'.join(current_section)
        if len(content.strip()) > 50:
            sections.append((current_title, content))

    for i, (title, content) in enumerate(sections):
        chunk_text = f"{title}\n{content}" if title else content
        chunks.append(
            Document(
                text=chunk_text,
                metadata={
                    **doc.metadata,
                    "chunk_type": "quant_table",
                    "table_title": title[:100] if title else "unknown",
                    "table_index": i
                }
            )
        )

    return chunks if chunks else [doc]


def chunk_default_document(doc: Document) -> List[Document]:
    """Chunk generic documents — standard approach"""
    parser = SimpleNodeParser.from_defaults(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    nodes = parser.get_nodes_from_documents([doc])

    return [
        Document(
            text=node.text,
            metadata={
                **doc.metadata,
                "chunk_type": "default"
            }
        )
        for node in nodes
    ]


# ============================================
# INITIALIZATION
# ============================================

def initialize_rag(force_reindex: bool = False):
    """Initialize RAG system with optimized chunking and auto-reindex on data change"""
    global _query_engine, _is_initialized, _index

    try:
        logger.info("🚀 Initializing RAG System...")
        logger.info(f"📊 Chunk size: {CHUNK_SIZE}, Overlap: {CHUNK_OVERLAP}, Top-K: {SIMILARITY_TOP_K}")

        Settings.embed_model = setup_embeddings()
        Settings.llm = setup_llm()

        # Determine data directory
        current_dir = Path(__file__).parent
        raw_dir = current_dir.parent.parent / "data" / "raw"

        if not raw_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {raw_dir}")

        # Check if data has changed
        needs_reindex = force_reindex or _data_has_changed(raw_dir)

        if needs_reindex:
            logger.info("📂 Indexing data files...")

            # Clear old vectors and query cache
            vector_store = setup_vector_store(force_clear=True)
            clear_query_cache()

            # Load documents
            raw_documents = SimpleDirectoryReader(str(raw_dir)).load_data()
            logger.info(f"✅ Loaded {len(raw_documents)} documents")

            # Log file names
            file_names = set(doc.metadata.get('file_name', 'unknown') for doc in raw_documents)
            for fn in sorted(file_names):
                logger.info(f"  📄 {fn}")

            # Apply intelligent chunking
            logger.info("🔨 Applying chunking strategies...")
            chunked_documents = chunk_documents_by_type(raw_documents)
            logger.info(f"✅ Created {len(chunked_documents)} chunks from {len(raw_documents)} documents")

            # Log chunk distribution
            chunk_types = {}
            for doc in chunked_documents:
                chunk_type = doc.metadata.get('chunk_type', 'unknown')
                chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
            for ct, count in sorted(chunk_types.items()):
                logger.info(f"  📈 {ct}: {count} chunks")

            # Create index
            logger.info("🔍 Building vector index...")
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            parser = setup_node_parser()

            _index = VectorStoreIndex.from_documents(
                chunked_documents,
                storage_context=storage_context,
                transformations=[parser],
                show_progress=True,
            )

            # Save hash so we skip reindex next time if data unchanged
            _save_data_hash(raw_dir)

        else:
            # Data unchanged — load existing index from ChromaDB
            logger.info("⚡ Loading existing index from ChromaDB...")
            vector_store = setup_vector_store(force_clear=False)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            _index = VectorStoreIndex.from_vector_store(
                vector_store,
                storage_context=storage_context,
            )

        _query_engine = _index.as_query_engine(
            similarity_top_k=SIMILARITY_TOP_K,
            response_mode="compact",
        )

        _is_initialized = True
        logger.info("✅ RAG initialized successfully")

    except Exception as e:
        logger.error(f"❌ RAG initialization failed: {str(e)}")
        raise


# ============================================
# QUERY WITH CACHING
# ============================================

async def query_rag(question: str, max_retries: int = 3) -> Dict[str, Any]:
    """Query RAG with caching and error handling - ASYNC VERSION"""
    global _query_engine, _is_initialized

    if not _is_initialized:
        await asyncio.to_thread(initialize_rag)

    # Check cache first
    cached_result = _get_cached_query(question)
    if cached_result:
        return {**cached_result, "from_cache": True}

    for attempt in range(max_retries):
        try:
            logger.info(f"🔍 Query: {question[:50]}... (Attempt {attempt+1}/{max_retries})")

            # Run query in thread pool
            response = await asyncio.to_thread(_query_engine.query, question)

            # Extract sources
            sources = []
            if hasattr(response, 'source_nodes'):
                for node in response.source_nodes:
                    sources.append({
                        "text": node.node.text[:300],
                        "score": float(node.score) if node.score else 0,
                        "chunk_type": node.node.metadata.get('chunk_type', 'unknown'),
                        "file": node.node.metadata.get('file_name', 'unknown'),
                        "category": node.node.metadata.get('category', ''),
                        "topic": node.node.metadata.get('topic', ''),
                    })

            result = {
                "answer": str(response),
                "sources": sources,
                "success": True,
                "attempts": attempt + 1,
                "from_cache": False
            }

            # Cache the result
            _set_cached_query(question, result)

            return result

        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt+1} failed: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
            else:
                logger.error(f"❌ All {max_retries} attempts failed")
                return {
                    "answer": f"Error: {str(e)}",
                    "sources": [],
                    "success": False,
                    "attempts": attempt + 1,
                    "error": str(e),
                    "from_cache": False
                }


def query_rag_sync(question: str, max_retries: int = 3) -> Dict[str, Any]:
    """Sync version of query_rag (for backward compatibility)"""
    global _query_engine, _is_initialized

    if not _is_initialized:
        initialize_rag()

    # Check cache first
    cached_result = _get_cached_query(question)
    if cached_result:
        return {**cached_result, "from_cache": True}

    for attempt in range(max_retries):
        try:
            logger.info(f"🔍 Query: {question[:50]}... (Attempt {attempt+1}/{max_retries})")
            response = _query_engine.query(question)

            sources = []
            if hasattr(response, 'source_nodes'):
                for node in response.source_nodes:
                    sources.append({
                        "text": node.node.text[:300],
                        "score": float(node.score) if node.score else 0,
                        "chunk_type": node.node.metadata.get('chunk_type', 'unknown'),
                        "file": node.node.metadata.get('file_name', 'unknown'),
                        "category": node.node.metadata.get('category', ''),
                        "topic": node.node.metadata.get('topic', ''),
                    })

            result = {
                "answer": str(response),
                "sources": sources,
                "success": True,
                "attempts": attempt + 1,
                "from_cache": False
            }

            _set_cached_query(question, result)
            return result

        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt+1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                logger.error(f"❌ All {max_retries} attempts failed")
                return {
                    "answer": f"Error: {str(e)}",
                    "sources": [],
                    "success": False,
                    "attempts": attempt + 1,
                    "error": str(e),
                    "from_cache": False
                }


# ============================================
# STATUS & UTILITY
# ============================================

def get_rag_status() -> Dict[str, Any]:
    """Get RAG system status"""
    return {
        "initialized": _is_initialized,
        "collection": "my_collection",
        "db_path": "./chroma_db",
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "similarity_top_k": SIMILARITY_TOP_K,
        "chunk_strategies": [
            "qa_pair",
            "glossary_entry",
            "scenario_playbook",
            "structured_row",
            "deep_dive_report",
            "quant_table",
            "default",
        ],
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "llm_model": "llama-3.3-70b-versatile",
        "cache": get_cache_stats()
    }


def test_chunking():
    """Test chunking strategy with detailed output"""
    current_dir = Path(__file__).parent
    raw_dir = current_dir.parent.parent / "data" / "raw"

    documents = SimpleDirectoryReader(str(raw_dir)).load_data()
    chunked = chunk_documents_by_type(documents)

    chunk_types = {}
    for doc in chunked:
        chunk_type = doc.metadata.get('chunk_type', 'unknown')
        chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

    avg_chunk_size = sum(len(doc.text) for doc in chunked) / len(chunked) if chunked else 0

    print(f"\n📊 Chunking Results:")
    print(f"  Raw documents: {len(documents)}")
    print(f"  Total chunks: {len(chunked)}")
    print(f"  Average chunk size: {avg_chunk_size:.0f} chars")
    print(f"  Chunk size config: {CHUNK_SIZE}")
    print(f"  Chunk overlap config: {CHUNK_OVERLAP}")
    print(f"\n📈 Chunk distribution:")
    for ct, count in sorted(chunk_types.items()):
        print(f"    {ct}: {count}")

    # Show sample from each type
    shown_types = set()
    print(f"\n📝 Sample chunks:")
    for doc in chunked:
        ct = doc.metadata.get('chunk_type', 'unknown')
        if ct not in shown_types:
            shown_types.add(ct)
            print(f"\n  --- {ct} ---")
            print(f"  {doc.text[:200]}...")
            print(f"  Metadata: { {k: v for k, v in doc.metadata.items() if k != 'file_name'} }")

    return chunked


if __name__ == "__main__":
    test_chunking()