"""Non-sensitive RAG configuration.

Privacy-related parameters (Milvus URI, feature flags) live in
``app.config.Settings`` and are read from ``.env``.

Algorithm / tuning parameters that developers adjust during development
are defined here as the single source of truth for RAG behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RAGConfig:
    """Tuning parameters for the RAG pipeline (no secrets, no env vars)."""

    # ── Chunking ──────────────────────────────────────────────────────
    chunk_size: int = 512
    """Target chunk size in *tokens* (≈ 256–512 Chinese characters)."""

    chunk_overlap: int = 50
    """Token overlap between adjacent chunks to preserve context."""

    chinese_separators: tuple[str, ...] = (
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        "；",
        "，",
        " ",
        "",
    )
    """Sentence-splitting priority for Chinese text (LlamaIndex SentenceSplitter)."""

    # ── Embedding ─────────────────────────────────────────────────────
    embedding_model: str = "GanymedeNil/text2vec-large-chinese"
    """HuggingFace sentence-transformers model name."""

    embedding_dim: int = 768
    """Output vector dimension (fixed by the model)."""

    embedding_batch_size: int = 32
    """Batch size for embedding generation (CPU-friendly)."""

    # ── Vector store ──────────────────────────────────────────────────
    collection_name: str = "eduagent_knowledge"
    """Milvus collection name."""

    index_metric: str = "COSINE"
    """Distance metric for vector similarity."""

    index_nlist: int = 128
    """IVF_FLAT cluster count — higher = more accurate but slower build."""

    # ── Query defaults ────────────────────────────────────────────────
    search_top_k: int = 5
    """Default number of results returned by a semantic search."""

    # ── Data source ───────────────────────────────────────────────────
    data_path: str = "../2_WikiDataLib/testdata"
    """Root directory containing AA/, AB/, … subdirectories with wiki_* NDJSON files."""


# Module-level singleton — import this everywhere.
rag_config = RAGConfig()
