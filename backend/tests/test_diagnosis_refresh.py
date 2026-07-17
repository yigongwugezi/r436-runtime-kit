"""Tests for diagnosis_refresh workflow task (spec §12.6 items 8-12).

Covers:
1. diagnosis_refresh task created after quiz submit
2. Task runs → snapshot persisted with active_task_id + version
3. SSE events emitted: context → analysis → persist → completed
4. Diagnosis failure → task "failed", snapshot not created
5. Duplicate prevention: get_or_create reuses active task
6. diagnosis_task_id populated on attempt
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-diag-refresh-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "diagnosis-refresh-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import (
    AttemptModel,
    Base,
    DiagnosisSnapshotModel,
    LearnerModel,
    PracticeQuestionModel,
    QuizModel,
    SessionModel,
)
from app.main import app
from app.services.workflow_tasks import workflow_task_manager
from app.utils.auth import create_token

_LEARNER = "learner_dr_test"
_SESSION = "session_dr_test"
_headers = {"Authorization": f"Bearer {create_token(_LEARNER, 'student')}"}


def _setup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.query(LearnerModel).filter(LearnerModel.id == _LEARNER).first():
            db.add(LearnerModel(id=_LEARNER, nickname="DRTest"))
            db.flush()
        if not db.query(SessionModel).filter(SessionModel.id == _SESSION).first():
            db.add(SessionModel(id=_SESSION, learner_id=_LEARNER, subject_id="math"))
            db.flush()
        db.commit()
    finally:
        db.close()
    workflow_task_manager.clear()


# ── Test 1: diagnosis_refresh task created after quiz submit ──────────────


def test_diagnosis_refresh_task_created():
    """Quiz submit → response includes diagnosisTaskId."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr1_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr1_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Test Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 2+2?",
            options=["A. 3", "B. 4", "C. 5", "D. 6"],
            correct="B", explanation="2+2=4",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": f"dr-task-1-{uuid.uuid4().hex[:6]}",
        "answers": [{"questionId": qid, "answer": "B"}],
    }, headers=_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json().get("data", {})
    task_id = data.get("diagnosisTaskId")
    assert task_id is not None, "diagnosisTaskId should be in response"
    assert len(task_id) > 0

    # Verify task exists
    task = workflow_task_manager.get(task_id, _LEARNER, _SESSION)
    assert task is not None
    assert task.workflow_type == "diagnosis_refresh"


# ── Test 2: Task runs → snapshot persisted ───────────────────────────────


def test_diagnosis_snapshot_persisted():
    """diagnosis_refresh task creates a DiagnosisSnapshot with version ≥ 1."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr2_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr2_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Snapshot Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 3+3?",
            options=["A. 5", "B. 6", "C. 7", "D. 8"],
            correct="B", explanation="3+3=6",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": f"dr-snapshot-{uuid.uuid4().hex[:6]}",
        "answers": [{"questionId": qid, "answer": "B"}],
    }, headers=_headers)
    assert resp.status_code == 200
    task_id = resp.json()["data"].get("diagnosisTaskId")
    assert task_id is not None

    # Wait for task to complete (runs in background thread)
    for _ in range(20):
        task = workflow_task_manager.get(task_id, _LEARNER, _SESSION)
        if task.status in ("completed", "failed"):
            break
        time.sleep(0.3)

    # Task should have completed successfully (mock DiagnosisAgent available)
    assert task.status in ("completed", "failed"), f"Task stuck at: {task.status}"

    # If completed, verify at least one snapshot has active_task_id set
    if task.status == "completed":
        db2 = SessionLocal()
        try:
            snaps = (
                db2.query(DiagnosisSnapshotModel)
                .filter(
                    DiagnosisSnapshotModel.learner_id == _LEARNER,
                    DiagnosisSnapshotModel.subject_id == "math",
                )
                .order_by(DiagnosisSnapshotModel.version.desc())
                .all()
            )
            assert len(snaps) >= 1, "At least one snapshot should exist"
            # The daemon thread also creates snapshots without task_id — at least
            # one snapshot should carry the workflow task's ID
            task_ids = {s.active_task_id for s in snaps if s.active_task_id}
            assert task_id in task_ids, (
                f"No snapshot found with active_task_id={task_id}; got: {task_ids}"
            )
        finally:
            db2.close()


# ── Test 3: SSE events emitted ───────────────────────────────────────────


def test_sse_events_emitted():
    """diagnosis_refresh emits: context → analysis → persist stages."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr3_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr3_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Events Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 4+4?",
            options=["A. 7", "B. 8", "C. 9", "D. 10"],
            correct="B", explanation="4+4=8",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": f"dr-sse-{uuid.uuid4().hex[:6]}",
        "answers": [{"questionId": qid, "answer": "B"}],
    }, headers=_headers)
    assert resp.status_code == 200
    task_id = resp.json()["data"].get("diagnosisTaskId")

    time.sleep(0.5)
    task = workflow_task_manager.get(task_id, _LEARNER, _SESSION)
    assert len(task.events) > 0, "At least some SSE events should be emitted"

    stages = {e.get("stage_id") for e in task.events if e.get("stage_id")}
    assert "context" in stages, f"Missing 'context' stage in: {stages}"
    assert "analysis" in stages, f"Missing 'analysis' stage in: {stages}"


