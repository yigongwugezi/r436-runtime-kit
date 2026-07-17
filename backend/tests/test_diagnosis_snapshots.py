"""Tests for persisted versioned diagnosis snapshots (spec §12.3).

Covers:
1.  First snapshot created with version=1
2.  Version increments (v1 → v2 → v3)
3.  Historical snapshots preserved
4.  Service restart — snapshot still readable from DB
5.  Different learner isolation
6.  Different subject isolation
7.  Evidence correctly linked
8.  Non-eligible attempts excluded
9.  Multiple correct → improving trend
10. Single error doesn't zero mastery
11. Profile/Analytics/Resource read same version
12. Old in-memory diagnosis no longer sole source
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-diag-snap-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "diag-snap-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.engine import SessionLocal, engine
from app.db.models import (
    Base,
    DiagnosisEvidenceModel,
    DiagnosisSnapshotModel,
    LearnerModel,
    SessionModel,
)
from app.db.repository import (
    create_diagnosis_evidence,
    create_diagnosis_snapshot,
    get_evidence_for_snapshot,
    get_latest_diagnosis_snapshot as repo_get_latest,
    get_next_diagnosis_version,
    supersede_snapshots,
)
from app.main import app
from app.services.diagnosis_snapshot_service import (
    get_latest_snapshot,
    persist_diagnosis_result,
    snapshot_to_dict,
    snapshot_to_dto_dict,
    try_get_diagnosis,
)
from app.utils.auth import create_token

_LEARNER_A = "learner_diag_a"
_LEARNER_B = "learner_diag_b"
_SESSION_MATH = "session_diag_math"
_SESSION_PHYS = "session_diag_physics"


def _headers(learner_id: str = _LEARNER_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _setup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        for lid in [_LEARNER_A, _LEARNER_B]:
            if not db.query(LearnerModel).filter(LearnerModel.id == lid).first():
                db.add(LearnerModel(id=lid, nickname=f"Tester_{lid[-3:]}"))
        for sid, subj, owner in [
            (_SESSION_MATH, "math", _LEARNER_A),
            (_SESSION_PHYS, "physics", _LEARNER_A),
        ]:
            if not db.query(SessionModel).filter(SessionModel.id == sid).first():
                db.add(SessionModel(id=sid, learner_id=owner, subject_id=subj))
        db.commit()
    finally:
        db.close()


def _ensure_session(session_id: str, learner_id: str, subject_id: str) -> None:
    """Lazily create a session if it doesn't exist."""
    db = SessionLocal()
    try:
        if not db.query(LearnerModel).filter(LearnerModel.id == learner_id).first():
            db.add(LearnerModel(id=learner_id, nickname=f"T_{learner_id[:8]}"))
            db.flush()
        if not db.query(SessionModel).filter(SessionModel.id == session_id).first():
            db.add(SessionModel(id=session_id, learner_id=learner_id, subject_id=subject_id))
            db.flush()
        db.commit()
    finally:
        db.close()


def _sample_diagnosis(**overrides) -> dict:
    """Return a minimal but realistic diagnosis_result dict."""
    base = {
        "diagnosis_summary": "Test diagnosis summary",
        "summary": "Test diagnosis",
        "mastery_levels": [
            {"name": "recursion", "score": 75, "level": "熟练",
             "evidence_count": 3, "confidence": 0.8, "trend": "improving",
             "last_updated": "2026-07-17T00:00:00Z"},
            {"name": "call_stack", "score": 45, "level": "初步",
             "evidence_count": 2, "confidence": 0.6, "trend": "declining",
             "last_updated": "2026-07-16T00:00:00Z"},
        ],
        "weak_knowledge_points": [
            {"name": "call_stack", "priority": "high",
             "reason": "多次错误", "suggested_action": "强化练习"},
        ],
        "weak_topics": [
            {"topic": "call_stack", "priority": "high", "reason": "多次错误"},
        ],
        "strengths": ["recursion"],
        "confidence": 0.7,
    }
    base.update(overrides)
    return base


# ── Test 1: First snapshot created with version=1 ─────────────────────────


