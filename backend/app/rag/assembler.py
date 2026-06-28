"""Cache-to-database assembler (streaming, memory-efficient).

Reads pre-computed ``.meta.json`` + ``.vecs.bin`` intermediate files
from a cache directory and builds the final FAISS + LlamaIndex
persisted database **one file at a time** to keep peak memory low.

No embedding model is loaded during assembly — all vectors already
exist in the cache.  Intermediate cache files are never deleted.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from llama_index.core import StorageContext
from llama_index.core.schema import TextNode
from llama_index.vector_stores.faiss import FaissVectorStore

from app.rag.config import RAGConfig

logger = logging.getLogger("app.rag.assembler")


@dataclass
class AsmResult:
    """Summary returned after assembly."""

    files_loaded: int = 0
    files_skipped: int = 0
    total_chunks: int = 0
    total_vectors: int = 0
    collection: str = ""
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


# ── Public API ──────────────────────────────────────────────────────────


def discover_cache_pairs(cache_dir: str | Path) -> list[tuple[Path, Path]]:
    """Find all ``(meta_path, vecs_path)`` pairs under *cache_dir*."""
    root = Path(cache_dir).resolve()
    if not root.exists():
        logger.warning("Cache directory not found: %s", root)
        return []

    pairs: list[tuple[Path, Path]] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        for meta_file in sorted(sub.glob("*.meta.json")):
            base = meta_file.name[:-len(".meta.json")]
            vecs_file = sub / f"{base}.vecs.bin"
            if vecs_file.exists():
                pairs.append((meta_file, vecs_file))
            else:
                logger.warning(
                    "Missing .vecs.bin for %s — skipping", meta_file
                )
    return pairs


def assemble_index(
    config: RAGConfig,
    cache_dir: str | Path,
    output_dir: str | Path | None = None,
) -> AsmResult:
    """Build the final FAISS + docstore database from cached intermediates.

    Streams files one at a time — peak memory is bounded by the largest
    single cache file, not the total dataset size.
    """
    t0 = time.monotonic()
    result = AsmResult(collection=config.collection_name)

    if output_dir is None:
        from app.rag.store import _persist_dir
        output_dir = _persist_dir(config)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Discover cache pairs ───────────────────────────────────
    pairs = discover_cache_pairs(cache_dir)
    logger.info("Found %d cache file pair(s) under %s", len(pairs), cache_dir)
    if not pairs:
        result.errors.append("No cache pairs found — nothing to assemble")
        return result

    # ── 2. Create empty stores once ────────────────────────────────
    dim = config.embedding_dim
    _clear_dir(output_dir)

    from llama_index.core import Settings, VectorStoreIndex
    from llama_index.core.embeddings.mock_embed_model import MockEmbedding
    from llama_index.core.storage.docstore import SimpleDocumentStore
    from llama_index.core.storage.index_store import SimpleIndexStore

    # Mock embedding prevents LlamaIndex from trying to resolve the
    # global default (OpenAI).  Never actually called because every
    # node carries a pre-computed embedding.
    Settings.embed_model = MockEmbedding(embed_dim=dim)

    faiss_index = faiss.IndexFlatIP(dim)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    docstore = SimpleDocumentStore()
    index_store = SimpleIndexStore()

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
        docstore=docstore,
        index_store=index_store,
        persist_dir=str(output_dir),
    )

    # Empty index — we'll call insert_nodes() per file below
    index = VectorStoreIndex([], storage_context=storage_context)

    # ── 3. Stream files one at a time ─────────────────────────────
    node_counter = 0

    for meta_path, vecs_path in pairs:
        try:
            meta = _load_meta(meta_path)
            vecs = _load_vecs(vecs_path, dim)
        except Exception as exc:
            msg = f"Failed to load {meta_path}: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            result.files_skipped += 1
            continue

        expected = meta["chunk_count"]
        actual = vecs.shape[0]
        if expected != actual:
            msg = (
                f"Mismatch in {meta_path.name}: "
                f"{expected} chunks but {actual} vectors — skipping"
            )
            logger.error(msg)
            result.errors.append(msg)
            result.files_skipped += 1
            # Free memory before next iteration
            del vecs, meta
            continue

        # Build TextNodes for this file only.
        # Convert embeddings to Python list only for this batch —
        # LlamaIndex needs List[float], but the per-file count is
        # small enough (~1k–3k nodes) to stay within reasonable RAM.
        batch_nodes: list[TextNode] = []
        for i, chunk in enumerate(meta["chunks"]):
            node = TextNode(
                id_=f"node_{node_counter}",
                text=chunk["text"],
                metadata={
                    "wiki_id": chunk["wiki_id"],
                    "title": chunk["title"],
                    "url": chunk["url"],
                    "source_file": chunk["source_file"],
                    "chunk_index": str(chunk["chunk_index"]),
                },
                embedding=vecs[i].tolist(),
            )
            batch_nodes.append(node)
            node_counter += 1

        # Insert this batch — LlamaIndex detects pre-set embeddings
        # and skips encoding, adding vectors to FAISS and nodes to
        # the docstore.
        index.insert_nodes(batch_nodes)

        result.files_loaded += 1
        result.total_chunks += len(batch_nodes)

        # Free this file's data before loading the next
        del vecs, meta, batch_nodes

    result.total_vectors = faiss_index.ntotal

    if result.total_vectors == 0:
        result.errors.append("No vectors loaded — nothing to persist")
        return result

    logger.info(
        "Streamed %d chunks / %d vectors from %d file(s) (%d skipped)",
        result.total_chunks,
        result.total_vectors,
        result.files_loaded,
        result.files_skipped,
    )

    # ── 4. Persist ─────────────────────────────────────────────────
    storage_context.persist(persist_dir=str(output_dir))
    logger.info("Final index persisted to: %s", output_dir)

    result.elapsed_seconds = round(time.monotonic() - t0, 1)
    logger.info(
        "Assembly complete: %d vectors in %.1f s",
        result.total_vectors,
        result.elapsed_seconds,
    )
    return result


# ── Internal helpers ────────────────────────────────────────────────────


def _load_meta(path: Path) -> dict[str, Any]:
    """Load and validate a ``.meta.json`` file."""
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("version") != 1:
        raise ValueError(f"Unsupported meta version: {meta.get('version')}")
    return meta


def _load_vecs(path: Path, dim: int) -> np.ndarray:
    """Load a ``.vecs.bin`` file as a float32 array of shape ``(N, dim)``."""
    raw = np.fromfile(path, dtype=np.float32)
    if raw.size % dim != 0:
        raise ValueError(
            f"{path.name}: size {raw.size} not divisible by dim {dim}"
        )
    return raw.reshape(-1, dim)


def _clear_dir(path: Path) -> None:
    """Remove all files in *path* (not subdirectories)."""
    if not path.exists():
        return
    for entry in path.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
            except Exception as exc:
                logger.warning("Failed to remove %s: %s", entry, exc)
