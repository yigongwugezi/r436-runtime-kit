"""Personalization context service — unified entry point for resource generation.

All resource generation entry points call ``build_context()`` to obtain
a consistent, versioned snapshot of learner data.  The service reads from
the persistent diagnosis snapshot (Commit 4), profile data, preferences,
and path context — falling back to ``conversation_store`` when DB data
is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal
from app.db.models import (
    DiagnosisSnapshotModel,
    LearningPathModel,
    ProfileSnapshotModel,
    ResourceModel,
    SessionModel,
    LearnerModel,
)

logger = logging.getLogger(__name__)


class PersonalizationContextService:
    """Builds a ``PersonalizationContextDTO``-shaped dict from persistent data."""

    def build(
        self,
        session_id: str,
        *,
        subject_id: str | None = None,
        path_id: str | None = None,
        stage_id: str | None = None,
        chapter_id: str | None = None,
        section_id: str | None = None,
        requested_resource_type: str | None = None,
    ) -> dict:
        """Assemble the personalization context for a session.

        Returns a dict suitable for serialisation as ``PersonalizationContextDTO``.
        """
        db = SessionLocal()
        try:
            ctx = self._build(db, session_id, subject_id,
                              path_id, stage_id, chapter_id, section_id,
                              requested_resource_type)
            return ctx
        finally:
            db.close()

    def _build(
        self,
        db: Session,
        session_id: str,
        subject_id: str | None,
        path_id: str | None,
        stage_id: str | None,
        chapter_id: str | None,
        section_id: str | None,
        requested_resource_type: str | None,
    ) -> dict:
        # ── Resolve learner + subject from session ────────────────
        sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        learner_id = sess.learner_id if sess else ""
        if not learner_id:
            # Fallback: try conversation_store
            try:
                from app.services.conversation_state import conversation_store
                cs = conversation_store.get(session_id)
                if cs and cs.last_result:
                    learner_id = cs.last_result.get("learner_id", "")
            except Exception:
                pass
        subj = subject_id or (sess.subject_id if sess else "")

        # ── Diagnosis ─────────────────────────────────────────────
        diagnosis_version: int | None = None
        mastery: list[dict] = []
        weaknesses: list[dict] = []
        strengths: list[str] = []
        try:
            snap = (
                db.query(DiagnosisSnapshotModel)
                .filter(
                    DiagnosisSnapshotModel.learner_id == learner_id,
                    DiagnosisSnapshotModel.subject_id == subj,
                    DiagnosisSnapshotModel.status == "ready",
                )
                .order_by(DiagnosisSnapshotModel.version.desc())
                .first()
            )
            if snap:
                diagnosis_version = snap.version
                mastery = snap.mastery_levels or []
                weaknesses = snap.weaknesses or []
                strengths = snap.strengths or []
        except Exception:
            logger.debug("No diagnosis snapshot for %s/%s", learner_id, subj)

        # ── Profile ───────────────────────────────────────────────
        profile_version: int | None = None
        stable_prefs: dict = {}
        subject_prefs: dict = {}
        target_goal: str | None = None

        # Try DB profile first
        try:
            profile = (
                db.query(ProfileSnapshotModel)
                .filter(ProfileSnapshotModel.session_id == session_id)
                .order_by(ProfileSnapshotModel.created_at.desc())
                .first()
            )
            if profile and profile.preferences:
                prefs = profile.preferences or {}
                subject_prefs = dict(prefs)
                pv2 = prefs.get("profile_v2", {})
                if pv2 and isinstance(pv2, dict):
                    profile_version = pv2.get("profile_version")
                    sc = pv2.get("subject_context", {})
                    if isinstance(sc, dict):
                        target_goal = sc.get("learning_goal")
                        subject_prefs["contentPreferences"] = sc.get("content_preferences", [])
                        subject_prefs["resourcePreferences"] = sc.get("resource_preferences", [])
        except Exception:
            logger.debug("No DB profile for session=%s", session_id)

        # Fallback: conversation_store
        if not subject_prefs:
            try:
                from app.services.conversation_state import conversation_store
                cs = conversation_store.get(session_id)
                if cs and cs.last_result:
                    cached = cs.last_result
                    prefs = cached.get("preferences", {}) or {}
                    subject_prefs = dict(prefs) if isinstance(prefs, dict) else {}
                    target_goal = target_goal or cs.facts.get("target_course") or cs.facts.get("learning_goal")
                    if cs.facts.get("preference"):
                        subject_prefs.setdefault("preferredFormats",
                                                  [cs.facts["preference"]])
            except Exception:
                pass

        # ── Stable preferences from LearnerModel ─────────────────
        try:
            learner = db.query(LearnerModel).filter(LearnerModel.id == learner_id).first()
            if learner:
                stable_prefs = {
                    "grade": learner.grade,
                    "targetExam": learner.target_exam,
                    "school": learner.school,
                }
                stable_prefs = {k: v for k, v in stable_prefs.items() if v}
        except Exception:
            pass

        # ── Path context ──────────────────────────────────────────
        path_ctx: dict | None = None
        stage_ctx: dict | None = None
        chapter_ctx: dict | None = None
        section_ctx: dict | None = None
        try:
            if path_id:
                lp = db.get(LearningPathModel, path_id)
                if lp and lp.stages:
                    path_ctx = {"id": lp.id, "courseName": lp.course_name,
                                "stages": lp.stages}
            if stage_id and path_ctx:
                for st in (path_ctx.get("stages") or []):
                    if st.get("stage_id") == stage_id:
                        stage_ctx = dict(st)
                        break
        except Exception:
            pass

        if chapter_id:
            chapter_ctx = {"id": chapter_id}
        if section_id:
            section_ctx = {"id": section_id}

        # ── Prior resources ───────────────────────────────────────
        prior_ids: list[str] = []
        try:
            resources = (
                db.query(ResourceModel)
                .filter(ResourceModel.session_id == session_id)
                .order_by(ResourceModel.created_at.desc())
                .limit(50)
                .all()
            )
            prior_ids = [r.id for r in resources]
        except Exception:
            pass

        return {
            "learnerId": learner_id,
            "subjectId": subj,
            "sessionId": session_id,
            "profileVersion": profile_version,
            "diagnosisVersion": diagnosis_version,
            "stablePreferences": stable_prefs,
            "subjectPreferences": subject_prefs,
            "mastery": mastery,
            "weaknesses": weaknesses,
            "strengths": strengths,
            "targetGoal": target_goal,
            "pathContext": path_ctx,
            "stageContext": stage_ctx,
            "chapterContext": chapter_ctx,
            "sectionContext": section_ctx,
            "priorResourceIds": prior_ids,
            "requestedResourceType": requested_resource_type,
        }