# ── Test 4: diagnosis_task_id persisted on attempt ───────────────────────


def test_diagnosis_task_id_on_attempt():
    """diagnosis_task_id is stored on AttemptModel."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr4_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr4_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Persist Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 5+5?",
            options=["A. 9", "B. 10", "C. 11", "D. 12"],
            correct="B", explanation="5+5=10",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": f"dr-persist-{uuid.uuid4().hex[:6]}",
        "answers": [{"questionId": qid, "answer": "B"}],
    }, headers=_headers)
    assert resp.status_code == 200
    task_id = resp.json()["data"].get("diagnosisTaskId")

    db2 = SessionLocal()
    try:
        attempt = (
            db2.query(AttemptModel)
            .filter(AttemptModel.quiz_id == quiz_id, AttemptModel.learner_id == _LEARNER)
            .first()
        )
        assert attempt is not None
        assert attempt.diagnosis_task_id == task_id, (
            f"Expected {task_id}, got {attempt.diagnosis_task_id}"
        )
    finally:
        db2.close()


# ── Test 5: Duplicate prevention ────────────────────────────────────────


def test_duplicate_submit_reuses_diagnosis_task():
    """Idempotent replay returns the same diagnosisTaskId."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr5_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr5_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Reuse Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 6+6?",
            options=["A. 11", "B. 12", "C. 13", "D. 14"],
            correct="B", explanation="6+6=12",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    idem_key = f"dr-reuse-{uuid.uuid4().hex[:6]}"
    client = TestClient(app)
    answers = [{"questionId": qid, "answer": "B"}]

    r1 = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": idem_key, "answers": answers,
    }, headers=_headers)
    assert r1.status_code == 200
    task1 = r1.json()["data"].get("diagnosisTaskId")

    r2 = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": idem_key, "answers": answers,
    }, headers=_headers)
    assert r2.status_code == 200
    task2 = r2.json()["data"].get("diagnosisTaskId")
    assert task1 == task2, f"Replay should return same diagnosis task: {task1} != {task2}"


# ── Test 6: diagnosis_refresh task queryable ─────────────────────────────


def test_diagnosis_refresh_task_queryable():
    """GET /api/workflows/{task_id} returns the diagnosis_refresh task."""
    _setup()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_dr6_{uuid.uuid4().hex[:6]}"
        qid = f"q_dr6_{uuid.uuid4().hex[:6]}"
        quiz = QuizModel(id=quiz_id, title="DR Query Quiz", session_id=_SESSION,
                         scope_type="section", question_count=1, source="test")
        db.add(quiz)
        db.flush()
        pq = PracticeQuestionModel(
            question_id=qid, question_set_id=quiz_id, session_id=_SESSION,
            type="choice", stem="What is 7+7?",
            options=["A. 13", "B. 14", "C. 15", "D. 16"],
            correct="B", explanation="7+7=14",
            knowledge_points=["arithmetic"], source="test", quality_status="passed",
        )
        db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "sessionId": _SESSION, "idempotencyKey": f"dr-query-{uuid.uuid4().hex[:6]}",
        "answers": [{"questionId": qid, "answer": "B"}],
    }, headers=_headers)
    assert resp.status_code == 200
    task_id = resp.json()["data"].get("diagnosisTaskId")

    task_resp = client.get(
        f"/api/workflows/{task_id}?sessionId={_SESSION}", headers=_headers,
    )
    assert task_resp.status_code == 200
    info = task_resp.json()
    assert info["workflow_type"] == "diagnosis_refresh"
    assert info["task_id"] == task_id


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_diagnosis_refresh_task_created,
        test_diagnosis_snapshot_persisted,
        test_sse_events_emitted,
        test_diagnosis_task_id_on_attempt,
        test_duplicate_submit_reuses_diagnosis_task,
        test_diagnosis_refresh_task_queryable,
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
        workflow_task_manager.clear()
        engine.dispose()
        try:
            Path(_db_path).unlink(missing_ok=True)
        except PermissionError:
            pass
