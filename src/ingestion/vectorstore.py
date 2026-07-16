"""
Vector DB Storage module for the Mutual Fund FAQ Assistant.

This module handles Phase 5 of the data ingestion pipeline (Phase 6 in the implementation plan):
- Initializes a ChromaDB persistent client at `vectorstore/`
- Stores chunks and their embeddings into the `mutual_fund_faq` collection
- Provides a querying interface with optional metadata filters
"""

import os
import logging
import chromadb
from typing import Optional, Any
from src.ingestion.embedder import embed_all

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Paths
DEFAULT_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "vectorstore")
COLLECTION_NAME = "mutual_fund_faq"

_collection = None

def init_vectorstore(persist_dir: str = DEFAULT_PERSIST_DIR) -> chromadb.Collection:
    """
    Initializes a ChromaDB persistent client and retrieves or creates the collection.
    
    Args:
        persist_dir: Path to the directory where ChromaDB will store its data.
        
    Returns:
        The ChromaDB collection instance.
    """
    global _collection
    
    # Ensure the directory exists
    os.makedirs(persist_dir, exist_ok=True)
    
    logger.info(f"Initializing ChromaDB persistent client at {persist_dir}")
    client = chromadb.PersistentClient(path=persist_dir)
    
    _collection = client.get_or_create_collection(name=COLLECTION_NAME)
    logger.info(f"Connected to collection: {COLLECTION_NAME}")
    
    return _collection

def store_chunks(chunks_with_embeddings: list[dict]) -> None:
    """
    Stores chunks and their embeddings in ChromaDB.
    
    Args:
        chunks_with_embeddings: List of chunk dictionaries containing 'embedding', 
                                'text', 'chunk_id', and metadata fields.
    """
    if not chunks_with_embeddings:
        logger.warning("No chunks to store.")
        return

    collection = _collection if _collection is not None else init_vectorstore()
    
    ids = []
    embeddings = []
    metadatas = []
    documents = []
    
    for chunk in chunks_with_embeddings:
        ids.append(chunk["chunk_id"])
        embeddings.append(chunk["embedding"])
        documents.append(chunk.get("text", ""))
        
        # Build metadata, filtering out None values as ChromaDB does not allow them
        metadata = {
            "source_url": chunk.get("source_url", ""),
            "scheme_name": chunk.get("scheme_name", ""),
            "category": chunk.get("category", ""),
            "chunk_type": chunk.get("chunk_type", ""),
        }
        
        if "section_heading" in chunk and chunk["section_heading"] is not None:
            metadata["section_heading"] = chunk["section_heading"]
            
        metadatas.append(metadata)
        
    logger.info(f"Upserting {len(ids)} chunks to ChromaDB...")
    
    # We can batch upserts if the list is very large, but 55 chunks is small enough to upsert at once.
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents
    )
    
    logger.info(f"Successfully stored {len(ids)} chunks in ChromaDB.")

def query_vectorstore(query_embedding: list[float], top_k: int = 5, filters: Optional[dict[str, Any]] = None) -> list[dict]:
    """
    Queries ChromaDB for the most similar chunks to the query embedding.
    
    Args:
        query_embedding: The embedding of the search query (list of floats).
        top_k: Number of results to return.
        filters: Optional dictionary of metadata filters (e.g. {"chunk_type": "faq"}).
        
    Returns:
        A list of dictionaries representing the retrieved chunks, including similarity scores.
    """
    collection = _collection if _collection is not None else init_vectorstore()
    
    logger.info(f"Querying vector store for top {top_k} results. Filters: {filters}")
    
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
    }
    
    if filters:
        # If there are multiple filters, ChromaDB syntax uses "$and"
        if len(filters) > 1:
            kwargs["where"] = {"$and": [{k: v} for k, v in filters.items()]}
        else:
            kwargs["where"] = filters
            
    results = collection.query(**kwargs)
    
    # Process results into a list of dicts
    retrieved_chunks = []
    
    if not results or not results['ids'] or not results['ids'][0]:
        return retrieved_chunks
        
    # results is a dict where values are lists of lists (since we queried with a batch of 1)
    for i in range(len(results['ids'][0])):
        chunk = {
            "chunk_id": results['ids'][0][i],
            "text": results['documents'][0][i],
            "distance": results['distances'][0][i] if 'distances' in results and results['distances'] else None,
        }
        if results['metadatas'] and results['metadatas'][0]:
            chunk.update(results['metadatas'][0][i])
        
        retrieved_chunks.append(chunk)
        
    return retrieved_chunks

def build_vectorstore() -> None:
    """
    Orchestrator function that:
    1. Loads and embeds all chunks (via embedder.embed_all())
    2. Stores them in ChromaDB
    """
    logger.info("Building vector store...")
    chunks_with_embeddings = embed_all()
    
    if chunks_with_embeddings:
        store_chunks(chunks_with_embeddings)
    else:
        logger.error("Failed to build vector store: No chunks were embedded.")

if __name__ == "__main__":
    build_vectorstore()
