"""
Unit tests for the vectorstore module.

Tests cover:
- ChromaDB collection is created and persisted
- Chunks are properly stored with their metadata
- Queries return top-K results
- Metadata filters successfully narrow down search results
- Similarity queries work as expected
"""

import os
import sys
import pytest
import shutil
from typing import Generator

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion import vectorstore
from src.ingestion.embedder import embed_query

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_vectorstore():
    """Reset the global collection before and after each test."""
    vectorstore._collection = None
    yield
    vectorstore._collection = None

@pytest.fixture
def temp_persist_dir(tmp_path) -> str:
    """Provides a temporary directory for ChromaDB persistence."""
    return str(tmp_path / "chromadb_test")

@pytest.fixture
def mock_embedded_chunks():
    """Returns a small list of mock chunks with precomputed embeddings."""
    return [
        {
            "chunk_id": "hdfc-large-cap_structured_facts_0",
            "text": "Expense Ratio is 1.04%. NAV is 1200.",
            "embedding": [0.1] * 384,
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "chunk_type": "structured_facts",
            "source_url": "https://example.com/1"
        },
        {
            "chunk_id": "hdfc-large-cap_faq_0",
            "text": "Q: What is the exit load?\nA: Exit load is 1%.",
            "embedding": [0.2] * 384,
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "chunk_type": "faq",
            "source_url": "https://example.com/1"
        },
        {
            "chunk_id": "hdfc-mid-cap_structured_facts_0",
            "text": "Expense Ratio is 0.8%. NAV is 2500.",
            "embedding": [0.3] * 384,
            "scheme_name": "HDFC Mid Cap Fund",
            "category": "Equity",
            "chunk_type": "structured_facts",
            "source_url": "https://example.com/2"
        },
    ]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_init_vectorstore(temp_persist_dir):
    """Test ChromaDB collection is created and persisted."""
    collection = vectorstore.init_vectorstore(persist_dir=temp_persist_dir)
    assert collection is not None
    assert collection.name == vectorstore.COLLECTION_NAME
    assert os.path.exists(temp_persist_dir)

def test_store_chunks(temp_persist_dir, mock_embedded_chunks):
    """Test that chunks are successfully indexed in the collection."""
    vectorstore.init_vectorstore(persist_dir=temp_persist_dir)
    vectorstore.store_chunks(mock_embedded_chunks)
    
    collection = vectorstore._collection
    assert collection.count() == len(mock_embedded_chunks)
    
    # Retrieve one document to check metadata
    result = collection.get(ids=["hdfc-large-cap_structured_facts_0"])
    assert result["documents"][0] == "Expense Ratio is 1.04%. NAV is 1200."
    assert result["metadatas"][0]["scheme_name"] == "HDFC Large Cap Fund"

def test_query_returns_top_k(temp_persist_dir, mock_embedded_chunks):
    """Test query returns top-K results with metadata."""
    vectorstore.init_vectorstore(persist_dir=temp_persist_dir)
    vectorstore.store_chunks(mock_embedded_chunks)
    
    # Query with a dummy embedding
    dummy_query = [0.15] * 384
    results = vectorstore.query_vectorstore(query_embedding=dummy_query, top_k=2)
    
    assert len(results) == 2
    assert "chunk_id" in results[0]
    assert "text" in results[0]
    assert "scheme_name" in results[0]
    assert "distance" in results[0]

def test_metadata_filters_chunk_type(temp_persist_dir, mock_embedded_chunks):
    """Test metadata filters (chunk_type) narrow results correctly."""
    vectorstore.init_vectorstore(persist_dir=temp_persist_dir)
    vectorstore.store_chunks(mock_embedded_chunks)
    
    dummy_query = [0.2] * 384
    
    # Filter by faq chunk type
    results = vectorstore.query_vectorstore(
        query_embedding=dummy_query, 
        top_k=5, 
        filters={"chunk_type": "faq"}
    )
    
    assert len(results) == 1
    assert results[0]["chunk_id"] == "hdfc-large-cap_faq_0"

def test_metadata_filters_scheme_name(temp_persist_dir, mock_embedded_chunks):
    """Test scheme-specific query returns chunks from that scheme only."""
    vectorstore.init_vectorstore(persist_dir=temp_persist_dir)
    vectorstore.store_chunks(mock_embedded_chunks)
    
    dummy_query = [0.2] * 384
    
    # Filter by scheme name
    results = vectorstore.query_vectorstore(
        query_embedding=dummy_query, 
        top_k=5, 
        filters={"scheme_name": "HDFC Mid Cap Fund"}
    )
    
    assert len(results) == 1
    assert results[0]["chunk_id"] == "hdfc-mid-cap_structured_facts_0"

def test_similarity_query():
    """Test a similarity query for 'expense ratio' returns relevant chunks."""
    # We test this using an ephemeral in-memory client for speed, 
    # but we generate real embeddings to test similarity.
    import chromadb
    client = chromadb.EphemeralClient()
    collection = client.create_collection("test_sim")
    
    # Temporarily replace the global collection with our ephemeral one
    vectorstore._collection = collection
    
    from src.ingestion.embedder import embed_chunks
    
    # 3 mock texts
    chunks = [
        {"chunk_id": "c1", "text": "The expense ratio is 1.2%.", "chunk_type": "faq"},
        {"chunk_id": "c2", "text": "Minimum SIP amount is ₹500.", "chunk_type": "faq"},
        {"chunk_id": "c3", "text": "NAV stands for Net Asset Value.", "chunk_type": "faq"}
    ]
    
    embedded_chunks = embed_chunks(chunks)
    vectorstore.store_chunks(embedded_chunks)
    
    query_emb = embed_query("What is the expense ratio?")
    results = vectorstore.query_vectorstore(query_emb, top_k=1)
    
    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"
