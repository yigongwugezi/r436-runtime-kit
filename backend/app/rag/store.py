"""Milvus Lite vector-store abstraction.

Wraps LlamaIndex's :class:`~llama_index.vector_stores.milvus.MilvusVectorStore`
to provide a clean, project-specific API for both the *build* and *query* paths.

Utility functions (``collection_exists``, ``collection_stats``, …) use the
``MilvusClient`` API which is the recommended PyMilvus interface.
"""

from __future__ import annotations

import logging
from typing import Any

from llama_index.vector_stores.milvus import MilvusVectorStore
from pymilvus import MilvusClient

from app.rag.config import RAGConfig

logger = logging.getLogger("app.rag.store")


def _build_uri(config: RAGConfig) -> str:
    """Resolve the Milvus URI, defaulting from Settings when not absolute."""
    from app.config import settings

    return settings.rag_milvus_uri or _default_uri(config)


def _default_uri(config: RAGConfig) -> str:
    """Fallback URI (should rarely be used — Settings is authoritative)."""
    return f"./data/milvus/{config.collection_name}.db"


def _client(config: RAGConfig) -> MilvusClient:
    """Return a throwaway ``MilvusClient`` for one-shot utility calls."""
    return MilvusClient(uri=_build_uri(config))


# ── Build-time ────────────────────────────────────────────────────────


def create_vector_store(
    config: RAGConfig,
    overwrite: bool = False,
) -> MilvusVectorStore:
    """Create (or overwrite) a Milvus Lite collection for index building.

    Parameters:
        config: RAG configuration (collection name, dimension, index params).
        overwrite: If ``True``, drop the existing collection first.

    Returns:
        A configured ``MilvusVectorStore`` ready for ``VectorStoreIndex.from_documents``.
    """
    uri = _build_uri(config)

    if overwrite:
        _drop_if_exists(config)

    logger.info(
        "Connecting to Milvus Lite: uri=%s, collection=%s, dim=%d, metric=%s",
        uri,
        config.collection_name,
        config.embedding_dim,
        config.index_metric,
    )

    store = MilvusVectorStore(
        uri=uri,
        collection_name=config.collection_name,
        dim=config.embedding_dim,
        similarity_metric=config.index_metric,
        index_config={
            "index_type": "IVF_FLAT",
            "metric_type": config.index_metric,
            "params": {"nlist": config.index_nlist},
        },
        overwrite=False,
    )
    return store


# ── Query-time ────────────────────────────────────────────────────────


def connect_vector_store(config: RAGConfig) -> MilvusVectorStore:
    """Connect to an *existing* Milvus Lite collection for querying.

    Does **not** create or modify the collection — use :func:`create_vector_store`
    for build-time operations.
    """
    uri = _build_uri(config)

    logger.info(
        "Connecting to existing Milvus collection: %s",
        config.collection_name,
    )

    store = MilvusVectorStore(
        uri=uri,
        collection_name=config.collection_name,
        dim=config.embedding_dim,
        similarity_metric=config.index_metric,
        overwrite=False,
    )
    return store


# ── Utility ───────────────────────────────────────────────────────────


def collection_exists(config: RAGConfig) -> bool:
    """Check whether the RAG collection has been built."""
    try:
        client = _client(config)
        return client.has_collection(config.collection_name)
    except Exception:
        return False


def collection_stats(config: RAGConfig) -> dict[str, Any]:
    """Return basic metadata about the collection.

    Returns a dict with keys ``exists``, ``num_entities`` (if available),
    ``collection``, ``milvus_uri``, and ``embedding_dim``.
    """
    uri = _build_uri(config)
    result: dict[str, Any] = {
        "collection": config.collection_name,
        "exists": False,
        "milvus_uri": uri,
        "embedding_dim": config.embedding_dim,
    }

    try:
        client = _client(config)
        if client.has_collection(config.collection_name):
            result["exists"] = True
            stats = client.get_collection_stats(config.collection_name)
            result["num_entities"] = stats.get("row_count", 0)
    except Exception as exc:
        logger.warning("Failed to read collection stats: %s", exc)

    return result


def _drop_if_exists(config: RAGConfig) -> None:
    """Drop a collection if it already exists (used before rebuild)."""
    try:
        client = _client(config)
        if client.has_collection(config.collection_name):
            logger.info("Dropping existing collection: %s", config.collection_name)
            client.drop_collection(config.collection_name)
    except Exception as exc:
        logger.warning(
            "Could not drop collection '%s': %s",
            config.collection_name,
            exc,
        )
