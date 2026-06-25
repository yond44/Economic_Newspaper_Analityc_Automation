import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

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

_query_engine = None
_is_initialized = False
_index = None


# ============================================
# SETUP FUNCTIONS
# ============================================

def setup_llm():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables")
    
    return Groq(
        model="llama-3.3-70b-versatile",
        api_key=api_key,
    )


def setup_embeddings():
    return FastEmbedEmbedding(
        model_name="BAAI/bge-small-en-v1.5",
    )


def setup_vector_store():
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_or_create_collection("my_collection")
    return ChromaVectorStore(chroma_collection=collection)


def setup_node_parser():
    return SimpleNodeParser.from_defaults(
        chunk_size=256,
        chunk_overlap=10,
    )


# ============================================
# CHUNKING FUNCTIONS
# ============================================

def chunk_documents_by_type(documents: List[Document]) -> List[Document]:
    chunked_docs = []
    
    for doc in documents:
        file_name = doc.metadata.get('file_name', '').lower()
        
        if 'structured' in file_name:
            chunks = chunk_structured_document(doc)
        elif 'deep' in file_name or 'report' in file_name:
            chunks = chunk_deep_document(doc)
        elif 'quant' in file_name or 'financial' in file_name:
            chunks = chunk_quant_document(doc)
        else:
            chunks = chunk_default_document(doc)
        
        chunked_docs.extend(chunks)
    
    return chunked_docs


def chunk_structured_document(doc: Document) -> List[Document]:
    chunks = []
    text = doc.text
    lines = text.split('\n')
    
    header = ""
    for line in lines:
        if '|' in line:
            header = line
            break
    
    for i, line in enumerate(lines):
        if '|' in line and line != header:
            chunk_text = f"{header}\n{line}"
            chunks.append(
                Document(
                    text=chunk_text,
                    metadata={
                        **doc.metadata,
                        "chunk_type": "structured_row",
                        "row_index": i
                    }
                )
            )
    
    return chunks if chunks else [doc]


def chunk_deep_document(doc: Document) -> List[Document]:
    chunks = []
    text = doc.text
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    chunk_size = 500  
    
    for para in paragraphs:
        if not para.strip():
            continue
        
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append(
                Document(
                    text=current_chunk,
                    metadata={
                        **doc.metadata,
                        "chunk_type": "report_paragraph"
                    }
                )
            )
            current_chunk = current_chunk[-100:] + "\n\n" + para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(
            Document(
                text=current_chunk,
                metadata={
                    **doc.metadata,
                    "chunk_type": "report_paragraph"
                }
            )
        )
    
    return chunks if chunks else [doc]


def chunk_quant_document(doc: Document) -> List[Document]:
    chunks = []
    text = doc.text
    lines = text.split('\n')
    
    current_table = []
    in_table = False
    
    for line in lines:
        if '=' * 10 in line or '|' in line:
            in_table = True
            current_table.append(line)
        else:
            if in_table and current_table:
                table_text = '\n'.join(current_table)
                chunks.append(
                    Document(
                        text=table_text,
                        metadata={
                            **doc.metadata,
                            "chunk_type": "quant_table"
                        }
                    )
                )
                current_table = []
                in_table = False
            elif line.strip():
                chunks.append(
                    Document(
                        text=line,
                        metadata={
                            **doc.metadata,
                            "chunk_type": "quant_text"
                        }
                    )
                )
    
    if current_table:
        table_text = '\n'.join(current_table)
        chunks.append(
            Document(
                text=table_text,
                metadata={
                    **doc.metadata,
                    "chunk_type": "quant_table"
                }
            )
        )
    
    return chunks if chunks else [doc]


def chunk_default_document(doc: Document) -> List[Document]:
    parser = SimpleNodeParser.from_defaults(
        chunk_size=512,
        chunk_overlap=50,
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
# MAIN FUNCTIONS
# ============================================

def initialize_rag(force_reindex: bool = False):
    global _query_engine, _is_initialized, _index
    
    try:
        logger.info("Initializing RAG...")
        
        Settings.embed_model = setup_embeddings()
        Settings.llm = setup_llm()
        
        vector_store = setup_vector_store()
        parser = setup_node_parser()
        
        current_dir = Path(__file__).parent
        raw_dir = current_dir.parent.parent / "data" / "raw"
        
        logger.info(f"Loading documents from: {raw_dir}")
        raw_documents = SimpleDirectoryReader(str(raw_dir)).load_data()
        logger.info(f"Loaded {len(raw_documents)} raw documents")
        
        # ============================================
        # CHUNKING - APPLY TO ALL DOCUMENTS
        # ============================================
        logger.info("Applying chunking strategies...")
        chunked_documents = chunk_documents_by_type(raw_documents)
        logger.info(f"Created {len(chunked_documents)} chunks")
        
        chunk_types = {}
        for doc in chunked_documents:
            chunk_type = doc.metadata.get('chunk_type', 'unknown')
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        logger.info(f"Chunk distribution: {chunk_types}")
        
        logger.info("Creating vector index...")
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        _index = VectorStoreIndex.from_documents(
            chunked_documents, 
            storage_context=storage_context,
            transformations=[parser],
            show_progress=True,
        )
        
        _query_engine = _index.as_query_engine(
            similarity_top_k=5,
            response_mode="compact",
        )
        
        _is_initialized = True
        logger.info("RAG initialized successfully with chunking")
        
    except Exception as e:
        logger.error(f"RAG initialization failed: {str(e)}")
        raise


def query_rag(question: str, max_retries: int = 3) -> Dict[str, Any]:
    global _query_engine, _is_initialized
    
    if not _is_initialized:
        initialize_rag()
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Query: {question[:50]}...")
            response = _query_engine.query(question)
            
            sources = []
            if hasattr(response, 'source_nodes'):
                for node in response.source_nodes:
                    sources.append({
                        "text": node.node.text[:200],
                        "score": node.score,
                        "chunk_type": node.node.metadata.get('chunk_type', 'unknown'),
                        "file": node.node.metadata.get('file_name', 'unknown')
                    })
            
            return {
                "answer": str(response),
                "sources": sources,
                "success": True,
                "attempts": attempt + 1
            }
            
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                logger.error(f"All {max_retries} attempts failed")
                return {
                    "answer": f"Error: {str(e)}",
                    "sources": [],
                    "success": False,
                    "attempts": attempt + 1,
                    "error": str(e)
                }


def get_rag_status() -> Dict[str, Any]:
    return {
        "initialized": _is_initialized,
        "collection": "my_collection",
        "db_path": "./chroma_db",
        "chunk_size": 256,
        "chunk_overlap": 10,
        "chunk_strategies": ["structured", "deep_report", "quantitative", "default"],
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "llm_model": "llama-3.3-70b-versatile"
    }


# ============================================
# TEST CHUNKING (for debugging)
# ============================================

def test_chunking():
    current_dir = Path(__file__).parent
    raw_dir = current_dir.parent.parent / "data" / "raw"
    
    documents = SimpleDirectoryReader(str(raw_dir)).load_data()
    chunked = chunk_documents_by_type(documents)
    
    print(f"\nChunking Results:")
    print(f"  Raw documents: {len(documents)}")
    print(f"  Chunks created: {len(chunked)}")
    
    chunk_types = {}
    for doc in chunked:
        chunk_type = doc.metadata.get('chunk_type', 'unknown')
        chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
    
    print(f"  Chunk distribution: {chunk_types}")
    print(f"  Average chunk size: {sum(len(doc.text) for doc in chunked) / len(chunked):.0f} chars")
    
    return chunked

if __name__ == "__main__":
    test_chunking()