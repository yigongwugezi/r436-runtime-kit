"""Public DTOs for canonical learning events (spec §2.2, §3.5, §3.6).

These are the stable public contracts that Analytics, Diagnosis, and
audit systems consume.  Once published, do NOT rename fields, delete
fields, or change semantics without version negotiation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgePointResultDTO(BaseModel):
    """Per-knowledge-point result computed from a single graded answer (spec §3.5).

    One instance per (question, knowledge_point) pair.  When a question
    maps to N knowledge points, N instances are produced, with scores
    weighted proportionally to the mapping weights.
    """

    knowledge_point_key: str = Field(alias="knowledgePointKey")
    knowledge_point_label: str = Field(default="", alias="knowledgePointLabel")
    question_id: str = Field(alias="questionId")
    attempt_id: str = Field(alias="attemptId")
    raw_score: float = Field(alias="rawScore")
    max_score: float = Field(alias="maxScore")
    normalized_score: float = Field(alias="normalizedScore")
    weight: float
    weighted_score: float = Field(alias="weightedScore")
    mapping_confidence: float = Field(alias="mappingConfidence")
    grading_confidence: float = Field(alias="gradingConfidence")
    is_correct: bool = Field(alias="isCorrect")
    error_type: str | None = Field(default=None, alias="errorType")
    assessment_eligible: bool = Field(alias="assessmentEligible")
    evidence_id: str | None = Field(default=None, alias="evidenceId")

    class Config:
        populate_by_name = True


class QuizResultEventDTO(BaseModel):
    """Canonical quiz/exam submission result event (spec §3.6).

    Written server-side after every successful grading.  One event per
    attempt, enforced by a DB-level unique constraint.  This is the
    authoritative source for correctness rates, per-KP mastery, and
    assessment eligibility — Analytics and Diagnosis consume it directly.
    """

    event_id: str = Field(alias="eventId")
    event_type: str = Field(default="quiz_result", alias="eventType")
    idempotency_key: str = Field(alias="idempotencyKey")
    learner_id: str = Field(alias="learnerId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    session_id: str = Field(alias="sessionId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    section_id: str | None = Field(default=None, alias="sectionId")
    quiz_id: str = Field(alias="quizId")
    attempt_id: str = Field(alias="attemptId")
    total_score: int = Field(alias="totalScore")
    max_score: int = Field(alias="maxScore")
    normalized_score: float = Field(alias="normalizedScore")
    assessment_eligible: bool = Field(alias="assessmentEligible")
    knowledge_point_results: list[KnowledgePointResultDTO] = Field(
        default_factory=list, alias="knowledgePointResults",
    )
    occurred_at: str = Field(alias="occurredAt")
    source: str = Field(default="server")
    schema_version: str = Field(default="1.0", alias="schemaVersion")

    class Config:
        populate_by_name = True
