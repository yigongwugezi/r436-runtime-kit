#!/usr/bin/env python3
"""One-time CLI script to build the RAG vector database.

Usage::

    cd backend
    python scripts/build_rag_db.py                     # full testdata build
    python scripts/build_rag_db.py --max-records 500   # quick smoke test
    python scripts/build_rag_db.py --data-path D:/...  # custom data path

The script is intentionally separate from the running backend —
run it once to produce the persisted Milvus Lite database, then
start the backend to serve queries.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("build_rag_db")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the EduAgent RAG vector database (one-time).",
    )
    parser.add_argument(
        "--data-path",
        default=None,
        help="Root directory containing AA/, AB/, … wiki_* NDJSON files.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="Cap number of records (0 = all). Useful for smoke tests.",
    )
    args = parser.parse_args()

    from app.rag.config import rag_config
    from app.rag.indexer import build_index

    if args.data_path:
        rag_config.data_path = args.data_path

    logger.info("Data path : %s", rag_config.data_path)
    logger.info("Collection: %s", rag_config.collection_name)
    logger.info("Embedding : %s", rag_config.embedding_model)
    logger.info("Chunk size: %d tokens, overlap: %d",
                rag_config.chunk_size, rag_config.chunk_overlap)

    result = build_index(rag_config, max_records=args.max_records)

    if result.errors:
        for err in result.errors:
            logger.error("BUILD ERROR: %s", err)
        sys.exit(1)

    print("\n" + "=" * 56)
    print("  Build Summary")
    print("=" * 56)
    print(f"  Raw records loaded : {result.raw_records:>6,d}")
    print(f"  Document chunks    : {result.document_nodes:>6,d}")
    print(f"  Collection name    : {result.collection}")
    print(f"  Elapsed time       : {result.elapsed_seconds:>6.1f} s")
    print("=" * 56)


if __name__ == "__main__":
    main()
