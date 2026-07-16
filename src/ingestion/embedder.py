"""
Embedder module for generating vector embeddings from chunked mutual fund data.

This module handles Phase 4 of the data ingestion pipeline (Phase 5 in the implementation plan):
- Loads all chunked JSONL files from data/chunks/
- Generates 384-dimensional embeddings using BAAI/bge-small-en-v1.5
- Supports instruction-prefixed query embedding for improved retrieval
- Processes chunks in batches for efficiency

Embedding Model: BAAI/bge-small-en-v1.5
  - Dimensions: 384
  - Context window: 512 tokens
  - Size: ~130 MB
  - Strategy: No prefix for documents, instruction prefix for queries
"""

from __future__ import annotations

import os
import json
import glob
import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CHUNKS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chunks")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
QUERY_INSTRUCTION_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_BATCH_SIZE = 32

# ---------------------------------------------------------------------------
# Module-level model cache (lazy-loaded)
# ---------------------------------------------------------------------------
_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """
    Lazy-load the sentence-transformer model.

    Uses module-level caching to avoid re-loading the model on every call.
    The first call downloads the model (~130 MB) if not already cached.

    Returns:
        The loaded SentenceTransformer model.
    """
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Model loaded. Embedding dimension: %d", EMBEDDING_DIM)
    return _model


def load_all_chunks() -> list[dict]:
    """
    Load all chunks from per-scheme JSONL files in data/chunks/.

    Reads every *.jsonl file in the chunks directory, parsing each line
    as a JSON object. Files are processed in sorted order for determinism.

    Returns:
        A flat list of chunk dicts from all scheme files.
    """
    chunks_dir = os.path.normpath(CHUNKS_DATA_DIR)
    jsonl_pattern = os.path.join(chunks_dir, "*.jsonl")
    jsonl_files = sorted(glob.glob(jsonl_pattern))

    if not jsonl_files:
        logger.warning("No JSONL files found in %s", chunks_dir)
        return []

    all_chunks = []
    for filepath in jsonl_files:
        filename = os.path.basename(filepath)
        file_chunks = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        file_chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Skipping invalid JSON in %s line %d: %s",
                            filename, line_num, e,
                        )
            all_chunks.extend(file_chunks)
            logger.info("Loaded %d chunks from %s", len(file_chunks), filename)
        except Exception as e:
            logger.error("Failed to read %s: %s", filename, e)

    logger.info("Total chunks loaded: %d from %d files", len(all_chunks), len(jsonl_files))
    return all_chunks


def embed_chunks(chunks: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict]:
    """
    Generate embeddings for a list of chunks.

    Embeds the 'text' field of each chunk using the BGE-small model.
    Documents are embedded WITHOUT an instruction prefix (as per BGE best practices).
    Processes in batches for memory efficiency.

    Args:
        chunks: List of chunk dicts, each must have a 'text' field.
        batch_size: Number of chunks to embed per batch.

    Returns:
        The same list of chunk dicts, each with an 'embedding' field added
        (a list of 384 floats).
    """
    if not chunks:
        logger.warning("No chunks to embed")
        return chunks

    model = _get_model()

    # Extract texts for embedding
    texts = [chunk.get("text", "") for chunk in chunks]

    logger.info(
        "Embedding %d chunks in batches of %d...",
        len(texts), batch_size,
    )

    # Embed in batches — SentenceTransformer handles batching internally,
    # but we pass batch_size to control memory usage
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    # Attach embeddings to chunks
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding.tolist()

    logger.info(
        "Embedded %d chunks. Embedding dimension: %d",
        len(chunks),
        len(chunks[0]["embedding"]) if chunks else 0,
    )

    return chunks


def embed_query(query: str) -> list[float]:
    """
    Generate an embedding for a user query with instruction prefix.

    BGE models achieve better retrieval accuracy when queries are prefixed
    with a task instruction. Documents should NOT be prefixed.

    The prefix used: "Represent this sentence for searching relevant passages: "

    Args:
        query: The user's search query string.

    Returns:
        A list of 384 floats representing the query embedding.
    """
    model = _get_model()

    # Prepend instruction prefix for query embedding
    prefixed_query = QUERY_INSTRUCTION_PREFIX + query

    embedding = model.encode(
        prefixed_query,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def embed_all() -> list[dict]:
    """
    Load all chunks and generate embeddings for each.

    Orchestrator function that:
    1. Reads all per-scheme JSONL files from data/chunks/
    2. Embeds all chunk texts using BGE-small
    3. Returns the chunks with embeddings attached

    Returns:
        A list of chunk dicts, each with an 'embedding' field (list of 384 floats).
    """
    chunks = load_all_chunks()
    if not chunks:
        logger.warning("No chunks to process")
        return []

    embedded_chunks = embed_chunks(chunks)

    # Verification
    total = len(embedded_chunks)
    with_embeddings = sum(1 for c in embedded_chunks if "embedding" in c)
    dim_check = all(
        len(c.get("embedding", [])) == EMBEDDING_DIM
        for c in embedded_chunks
    )

    logger.info(
        "Embedding complete: %d/%d chunks have embeddings, dimension check: %s",
        with_embeddings, total, "PASS" if dim_check else "FAIL",
    )

    if not dim_check:
        logger.error(
            "Dimension mismatch detected! Expected %d, check individual chunks.",
            EMBEDDING_DIM,
        )

    return embedded_chunks


if __name__ == "__main__":
    results = embed_all()
    if results:
        print(f"\nEmbedded {len(results)} chunks successfully.")
        print(f"Embedding dimension: {len(results[0]['embedding'])}")
        # Show a sample
        sample = results[0]
        print(f"\nSample chunk: {sample['chunk_id']}")
        print(f"  Text (first 100 chars): {sample['text'][:100]}...")
        print(f"  Embedding (first 5 dims): {sample['embedding'][:5]}")
    else:
        print("No chunks were embedded.")
