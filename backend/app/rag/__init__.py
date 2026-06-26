"""RAG (Retrieval-Augmented Generation) module.

Provides semantic search over a pre-built Chinese Wikipedia knowledge base
using LlamaIndex + HuggingFace ``text2vec-large-chinese`` + Milvus Lite.

The build pipeline (``loader`` → ``chunker`` → ``embedder`` → ``store`` → ``indexer``)
is executed once via ``scripts/build_rag_db.py``.  At runtime the ``query_engine``
and ``routers/rag.py`` serve queries from the persisted vector database.
"""

from app.rag.config import RAGConfig, rag_config
from app.rag.errors import RAGServiceError

__all__ = ["RAGConfig", "rag_config", "RAGServiceError"]
