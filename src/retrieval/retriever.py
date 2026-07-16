"""
Retriever module for the Mutual Fund FAQ Assistant.

This module implements Phase 7 of the implementation plan:
- Embeds user queries using BGE-small with instruction prefix
- Performs similarity search via ChromaDB (L2 distance)
- Converts L2 distance to cosine similarity: sim = 1 - (dist / 2)
- Filters results by SIMILARITY_THRESHOLD (0.55, empirically calibrated)
- Optionally reranks via cross-encoder (placeholder, default OFF)

Distance Metric Note:
    ChromaDB uses L2 (squared Euclidean) distance by default.
    Our embeddings are normalized (norm = 1.0), so:
        cosine_similarity = 1 - (L2_distance / 2)
    This is NOT the same as `1 - distance`.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.ingestion.embedder import embed_query
from src.ingestion.vectorstore import query_vectorstore, init_vectorstore
from src.retrieval.reranker import rerank

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config constants (calibrated from empirical testing — see Phase 7.2/7.3)
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.55   # Cosine sim floor (empirically calibrated)
DEFAULT_TOP_K = 5             # Chunks to retrieve from ChromaDB before filtering
RERANKER_ENABLED = False      # Toggle cross-encoder reranking
RERANKER_TOP_K = 3            # Chunks to return after reranking


def _l2_to_cosine_similarity(l2_distance: float) -> float:
    """
    Convert ChromaDB's L2 (squared Euclidean) distance to cosine similarity.

    For normalized embeddings (norm = 1.0):
        L2_distance = 2 * (1 - cosine_similarity)
        => cosine_similarity = 1 - (L2_distance / 2)

    Args:
        l2_distance: The L2 distance from ChromaDB query results.

    Returns:
        Cosine similarity in the range [-1, 1]. For normalized embeddings,
        typical values are [0, 1] for relevant results and can go slightly
        negative for very dissimilar content.
    """
    return 1.0 - (l2_distance / 2.0)


def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    scheme_name: Optional[str] = None,
) -> list[dict]:
    """
    Search the vector store for chunks relevant to the user query.

    Full retrieval flow:
        1. Embed the query (BGE-small, instruction-prefixed)
        2. Query ChromaDB for top_k results (L2 distance)
        3. Convert L2 distance → cosine similarity
        4. Filter by SIMILARITY_THRESHOLD
        5. Optionally rerank (default OFF)
        6. Return chunks with similarity scores and metadata

    Args:
        query: The user's search query string.
        top_k: Number of chunks to retrieve from ChromaDB before filtering.
               Defaults to DEFAULT_TOP_K (5).
        scheme_name: Optional scheme name to filter results (e.g., "HDFC Large Cap Fund").
                     If provided, only chunks from this scheme are returned.

    Returns:
        A list of chunk dicts, each containing:
            - chunk_id: Unique identifier
            - text: Chunk content
            - similarity: Cosine similarity score (float)
            - scheme_name: Source scheme name
            - source_url: Source URL
            - category: Fund category
            - chunk_type: Type of chunk (faq, structured_facts, section)
            - section_heading: Section heading (if applicable)
        Sorted by similarity (descending). Empty list if no results pass
        the similarity threshold.
    """
    if not query or not query.strip():
        logger.warning("Empty query provided to search()")
        return []

    # Step 1: Embed the query (with BGE instruction prefix)
    logger.info("Embedding query: '%s'", query[:80])
    query_embedding = embed_query(query)

    # Step 2: Build metadata filters
    filters = None
    if scheme_name:
        filters = {"scheme_name": scheme_name}
        logger.info("Applying scheme_name filter: '%s'", scheme_name)

    # Step 3: Query ChromaDB (returns L2 distances)
    raw_results = query_vectorstore(
        query_embedding=query_embedding,
        top_k=top_k,
        filters=filters,
    )

    if not raw_results:
        logger.info("No results returned from vector store")
        return []

    # Step 4: Convert L2 distance → cosine similarity
    for chunk in raw_results:
        l2_dist = chunk.get("distance")
        if l2_dist is not None:
            chunk["similarity"] = _l2_to_cosine_similarity(l2_dist)
        else:
            chunk["similarity"] = 0.0

    # Step 5: Filter by similarity threshold
    filtered = [
        chunk for chunk in raw_results
        if chunk["similarity"] >= SIMILARITY_THRESHOLD
    ]

    logger.info(
        "Similarity filtering: %d/%d chunks passed threshold (%.2f)",
        len(filtered), len(raw_results), SIMILARITY_THRESHOLD,
    )

    if not filtered:
        logger.info("No chunks passed similarity threshold of %.2f", SIMILARITY_THRESHOLD)
        return []

    # Sort by similarity descending (highest first)
    filtered.sort(key=lambda c: c["similarity"], reverse=True)

    # Step 6: Optionally rerank
    if RERANKER_ENABLED:
        logger.info("Reranker enabled — reranking %d chunks", len(filtered))
        filtered = rerank(query=query, chunks=filtered, top_k=RERANKER_TOP_K)
    else:
        # Without reranker, still cap at RERANKER_TOP_K
        filtered = filtered[:RERANKER_TOP_K]

    # Clean up internal fields before returning
    for chunk in filtered:
        chunk.pop("distance", None)

    logger.info(
        "Returning %d chunks (top similarity: %.4f)",
        len(filtered),
        filtered[0]["similarity"] if filtered else 0.0,
    )

    return filtered


if __name__ == "__main__":
    # Quick manual test
    test_queries = [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "exit load HDFC Small Cap",
        "minimum SIP amount",
        "What is the weather today?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"Query: \"{q}\"")
        print(f"{'='*70}")
        results = search(q)
        if results:
            for i, r in enumerate(results):
                print(f"  [{i+1}] sim={r['similarity']:.4f} | {r['chunk_type']:20s} | {r['scheme_name']}")
                print(f"       {r['text'][:100]}...")
        else:
            print("  No results (below similarity threshold)")
