"""
Pipeline Retriever for the Mutual Fund FAQ Assistant.

Thin wrapper that delegates to src/retrieval/retriever.py (Phase 7).
Provides a clean interface for the generation pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.retrieval.retriever import search

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    top_k: int = 5,
    scheme_name: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve relevant chunks for a user query.

    Delegates to src/retrieval/retriever.search() which handles:
        - Query embedding (BGE-small, instruction-prefixed)
        - ChromaDB L2 similarity search
        - L2 → cosine similarity conversion
        - Similarity threshold filtering (0.55)
        - Optional reranking (default OFF)
        - Returns top-3 chunks

    Args:
        query: The user's search query string.
        top_k: Number of chunks to retrieve from ChromaDB before filtering.
        scheme_name: Optional scheme name to filter results.

    Returns:
        A list of chunk dicts, each containing:
            - chunk_id: Unique identifier
            - text: Chunk content
            - similarity: Cosine similarity score
            - scheme_name: Source scheme name
            - source_url: Source URL
            - category: Fund category
            - chunk_type: Type of chunk
        Empty list if no relevant results found.
    """
    logger.info("Pipeline retriever: querying for '%s'", query[:80])

    results = search(
        query=query,
        top_k=top_k,
        scheme_name=scheme_name,
    )

    logger.info(
        "Pipeline retriever: %d chunks retrieved",
        len(results),
    )

    return results
