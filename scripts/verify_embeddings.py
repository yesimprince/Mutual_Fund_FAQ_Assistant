"""
Embedding Verification Script

Loads all chunks, generates embeddings, and displays a comprehensive
verification report including dimensions, norms, similarity checks,
and a sample query test.

Usage:
    python scripts/verify_embeddings.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.embedder import (
    load_all_chunks,
    embed_chunks,
    embed_query,
    EMBEDDING_DIM,
    MODEL_NAME,
)


def cosine_sim(a, b):
    """Dot product of two L2-normalised vectors = cosine similarity."""
    return sum(x * y for x, y in zip(a, b))


def l2_norm(vec):
    return sum(v ** 2 for v in vec) ** 0.5


def main():
    # ── 1. Load chunks ──────────────────────────────────────────────────
    print("=" * 70)
    print("  EMBEDDING VERIFICATION REPORT")
    print("=" * 70)

    chunks = load_all_chunks()
    print(f"\n📂 Loaded {len(chunks)} chunks from data/chunks/\n")

    if not chunks:
        print("❌ No chunks found. Run `python scripts/ingest.py --chunk` first.")
        return

    # ── 2. Generate embeddings ──────────────────────────────────────────
    print(f"🔧 Model: {MODEL_NAME}")
    print(f"📐 Expected dimension: {EMBEDDING_DIM}\n")
    print("Generating embeddings...")
    embedded = embed_chunks(chunks)
    print()

    # ── 3. Per-chunk verification table ─────────────────────────────────
    print("─" * 70)
    print(f"{'#':<4} {'Chunk ID':<55} {'Dim':>4} {'Norm':>6} {'✓':>3}")
    print("─" * 70)

    all_pass = True
    for i, chunk in enumerate(embedded):
        cid = chunk.get("chunk_id", "???")
        emb = chunk.get("embedding")

        if emb is None:
            print(f"{i+1:<4} {cid:<55} {'—':>4} {'—':>6} ❌")
            all_pass = False
            continue

        dim = len(emb)
        norm = l2_norm(emb)
        dim_ok = dim == EMBEDDING_DIM
        norm_ok = abs(norm - 1.0) < 0.01
        ok = dim_ok and norm_ok

        if not ok:
            all_pass = False

        status = "✅" if ok else "❌"
        print(f"{i+1:<4} {cid:<55} {dim:>4} {norm:>6.4f} {status:>3}")

    print("─" * 70)

    # ── 4. Summary stats ────────────────────────────────────────────────
    total = len(embedded)
    with_emb = sum(1 for c in embedded if c.get("embedding"))
    dims_ok = sum(1 for c in embedded if c.get("embedding") and len(c["embedding"]) == EMBEDDING_DIM)
    norms_ok = sum(
        1 for c in embedded
        if c.get("embedding") and abs(l2_norm(c["embedding"]) - 1.0) < 0.01
    )

    print(f"\n📊 SUMMARY")
    print(f"   Total chunks:          {total}")
    print(f"   Have embeddings:       {with_emb}/{total} {'✅' if with_emb == total else '❌'}")
    print(f"   Correct dimension:     {dims_ok}/{total} {'✅' if dims_ok == total else '❌'}")
    print(f"   L2-normalised:         {norms_ok}/{total} {'✅' if norms_ok == total else '❌'}")

    # ── 5. Chunk type breakdown ─────────────────────────────────────────
    print(f"\n📋 CHUNK TYPE BREAKDOWN")
    types = {}
    for c in embedded:
        ct = c.get("chunk_type", "unknown")
        types[ct] = types.get(ct, 0) + 1
    for ct, count in sorted(types.items()):
        print(f"   {ct:<25} {count}")

    # ── 6. Scheme breakdown ─────────────────────────────────────────────
    print(f"\n🏦 SCHEME BREAKDOWN")
    schemes = {}
    for c in embedded:
        s = c.get("scheme_name", "unknown")
        schemes[s] = schemes.get(s, 0) + 1
    for s, count in sorted(schemes.items()):
        print(f"   {s:<45} {count} chunks")

    # ── 7. Similarity sanity checks ─────────────────────────────────────
    print(f"\n🔍 SIMILARITY CHECKS")

    # Find structured_facts and faq chunks
    facts_chunks = [c for c in embedded if c["chunk_type"] == "structured_facts"]
    faq_chunks = [c for c in embedded if c["chunk_type"] == "faq"]

    if len(facts_chunks) >= 2:
        sim = cosine_sim(facts_chunks[0]["embedding"], facts_chunks[1]["embedding"])
        print(f"   Similarity between two structured_facts chunks: {sim:.4f}")
        print(f"   (Same type, different schemes — expect moderate: 0.5–0.9)")

    if facts_chunks and faq_chunks:
        sim = cosine_sim(facts_chunks[0]["embedding"], faq_chunks[0]["embedding"])
        print(f"   Similarity between structured_facts and faq:    {sim:.4f}")
        print(f"   (Different types — expect lower: 0.3–0.7)")

    # ── 8. Query embedding test ─────────────────────────────────────────
    print(f"\n🔎 QUERY RETRIEVAL TEST")
    test_queries = [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "How to invest in SIP?",
        "What is the NAV?",
    ]

    for query in test_queries:
        q_emb = embed_query(query)
        print(f"\n   Query: \"{query}\"")
        print(f"   Query embedding dim: {len(q_emb)}, norm: {l2_norm(q_emb):.4f}")

        # Rank all chunks by similarity
        ranked = sorted(
            embedded,
            key=lambda c: cosine_sim(q_emb, c["embedding"]),
            reverse=True,
        )

        print(f"   Top 3 matches:")
        for j, match in enumerate(ranked[:3]):
            sim = cosine_sim(q_emb, match["embedding"])
            text_preview = match["text"][:80].replace("\n", " ")
            print(f"     {j+1}. [{sim:.4f}] {match['chunk_id']}")
            print(f"        \"{text_preview}...\"")

    # ── 9. Final verdict ────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    if all_pass and with_emb == total:
        print("  ✅ ALL EMBEDDINGS VERIFIED SUCCESSFULLY")
    else:
        print("  ❌ SOME CHECKS FAILED — review the report above")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
