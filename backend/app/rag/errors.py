"""RAG-specific error types.

Extends :class:`app.utils.errors.AppError` so the global exception handler
in ``main.py`` converts these into consistent ``ProductApiResponse`` error
envelopes automatically.
"""

from __future__ import annotations

from app.utils.errors import AppError


class RAGServiceError(AppError):
    """RAG knowledge-base is unavailable or the query could not be served.

    Mirrors :class:`~app.utils.errors.SearchServiceError` design —
    always a 5xx system error, never the user's fault.
    """

    def __init__(
        self,
        message: str = "知识库检索服务暂不可用",
        *,
        code: str = "RAG_SERVICE_ERROR",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=503,
            is_user_error=False,
            cause=cause,
        )


class RAGCollectionNotFoundError(RAGServiceError):
    """The Milvus collection has not been built yet or was deleted."""

    def __init__(self, collection: str = "eduagent_knowledge") -> None:
        super().__init__(
            message=f"知识库集合 '{collection}' 不存在，请先运行 build_rag_db.py 构建",
            code="RAG_COLLECTION_NOT_FOUND",
        )
