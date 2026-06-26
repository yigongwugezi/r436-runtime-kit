#!/usr/bin/env python3
"""Post-build verification script for the RAG vector database.

Usage::

    cd backend
    python scripts/verify_rag_db.py

Runs a battery of checks and test queries against the built Milvus Lite
database and prints a pass / fail summary.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("verify_rag_db")

# Test queries covering different domains in the Chinese Wikipedia test dataset
TEST_QUERIES = [
    "神经网络",
    "中国历史",
    "数学",
    "微积分",
    "数据库",
    "机器学习",
    "操作系统",
    "量子力学",
]


def main() -> None:
    from app.rag.config import rag_config
    from app.rag.store import collection_exists, collection_stats
    from app.rag.query_engine import RagQueryEngine

    print("\n" + "=" * 60)
    print("  RAG Database Verification")
    print("=" * 60)
    print(f"  Collection : {rag_config.collection_name}")
    print(f"  Embedding  : {rag_config.embedding_model}")

    # ── 1. Collection check ─────────────────────────────────────────
    print("\n── 1. Collection existence ──")
    stats = collection_stats(rag_config)
    print(f"  exists       : {stats['exists']}")
    print(f"  num_entities : {stats.get('num_entities', 'N/A')}")
    print(f"  embedding_dim: {stats['embedding_dim']}")
    print(f"  milvus_uri   : {stats['milvus_uri']}")

    if not stats["exists"]:
        print("\n  ❌ FAIL: Collection does not exist. Run build_rag_db.py first.")
        sys.exit(1)

    if stats.get("num_entities", 0) == 0:
        print("\n  ❌ FAIL: Collection is empty (0 entities).")
        sys.exit(1)

    print("  ✅ Collection found with entities.")

    # ── 2. Query engine initialisation ──────────────────────────────
    print("\n── 2. Query engine initialisation ──")
    engine = RagQueryEngine()
    if not engine.is_ready():
        print("  ❌ FAIL: Query engine failed to initialise.")
        sys.exit(1)
    print("  ✅ Query engine ready.")

    # ── 3. Test queries ─────────────────────────────────────────────
    print("\n── 3. Semantic search tests ──")
    passed = 0
    failed = 0

    for query in TEST_QUERIES:
        started = time.monotonic()
        try:
            resp = engine.search(query, top_k=3)
            elapsed = (time.monotonic() - started) * 1000
            if resp.total > 0:
                top = resp.results[0]
                print(
                    f"  ✅ '{query}' → {resp.total} results ({elapsed:.0f} ms)  "
                    f"top: \"{top.title}\" (score={top.score})"
                )
                passed += 1
            else:
                print(f"  ⚠️  '{query}' → 0 results ({elapsed:.0f} ms)")
                failed += 1
        except Exception as exc:
            print(f"  ❌ '{query}' → ERROR: {exc}")
            failed += 1

    # ── 4. Summary ──────────────────────────────────────────────────
    total = passed + failed
    print(f"\n── 4. Summary ──")
    print(f"  Passed : {passed}/{total}")
    print(f"  Failed : {failed}/{total}")

    if failed == 0:
        print("\n  🎉 All checks passed!")
        sys.exit(0)
    elif failed <= 2:
        print("\n  ⚠️  Some queries returned no results (may be normal for this dataset).")
        sys.exit(0)
    else:
        print("\n  ❌ Too many failed queries — investigation recommended.")
        sys.exit(1)


if __name__ == "__main__":
    main()
