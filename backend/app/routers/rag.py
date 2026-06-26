"""RAG (Retrieval-Augmented Generation) API endpoints.

Provides semantic search over the pre-built Wikipedia knowledge base.

All responses follow the :class:`~app.schemas.product.ProductApiResponse` envelope
convention used by every other product endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from app.rag.config import rag_config
from app.rag.errors import RAGServiceError
from app.rag.query_engine import rag_query_engine
from app.rag.store import collection_stats
from app.schemas.product import ProductApiResponse

logger = logging.getLogger("app.routers.rag")

router = APIRouter(tags=["rag"])


def _ok(
    data: Any,
    *,
    message: str = "success",
    source: str = "rag",
    session_id: str = "",
    subject_id: str = "",
) -> dict[str, Any]:
    """Build a success ProductApiResponse dict."""
    return ProductApiResponse(
        status="success",
        data=data,
        message=message,
        source=source,
        sessionId=session_id,
        subjectId=subject_id,
    ).model_dump()


def _error(
    message: str,
    *,
    code: str = "RAG_SERVICE_ERROR",
    is_user_error: bool = False,
    session_id: str = "",
) -> dict[str, Any]:
    """Build an error ProductApiResponse dict."""
    return ProductApiResponse(
        status="error",
        data=None,
        message=message,
        code=code,
        is_user_error=is_user_error,
        sessionId=session_id,
        source="rag",
    ).model_dump()


# ── Endpoints ──────────────────────────────────────────────────────────


@router.get("/rag/search")
def rag_search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language search query (Chinese or English).",
    ),
    top_k: int = Query(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return.",
    ),
    sessionId: str = Query(
        default="",
        description="Session context (optional for this endpoint).",
    ),
    subjectId: str = Query(
        default="",
        description="Subject context (optional for this endpoint).",
    ),
) -> dict[str, Any]:
    """Semantic search over the Chinese Wikipedia knowledge base.

    Returns scored results with provenance metadata (title, url, source file).
    When the RAG database has not been built, returns an empty result set
    with a warning — it never crashes.
    """
    if not rag_query_engine.is_ready():
        warnings = [
            "知识库尚未构建，请先运行 scripts/build_rag_db.py 构建 RAG 数据库。"
        ]
        return _ok(
            {"query": q, "results": [], "total": 0},
            message="知识库未就绪",
            source="rag",
            session_id=sessionId,
            subject_id=subjectId,
        ) | {"warnings": warnings}

    try:
        response = rag_query_engine.search(q, top_k=top_k)
        return _ok(
            {
                "query": response.query,
                "results": [
                    {
                        "id": r.id,
                        "text": r.text,
                        "title": r.title,
                        "url": r.url,
                        "source_file": r.source_file,
                        "score": r.score,
                    }
                    for r in response.results
                ],
                "total": response.total,
            },
            source="rag",
            session_id=sessionId,
            subject_id=subjectId,
        )
    except RAGServiceError as exc:
        return _error(
            str(exc.message),
            code=exc.code,
            is_user_error=exc.is_user_error,
            session_id=sessionId,
        )


@router.get("/rag/status")
def rag_status() -> dict[str, Any]:
    """Health-check for the RAG knowledge base.

    Returns collection metadata: existence, entity count, dimension, URI.
    Does **not** trigger a build — purely read-only.
    """
    try:
        stats = collection_stats(rag_config)
        return _ok(stats, source="rag")
    except Exception as exc:
        logger.error("Failed to read RAG status: %s", exc)
        return _error("无法读取知识库状态", code="RAG_SERVICE_ERROR")
