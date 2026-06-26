"""Full build-pipeline orchestrator.

Wires together ``loader → chunker → embedder → store`` into a single
:func:`build_index` call that the CLI build script invokes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from llama_index.core import VectorStoreIndex

from app.rag.chunker import chunk_records
from app.rag.config import RAGConfig
from app.rag.embedder import create_embedding_model
from app.rag.loader import load_all_records
from app.rag.store import create_vector_store

logger = logging.getLogger("app.rag.indexer")


@dataclass
class BuildResult:
    """Summary returned after a successful (or partial) build."""

    raw_records: int = 0
    """Total records loaded from NDJSON files."""

    document_nodes: int = 0
    """Number of LlamaIndex Document / Node objects after chunking."""

    collection: str = ""
    """Milvus collection name."""

    elapsed_seconds: float = 0.0
    """Wall-clock build time."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal warnings / errors encountered during the build."""


def build_index(
    config: RAGConfig,
    max_records: int = 0,
) -> BuildResult:
    """Execute the full RAG build pipeline.

    Steps:

    1. Load & clean NDJSON records from *config.data_path*.
    2. Chunk cleaned text into ``Document`` nodes.
    3. Create embedding model.
    4. Create (or overwrite) Milvus Lite vector store.
    5. Build and persist the ``VectorStoreIndex``.

    Parameters:
        config: RAG configuration (chunking, embedding, store params).
        max_records: If > 0, cap the number of records (for smoke tests).

    Returns:
        A :class:`BuildResult` with counts and timing.
    """
    started = time.monotonic()
    result = BuildResult()

    # ── 1. Load ────────────────────────────────────────────────────
    logger.info("=== Step 1/4: Loading NDJSON files ===")
    raw = load_all_records(config.data_path, max_records=max_records)
    result.raw_records = len(raw)
    if not raw:
        result.errors.append("No valid records found — aborting build")
        return result

    # ── 2. Clean & Chunk ───────────────────────────────────────────
    logger.info("=== Step 2/4: Cleaning & chunking text ===")
    # Annotate source file for traceability
    from app.rag.loader import discover_files

    files = discover_files(config.data_path)
    for rec in raw:
        # Derive source_file from the id range (approximate — good enough
        # for provenance display).
        rec["_source_file"] = _guess_source_file(rec.get("id", ""), files)

    from app.rag.chunker import clean_all_records

    raw = clean_all_records(raw)
    documents = chunk_records(raw, config)
    result.document_nodes = len(documents)
    if not documents:
        result.errors.append("No document chunks produced — aborting build")
        return result

    # ── 3. Embedding model ─────────────────────────────────────────
    logger.info("=== Step 3/4: Loading embedding model ===")
    embed_model = create_embedding_model(config)

    # ── 4. Build & persist index ───────────────────────────────────
    logger.info("=== Step 4/4: Building vector index ===")
    vector_store = create_vector_store(config, overwrite=True)

    logger.info(
        "Indexing %d document nodes (this may take a while on first run) …",
        len(documents),
    )
    _index = VectorStoreIndex.from_documents(
        documents,
        embed_model=embed_model,
        vector_store=vector_store,
        show_progress=True,
    )

    result.collection = config.collection_name
    result.elapsed_seconds = round(time.monotonic() - started, 1)
    logger.info(
        "Build complete: %d records → %d nodes in %.1f s",
        result.raw_records,
        result.document_nodes,
        result.elapsed_seconds,
    )
    return result


def _guess_source_file(wiki_id: str, files: list[Path]) -> str:
    """Return a human-readable source label for a wiki id.

    Since NDJSON files are sharded by id range, we can label records
    with the directory + filename for traceability.
    """
    try:
        nid = int(wiki_id)
    except (ValueError, TypeError):
        return "unknown"

    # Most files hold contiguous id ranges. Report the file whose
    # directory prefix roughly matches (AA → low ids, AB → mid, etc.).
    for fp in sorted(files):
        if fp.parent.name <= _id_prefix(nid) <= fp.parent.name:
            return f"{fp.parent.name}/{fp.name}"
    # Fallback
    return f"{files[0].parent.name}/{files[0].name}" if files else "unknown"


def _id_prefix(nid: int) -> str:
    """Map a numeric wiki id to a two-letter prefix (approximate shard)."""
    # The test data shows: AA → ids 13–5572, AB → ids 503385–508392
    # Production data is sharded more densely.
    if nid < 100_000:
        return "AA"
    elif nid < 200_000:
        return "AB"
    elif nid < 300_000:
        return "AC"
    elif nid < 400_000:
        return "AD"
    elif nid < 500_000:
        return "AE"
    elif nid < 600_000:
        return "AF"
    else:
        # For higher ranges, produce the right prefix dynamically
        prefix_index = nid // 100_000
        first = ord("A") + (prefix_index // 26)
        second = ord("A") + (prefix_index % 26)
        if first <= ord("Z") and second <= ord("Z"):
            return chr(first) + chr(second)
        return "ZZ"
