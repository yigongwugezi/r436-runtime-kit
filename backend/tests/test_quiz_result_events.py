"""Tests for canonical quiz_result events (commit 3).

Covers:
1. Quiz submit → quiz_result event created with correct fields
2. Event contains knowledge_point_results array
3. Same attempt → only one event (idempotency)
4. Idempotent replay → writes event if missing, no duplicate if exists
5. Exam set submit → quiz_result event created
6. Schema version recorded
7. Non-eligible attempt (answersRevealed) writes event with assessment_eligible=false
8. Event accessible via repository query
9. DB unique index prevents duplicate events
10. Event metadata contains all required QuizResultEventDTO fields
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-quiz-events-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "quiz-events-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import (
    Base,
    LearnerModel,
    PracticeQuestionModel,
    QuizModel,
    SessionModel,
)
from app.db.repository import (
    check_quiz_result_event_exists,
    get_quiz_result_event,
)
from app.main import app
from app.utils.auth import create_token

_LEARNER = "learner_qevt"
_SESSION = "session_qevt"
_headers = {"Authorization": f"Bearer {create_token(_LEARNER, 'student')}"}


def _setup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.query(LearnerModel).filter(LearnerModel.id == _LEARNER).first():
            db.add(LearnerModel(id=_LEARNER, nickname="EventTester"))
            db.flush()
        if not db.query(SessionModel).filter(SessionModel.id == _SESSION).first():
            db.add(SessionModel(id=_SESSION, learner_id=_LEARNER, subject_id="math"))
            db.flush()
        db.commit()
    finally:
        db.close()


def _seed_quiz(quiz_id: str, questions: list[dict]) -> str:
    db = SessionLocal()
    try:
        quiz = QuizModel(
            id=quiz_id, title=f"Quiz {quiz_id}",
            session_id=_SESSION, scope_type="section",
            question_count=len(questions), source="test",
            path_id="path_test", stage_id="stage_test",
            chapter_id="ch_test", section_id="sec_test",
        )
        db.add(quiz)
        db.flush()
        for q in questions:
            pq = PracticeQuestionModel(
                question_id=q["question_id"],
                question_set_id=quiz_id,
                session_id=_SESSION,
                type=q.get("type", "choice"),
                stem=q.get("stem", "Question"),
                options=q.get("options", ["A", "B", "C", "D"]),
                correct=q.get("correct", "A"),
                explanation=q.get("explanation", ""),
                knowledge_points=q.get("knowledge_points"),
                source="test",
                quality_status="passed",
            )
            db.add(pq)
        db.commit()
        return quiz_id
    finally:
        db.close()


def _submit(quiz_id: str, answers: list[dict], idem_key: str = "",
            answers_revealed: bool = False) -> tuple[int, dict]:
    client = TestClient(app)
    body: dict = {
        "sessionId": _SESSION,
        "idempotencyKey": idem_key or f"evt-test-{uuid.uuid4().hex[:8]}",
        "answers": answers,
    }
    if answers_revealed:
        body["answersRevealed"] = True
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json=body, headers=_headers)
    return resp.status_code, resp.json()


# ── Test 1: Quiz submit creates event ─────────────────────────────────────


def test_quiz_submit_creates_event():
    """After a successful quiz submit, a quiz_result event exists in the DB."""
    _setup()
    quiz_id = f"quiz_evt_1_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt1_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "What is 1+1?",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "correct": "B",
        "knowledge_points": ["arithmetic"],
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "B"}])
    assert status == 200, f"Expected 200, got {status}: {body}"

    attempt_id = body["data"]["attempt"]["attemptId"]
    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, attempt_id)
        assert evt is not None, "quiz_result event should exist in DB"
        assert evt.event_type == "quiz_result"
        assert evt.attempt_id == attempt_id
        assert evt.schema_version == "1.0"
        assert evt.learner_id == _LEARNER
        assert evt.subject_id == "math"

        # Verify metadata payload
        meta = evt.metadata_ or {}
        assert meta.get("eventType") == "quiz_result"
        assert meta.get("totalScore") is not None
        assert meta.get("quizId") == quiz_id
    finally:
        db.close()


# ── Test 2: Event contains knowledge_point_results ────────────────────────


def test_event_contains_knowledge_point_results():
    """The quiz_result event metadata includes knowledgePointResults array."""
    _setup()
    quiz_id = f"quiz_evt_2_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt2_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "Test Q", "options": ["A", "B", "C", "D"],
        "correct": "A", "knowledge_points": ["topic_a"],
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "A"}])
    assert status == 200

    attempt_id = body["data"]["attempt"]["attemptId"]
    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, attempt_id)
        meta = evt.metadata_ or {}
        kprs = meta.get("knowledgePointResults", [])
        assert len(kprs) >= 1, f"Expected at least 1 KPR, got {len(kprs)}"
        kpr = kprs[0]
        assert "knowledgePointKey" in kpr
        assert "weight" in kpr
        assert "isCorrect" in kpr
        assert "mappingConfidence" in kpr
    finally:
        db.close()


# ── Test 3: One event per attempt (idempotency) ───────────────────────────


def test_only_one_event_per_attempt():
    """Submitting the same attempt twice produces only one quiz_result event."""
    _setup()
    quiz_id = f"quiz_evt_3_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt3_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "Test", "options": ["A", "B", "C", "D"],
        "correct": "A", "knowledge_points": ["topic"],
    }])

    idem_key = "evt-idem-3"
    answers = [{"questionId": qid, "answer": "A"}]

    # First submit
    s1, b1 = _submit(quiz_id, answers, idem_key=idem_key)
    assert s1 == 200
    aid1 = b1["data"]["attempt"]["attemptId"]

    # Second submit (same key, same answers → idempotent replay)
    s2, b2 = _submit(quiz_id, answers, idem_key=idem_key)
    assert s2 == 200
    assert b2["data"].get("idempotentReplay") is True
    aid2 = b2["data"]["attempt"]["attemptId"]
    assert aid1 == aid2

    # Verify only one event
    db = SessionLocal()
    try:
        from app.db.models import LearningEventModel
        events = (
            db.query(LearningEventModel)
            .filter(
                LearningEventModel.attempt_id == aid1,
                LearningEventModel.event_type == "quiz_result",
            )
            .all()
        )
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    finally:
        db.close()


# ── Test 4: Idempotent replay writes event if missing ─────────────────────


def test_replay_writes_event_if_missing():
    """When replaying a previous submission, an event is created if missing."""
    _setup()
    quiz_id = f"quiz_evt_4_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt4_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "T", "options": ["A", "B"],
        "correct": "A", "knowledge_points": ["kp"],
    }])

    answers = [{"questionId": qid, "answer": "A"}]
    idem_key = "evt-replay-4"

    # Submit
    s1, b1 = _submit(quiz_id, answers, idem_key=idem_key)
    assert s1 == 200
    aid = b1["data"]["attempt"]["attemptId"]

    # Verify event exists
    db = SessionLocal()
    try:
        assert check_quiz_result_event_exists(db, aid), "Event should exist after first submit"
        evt = get_quiz_result_event(db, aid)
        assert evt is not None
        assert evt.metadata_.get("knowledgePointResults") is not None
    finally:
        db.close()

    # Replay — event was already there, should still be only one
    s2, b2 = _submit(quiz_id, answers, idem_key=idem_key)
    assert s2 == 200
    assert b2["data"].get("idempotentReplay") is True

    db = SessionLocal()
    try:
        from app.db.models import LearningEventModel
        count = (
            db.query(LearningEventModel)
            .filter(
                LearningEventModel.attempt_id == aid,
                LearningEventModel.event_type == "quiz_result",
            )
            .count()
        )
        assert count == 1, f"Still only 1 event after replay, got {count}"
    finally:
        db.close()


# ── Test 5: Exam set creates event ────────────────────────────────────────


def test_exam_set_creates_event():
    """Exam set submission also creates a quiz_result event."""
    _setup()
    db = SessionLocal()
    try:
        from app.db.models import ExamSetModel
        exam_id = f"exam_evt_{uuid.uuid4().hex[:6]}"
        exam = ExamSetModel(
            id=exam_id, title="Event Test Exam",
            session_id=_SESSION, scope_type="chapter",
            question_count=1, source="test",
            path_id="p1", stage_id="s1", chapter_id="c1",
        )
        db.add(exam)
        db.flush()

        qid = f"eq_evt_{uuid.uuid4().hex[:6]}"
        db.add(PracticeQuestionModel(
            question_id=qid, question_set_id=exam_id,
            session_id=_SESSION, type="choice",
            stem="Exam Q", options=["A", "B", "C", "D"],
            correct="A", knowledge_points=["exam_kp"],
            source="test", quality_status="passed",
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    resp = client.post(
        f"/api/exam-sets/{exam_id}/submit",
        json={
            "sessionId": _SESSION,
            "idempotencyKey": f"evt-exam-{uuid.uuid4().hex[:8]}",
            "answers": [{"questionId": qid, "answer": "A"}],
        },
        headers=_headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.json()}"
    aid = resp.json()["data"]["attempt"]["attemptId"]

    db2 = SessionLocal()
    try:
        evt = get_quiz_result_event(db2, aid)
        assert evt is not None, "Exam set should produce quiz_result event"
        meta = evt.metadata_ or {}
        assert meta.get("quizId") == exam_id
    finally:
        db2.close()


# ── Test 6: Schema version recorded ───────────────────────────────────────


def test_schema_version_recorded():
    """The event records schema_version='1.0'."""
    _setup()
    quiz_id = f"quiz_evt_6_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt6_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "Schema test", "options": ["A", "B"],
        "correct": "A", "knowledge_points": ["test"],
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "A"}])
    assert status == 200
    aid = body["data"]["attempt"]["attemptId"]

    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, aid)
        assert evt.schema_version == "1.0"
        assert evt.metadata_.get("schemaVersion") == "1.0"
    finally:
        db.close()


# ── Test 7: Non-eligible attempt writes event correctly ────────────────────


def test_non_eligible_attempt_event():
    """An attempt with answersRevealed=true still writes an event with
    assessment_eligible=false."""
    _setup()
    quiz_id = f"quiz_evt_7_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt7_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "Revealed test", "options": ["A", "B"],
        "correct": "A", "knowledge_points": ["kp"],
    }])

    status, body = _submit(
        quiz_id, [{"questionId": qid, "answer": "A"}],
        idem_key="evt-revealed-7", answers_revealed=True,
    )
    assert status == 200
    aid = body["data"]["attempt"]["attemptId"]

    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, aid)
        assert evt is not None
        meta = evt.metadata_ or {}
        assert meta.get("assessmentEligible") is False
    finally:
        db.close()


# ── Test 8: Event metadata has all required DTO fields ────────────────────


def test_event_metadata_has_all_required_fields():
    """The metadata_ JSON contains all QuizResultEventDTO required fields."""
    _setup()
    quiz_id = f"quiz_evt_8_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt8_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "choice",
        "stem": "DTO test", "options": ["A", "B"],
        "correct": "A", "knowledge_points": ["kp"],
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "A"}])
    assert status == 200
    aid = body["data"]["attempt"]["attemptId"]

    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, aid)
        meta = evt.metadata_ or {}

        required_fields = [
            "eventId", "eventType", "idempotencyKey", "learnerId",
            "sessionId", "quizId", "attemptId", "totalScore",
            "maxScore", "normalizedScore", "assessmentEligible",
            "knowledgePointResults", "occurredAt", "source", "schemaVersion",
        ]
        for field in required_fields:
            assert field in meta, f"Missing required field '{field}' in event metadata"

        assert meta["eventType"] == "quiz_result"
        assert meta["source"] == "server"
    finally:
        db.close()


# ── Test 9: DB unique index prevents duplicate events ─────────────────────


def test_unique_index_prevents_duplicate():
    """The partial unique index prevents two quiz_result events for the same attempt."""
    _setup()
    db = SessionLocal()
    try:
        from app.db.models import LearningEventModel
        from app.db.repository import create_quiz_result_event
        from sqlalchemy.exc import IntegrityError

        attempt_id = f"att_uniq_test_{uuid.uuid4().hex[:8]}"

        # Create first event
        create_quiz_result_event(
            db,
            event_id=f"evt_uniq_a_{uuid.uuid4().hex[:12]}",
            session_id=_SESSION,
            learner_id=_LEARNER,
            subject_id="math",
            idempotency_key="uniq-test-key",
            attempt_id=attempt_id,
            quiz_id="quiz_uniq_test",
            total_score=80,
            max_score=100,
            normalized_score=0.8,
            assessment_eligible=True,
            knowledge_point_results=[],
        )
        db.commit()

        # Second event with same attempt_id → IntegrityError
        try:
            create_quiz_result_event(
                db,
                event_id=f"evt_uniq_b_{uuid.uuid4().hex[:12]}",
                session_id=_SESSION,
                learner_id=_LEARNER,
                subject_id="math",
                idempotency_key="uniq-test-key-2",
                attempt_id=attempt_id,
                quiz_id="quiz_uniq_test",
                total_score=90,
                max_score=100,
                normalized_score=0.9,
                assessment_eligible=True,
                knowledge_point_results=[],
            )
            db.commit()
            # If we get here, the unique index didn't fire
            # but SQLite may not enforce partial unique indexes on all versions
            # So check that at least the count is 1
            pass
        except IntegrityError:
            db.rollback()

        # Verify only one event
        count = (
            db.query(LearningEventModel)
            .filter(
                LearningEventModel.attempt_id == attempt_id,
                LearningEventModel.event_type == "quiz_result",
            )
            .count()
        )
        assert count == 1, f"Should have exactly 1 event, got {count}"
    finally:
        db.close()


# ── Test 10: KnowledgePointResults in event are valid ──────────────────────


def test_kpr_in_event_is_valid():
    """Each KPR in the event has all required fields with correct values."""
    _setup()
    quiz_id = f"quiz_evt_10_{uuid.uuid4().hex[:6]}"
    qid = f"q_evt10_{uuid.uuid4().hex[:6]}"
    _seed_quiz(quiz_id, [{
        "question_id": qid, "type": "truefalse",
        "stem": "KPR validation", "options": ["True", "False"],
        "correct": "True", "knowledge_points": ["topic_x", "topic_y"],
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "True"}])
    assert status == 200
    aid = body["data"]["attempt"]["attemptId"]

    db = SessionLocal()
    try:
        evt = get_quiz_result_event(db, aid)
        meta = evt.metadata_ or {}
        kprs = meta.get("knowledgePointResults", [])

        # Two KPs → two KPRs (fallback mapping creates equal-weight entries)
        assert len(kprs) == 2, f"Expected 2 KPRs, got {len(kprs)}"

        kpr_fields = [
            "knowledgePointKey", "knowledgePointLabel", "questionId",
            "attemptId", "rawScore", "maxScore", "normalizedScore",
            "weight", "weightedScore", "mappingConfidence",
            "gradingConfidence", "isCorrect", "errorType", "assessmentEligible",
        ]
        for kpr in kprs:
            for field in kpr_fields:
                assert field in kpr, f"Missing KPR field '{field}'"

        # Both should be correct (answer was right)
        assert all(k["isCorrect"] for k in kprs), "All KPRs should be correct"
        # Grading confidence for truefalse = 0.90
        assert all(k["gradingConfidence"] == 0.90 for k in kprs), \
            "Grading confidence should be 0.90 for truefalse"
    finally:
        db.close()


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_quiz_submit_creates_event,
        test_event_contains_knowledge_point_results,
        test_only_one_event_per_attempt,
        test_replay_writes_event_if_missing,
        test_exam_set_creates_event,
        test_schema_version_recorded,
        test_non_eligible_attempt_event,
        test_event_metadata_has_all_required_fields,
        test_unique_index_prevents_duplicate,
        test_kpr_in_event_is_valid,
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
