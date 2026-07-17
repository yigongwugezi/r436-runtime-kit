"""Public DTOs for diagnosis snapshots and evidence (spec §2.2, §4.3).

These are the stable public contracts that Profile, Analytics, Resource,
and guided-path modules consume.  Once published, do NOT rename fields,
delete fields, or change semantics without version negotiation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnosisEvidenceDTO(BaseModel):
    """A single piece of evidence backing a diagnosis conclusion (spec §4.2)."""

    evidence_id: str = Field(alias="evidenceId")
    diagnosis_snapshot_id: str = Field(alias="diagnosisSnapshotId")
    learner_id: str = Field(alias="learnerId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    knowledge_point_key: str = Field(alias="knowledgePointKey")
    evidence_type: str = Field(default="quiz_answer", alias="evidenceType")
    attempt_id: str | None = Field(default=None, alias="attemptId")
    question_id: str | None = Field(default=None, alias="questionId")
    learning_event_id: str | None = Field(default=None, alias="learningEventId")
    resource_id: str | None = Field(default=None, alias="resourceId")
    score: float | None = Field(default=None)
    weight: float | None = Field(default=None)
    confidence: float | None = Field(default=None)
    occurred_at: str | None = Field(default=None, alias="occurredAt")

    class Config:
        populate_by_name = True


class MasteryItemDTO(BaseModel):
    """Per-knowledge-point mastery level entry (spec §4.3)."""

    knowledge_point_key: str = Field(alias="knowledgePointKey")
    label: str = ""
    score: float = 0.0
    confidence: float = 0.0
    evidence_count: int = Field(default=0, alias="evidenceCount")
    trend: str = "stable"  # improving | declining | stable
    updated_at: str | None = Field(default=None, alias="updatedAt")

    class Config:
        populate_by_name = True


class WeaknessItemDTO(BaseModel):
    """Per-knowledge-point weakness entry (spec §4.3)."""

    knowledge_point_key: str = Field(alias="knowledgePointKey")
    severity: str = "medium"  # high | medium | low
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    recommended_action: str | None = Field(default=None, alias="recommendedAction")

    class Config:
        populate_by_name = True


class DiagnosisSnapshotDTO(BaseModel):
    """Versioned diagnosis snapshot — the unified fact source (spec §4.3).

    Profile, Analytics, and Resource modules all read the same snapshot
    identified by (learnerId, subjectId, version).
    """

    id: str = Field(alias="id")
    learner_id: str = Field(alias="learnerId")
    subject_id: str = Field(default="", alias="subjectId")
    session_id: str = Field(alias="sessionId")
    version: int
    status: str  # ready | generating | failed | superseded
    mastery: list[MasteryItemDTO] = Field(default_factory=list)
    weaknesses: list[WeaknessItemDTO] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    confidence: float | None = None
    evidence_summary: dict = Field(default_factory=dict, alias="evidenceSummary")
    source_attempt_ids: list[str] = Field(default_factory=list, alias="sourceAttemptIds")
    source_event_ids: list[str] = Field(default_factory=list, alias="sourceEventIds")
    created_at: str = Field(alias="createdAt")

    class Config:
        populate_by_name = True
