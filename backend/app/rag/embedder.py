"""Embedding model wrapper.

Provides a singleton factory for the HuggingFace
``text2vec-large-chinese`` sentence-transformers model via LlamaIndex's
:class:`~llama_index.embeddings.huggingface.HuggingFaceEmbedding`.

Device selection is automatic: CUDA GPU when available, CPU otherwise.
When PyTorch is not installed at all the module still imports cleanly;
the error is deferred until :func:`create_embedding_model` is called.

**Offline-first**: ``TRANSFORMERS_OFFLINE`` and ``HF_HUB_OFFLINE`` are
set at module-import time so that *every* library in the stack
(huggingface_hub, transformers, sentence-transformers) sees them
before its first network attempt.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

# ── Set offline env vars at module level ──────────────────────────
# Must happen BEFORE any huggingface / transformers import so that
# every library in the stack sees them on first access.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.rag.config import RAGConfig

if TYPE_CHECKING:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

logger = logging.getLogger("app.rag.embedder")

_embed_model: "HuggingFaceEmbedding | None" = None
_torch_available: bool | None = None  # tri-state: None = unchecked


def _ensure_torch() -> bool:
    """Check whether PyTorch is importable.  Cached after first call."""
    global _torch_available
    if _torch_available is not None:
        return _torch_available
    try:
        import torch  # noqa: F401
        _torch_available = True
    except ImportError:
        logger.warning("PyTorch not installed — embedding will fall back to CPU if available")
        _torch_available = False
    return _torch_available


def _resolve_device() -> str:
    """Auto-detect the best available device.

    Returns ``"cuda"`` when PyTorch is installed AND a CUDA-capable GPU
    is present, ``"cpu"`` otherwise.  Never raises — always returns a
    valid device string.
    """
    if not _ensure_torch():
        logger.info("PyTorch unavailable — assuming CPU device")
        return "cpu"

    import torch

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_count = torch.cuda.device_count()
        logger.info(
            "CUDA GPU detected: %s (x%d) — embedding will use GPU acceleration",
            gpu_name,
            gpu_count,
        )
        return "cuda"
    else:
        logger.info("No CUDA GPU found — embedding will use CPU")
        return "cpu"


def create_embedding_model(config: RAGConfig) -> "HuggingFaceEmbedding":
    """Build (or return a cached) HuggingFace embedding model instance.

    The model is downloaded from HuggingFace Hub on first call and cached
    locally (respects ``HF_HOME`` env var / ``Settings.hf_home``).

    Device selection: CUDA GPU is used automatically when available;
    falls back to CPU otherwise.  Batch size is scaled up for GPU.

    **Offline-first strategy**: always attempt loading with
    ``HF_HUB_OFFLINE=1`` first.  If the model is fully cached this
    succeeds in <1 s with zero network I/O.  If the cache is missing or
    incomplete the library raises a ``LocalEntryNotFoundError`` — we
    then clear the offline flag and retry with network access.

    Raises:
        ImportError: If ``llama-index-embeddings-huggingface`` or
            ``sentence-transformers`` are not installed.
    """
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    # Deferred import — only needed when actually building/querying.
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    # ── Resolve project cache directory (absolute, one source of truth) ──
    from app.config import settings

    cache_dir = os.path.abspath(settings.hf_home or "./data/huggingface_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Force *every* HuggingFace / transformers cache path into the
    # project directory so nothing ever leaks to ~/.cache or elsewhere.
    os.environ["HF_HOME"] = cache_dir
    os.environ["HF_HUB_CACHE"] = cache_dir
    os.environ["TRANSFORMERS_CACHE"] = cache_dir
    os.environ["HUGGINGFACE_HUB_CACHE"] = cache_dir

    logger.info("Model cache directory: %s", cache_dir)

    device = _resolve_device()

    # GPU can handle larger batches comfortably
    batch_size = config.embedding_batch_size
    if device == "cuda":
        batch_size = batch_size * 4  # 128 on GPU vs 32 on CPU

    logger.info(
        "Loading embedding model: %s (batch_size=%d, device=%s) …",
        config.embedding_model,
        batch_size,
        device,
    )

    # ── Offline-first: try cached, fall back to network ────────────
    # Module-level already set HF_HUB_OFFLINE + TRANSFORMERS_OFFLINE.
    # We also pass local_files_only through model_kwargs so that
    # SentenceTransformer → AutoModel.from_pretrained sees it.
    common_kwargs = dict(
        model_name=config.embedding_model,
        embed_batch_size=batch_size,
        device=device,
        cache_folder=cache_dir,
    )
    offline_kwargs = {**common_kwargs, "model_kwargs": {"local_files_only": True}}

    try:
        logger.info("Trying offline load first …")
        _embed_model = HuggingFaceEmbedding(**offline_kwargs)
        logger.info("Embedding model loaded from local cache (offline)")

    except Exception as exc:
        cls_name = exc.__class__.__name__
        msg = str(exc)

        if ("LocalEntryNotFoundError" in cls_name
                or "local" in msg.lower()
                or "offline" in msg.lower()):
            logger.info(
                "Model not fully cached — retrying with network: %s",
                exc,
            )
            # Temporarily re-enable network for this one load
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            _embed_model = HuggingFaceEmbedding(**common_kwargs)
            # Restore offline mode for subsequent loads
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        else:
            raise

    # Note: env vars intentionally left set — all subsequent
    # HuggingFace operations in this process should be offline.

    logger.info("Embedding model ready (dim=%d, device=%s)", config.embedding_dim, device)
    return _embed_model


def get_embedding_model() -> "HuggingFaceEmbedding | None":
    """Return the already-loaded model, or ``None`` if not initialised."""
    return _embed_model