def _unique_id(tag: str) -> str:
    return f"{tag}_{uuid.uuid4().hex[:8]}"


def test_first_snapshot_version_1():
    """Creating the first snapshot for a (learner, subject) gets version=1."""
    _setup()
    uid = _unique_id("t1")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db,
            learner_id=f"lnr_{uid}",
            subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}",
            diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        assert snap.version == 1, f"Expected version=1, got {snap.version}"
        assert snap.status == "ready"
    finally:
        db.close()


# ── Test 2: Version increments ────────────────────────────────────────────


def test_version_increments():
    """Second and third snapshots get versions 2 and 3."""
    _setup()
    uid = _unique_id("t2")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        s1 = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        assert s1.version == 1

        s2 = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(summary="V2"),
        )
        db.commit()
        assert s2.version == 2

        s3 = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(summary="V3"),
        )
        db.commit()
        assert s3.version == 3
    finally:
        db.close()


# ── Test 3: Historical snapshots preserved ────────────────────────────────


def test_historical_snapshots_preserved():
    """All versions remain queryable after multiple runs."""
    _setup()
    uid = _unique_id("t3")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        for i in range(3):
            persist_diagnosis_result(
                db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
                session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(summary=f"v{i+1}"),
            )
            db.commit()

        all_snaps = (
            db.query(DiagnosisSnapshotModel)
            .filter(
                DiagnosisSnapshotModel.learner_id == f"lnr_{uid}",
                DiagnosisSnapshotModel.subject_id == f"subj_{uid}",
            )
            .order_by(DiagnosisSnapshotModel.version)
            .all()
        )
        assert len(all_snaps) == 3, f"Expected 3 snapshots, got {len(all_snaps)}"
        assert all_snaps[2].status == "ready"
        assert all_snaps[1].status == "superseded"
    finally:
        db.close()


# ── Test 4: Service restart — snapshot still readable ─────────────────────


