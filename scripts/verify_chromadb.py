"""
ChromaDB Verification Script

Connects to the local ChromaDB vector store and retrieves stored embeddings
to verify that Phase 6 (Vector DB Storage) was completed successfully.

Usage:
    python3 scripts/verify_chromadb.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.vectorstore import init_vectorstore

def main():
    print("=" * 70)
    print("  CHROMADB VECTOR STORE VERIFICATION")
    print("=" * 70)

    try:
        collection = init_vectorstore()
    except Exception as e:
        print(f"❌ Failed to connect to ChromaDB: {e}")
        return

    # Get total count
    count = collection.count()
    print(f"\n📂 Total chunks in Vector DB: {count}\n")

    if count == 0:
        print("❌ Database is empty. Run `python3 scripts/ingest.py --vectorstore` to populate.")
        return

    # Fetch a few items to verify embeddings are stored
    print("Fetching sample records from the database...")
    results = collection.get(include=["embeddings", "metadatas", "documents"], limit=5)

    if not results or not results['ids']:
        print("❌ Could not retrieve records.")
        return

    print("─" * 70)
    print(f"{'#':<4} {'Chunk ID':<40} {'Dim':>4} {'Type'}")
    print("─" * 70)

    for i, (doc_id, emb, meta) in enumerate(zip(results['ids'], results['embeddings'], results['metadatas'])):
        dim = len(emb) if emb is not None else 0
        chunk_type = meta.get('chunk_type', 'unknown') if meta else 'unknown'
        emb_preview = str(emb[:5]) + "..." if emb is not None else "None"
        print(f"{i+1:<4} {doc_id:<40} {dim:>4} {chunk_type}")
        print(f"     Embedding preview: {emb_preview}")

    print("─" * 70)
    
    # Verify dimensions for all fetched samples
    dim_ok = all(len(emb) == 384 for emb in results['embeddings'] if emb is not None)
    if dim_ok:
        print("\n✅ Verified: Sample embeddings have correct dimensions (384).")
    else:
        print("\n❌ Error: Some embeddings have incorrect dimensions.")

    print(f"\nTo see full similarity test, you can also run: python3 scripts/verify_embeddings.py")
    print("=" * 70)

if __name__ == "__main__":
    main()
