"""Idempotency contract tests for quiz/exam assessment submission.

Each test uses a unique quiz_id to avoid cross-test DB conflicts.
The database file is created once and reused across all tests in the run.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-assessment-idem-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "assessment-idempotency-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import (
    AnswerRecordModel,
    AttemptModel,
    Base,
    ExamSetModel,
    LearnerModel,
    PracticeQuestionModel,
    QuizModel,
    SessionModel,
)
from app.main import app
from app.utils.auth import create_token

_LEARNER_A = "learner_idem_a"
_LEARNER_B = "learner_idem_b"
_SESSION_ID = "session_idem_main"


def _headers(learner_id: str = _LEARNER_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _setup_base() -> None:
    """Create tables and seed base learners/session. Idempotent."""
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.query(LearnerModel).filter(LearnerModel.id == _LEARNER_A).first()
        if existing is None:
            db.add_all([
                LearnerModel(id=_LEARNER_A, nickname="IdempotencyTester"),
                LearnerModel(id=_LEARNER_B, nickname="OtherLearner"),
            ])
            db.flush()
        existing_sess = db.query(SessionModel).filter(SessionModel.id == _SESSION_ID).first()
        if existing_sess is None:
            db.add(SessionModel(id=_SESSION_ID, learner_id=_LEARNER_A, subject_id="math"))
            db.flush()
        db.commit()
    finally:
        db.close()


def _seed_quiz(suffix: str = "") -> tuple[str, str]:
    """Create a quiz with 3 choice questions. Returns (quiz_id, session_id).

    Each call with a different suffix creates a separate quiz, avoiding
    cross-test conflicts.
    """
    _setup_base()
    db = SessionLocal()
    try:
        quiz_id = f"quiz_idem_{suffix}" if suffix else f"quiz_idem_{uuid.uuid4().hex[:8]}"
        quiz = QuizModel(
            id=quiz_id, title=f"Quiz {suffix}",
            session_id=_SESSION_ID, scope_type="section",
            question_count=3, source="test",
        )
        db.add(quiz)
        db.flush()

        for i, (correct_letter, stem_text) in enumerate([
            ("A", "What is 2+2?"),
            ("B", "What is the capital of France?"),
            ("C", "Which planet is closest to the sun?"),
        ]):
            pq = PracticeQuestionModel(
                question_id=f"q_{suffix}_{i}" if suffix else f"q_{uuid.uuid4().hex[:6]}_{i}",
                question_set_id=quiz_id,
                session_id=_SESSION_ID,
                type="choice",
                stem=stem_text,
                options=[f"A. optA_{i}", f"B. optB_{i}", f"C. optC_{i}", f"D. optD_{i}"],
                correct=correct_letter,
                explanation=f"Explanation for q{i}",
                knowledge_points=[f"kp_{i}"],
                source="test",
                quality_status="passed",
            )
            db.add(pq)
        db.commit()
        return quiz_id, _SESSION_ID
    finally:
        db.close()


def _submit(
    quiz_id: str, session_id: str, idem_key: str,
    answers: list[dict], learner_id: str = _LEARNER_A,
    answers_revealed: bool = False,
) -> tuple[int, dict]:
    """Submit quiz answers and return (status_code, json_body)."""
    client = TestClient(app)
    body: dict = {
        "sessionId": session_id,
        "idempotencyKey": idem_key,
        "answers": answers,
    }
    if answers_revealed:
        body["answersRevealed"] = True
    resp = client.post(
        f"/api/quizzes/{quiz_id}/submit",
        json=body,
        headers=_headers(learner_id),
    )
    return resp.status_code, resp.json()


def _correct_answers(suffix: str = "") -> list[dict]:
    q_prefix = f"q_{suffix}_" if suffix else "q_"
    # We need to discover the actual question IDs from the DB
    db = SessionLocal()
    try:
        quiz_id = f"quiz_idem_{suffix}" if suffix else None
        if quiz_id:
            pqs = db.query(PracticeQuestionModel).filter(
                PracticeQuestionModel.question_set_id == quiz_id,
            ).order_by(PracticeQuestionModel.question_id).all()
            if len(pqs) >= 3:
                return [
                    {"questionId": pqs[0].question_id, "answer": "A"},
                    {"questionId": pqs[1].question_id, "answer": "B"},
                    {"questionId": pqs[2].question_id, "answer": "C"},
                ]
    finally:
        db.close()
    # Fallback
    return [
        {"questionId": f"q_{suffix}_0", "answer": "A"},
        {"questionId": f"q_{suffix}_1", "answer": "B"},
        {"questionId": f"q_{suffix}_2", "answer": "C"},
    ]


# ── Tests ────────────────────────────────────────────────────────────────

def test_normal_submit_creates_attempt():
    """1. Normal submit → 200, attempt created with expected fields."""
    quiz_id, session_id = _seed_quiz("t1")
    status, body = _submit(quiz_id, session_id, "key-1", _correct_answers("t1"))
    assert status == 200, f"Expected 200, got {status}: {body}"
    data = body.get("data", {})
    attempt = data.get("attempt", {})
    assert attempt.get("attemptId", "").startswith("att_"), f"Missing attemptId: {attempt}"
    assert attempt.get("status") == "graded"
    assert attempt.get("idempotencyKey") == "key-1"
    assert attempt.get("attemptNumber") == 1
    assert attempt.get("assessmentEligible") is True
    assert data.get("totalScore") is not None
    assert len(data.get("results", [])) == 3


def test_same_key_same_content_returns_existing():
    """2. Same idempotency_key + same answers → 200, SAME attempt returned."""
    quiz_id, session_id = _seed_quiz("t2")
    answers = _correct_answers("t2")

    status1, body1 = _submit(quiz_id, session_id, "key-same", answers)
    assert status1 == 200
    attempt_id_1 = body1["data"]["attempt"]["attemptId"]

    status2, body2 = _submit(quiz_id, session_id, "key-same", answers)
    assert status2 == 200
    attempt_id_2 = body2["data"]["attempt"]["attemptId"]

    assert attempt_id_1 == attempt_id_2, (
        f"Idempotent replay should return same attempt: {attempt_id_1} != {attempt_id_2}"
    )
    assert body2["data"].get("idempotentReplay") is True, "Should mark idempotentReplay=True"


def test_same_key_same_content_no_duplicate_records():
    """3. Idempotent replay does NOT create duplicate AnswerRecords."""
    quiz_id, session_id = _seed_quiz("t3")
    answers = _correct_answers("t3")
    idem_key = "key-no-dup"

    _, body1 = _submit(quiz_id, session_id, idem_key, answers)
    _, body2 = _submit(quiz_id, session_id, idem_key, answers)
    assert body2["data"].get("idempotentReplay") is True

    # Check DB
    db = SessionLocal()
    try:
        attempt = db.query(AttemptModel).filter(
            AttemptModel.idempotency_key == idem_key,
            AttemptModel.learner_id == _LEARNER_A,
        ).first()
        assert attempt is not None
        records = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.attempt_id == attempt.attempt_id,
        ).all()
        assert len(records) == 3, f"Expected 3 AnswerRecords, got {len(records)}"
    finally:
        db.close()


def test_same_key_different_content_409():
    """4. Same idempotency_key + different answers → 409 Conflict."""
    quiz_id, session_id = _seed_quiz("t4")
    answers = _correct_answers("t4")
    idem_key = "key-diff"

    status1, _ = _submit(quiz_id, session_id, idem_key, answers)
    assert status1 == 200

    # Discover question IDs from DB to construct different answers
    db = SessionLocal()
    try:
        pqs = db.query(PracticeQuestionModel).filter(
            PracticeQuestionModel.question_set_id == quiz_id,
        ).order_by(PracticeQuestionModel.question_id).all()
        diff_answers = [
            {"questionId": pqs[0].question_id, "answer": "B"},  # was A
            {"questionId": pqs[1].question_id, "answer": "B"},
            {"questionId": pqs[2].question_id, "answer": "C"},
        ]
    finally:
        db.close()

    status2, body2 = _submit(quiz_id, session_id, idem_key, diff_answers)
    assert status2 == 409, f"Expected 409, got {status2}: {body2}"
    assert "idempotency" in str(body2.get("detail", "")).lower()


def test_different_keys_create_separate_attempts():
    """5. Different idempotency_keys → separate attempts."""
    quiz_id, session_id = _seed_quiz("t5")
    answers = _correct_answers("t5")

    _, body1 = _submit(quiz_id, session_id, "key-a", answers)
    _, body2 = _submit(quiz_id, session_id, "key-b", answers)

    aid1 = body1["data"]["attempt"]["attemptId"]
    aid2 = body2["data"]["attempt"]["attemptId"]
    assert aid1 != aid2, "Different keys should create different attempts"


def test_attempt_number_increments():
    """6. attempt_number increments correctly: 1st=1, 2nd=2, 3rd=3."""
    quiz_id, session_id = _seed_quiz("t6")
    answers = _correct_answers("t6")

    _, body1 = _submit(quiz_id, session_id, "key-n1", answers)
    _, body2 = _submit(quiz_id, session_id, "key-n2", answers)
    _, body3 = _submit(quiz_id, session_id, "key-n3", answers)

    assert body1["data"]["attempt"]["attemptNumber"] == 1
    assert body2["data"]["attempt"]["attemptNumber"] == 2
    assert body3["data"]["attempt"]["attemptNumber"] == 3


def test_answers_revealed_makes_not_eligible():
    """7. answersRevealed=true → assessment_eligible=false."""
    quiz_id, session_id = _seed_quiz("t7")
    answers = _correct_answers("t7")

    status, body = _submit(quiz_id, session_id, "key-revealed", answers, answers_revealed=True)
    assert status == 200
    assert body["data"]["attempt"]["assessmentEligible"] is False


def test_answers_not_revealed_is_eligible():
    """8. answersRevealed=false → assessment_eligible=true."""
    quiz_id, session_id = _seed_quiz("t8")
    answers = _correct_answers("t8")

    status, body = _submit(quiz_id, session_id, "key-not-revealed", answers)
    assert status == 200
    assert body["data"]["attempt"]["assessmentEligible"] is True


def test_non_owner_403():
    """9. Cross-learner access → 403."""
    quiz_id, session_id = _seed_quiz("t9")
    answers = _correct_answers("t9")
    status, body = _submit(quiz_id, session_id, "key-auth", answers, learner_id=_LEARNER_B)
    assert status == 403, f"Expected 403, got {status}: {body}"


def test_missing_idempotency_key_422():
    """10. Missing idempotency_key → 422."""
    quiz_id, session_id = _seed_quiz("t10")
    client = TestClient(app)

    resp = client.post(
        f"/api/quizzes/{quiz_id}/submit",
        json={
            "sessionId": session_id,
            "answers": _correct_answers("t10"),
        },
        headers=_headers(),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_concurrent_same_key_only_one_attempt():
    """11. Concurrent submits with same key → only one attempt created."""
    quiz_id, session_id = _seed_quiz("t11")
    answers = _correct_answers("t11")
    idem_key = "key-concurrent"

    def _do_submit() -> tuple[int, dict | None]:
        try:
            return _submit(quiz_id, session_id, idem_key, answers)
        except Exception as e:
            return 0, {"error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_do_submit) for _ in range(4)]
        for f in as_completed(futures):
            results.append(f.result())

    # All should succeed (some may be replays, some may succeed)
    success_count = sum(1 for s, _ in results if s == 200)
    assert success_count >= 1, f"At least 1 request should succeed: {results}"

    # Verify only one attempt in DB
    db = SessionLocal()
    try:
        attempts = db.query(AttemptModel).filter(
            AttemptModel.idempotency_key == idem_key,
            AttemptModel.learner_id == _LEARNER_A,
        ).all()
        assert len(attempts) == 1, f"Expected 1 attempt, got {len(attempts)}"
    finally:
        db.close()


def test_subject_id_populated():
    """12. subject_id is populated from the session."""
    quiz_id, session_id = _seed_quiz("t12")
    _, body = _submit(quiz_id, session_id, "key-subj", _correct_answers("t12"))
    attempt = body["data"]["attempt"]
    assert attempt.get("subjectId") == "math", f"Expected subjectId='math', got {attempt.get('subjectId')}"


def test_graded_at_is_set():
    """13. graded_at timestamp is set on successful grading."""
    quiz_id, session_id = _seed_quiz("t13")
    _, body = _submit(quiz_id, session_id, "key-graded-at", _correct_answers("t13"))
    attempt = body["data"]["attempt"]
    assert attempt.get("gradedAt") is not None, "gradedAt should be set on graded attempt"


def test_exam_set_idempotency():
    """14. Exam set submission also respects idempotency."""
    _setup_base()
    db = SessionLocal()
    try:
        exam_id = "exam_idem_t14"
        exam = ExamSetModel(
            id=exam_id, title="Idempotency Test Exam",
            session_id=_SESSION_ID, scope_type="chapter",
            question_count=2, source="test",
        )
        db.add(exam)
        db.flush()

        for i in range(2):
            pq = PracticeQuestionModel(
                question_id=f"eq_t14_{i}",
                question_set_id=exam_id,
                session_id=_SESSION_ID,
                type="choice",
                stem=f"Exam question {i}",
                options=["A. a", "B. b", "C. c", "D. d"],
                correct="A",
                explanation="Because A",
                knowledge_points=[f"ekp_{i}"],
                source="test",
                quality_status="passed",
            )
            db.add(pq)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    answers = [{"questionId": "eq_t14_0", "answer": "A"}, {"questionId": "eq_t14_1", "answer": "A"}]

    # First submit
    r1 = client.post(
        f"/api/exam-sets/{exam_id}/submit",
        json={"sessionId": _SESSION_ID, "idempotencyKey": "exam-key-t14", "answers": answers},
        headers=_headers(),
    )
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.json()}"

    # Same key, same answers → replay
    r2 = client.post(
        f"/api/exam-sets/{exam_id}/submit",
        json={"sessionId": _SESSION_ID, "idempotencyKey": "exam-key-t14", "answers": answers},
        headers=_headers(),
    )
    assert r2.status_code == 200
    assert r1.json()["data"]["attempt"]["attemptId"] == r2.json()["data"]["attempt"]["attemptId"]
    assert r2.json()["data"].get("idempotentReplay") is True

    # Same key, different answers → 409
    diff = [{"questionId": "eq_t14_0", "answer": "B"}, {"questionId": "eq_t14_1", "answer": "A"}]
    r3 = client.post(
        f"/api/exam-sets/{exam_id}/submit",
        json={"sessionId": _SESSION_ID, "idempotencyKey": "exam-key-t14", "answers": diff},
        headers=_headers(),
    )
    assert r3.status_code == 409, f"Expected 409, got {r3.status_code}: {r3.json()}"


# ── Run ──────────────────────────────────────────────────────────────────

def main():
    tests = [
        test_normal_submit_creates_attempt,
        test_same_key_same_content_returns_existing,
        test_same_key_same_content_no_duplicate_records,
        test_same_key_different_content_409,
        test_different_keys_create_separate_attempts,
        test_attempt_number_increments,
        test_answers_revealed_makes_not_eligible,
        test_answers_not_revealed_is_eligible,
        test_non_owner_403,
        test_missing_idempotency_key_422,
        test_concurrent_same_key_only_one_attempt,
        test_subject_id_populated,
        test_graded_at_is_set,
        test_exam_set_idempotency,
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
