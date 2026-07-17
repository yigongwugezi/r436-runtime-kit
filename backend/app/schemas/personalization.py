"""Public DTO for personalization context (spec §2.2, §5).

This is the stable public contract that all resource generation entry
points consume.  Once published, do NOT rename fields, delete fields,
or change semantics without version negotiation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PersonalizationContextDTO(BaseModel):
    """Unified personalization context for resource generation and recommendation.

    Provides a single, versioned snapshot of all learner data that should
    influence what resources are generated or recommended.  All resource
    entry points read this context through ``PersonalizationContextService``
    so that Profile, Analytics, and Resource share the same view.
    """

    learner_id: str = Field(alias="learnerId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    session_id: str = Field(alias="sessionId")

    # ── Version tracking ──────────────────────────────────────────
    profile_version: int | None = Field(default=None, alias="profileVersion")
    diagnosis_version: int | None = Field(default=None, alias="diagnosisVersion")

    # ── Stable preferences (cross-session) ────────────────────────
    stable_preferences: dict = Field(default_factory=dict, alias="stablePreferences")
    subject_preferences: dict = Field(default_factory=dict, alias="subjectPreferences")

    # ── Current mastery & weaknesses ──────────────────────────────
    mastery: list[dict] = Field(default_factory=list)
    weaknesses: list[dict] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)

    # ── Goal & path context ───────────────────────────────────────
    target_goal: str | None = Field(default=None, alias="targetGoal")
    path_context: dict | None = Field(default=None, alias="pathContext")
    stage_context: dict | None = Field(default=None, alias="stageContext")
    chapter_context: dict | None = Field(default=None, alias="chapterContext")
    section_context: dict | None = Field(default=None, alias="sectionContext")

    # ── Resource dedup & type hint ─────────────────────────────────
    prior_resource_ids: list[str] = Field(default_factory=list, alias="priorResourceIds")
    requested_resource_type: str | None = Field(
        default=None, alias="requestedResourceType",
    )

    class Config:
        populate_by_name = True
