"""
Reranker module for the Mutual Fund FAQ Assistant.

This module provides an optional cross-encoder reranking step for retrieval results.

Current implementation: PASSTHROUGH PLACEHOLDER
    - Sorts chunks by existing similarity score and returns top_k.
    - No external model is loaded.

Future implementation (commented out below):
    - Uses a cross-encoder model (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2)
    - Scores each (query, chunk.text) pair independently
    - Re-sorts by cross-encoder score and returns top_k

Toggled via RERANKER_ENABLED in retriever.py config (default: False).
"""

from __future__ import annotations

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def rerank(query: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    """
    Rerank retrieved chunks by relevance to the query.

    CURRENT IMPLEMENTATION (Passthrough):
        Returns the top_k chunks sorted by existing similarity score.
        No additional model inference is performed.

    FUTURE IMPLEMENTATION (Cross-Encoder):
        Will score each (query, chunk.text) pair using a cross-encoder model,
        re-sort by the new scores, and return top_k.

    Args:
        query: The user's search query string.
        chunks: List of chunk dicts, each must have a 'similarity' field.
        top_k: Number of top chunks to return after reranking.

    Returns:
        A list of the top_k chunks, sorted by relevance (descending).
    """
    if not chunks:
        return []

    logger.info(
        "Reranking %d chunks (passthrough mode) — returning top %d by similarity",
        len(chunks), top_k,
    )

    # --- PASSTHROUGH: Sort by existing similarity score ---
    sorted_chunks = sorted(chunks, key=lambda c: c.get("similarity", 0.0), reverse=True)
    reranked = sorted_chunks[:top_k]

    # -------------------------------------------------------------------------
    # FUTURE: Cross-Encoder Reranking
    # -------------------------------------------------------------------------
    # To activate cross-encoder reranking:
    #   1. Install: pip install sentence-transformers
    #   2. Uncomment the code below
    #   3. Set RERANKER_ENABLED = True in retriever.py
    #
    # from sentence_transformers import CrossEncoder
    #
    # _cross_encoder = None
    #
    # def _get_cross_encoder():
    #     global _cross_encoder
    #     if _cross_encoder is None:
    #         _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    #     return _cross_encoder
    #
    # model = _get_cross_encoder()
    #
    # # Score each (query, chunk.text) pair
    # pairs = [(query, chunk["text"]) for chunk in chunks]
    # scores = model.predict(pairs)
    #
    # # Attach cross-encoder scores and re-sort
    # for chunk, score in zip(chunks, scores):
    #     chunk["cross_encoder_score"] = float(score)
    #
    # sorted_chunks = sorted(chunks, key=lambda c: c["cross_encoder_score"], reverse=True)
    # reranked = sorted_chunks[:top_k]
    #
    # logger.info(
    #     "Cross-encoder reranking complete: top score=%.4f, bottom score=%.4f",
    #     reranked[0]["cross_encoder_score"] if reranked else 0,
    #     reranked[-1]["cross_encoder_score"] if reranked else 0,
    # )
    # -------------------------------------------------------------------------

    return reranked