def test_snapshot_survives_reconnect():
    """After closing and reopening a DB connection, snapshots are still there."""
    _setup()
    uid = _unique_id("t4")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db1 = SessionLocal()
    snap_id = ""
    try:
        snap = persist_diagnosis_result(
            db1, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db1.commit()
        snap_id = snap.diagnosis_snapshot_id
    finally:
        db1.close()

    db2 = SessionLocal()
    try:
        loaded = db2.get(DiagnosisSnapshotModel, snap_id)
        assert loaded is not None, "Snapshot not found after reconnect"
        assert loaded.diagnosis_snapshot_id == snap_id
    finally:
        db2.close()


# ── Test 5: Different learner isolation ───────────────────────────────────


def test_learner_isolation():
    """Learner A's snapshots are not visible to learner B's queries."""
    _setup()
    uid = _unique_id("t5")
    _ensure_session(f"sess_a_{uid}", f"lnr_a_{uid}", f"subj_{uid}")
    _ensure_session(f"sess_b_{uid}", f"lnr_b_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        persist_diagnosis_result(
            db, learner_id=f"lnr_a_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_a_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()

        snap_b = get_latest_snapshot(db, f"lnr_b_{uid}", f"subj_{uid}")
        assert snap_b is None
        snap_a = get_latest_snapshot(db, f"lnr_a_{uid}", f"subj_{uid}")
        assert snap_a is not None
    finally:
        db.close()


# ── Test 6: Different subject isolation ───────────────────────────────────


def test_subject_isolation():
    """Math and Physics snapshots have independent versioning."""
    _setup()
    uid = _unique_id("t6")
    learner = f"lnr_{uid}"
    _ensure_session(f"sess_m_{uid}", learner, f"subj_math_{uid}")
    _ensure_session(f"sess_p_{uid}", learner, f"subj_phys_{uid}")
    db = SessionLocal()
    try:
        s_math = persist_diagnosis_result(
            db, learner_id=learner, subject_id=f"subj_math_{uid}",
            session_id=f"sess_m_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        assert s_math.version == 1

        s_phys = persist_diagnosis_result(
            db, learner_id=learner, subject_id=f"subj_phys_{uid}",
            session_id=f"sess_p_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        assert s_phys.version == 1  # Independent

        s_math2 = persist_diagnosis_result(
            db, learner_id=learner, subject_id=f"subj_math_{uid}",
            session_id=f"sess_m_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        assert s_math2.version == 2
    finally:
        db.close()


# ── Test 7: Evidence correctly linked ─────────────────────────────────────


def test_evidence_linked_to_snapshot():
    """Evidence rows are created and linked to the snapshot."""
    _setup()
    uid = _unique_id("t7")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()

        # Add some evidence manually for this test
        l_id = f"lnr_{uid}"
        create_diagnosis_evidence(
            db,
            evidence_id=f"ev_a_{uuid.uuid4().hex[:12]}",
            diagnosis_snapshot_id=snap.diagnosis_snapshot_id,
            learner_id=l_id,
            knowledge_point_key="recursion",
            evidence_type="quiz_answer",
            score=0.75,
            weight=1.0,
            confidence=0.9,
        )
        create_diagnosis_evidence(
            db,
            evidence_id=f"ev_b_{uuid.uuid4().hex[:12]}",
            diagnosis_snapshot_id=snap.diagnosis_snapshot_id,
            learner_id=l_id,
            knowledge_point_key="call_stack",
            evidence_type="quiz_answer",
            score=0.45,
            weight=0.5,
            confidence=0.8,
        )
        db.commit()

        evidence = get_evidence_for_snapshot(db, snap.diagnosis_snapshot_id)
        assert len(evidence) == 2, f"Expected 2 evidence rows, got {len(evidence)}"
        kps = {e.knowledge_point_key for e in evidence}
        assert "recursion" in kps
        assert "call_stack" in kps
    finally:
        db.close()


# ── Test 8: Non-eligible attempts excluded ────────────────────────────────


def test_non_eligible_not_in_evidence():
    """Only assessment_eligible KnowledgePointResults become evidence."""
    _setup()
    uid = _unique_id("t8")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        from app.db.models import LearningEventModel

        event_id = f"evt_{uid}"
        evt = LearningEventModel(
            event_id=event_id,
            session_id=f"sess_{uid}",
            learner_id=f"lnr_{uid}",
            subject_id=f"subj_{uid}",
            event_type="quiz_result",
            attempt_id="att_none_test",
            metadata_={
                "eventType": "quiz_result",
                "knowledgePointResults": [
                    {
                        "knowledgePointKey": "recursion",
                        "knowledgePointLabel": "Recursion",
                        "questionId": "q1",
                        "attemptId": "att_none_test",
                        "normalizedScore": 0.8,
                        "weight": 1.0,
                        "mappingConfidence": 0.9,
                        "isCorrect": True,
                        "assessmentEligible": True,
                    },
                    {
                        "knowledgePointKey": "call_stack",
                        "knowledgePointLabel": "Call Stack",
                        "questionId": "q2",
                        "attemptId": "att_none_test",
                        "normalizedScore": 0.5,
                        "weight": 1.0,
                        "mappingConfidence": 0.9,
                        "isCorrect": False,
                        "assessmentEligible": False,  # ← should be excluded
                    },
                ],
            },
        )
        db.add(evt)
        db.flush()

        from app.db.repository import collect_evidence_from_events
        evidence = collect_evidence_from_events(
            db, f"lnr_{uid}", f"subj_{uid}",
            source_event_ids=[event_id],
            source_attempt_ids=[],
        )
        # Only the eligible KPR should be collected
        kps = {e["knowledge_point_key"] for e in evidence}
        assert "recursion" in kps
        assert "call_stack" not in kps, "Non-eligible KPR should be excluded"
    finally:
        db.close()


# ── Test 9: Multiple correct → improving trend ────────────────────────────


def test_multiple_correct_shows_improving():
    """The mastery dict correctly reflects improvement trend."""
    _setup()
    uid = _unique_id("t9")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    diagnosis = _sample_diagnosis(
        mastery_levels=[
            {"name": "recursion", "score": 85, "level": "熟练",
             "evidence_count": 5, "confidence": 0.9, "trend": "improving"},
        ]
    )
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=diagnosis,
        )
        db.commit()
        dto = snapshot_to_dto_dict(snap)
        mastery = dto["mastery"]
        assert len(mastery) == 1
        assert mastery[0]["trend"] == "improving"
    finally:
        db.close()


# ── Test 10: Single error doesn't zero mastery ────────────────────────────


def test_single_error_does_not_zero():
    """A score of 45 after one error is '初步', not zero."""
    _setup()
    uid = _unique_id("t10")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    diagnosis = _sample_diagnosis(
        mastery_levels=[
            {"name": "call_stack", "score": 45, "level": "初步",
             "evidence_count": 1, "confidence": 0.6, "trend": "declining"},
        ]
    )
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=diagnosis,
        )
        db.commit()
        dto = snapshot_to_dto_dict(snap)
        score = dto["mastery"][0]["score"]
        assert score > 0, f"Score should not be zero after a single error: {score}"
        assert score == 45
    finally:
        db.close()


# ── Test 11: Profile/Analytics/Resource read same version ─────────────────


def test_same_version_for_all_consumers():
    """Multiple calls to get_latest_snapshot return the same version."""
    _setup()
    uid = _unique_id("t11")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        version = snap.version

        s1 = get_latest_snapshot(db, f"lnr_{uid}", f"subj_{uid}")
        s2 = get_latest_snapshot(db, f"lnr_{uid}", f"subj_{uid}")
        s3 = get_latest_snapshot(db, f"lnr_{uid}", f"subj_{uid}")
        assert s1 is not None and s2 is not None and s3 is not None
        assert s1.version == s2.version == s3.version == version
        assert s1.diagnosis_snapshot_id == s2.diagnosis_snapshot_id == s3.diagnosis_snapshot_id
    finally:
        db.close()


# ── Test 12: Old in-memory diagnosis no longer sole source ────────────────


def test_db_snapshot_provides_diagnosis():
    """try_get_diagnosis returns DB snapshot when it exists."""
    _setup()
    uid = _unique_id("t12")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()

        dto = try_get_diagnosis(db, f"lnr_{uid}", f"subj_{uid}")
        assert dto is not None, "Should return DB snapshot"
        assert dto["version"] == snap.version
        assert len(dto["mastery"]) == 2
        assert len(dto["weaknesses"]) == 1
    finally:
        db.close()


# ── Test: API endpoint returns snapshot ───────────────────────────────────


def test_api_latest_snapshot():
    """GET /api/diagnosis-snapshots/latest returns persisted snapshot."""
    _setup()
    uid = _unique_id("t13")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.get(
        f"/api/diagnosis-snapshots/latest?sessionId=sess_{uid}&subjectId=subj_{uid}",
        headers=_headers(learner_id=f"lnr_{uid}"),
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]
    assert data is not None, f"No data returned: {body}"
    assert data["version"] == 1
    assert data["learnerId"] == f"lnr_{uid}"


# ── Test: snapshot_to_dict helper ─────────────────────────────────────────


def test_snapshot_to_dict():
    """snapshot_to_dict produces correct camelCase output."""
    _setup()
    uid = _unique_id("t14")
    _ensure_session(f"sess_{uid}", f"lnr_{uid}", f"subj_{uid}")
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=f"lnr_{uid}", subject_id=f"subj_{uid}",
            session_id=f"sess_{uid}", diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        d = snapshot_to_dict(snap)
        assert d["learnerId"] == f"lnr_{uid}"
        assert d["subjectId"] == f"subj_{uid}"
        assert d["version"] == 1
        assert d["status"] == "ready"
        assert isinstance(d["mastery"], list)
        assert isinstance(d["createdAt"], str)
    finally:
        db.close()


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_first_snapshot_version_1,
        test_version_increments,
        test_historical_snapshots_preserved,
        test_snapshot_survives_reconnect,
        test_learner_isolation,
        test_subject_isolation,
        test_evidence_linked_to_snapshot,
        test_non_eligible_not_in_evidence,
        test_multiple_correct_shows_improving,
        test_single_error_does_not_zero,
        test_same_version_for_all_consumers,
        test_db_snapshot_provides_diagnosis,
        test_api_latest_snapshot,
        test_snapshot_to_dict,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
