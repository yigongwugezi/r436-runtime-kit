"""RAG (Retrieval-Augmented Generation) module.

Provides semantic search over a pre-built Chinese Wikipedia knowledge base
using LlamaIndex + HuggingFace ``text2vec-large-chinese`` + FAISS (IndexFlatIP).

The build pipeline (``loader`` → ``chunker`` → ``embedder`` → ``store`` → ``indexer``)
is executed once via ``scripts/build_rag_db.py``.  At runtime the ``query_engine``
and ``routers/rag.py`` serve queries from the persisted vector database.
"""

from app.rag.config import RAGConfig, rag_config
from app.rag.errors import RAGServiceError

# Lazy import for optional llama_index dependency
try:
    from app.rag.query_engine import RagQueryEngine, SearchResponse, SearchResult, rag_query_engine
except ImportError:
    RagQueryEngine = None  # type: ignore[assignment]
    SearchResponse = None  # type: ignore[assignment]
    SearchResult = None  # type: ignore[assignment]
    rag_query_engine = None  # type: ignore[assignment]

__all__ = [
    "RAGConfig",
    "rag_config",
    "RAGServiceError",
    "RagQueryEngine",
    "SearchResponse",
    "SearchResult",
    "rag_query_engine",
]
