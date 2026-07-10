"""Pydantic schemas for quiz, exam-set and attempt data models.

These schemas power the assessment REST API and serve as the
type contract between backend routers and the frontend client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
# Shared / enum types
# ═══════════════════════════════════════════════════════════════════════

SCOPE_TYPES_QUIZ = {"knowledge_point", "section", "chapter", "stage", "path"}
SCOPE_TYPES_EXAM = {"chapter", "stage", "path"}
ATTEMPT_STATUSES = {"in_progress", "submitted", "graded"}
EXAM_SET_STATUSES = {"not_started", "in_progress", "completed"}


# ═══════════════════════════════════════════════════════════════════════
# Quiz
# ═══════════════════════════════════════════════════════════════════════


class QuizCreate(BaseModel):
    """Payload for creating a new instant quiz."""

    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: str = Field(default="knowledge_point", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    section_id: str | None = Field(default=None, alias="sectionId")
    knowledge_point_ids: list[str] | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    questions: list[dict[str, Any]] | None = None
    source: str = "llm_generated"


class QuizResponse(BaseModel):
    """Serialised QuizModel returned to the frontend."""

    id: str = ""
    title: str = ""
    session_id: str = Field(default="", alias="sessionId")
    scope_type: str = Field(default="knowledge_point", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    section_id: str | None = Field(default=None, alias="sectionId")
    knowledge_point_ids: list | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    question_count: int = Field(default=0, alias="questionCount")
    questions: list | None = None
    source: str = "llm_generated"
    archive_policy: str = Field(default="none", alias="archivePolicy")
    created_at: str | None = Field(default=None, alias="createdAt")


# ═══════════════════════════════════════════════════════════════════════
# Exam Set
# ═══════════════════════════════════════════════════════════════════════


class ExamSetCreate(BaseModel):
    """Payload for creating a new exam set."""

    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: str = Field(default="chapter", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    knowledge_point_ids: list[str] | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    difficulty_distribution: dict[str, int] | None = Field(default=None, alias="difficultyDistribution")
    question_count: int = Field(default=0, alias="questionCount")
    questions: list[dict[str, Any]] | None = None
    estimated_minutes: int = Field(default=30, alias="estimatedMinutes")
    total_score: int = Field(default=100, alias="totalScore")
    source: str = "llm_generated"
    archive_policy: str = Field(default="archive", alias="archivePolicy")


class ExamSetUpdate(BaseModel):
    """Payload for updating an exam set (partial update)."""

    title: str | None = None
    status: str | None = None
    question_count: int | None = Field(default=None, alias="questionCount")
    questions: list[dict[str, Any]] | None = None
    difficulty_distribution: dict[str, int] | None = Field(default=None, alias="difficultyDistribution")
    estimated_minutes: int | None = Field(default=None, alias="estimatedMinutes")
    total_score: int | None = Field(default=None, alias="totalScore")


class ExamSetResponse(BaseModel):
    """Serialised ExamSetModel returned to the frontend."""

    id: str = ""
    title: str = ""
    session_id: str = Field(default="", alias="sessionId")
    scope_type: str = Field(default="chapter", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    knowledge_point_ids: list | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    difficulty_distribution: dict | None = Field(default=None, alias="difficultyDistribution")
    question_count: int = Field(default=0, alias="questionCount")
    questions: list | None = None
    estimated_minutes: int = Field(default=30, alias="estimatedMinutes")
    total_score: int = Field(default=100, alias="totalScore")
    status: str = "not_started"
    source: str = "llm_generated"
    archive_policy: str = Field(default="archive", alias="archivePolicy")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


# ═══════════════════════════════════════════════════════════════════════
# Attempt
# ═══════════════════════════════════════════════════════════════════════


class AttemptCreate(BaseModel):
    """Payload for starting a new attempt on a quiz or exam set."""

    session_id: str = Field(default="", alias="sessionId")
    quiz_id: str | None = Field(default=None, alias="quizId")
    exam_set_id: str | None = Field(default=None, alias="examSetId")
    max_score: int = Field(default=100, alias="maxScore")


class AttemptUpdate(BaseModel):
    """Payload for updating an in-progress attempt (e.g. saving progress)."""

    answers: list[dict[str, Any]] | None = None
    status: str | None = None


class AttemptSubmit(BaseModel):
    """Payload for submitting an attempt for grading."""

    answers: list[dict[str, Any]] = Field(default_factory=list)
    total_score: int | None = Field(default=None, alias="totalScore")


class AttemptResponse(BaseModel):
    """Serialised AttemptModel returned to the frontend."""

    id: int = 0
    attempt_id: str = Field(default="", alias="attemptId")
    session_id: str = Field(default="", alias="sessionId")
    quiz_id: str | None = Field(default=None, alias="quizId")
    exam_set_id: str | None = Field(default=None, alias="examSetId")
    learner_id: str | None = Field(default=None, alias="learnerId")
    answers: list | None = None
    total_score: int | None = Field(default=None, alias="totalScore")
    max_score: int = Field(default=100, alias="maxScore")
    status: str = "in_progress"
    started_at: str | None = Field(default=None, alias="startedAt")
    submitted_at: str | None = Field(default=None, alias="submittedAt")
    created_at: str | None = Field(default=None, alias="createdAt")
