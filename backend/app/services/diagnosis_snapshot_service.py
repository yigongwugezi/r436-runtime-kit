"""Diagnosis snapshot persistence and unified query service (spec §4).

Provides the bridge between ``DiagnosisAgent`` output and the persistent
``DiagnosisSnapshotModel`` + ``DiagnosisEvidenceModel`` tables.  All
consumers (Profile, Analytics, Resource) should query diagnosis through
this service to ensure they read the same version.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    DiagnosisSnapshotModel,
    LearnerModel,
    SessionModel,
)
from app.db.repository import (
    collect_evidence_from_events,
    create_diagnosis_evidence,
    create_diagnosis_snapshot,
    get_evidence_for_snapshot,
    get_latest_diagnosis_snapshot,
    get_next_diagnosis_version,
    supersede_snapshots,
)

logger = logging.getLogger(__name__)


def persist_diagnosis_result(
    db: Session,
    *,
    learner_id: str,
    subject_id: str | None,
    session_id: str,
    diagnosis_result: dict,
    source_attempt_ids: list[str] | None = None,
    source_event_ids: list[str] | None = None,
    generated_by: str = "diagnosis_agent",
    active_task_id: str | None = None,
) -> DiagnosisSnapshotModel:
    """Persist a DiagnosisAgent result as a new versioned snapshot.

    Steps:
    1. Compute next version for (learner_id, subject_id)
    2. Supersede previous ready snapshots
    3. Create DiagnosisSnapshotModel
    4. Collect + create DiagnosisEvidence rows
    5. Flush and return the snapshot

    Args:
        db: Active DB session (caller manages commit).
        learner_id: The learner this diagnosis belongs to.
        subject_id: Subject scope (nullable for legacy sessions).
        session_id: The session that triggered this diagnosis.
        diagnosis_result: Raw dict from ``DiagnosisAgent.run()``.
        source_attempt_ids: Attempt IDs that contributed to this diagnosis.
        source_event_ids: LearningEvent IDs that contributed.
        generated_by: Agent identifier.
        active_task_id: Workflow task ID (populated in commit 9).

    Returns:
        The newly created ``DiagnosisSnapshotModel`` (flushed but not committed).
    """
    attempt_ids = list(source_attempt_ids or [])
    event_ids = list(source_event_ids or [])

    # ── Version ──────────────────────────────────────────────────
    subj = subject_id or ""
    version = get_next_diagnosis_version(db, learner_id, subj)

    # ── Supersede old snapshots ──────────────────────────────────
    supersede_snapshots(db, learner_id, subj)

    # ── Extract fields from diagnosis_result ─────────────────────
    mastery = diagnosis_result.get("mastery_levels") or []
    weaknesses = diagnosis_result.get("weak_knowledge_points") or diagnosis_result.get("weak_topics") or []
    strengths = diagnosis_result.get("strengths") or []
    confidence = diagnosis_result.get("confidence") or diagnosis_result.get("diagnosis_confidence")
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
    else:
        confidence = None
    summary_text = diagnosis_result.get("summary") or diagnosis_result.get("diagnosis_summary") or ""

    snapshot_id = f"ds_{uuid.uuid4().hex[:12]}"

    # ── Create snapshot ──────────────────────────────────────────
    snapshot = create_diagnosis_snapshot(
        db,
        diagnosis_snapshot_id=snapshot_id,
        learner_id=learner_id,
        subject_id=subj,
        session_id=session_id,
        version=version,
        status="ready",
        mastery_levels=mastery,
        weaknesses=weaknesses,
        strengths=strengths if isinstance(strengths, list) else [],
        confidence=confidence,
        summary=summary_text,
        source_attempt_ids=attempt_ids,
        source_event_ids=event_ids,
        evidence_count=0,  # updated below
        generated_by=generated_by,
        active_task_id=active_task_id,
    )

    # ── Collect + create evidence ────────────────────────────────
    evidence_records = collect_evidence_from_events(
        db, learner_id, subj, event_ids, attempt_ids,
    )
    for ev_dict in evidence_records:
        create_diagnosis_evidence(
            db,
            evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
            diagnosis_snapshot_id=snapshot_id,
            learner_id=learner_id,
            subject_id=subj,
            **{k: v for k, v in ev_dict.items()
               if k != "metadata_"},
            metadata_=ev_dict.get("metadata_"),
        )

    snapshot.evidence_count = len(evidence_records)
    db.flush()

    logger.info(
        "Diagnosis snapshot persisted: id=%s learner=%s subject=%s v%d evidence=%d",
        snapshot_id, learner_id, subj, version, snapshot.evidence_count,
    )
    return snapshot


def get_latest_snapshot(
    db: Session, learner_id: str, subject_id: str,
) -> DiagnosisSnapshotModel | None:
    """Return the latest ready snapshot for a (learner, subject) pair."""
    return get_latest_diagnosis_snapshot(db, learner_id, subject_id)


def get_latest_for_session(
    db: Session, session_id: str,
) -> DiagnosisSnapshotModel | None:
    """Return the latest ready snapshot for the learner+subject of a session.

    Resolves learner_id and subject_id from the session first.
    """
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess or not sess.learner_id:
        return None
    return get_latest_diagnosis_snapshot(
        db, sess.learner_id, sess.subject_id or "",
    )


def snapshot_to_dict(snapshot: DiagnosisSnapshotModel) -> dict:
    """Convert a DiagnosisSnapshotModel to a dict suitable for JSON serialisation.

    This is a lightweight serialisation — for the full public DTO see
    ``app.schemas.diagnosis.DiagnosisSnapshotDTO``.
    """
    return {
        "id": snapshot.diagnosis_snapshot_id,
        "learnerId": snapshot.learner_id,
        "subjectId": snapshot.subject_id,
        "sessionId": snapshot.session_id,
        "version": snapshot.version,
        "status": snapshot.status,
        "mastery": snapshot.mastery_levels or [],
        "weaknesses": snapshot.weaknesses or [],
        "strengths": snapshot.strengths or [],
        "confidence": snapshot.confidence,
        "summary": snapshot.summary,
        "evidenceCount": snapshot.evidence_count,
        "sourceAttemptIds": snapshot.source_attempt_ids or [],
        "sourceEventIds": snapshot.source_event_ids or [],
        "generatedBy": snapshot.generated_by,
        "createdAt": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def snapshot_to_dto_dict(snapshot: DiagnosisSnapshotModel) -> dict:
    """Convert a snapshot to the DiagnosisSnapshotDTO shape.

    Mastery items are adapted from the stored mastery_levels JSON
    into the public DTO field names.
    """
    mastery_dto = []
    for m in (snapshot.mastery_levels or []):
        if isinstance(m, dict):
            mastery_dto.append({
                "knowledgePointKey": m.get("name", m.get("knowledgePointKey", "")),
                "label": m.get("name", m.get("knowledgePointKey", "")),
                "score": float(m.get("score", 0)),
                "confidence": float(m.get("confidence", 0)),
                "evidenceCount": int(m.get("evidence_count", m.get("evidenceCount", 0))),
                "trend": str(m.get("trend", "stable")),
                "updatedAt": m.get("last_updated", m.get("updatedAt")),
            })

    weakness_dto = []
    for w in (snapshot.weaknesses or []):
        if isinstance(w, dict):
            weakness_dto.append({
                "knowledgePointKey": w.get("name", w.get("knowledgePointKey", "")),
                "severity": w.get("priority", w.get("severity", "medium")),
                "reason": str(w.get("reason", "")),
                "evidenceIds": w.get("evidenceIds", []),
                "recommendedAction": w.get("recommended_action", w.get("suggested_action")),
            })

    return {
        "id": snapshot.diagnosis_snapshot_id,
        "learnerId": snapshot.learner_id,
        "subjectId": snapshot.subject_id,
        "sessionId": snapshot.session_id,
        "version": snapshot.version,
        "status": snapshot.status,
        "mastery": mastery_dto,
        "weaknesses": weakness_dto,
        "strengths": snapshot.strengths or [],
        "confidence": snapshot.confidence,
        "evidenceSummary": {
            "total": snapshot.evidence_count,
            "byType": {},
        },
        "sourceAttemptIds": snapshot.source_attempt_ids or [],
        "sourceEventIds": snapshot.source_event_ids or [],
        "createdAt": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def try_get_diagnosis(
    db: Session,
    learner_id: str | None,
    subject_id: str | None,
    session_id: str | None = None,
) -> dict | None:
    """Try to get the latest diagnosis from DB.

    Returns a dict in the DiagnosisSnapshotDTO shape, or None if no
    snapshot exists.  Callers should fall back to conversation_store
    when None is returned.
    """
    if not learner_id:
        # Try resolving from session
        if session_id:
            sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if sess:
                learner_id = sess.learner_id
                subject_id = subject_id or sess.subject_id
        if not learner_id:
            return None

    subj = subject_id or ""
    snapshot = get_latest_diagnosis_snapshot(db, learner_id, subj)
    if snapshot is None:
        return None

    return snapshot_to_dto_dict(snapshot)
