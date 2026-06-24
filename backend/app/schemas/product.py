"""Product API unified response envelope.

Provides the ``ProductApiResponse`` envelope used by all product-facing
endpoints to guarantee a consistent response structure for the frontend.

.. versionadded:: 0.4.0
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ProductApiResponse(BaseModel, Generic[T]):
    """Unified response envelope for all Product API endpoints.

    Fields:
        status:       ``"success"`` or ``"error"``.
        data:         The endpoint-specific payload (same shape as before the envelope).
        message:      Human-readable result description.
        warnings:     Non-blocking advisory messages for the frontend.
        source:       Provenance indicator (``"db"``, ``"agent"``, ``"user_action"``, …).
        sessionId:    Data ownership key from the request.
        subjectId:    Course context key from the request (may be empty).
        code:         Machine-readable error code (only set on errors, e.g. ``"MISSING_SESSION_ID"``).
        is_user_error: ``True`` for user-input errors (4xx), ``False`` for system errors (5xx).
    """

    status: str = "success"
    data: T
    message: str = "success"
    warnings: list[str] = Field(default_factory=list)
    source: str = "runtime_kit"
    sessionId: str = ""
    subjectId: str = ""
    code: str | None = Field(default=None)
    is_user_error: bool | None = Field(default=None)
