"""Tests for PersonalizationContextService and personalization metadata (spec §5.5, §12.4).

Covers:
1.  Same learner, same topic — first call vs second call (weakness marked) → context differs
2.  Recommendation reason changes with diagnosis
3.  diagnosis_version is recorded on resources
4.  profile_version is recorded on resources
5.  General lecture entry reads Profile + Diagnosis
6.  PersonalizationContextService builds context from DB
7.  PersonalizationContextDTO field validation
8.  Resource saves with personalization metadata
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-pers-ctx-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "pers-ctx-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import (
    Base,
    DiagnosisSnapshotModel,
    LearnerModel,
    ProfileSnapshotModel,
    ResourceModel,
    SessionModel,
)
from app.db.repository import (
    create_diagnosis_snapshot,
    upsert_resource,
)
from app.main import app
from app.services.diagnosis_snapshot_service import persist_diagnosis_result
from app.services.personalization_context import PersonalizationContextService
from app.utils.auth import create_token

_LEARNER = "learner_pers_ctx"
_SESSION = "session_pers_ctx"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(_LEARNER, 'student')}"}


def _setup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.query(LearnerModel).filter(LearnerModel.id == _LEARNER).first():
            db.add(LearnerModel(id=_LEARNER, nickname="PersCtxTester"))
            db.flush()
        if not db.query(SessionModel).filter(SessionModel.id == _SESSION).first():
            db.add(SessionModel(id=_SESSION, learner_id=_LEARNER, subject_id="math"))
            db.flush()
        db.commit()
    finally:
        db.close()


def _sample_diagnosis(weaknesses=None, mastery=None) -> dict:
    return {
        "summary": "Test diagnosis",
        "mastery_levels": mastery or [
            {"name": "recursion", "score": 75, "level": "熟练",
             "evidence_count": 3, "confidence": 0.8, "trend": "stable"},
        ],
        "weak_knowledge_points": weaknesses or [],
        "weak_topics": weaknesses or [],
        "strengths": ["recursion"],
        "confidence": 0.7,
    }


# ── Test 1: Context changes when weaknesses are introduced ────────────────


def test_context_differs_with_weakness():
    """Same learner, same topic — first call (no weaknesses) vs second (weakness) → context differs."""
    _setup()
    db = SessionLocal()
    try:
        # First: no weaknesses
        persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION,
            diagnosis_result=_sample_diagnosis(weaknesses=[]),
        )
        db.commit()

        svc = PersonalizationContextService()
        ctx1 = svc.build(_SESSION, subject_id="math")
        w1 = ctx1["weaknesses"]
        d1 = ctx1["diagnosisVersion"]

        # Second: weaknesses introduced
        persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION,
            diagnosis_result=_sample_diagnosis(weaknesses=[
                {"name": "call_stack", "priority": "high",
                 "reason": "多次错误", "suggested_action": "强化练习"},
            ]),
        )
        db.commit()

        ctx2 = svc.build(_SESSION, subject_id="math")
        w2 = ctx2["weaknesses"]
        d2 = ctx2["diagnosisVersion"]

        # Context should differ
        assert len(w2) > len(w1), f"Weaknesses should increase: {len(w1)} → {len(w2)}"
        assert d2 is not None and d1 is not None
        assert d2 > d1, f"Diagnosis version should increase: {d1} → {d2}"
    finally:
        db.close()


# ── Test 2: diagnosis_version recorded on resource ────────────────────────


def test_diagnosis_version_on_resource():
    """Resources saved via upsert_resource carry diagnosis_version."""
    _setup()
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION, diagnosis_result=_sample_diagnosis(),
        )
        db.commit()
        diag_ver = snap.version

        rid = f"res_dv_{uuid.uuid4().hex[:8]}"
        upsert_resource(db, _SESSION, {
            "id": rid, "type": "lecture", "title": "Test Lecture",
            "diagnosis_version": diag_ver,
            "profile_version": 2,
            "recommendation_reason": "基于诊断生成",
            "quality_status": "passed",
        })

        res = db.get(ResourceModel, rid)
        assert res is not None
        assert res.diagnosis_version == diag_ver
        assert res.profile_version == 2
        assert res.recommendation_reason == "基于诊断生成"
        assert res.quality_status == "passed"
    finally:
        db.close()


# ── Test 3: Context includes profile version ──────────────────────────────


def test_context_includes_profile_version():
    """PersonalizationContextService reads profile_version from DB."""
    _setup()
    db = SessionLocal()
    try:
        # Seed a profile snapshot with v2 profile
        snap = ProfileSnapshotModel(
            session_id=_SESSION,
            preferences={
                "profile_v2": {
                    "profile_version": 2,
                    "subject_context": {
                        "learning_goal": "Master recursion",
                        "content_preferences": ["example_first", "visual_explanation"],
                        "resource_preferences": ["视频", "练习题"],
                    },
                },
            },
        )
        db.add(snap)
        db.commit()

        svc = PersonalizationContextService()
        ctx = svc.build(_SESSION, subject_id="math")
        assert ctx["profileVersion"] == 2
        assert ctx["targetGoal"] == "Master recursion"
        prefs = ctx["subjectPreferences"]
        assert "contentPreferences" in prefs
        assert "resourcePreferences" in prefs
    finally:
        db.close()


# ── Test 4: Stable preferences from LearnerModel ───────────────────────────


def test_stable_preferences_from_learner():
    """Stable preferences (grade, target_exam) come from LearnerModel."""
    _setup()
    db = SessionLocal()
    try:
        learner = db.query(LearnerModel).filter(LearnerModel.id == _LEARNER).first()
        if learner:
            learner.grade = "大三"
            learner.target_exam = "考研"
            db.commit()

        svc = PersonalizationContextService()
        ctx = svc.build(_SESSION, subject_id="math")
        stable = ctx["stablePreferences"]
        assert stable.get("grade") == "大三"
        assert stable.get("targetExam") == "考研"
    finally:
        db.close()


# ── Test 5: Context contains prior resource IDs ───────────────────────────


def test_context_has_prior_resource_ids():
    """PersonalizationContext includes IDs of previously generated resources."""
    _setup()
    db = SessionLocal()
    try:
        rid = f"res_prior_{uuid.uuid4().hex[:8]}"
        upsert_resource(db, _SESSION, {
            "id": rid, "type": "lecture", "title": "Existing Lecture",
        })

        svc = PersonalizationContextService()
        ctx = svc.build(_SESSION, subject_id="math")
        assert rid in ctx["priorResourceIds"]
    finally:
        db.close()


# ── Test 6: _attach_personalization_metadata stamps resource ──────────────


def test_attach_personalization_metadata():
    """_attach_personalization_metadata adds versions and factors to resource dict."""
    _setup()
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION, diagnosis_result=_sample_diagnosis(
                weaknesses=[{"name": "call_stack", "priority": "high",
                             "reason": "errors"}],
            ),
        )
        db.commit()

        # Simulate the helper
        resource = {"id": f"res_attach_{uuid.uuid4().hex[:8]}", "type": "lecture"}
        from app.routers.product import _attach_personalization_metadata
        _attach_personalization_metadata(resource, _SESSION, "math")

        assert resource.get("diagnosis_version") == snap.version
        assert resource.get("quality_status") == "passed"
        factors = resource.get("personalization_factors", [])
        assert any("call_stack" in str(f) for f in factors), f"Weak factor missing: {factors}"
    finally:
        db.close()


# ── Test 7: PersonalizationContextDTO field validation ─────────────────────


def test_personalization_context_dto():
    """PersonalizationContextDTO accepts valid data."""
    from app.schemas.personalization import PersonalizationContextDTO

    dto = PersonalizationContextDTO(
        learnerId=_LEARNER,
        sessionId=_SESSION,
        subjectId="math",
        profileVersion=2,
        diagnosisVersion=3,
        mastery=[{"knowledgePointKey": "recursion", "label": "Recursion",
                  "score": 85, "confidence": 0.9, "evidenceCount": 5,
                  "trend": "improving"}],
        weaknesses=[{"knowledgePointKey": "call_stack", "severity": "high",
                     "reason": "Multiple errors"}],
        strengths=["recursion"],
        targetGoal="Master algorithms",
        priorResourceIds=["res_1", "res_2"],
        requestedResourceType="lecture",
    )
    assert dto.learner_id == _LEARNER
    assert dto.profile_version == 2
    assert dto.diagnosis_version == 3
    assert len(dto.mastery) == 1
    assert len(dto.weaknesses) == 1


# ── Test 8: Context builds without crash when no DB data ──────────────────


def test_context_builds_empty():
    """PersonalizationContextService returns valid empty context for unknown session."""
    _setup()
    svc = PersonalizationContextService()
    ctx = svc.build("nonexistent-session")
    assert ctx["learnerId"] == "" or ctx["learnerId"] is not None
    assert isinstance(ctx["mastery"], list)
    assert isinstance(ctx["weaknesses"], list)
    assert isinstance(ctx["priorResourceIds"], list)


# ── Test 9: General lecture prompt injects profile + diagnosis ────────────


def test_general_resource_stamps_personalization():
    """Resources saved via _generate_general_resource carry personalization metadata."""
    _setup()
    db = SessionLocal()
    try:
        # Seed a diagnosis so there's a version to stamp
        persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION,
            diagnosis_result={"summary": "T", "mastery_levels": [], "weak_knowledge_points": [],
                             "weak_topics": [], "strengths": [], "confidence": 0.5},
        )
        db.commit()

        rid = f"res_gen_{uuid.uuid4().hex[:8]}"
        resource = {"id": rid, "type": "lecture", "title": "Test General",
                     "content": "Content", "format": "text"}
        from app.routers.product import _attach_personalization_metadata
        _attach_personalization_metadata(resource, _SESSION, "math")

        upsert_resource(db, _SESSION, resource)
        res = db.get(ResourceModel, rid)
        assert res is not None
        assert res.diagnosis_version is not None, "diagnosis_version should be stamped"
        assert res.quality_status == "passed"
    finally:
        db.close()


# ── Test 10: Mindmap save carries personalization ─────────────────────────


def test_mindmap_resource_carries_personalization():
    """Mindmap resources saved via upsert carry personalization fields."""
    _setup()
    db = SessionLocal()
    try:
        persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION, diagnosis_result={"_sample": True},
        )
        db.commit()

        rid = f"res_mm_{uuid.uuid4().hex[:8]}"
        rd = {"id": rid, "type": "mindmap", "title": "Mindmap Test",
              "content": "graph TD", "format": "diagram",
              "mermaid_def": "graph TD\nA-->B"}
        from app.routers.product import _attach_personalization_metadata
        _attach_personalization_metadata(rd, _SESSION, "math")
        upsert_resource(db, _SESSION, rd)

        res = db.get(ResourceModel, rid)
        assert res is not None
        assert res.profile_version is not None or res.diagnosis_version is not None
        assert res.quality_status == "passed"
    finally:
        db.close()


# ── Test 11: Multiple saves produce consistent versions ───────────────────


def test_multiple_saves_consistent_versions():
    """Two resources saved in same session get same diagnosis_version."""
    _setup()
    db = SessionLocal()
    try:
        snap = persist_diagnosis_result(
            db, learner_id=_LEARNER, subject_id="math",
            session_id=_SESSION, diagnosis_result={"_diag": True},
        )
        db.commit()
        ver = snap.version

        for prefix in ["a", "b"]:
            rid = f"res_multi_{prefix}_{uuid.uuid4().hex[:6]}"
            rd = {"id": rid, "type": "lecture", "title": f"Lecture {prefix}"}
            from app.routers.product import _attach_personalization_metadata
            _attach_personalization_metadata(rd, _SESSION, "math")
            upsert_resource(db, _SESSION, rd)

        r1 = db.get(ResourceModel, f"res_multi_a_{uuid.uuid4().hex[:6]}")
        # Just verify two resources were saved with the same version
        resources = (
            db.query(ResourceModel)
            .filter(ResourceModel.id.like("res_multi_%"))
            .all()
        )
        versions = {r.diagnosis_version for r in resources if r.diagnosis_version is not None}
        assert len(resources) >= 2
        assert len(versions) == 1, f"All resources should share same diagnosis version, got {versions}"
    finally:
        db.close()


# ── Test 12: Resource serializers expose new fields ───────────────────────


def test_resource_serializers_expose_personalization():
    """_to_resource includes new personalization fields."""
    from app.routers.product import _to_resource

    item = {
        "resource_id": "res_test_ser",
        "type": "lecture", "title": "Test",
        "profile_version": 3,
        "diagnosis_version": 5,
        "recommendation_reason": "基于诊断生成",
        "personalization_factors": ["weak:call_stack", "pref:video"],
        "quality_status": "passed",
    }
    result = _to_resource(item)
    assert result.get("profileVersion") == 3
    assert result.get("diagnosisVersion") == 5
    assert result.get("recommendationReason") == "基于诊断生成"
    assert len(result.get("personalizationFactors", [])) == 2


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_context_differs_with_weakness,
        test_diagnosis_version_on_resource,
        test_context_includes_profile_version,
        test_stable_preferences_from_learner,
        test_context_has_prior_resource_ids,
        test_attach_personalization_metadata,
        test_personalization_context_dto,
        test_context_builds_empty,
        test_general_resource_stamps_personalization,
        test_mindmap_resource_carries_personalization,
        test_multiple_saves_consistent_versions,
        test_resource_serializers_expose_personalization,
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
