"""Structured application exception hierarchy.

All application-level exceptions inherit from :class:`AppError`.
The global exception handler in ``main.py`` converts these into
consistent, safe-to-expose JSON error responses.

.. versionadded:: 0.5.0
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error with structured, safe-to-expose payload.

    Attributes:
        message:     Human-readable error description (safe to show to users).
        code:        Machine-readable error code (e.g. ``"VALIDATION_ERROR"``).
        status_code: HTTP status code to return.
        is_user_error: ``True`` when the error is caused by user input (4xx),
                       ``False`` for system/infrastructure errors (5xx).
        cause:       Original exception for server-side logging (never exposed).
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        is_user_error: bool = False,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.is_user_error = is_user_error
        self.cause = cause

    def to_response_dict(self) -> dict[str, Any]:
        """Build a response dict compatible with both the ProductApiResponse
        envelope and the frontend Axios interceptor's error parser."""
        return {
            "status": "error",
            "data": None,
            "message": self.message,
            "detail": self.message,  # backward-compat: frontend checks body.detail
            "code": self.code,
            "is_user_error": self.is_user_error,
            "sessionId": "",
            "subjectId": "",
        }


# ── User-input errors (4xx) ─────────────────────────────────────────────


class ValidationError(AppError):
    """Invalid or missing user input — always the caller's responsibility."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "VALIDATION_ERROR",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=422,
            is_user_error=True,
            cause=cause,
        )


class MissingSessionIdError(ValidationError):
    """``sessionId`` is missing or empty in the request."""

    def __init__(self) -> None:
        super().__init__(
            message="sessionId 不能为空",
            code="MISSING_SESSION_ID",
        )


class MissingSubjectIdError(ValidationError):
    """``subjectId`` is missing or empty when required."""

    def __init__(self) -> None:
        super().__init__(
            message="subjectId 不能为空",
            code="MISSING_SUBJECT_ID",
        )


class InvalidEventTypeError(ValidationError):
    """``event_type`` is not in the set of allowed event types."""

    def __init__(self, event_type: str) -> None:
        super().__init__(
            message=f"不支持的事件类型: {event_type}",
            code="INVALID_EVENT_TYPE",
        )


class NotFoundError(AppError):
    """Requested resource does not exist."""

    def __init__(
        self,
        message: str,
        *,
        resource: str = "",
        resource_id: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            is_user_error=True,
            cause=cause,
        )
        self.resource = resource
        self.resource_id = resource_id

    def to_response_dict(self) -> dict[str, Any]:
        d = super().to_response_dict()
        d["resource"] = self.resource
        d["resource_id"] = self.resource_id
        return d


# ── System / infrastructure errors (5xx) ─────────────────────────────────


class AgentPipelineError(AppError):
    """One or more agents in the pipeline failed unrecoverably."""

    def __init__(
        self,
        message: str,
        *,
        agent_id: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="AGENT_FAILURE",
            status_code=500,
            is_user_error=False,
            cause=cause,
        )
        self.agent_id = agent_id


class LLMServiceError(AppError):
    """LLM provider is unavailable or returned an unrecoverable error."""

    def __init__(
        self,
        message: str = "LLM 服务暂不可用，已使用规则兜底",
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="LLM_SERVICE_ERROR",
            status_code=503,
            is_user_error=False,
            cause=cause,
        )


class DatabaseError(AppError):
    """Database operation failed."""

    def __init__(
        self,
        message: str = "数据操作失败，请稍后重试",
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DB_ERROR",
            status_code=500,
            is_user_error=False,
            cause=cause,
        )
