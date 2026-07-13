"""Runtime query pipeline.

Provides :class:`RagQueryEngine` — the programmatic API that agents and
routers use to perform semantic search against the pre-built FAISS vector
index and document store.

Initialization happens **once** on a background thread at FastAPI startup
so that the first (and every subsequent) query is fast.  Callers that
arrive before init completes block with a configurable timeout.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.rag.config import RAGConfig, rag_config
from app.rag.errors import RAGServiceError
from app.rag.store import collection_exists, load_index

if TYPE_CHECKING:
    from llama_index.core.schema import NodeWithScore

logger = logging.getLogger("app.rag.query_engine")


@dataclass
class SearchResult:
    """A single semantic-search hit."""

    id: str
    text: str
    title: str = ""
    url: str = ""
    source_file: str = ""
    score: float = 0.0


@dataclass
class SearchResponse:
    """Complete response for a semantic search."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0


class RagQueryEngine:
    """Semantic search over the pre-built RAG knowledge base.

    Use the module-level ``rag_query_engine`` singleton.  Call
    ``start_background_init()`` once at process startup to begin
    loading the embedding model + FAISS index on a daemon thread.
    """

    def __init__(self, config: RAGConfig | None = None) -> None:
        self._config = config or rag_config
        self._index = None
        self._ready: bool | None = None  # None=not started, True=done, False=failed
        self._init_lock = threading.Lock()
        self._init_started = False

    # ── Background init (called once at startup) ────────────────────

    def start_background_init(self) -> None:
        """Launch non-blocking, one-time initialization on a daemon thread.

        Safe to call multiple times — only the first call has any effect.
        """
        with self._init_lock:
            if self._init_started:
                return
            self._init_started = True

        logger.info(
            "Starting RAG background initialization (index=%s) …",
            self._config.collection_name,
        )
        t = threading.Thread(target=self._do_init, daemon=True, name="rag-init")
        t.start()

    def wait_until_ready(self, timeout: float = 120.0) -> bool:
        """Block until the background init completes or *timeout* seconds pass.

        Returns ``True`` if the engine is queryable.
        """
        # If init hasn't been started, try lazy init as fallback
        if not self._init_started:
            return self._ensure_ready()

        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ready is not None:
                return self._ready
            time.sleep(0.1)
        logger.warning("RAG init timed out after %.0f s", timeout)
        return False

    # ── Public API ──────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int | None = None,
    ) -> SearchResponse:
        """Run a semantic search query.

        Blocks until the background init completes (or times out).
        """
        top_k = top_k or self._config.search_top_k

        if not self.wait_until_ready():
            return SearchResponse(query=query, results=[], total=0)

        try:
            retriever = self._index.as_retriever(similarity_top_k=top_k)
            nodes: list[NodeWithScore] = retriever.retrieve(query)
        except Exception as exc:
            logger.error("Retrieval failed for query '%s': %s", query, exc)
            raise RAGServiceError(cause=exc) from exc

        results = [
            SearchResult(
                id=node.node_id,
                text=node.text or "",
                title=node.metadata.get("title", ""),
                url=node.metadata.get("url", ""),
                source_file=node.metadata.get("source_file", ""),
                score=round(node.score or 0.0, 4),
            )
            for node in nodes[:top_k]
        ]

        return SearchResponse(query=query, results=results, total=len(results))

    def insert_nodes(self, nodes: list) -> int:
        """Insert pre-embedded TextNode objects into the FAISS index at runtime.

        Returns the number of nodes inserted.  Persists the updated index to disk.
        """
        if not self.wait_until_ready():
            raise RAGServiceError("RAG engine is not ready for insertion")

        from app.rag.store import _persist_dir

        try:
            self._index.insert_nodes(nodes)
            persist_dir = _persist_dir(self._config)
            self._index.storage_context.persist(persist_dir=persist_dir)
            logger.info("Inserted %d web nodes into RAG index and persisted", len(nodes))
            return len(nodes)
        except Exception as exc:
            logger.error("Failed to insert nodes into RAG index: %s", exc)
            raise RAGServiceError(cause=exc) from exc

    def is_ready(self) -> bool:
        """Check whether the RAG index is loaded and queryable."""
        if self._ready is not None:
            return self._ready
        return self._ensure_ready()

    # ── Internal ────────────────────────────────────────────────────

    def _do_init(self) -> None:
        """Perform the heavy init work (model + FAISS load).  Runs on a daemon thread."""
        with self._init_lock:
            # Double-check — another thread may have already finished
            if self._ready is not None:
                return

            if not collection_exists(self._config):
                logger.warning(
                    "RAG index not found — run scripts/build_rag_db.py first. "
                    "Queries will return empty results."
                )
                self._ready = False
                return

            try:
                from app.rag.embedder import create_embedding_model

                embed_model = create_embedding_model(self._config)
                self._index = load_index(self._config, embed_model)

                if self._index is None:
                    self._ready = False
                    return

                self._ready = True
                logger.info(
                    "RAG query engine ready (index=%s)",
                    self._config.collection_name,
                )
            except ImportError as exc:
                logger.error(
                    "Cannot initialise RAG — missing dependencies: %s",
                    exc,
                )
                self._ready = False
            except Exception as exc:
                logger.error("Failed to initialise RAG query engine: %s", exc)
                self._ready = False

    def _ensure_ready(self) -> bool:
        """Legacy lazy-init fallback (used when start_background_init was not called)."""
        if self._ready is not None:
            return self._ready

        # _do_init() acquires _init_lock internally — do NOT hold it here
        # or we deadlock since threading.Lock() is not reentrant.
        self._do_init()
        return self._ready is True


# Module-level singleton — use this everywhere.
rag_query_engine = RagQueryEngine()
