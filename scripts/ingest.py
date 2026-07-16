"""
Ingestion pipeline runner.

Usage:
    python scripts/ingest.py              # Run all phases
    python scripts/ingest.py --full       # Run all phases (explicit flag, used by GitHub Actions)
    python scripts/ingest.py --scrape     # Run scraping only (Phase 1)
    python scripts/ingest.py --parse      # Run parsing only (Phase 2)
    python scripts/ingest.py --chunk      # Run chunking only (Phase 3)
    python scripts/ingest.py --embed      # Run embedding only (Phase 4)
"""

import argparse
import sys
import os

# Add project root to Python path so we can import src.*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.scraper import scrape_all
from src.ingestion.parser import parse_all
from src.ingestion.chunker import chunk_all
from src.ingestion.embedder import embed_all
from src.ingestion.vectorstore import build_vectorstore


def run_scraping():
    """Phase 1 — Scrape raw HTML from Groww scheme pages."""
    print("=" * 60)
    print("Phase 1: SCRAPING")
    print("=" * 60)

    results = scrape_all()

    # Print summary table
    print("\n" + "-" * 60)
    print(f"{'Scheme Slug':<55} {'Status'}")
    print("-" * 60)
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        size = f"({r['content_length']:,} chars)" if r["status"] == "success" else f"({r['error']})"
        print(f"{r['slug']:<55} {status_icon} {size}")
    print("-" * 60)

    success = sum(1 for r in results if r["status"] == "success")
    print(f"\nResult: {success}/{len(results)} pages scraped successfully.\n")

    return results


def run_parsing():
    """Phase 2 — Parse raw HTML into clean text + metadata."""
    print("=" * 60)
    print("Phase 2: PARSING")
    print("=" * 60)

    results = parse_all()

    # Print summary table
    print("\n" + "-" * 60)
    print(f"{'Scheme Slug':<55} {'Status'}")
    print("-" * 60)
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        detail = "" if r["status"] == "success" else f"({r['error']})"
        print(f"{r['slug']:<55} {status_icon} {detail}")
    print("-" * 60)

    success = sum(1 for r in results if r["status"] == "success")
    print(f"\nResult: {success}/{len(results)} files parsed successfully.\n")

    return results


def run_chunking():
    """Phase 3 — Chunk parsed data into semantic chunks for RAG."""
    print("=" * 60)
    print("Phase 3: CHUNKING")
    print("=" * 60)

    results = chunk_all()

    # Print summary table
    print("\n" + "-" * 60)
    print(f"{'Scheme Slug':<55} {'Chunks'}")
    print("-" * 60)
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        detail = f"({r['chunk_count']} chunks)" if r["status"] == "success" else f"({r['error']})"
        print(f"{r['slug']:<55} {status_icon} {detail}")
    print("-" * 60)

    total_chunks = sum(r["chunk_count"] for r in results)
    success = sum(1 for r in results if r["status"] == "success")
    print(f"\nResult: {success}/{len(results)} schemes chunked, {total_chunks} total chunks.\n")

    return results


def run_embedding():
    """Phase 4 — Generate embeddings for all chunks."""
    print("=" * 60)
    print("Phase 4: EMBEDDING")
    print("=" * 60)

    results = embed_all()

    if results:
        with_embeddings = sum(1 for c in results if "embedding" in c)
        dim = len(results[0]["embedding"]) if results[0].get("embedding") else 0
        print(f"\nResult: {with_embeddings}/{len(results)} chunks embedded.")
        print(f"Embedding dimension: {dim}")
        print(f"Model: BAAI/bge-small-en-v1.5\n")
    else:
        print("\nNo chunks were embedded.\n")

    return results


def run_vectorstore():
    """Phase 5 — Store chunks in ChromaDB vector database."""
    print("=" * 60)
    print("Phase 5: VECTOR DB STORAGE")
    print("=" * 60)

    try:
        build_vectorstore()
        print("\nResult: Successfully stored chunks in Vector DB.\n")
    except Exception as e:
        print(f"\nError building vector store: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="Mutual Fund FAQ Assistant — Ingestion Pipeline")
    parser.add_argument("--scrape", action="store_true", help="Run scraping only (Phase 1)")
    parser.add_argument("--parse", action="store_true", help="Run parsing only (Phase 2)")
    parser.add_argument("--chunk", action="store_true", help="Run chunking only (Phase 3)")
    parser.add_argument("--embed", action="store_true", help="Run embedding only (Phase 4)")
    parser.add_argument("--vectorstore", action="store_true", help="Run vector DB storage only (Phase 5)")
    parser.add_argument("--full", action="store_true", help="Run all phases sequentially (same as no flags)")
    args = parser.parse_args()

    if args.scrape:
        run_scraping()
    elif args.parse:
        run_parsing()
    elif args.chunk:
        run_chunking()
    elif args.embed:
        run_embedding()
    elif args.vectorstore:
        run_vectorstore()
    else:
        # Default (no flags) or --full: run all available phases sequentially
        run_scraping()
        run_parsing()
        run_chunking()
        run_embedding()
        run_vectorstore()
        # Future phases will be added here:


if __name__ == "__main__":
    main()
