"""Stable Pydantic response types for agent execution results and API responses.

These schemas guarantee that the frontend always receives consistent field names
and data shapes, regardless of whether the backend returns live agent output,
DB-persisted data, or mock fallback values.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Agent step execution result ────────────────────────────────────────────


class AgentStepResult(BaseModel):
    """Result of a single agent's execution within the orchestrator pipeline."""

    agent_id: str = ""
    agent_name: str = ""
    status: str = "completed"  # completed | failed | timeout | skipped
    summary: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0


# ── Agent orchestrator result ──────────────────────────────────────────────


class OrchestratorResult(BaseModel):
    """Complete result from the multi-agent orchestrator pipeline."""

    session_id: str = ""
    course_id: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    agent_steps: list[AgentStepResult] = Field(default_factory=list)
    overall_status: str = "completed"  # completed | partial | failed
    overall_error: str | None = None
    course: dict[str, Any] | None = None


# ── Agent run request ──────────────────────────────────────────────────────


class AgentRunRequest(BaseModel):
    """Request body for triggering a full multi-agent pipeline run."""

    session_id: str = Field(alias="sessionId", min_length=1)
    user_message: str = Field(default="我想学习人工智能导论")
    course_id: str | None = Field(default=None)

    class Config:
        populate_by_name = True


# ── API response envelope ──────────────────────────────────────────────────

# Re-use the existing ApiResponse from common.py for consistency.
# The schemas below define the *data* payloads used inside ApiResponse.data.


# ── Profile read response (data field of ApiResponse) ──────────────────────


class ProfileData(BaseModel):
    """Profile data returned by GET /profile and POST /profile/build."""

    id: str = ""
    nickname: str = "学习者"
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    weaknesses: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)
    createdAt: int = 0
    updatedAt: int = 0
    source: str = "none"  # agent_generated | system_inferred | none
    readiness: dict[str, Any] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    """Wrapper for profile endpoint responses."""

    profile: ProfileData = Field(default_factory=ProfileData)


# ── Learning path read response ────────────────────────────────────────────


class LearningPathData(BaseModel):
    """Learning path data returned by GET /learning-path."""

    id: str = ""
    title: str = ""
    description: str = ""
    courseName: str = ""
    courseId: str = ""
    stages: list[dict[str, Any]] = Field(default_factory=list)
    createdAt: int = 0
    overallProgress: int = 0
    estimatedDays: int = 14
    source: str = "none"  # agent_generated | system_inferred | none


class LearningPathResponse(BaseModel):
    """Wrapper for learning path endpoint responses."""

    path: LearningPathData = Field(default_factory=LearningPathData)


# ── Resource read response ─────────────────────────────────────────────────


class ResourceItemData(BaseModel):
    """Single resource item in a resource list."""

    id: str = ""
    type: str = "lecture"
    title: str = "学习资源"
    description: str = ""
    content: str = ""
    knowledgePoints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "easy"
    estimatedMinutes: int = 20
    format: str = "text"
    mermaidDef: str | None = None
    codeBlocks: list[dict[str, Any]] | None = None
    questions: list[dict[str, Any]] | None = None
    pptOutline: list[dict[str, Any]] | None = None
    createdAt: int = 0
    bookmarked: bool = False
    studyStatus: str = "new"
    source: str = "none"  # agent_generated | system_inferred | none


class ResourceListData(BaseModel):
    """Resource list returned by GET /resources."""

    resources: list[ResourceItemData] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    sessionId: str = ""


# ── Learning analytics response ────────────────────────────────────────────


class LearningAnalyticsData(BaseModel):
    """Learning analytics summary returned by GET /learning-analytics."""

    eventCount: int = 0
    totalStudyMinutes: int = 0
    activeResourceCount: int = 0
    eventBreakdown: dict[str, int] = Field(default_factory=dict)
    topResources: list[dict[str, Any]] = Field(default_factory=list)
    quizAccuracy: int | None = None
    weakTopics: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    recentEvents: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


# ── Chat response ──────────────────────────────────────────────────────────


class ChatReplyData(BaseModel):
    """Chat message reply returned by POST /chat/send."""

    id: str = ""
    role: str = "assistant"
    content: str = ""
    timestamp: int = 0


class ChatSendResponse(BaseModel):
    """Response for non-streaming chat."""

    sessionId: str = ""
    reply: ChatReplyData = Field(default_factory=ChatReplyData)
