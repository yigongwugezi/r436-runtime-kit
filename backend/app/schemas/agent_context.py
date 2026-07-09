"""Pydantic models for agent execution context — structured type contracts between agents.

These models describe the expected input and output shapes for each agent in the pipeline.
They serve as documentation and optional validation; agents are NOT required to use them
at runtime unless ``validate_context=True`` is passed (future increment).

Usage::

    from app.schemas.agent_context import ProfileAgentInput, ProfileAgentOutput
    # Optional validation:
    # validated = ProfileAgentInput.model_validate(context)
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Shared dimension/item types ────────────────────────────────────────────

class ProfileDimension(BaseModel):
    """A single dimension of the student profile."""
    key: str = ""
    label: str = ""
    value: str = ""
    score: int = 50
    confidence: float = 0.5
    explanation: str = ""
    evidence: str = ""
    source: str = "inferred"


class KnowledgePoint(BaseModel):
    """A single knowledge point retrieved from RAG or course catalog."""
    point_id: str = ""
    chapter_id: str = ""
    name: str = ""
    priority: str = "medium"
    difficulty: str = "medium"
    content_excerpt: str = ""


class WeakKnowledgePoint(BaseModel):
    """A weakness identified by the diagnosis agent."""
    name: str = ""
    priority: str = "medium"
    reason: str = ""
    evidence: str = ""
    confidence: float = 0.5


class StageItem(BaseModel):
    """A single stage in a learning path."""
    stage_id: str = ""
    title: str = ""
    description: str = ""
    goal: str = ""
    duration: str = ""
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    estimated_days: int = 1
    resource_types: list[str] = Field(default_factory=list)


class ResourceItem(BaseModel):
    """A single generated learning resource."""
    resource_id: str = ""
    type: str = "lecture"
    title: str = ""
    content: str = ""
    related_stage_id: str = ""
    source: str = "agent_generated"
    format: str = "markdown"
    difficulty: str = "medium"
    quality_status: str = "passed"


# ── Agent Input Models ─────────────────────────────────────────────────────


class ConversationAgentInput(BaseModel):
    """Input context for ConversationAgent (intent or final_reply mode)."""
    mode: str = "intent"
    user_message: str = ""
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    last_proposal: Optional[str] = None
    pipeline_result: Optional[dict[str, Any]] = None
    profile: Optional[dict[str, Any]] = None


class ProfileAgentInput(BaseModel):
    """Input context for ProfileAgent."""
    user_message: str = ""
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    course_id: str = ""
    diagnosis: Optional[dict[str, Any]] = None


class KnowledgeAgentInput(BaseModel):
    """Input context for KnowledgeAgent."""
    user_message: str = ""
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    course_id: str = ""
    profile: Optional[dict[str, Any]] = None


class DiagnosisAgentInput(BaseModel):
    """Input context for DiagnosisAgent."""
    user_message: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    analytics: Optional[dict[str, Any]] = None
    diagnosis: Optional[dict[str, Any]] = None
    mode: str = "standard"
    previous_grades: list[dict[str, Any]] = Field(default_factory=list)


class PlannerAgentInput(BaseModel):
    """Input context for PlannerAgent."""
    user_message: str = ""
    course_id: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    existing_path: Optional[list[dict[str, Any]]] = None
    mode: str = "plan"
    profile_facts: dict[str, Any] = Field(default_factory=dict)


class ResourceAgentInput(BaseModel):
    """Input context for ResourceAgent."""
    user_message: str = ""
    course_id: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""


class QuestionAgentInput(BaseModel):
    """Input context for QuestionAgent."""
    user_message: str = ""
    course_id: str = ""
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str = ""


class ReviewAgentInput(BaseModel):
    """Input context for ReviewAgent."""
    profile: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    course_id: str = ""


class GradingAgentInput(BaseModel):
    """Input context for GradingAgent."""
    session_id: str = ""
    question: dict[str, Any] = Field(default_factory=dict)
    student_answer: str = ""
    profile_facts: dict[str, Any] = Field(default_factory=dict)


# ── Pipeline State (what flows through LangGraph nodes) ────────────────────


class PipelineState(BaseModel):
    """Shared state dict passed between agents in the LangGraph pipeline.

    This model documents all keys that may be present in the state dict.
    It uses ``extra="allow"`` so that intermediate/internal keys (e.g.,
    ``_retry_count``, ``_conversation_reply``) are tolerated.
    """
    model_config = {"extra": "allow"}

    # Input
    session_id: str = ""
    user_message: str = ""
    course_id: str = ""
    intent: str = ""
    messages: list[dict[str, str]] = Field(default_factory=list)

    # Agent outputs (populated sequentially)
    profile: dict[str, Any] = Field(default_factory=dict)
    profile_facts: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    learning_path: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    review: dict[str, Any] = Field(default_factory=dict)
    grading_result: Optional[dict[str, Any]] = None

    # Execution metadata
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_executed: bool = False
    overall_status: str = ""

    # Output
    final_reply: str = ""
