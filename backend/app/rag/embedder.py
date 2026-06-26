"""Embedding model wrapper.

Provides a singleton factory for the HuggingFace
``text2vec-large-chinese`` sentence-transformers model via LlamaIndex's
:class:`~llama_index.embeddings.huggingface.HuggingFaceEmbedding`.
"""

from __future__ import annotations

import logging
import os

from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.rag.config import RAGConfig

logger = logging.getLogger("app.rag.embedder")

_embed_model: HuggingFaceEmbedding | None = None


def create_embedding_model(config: RAGConfig) -> HuggingFaceEmbedding:
    """Build (or return a cached) HuggingFace embedding model instance.

    The model is downloaded from HuggingFace Hub on first call and cached
    locally (respects ``HF_HOME`` env var / ``Settings.hf_home``).

    Uses CPU inference for portability — no GPU required.
    """
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    # Ensure HF_HOME is set before the model loads so the cache directory
    # is predictable (important for CI / deployment).
    from app.config import settings

    if settings.hf_home and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = settings.hf_home
        os.makedirs(settings.hf_home, exist_ok=True)

    logger.info(
        "Loading embedding model: %s (batch_size=%d, device=cpu) …",
        config.embedding_model,
        config.embedding_batch_size,
    )

    _embed_model = HuggingFaceEmbedding(
        model_name=config.embedding_model,
        embed_batch_size=config.embedding_batch_size,
        device="cpu",
    )

    logger.info("Embedding model ready (dim=%d)", config.embedding_dim)
    return _embed_model


def get_embedding_model() -> HuggingFaceEmbedding | None:
    """Return the already-loaded model, or ``None`` if not initialised."""
    return _embed_model
