"""Authorization regression coverage for all registered assessment routes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-assessment-auth-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "assessment-auth-test-secret"

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
from app.routers import assessment
from app.utils.auth import create_token

_SENTINEL = "SYNTHETIC_ASSESSMENT_PRIVATE_FIELD"


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _assert_private(response) -> None:
    assert _SENTINEL not in response.text
    assert "correctAnswer" not in response.text
    assert "errorExplanation" not in response.text


def _seed() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="learner_a", nickname="A"),
            LearnerModel(id="learner_b", nickname="B"),
            SessionModel(id="session_a", learner_id="learner_a"),
            SessionModel(id="session_b", learner_id="learner_b"),
            QuizModel(id="quiz_a", session_id="session_a", title="A quiz"),
            QuizModel(id="quiz_b", session_id="session_b", title="B quiz"),
            ExamSetModel(id="exam_a", session_id="session_a", title="A exam"),
            ExamSetModel(id="exam_b", session_id="session_b", title="B exam"),
            PracticeQuestionModel(
                question_id="question_a", question_set_id="quiz_a", session_id="session_a",
                type="choice", stem="owner question", options=["A", "B"], correct="A",
                explanation=_SENTINEL,
            ),
            PracticeQuestionModel(
                question_id="question_b", question_set_id="quiz_b", session_id="session_b",
                type="choice", stem="other question", options=["A", "B"], correct=_SENTINEL,
                explanation=_SENTINEL,
            ),
            PracticeQuestionModel(
                question_id="exam_question_a", question_set_id="exam_a", session_id="session_a",
                type="choice", stem="owner exam question", options=["A", "B"], correct="A",
            ),
            PracticeQuestionModel(
                question_id="exam_question_b", question_set_id="exam_b", session_id="session_b",
                type="choice", stem="other exam question", options=["A", "B"], correct=_SENTINEL,
                explanation=_SENTINEL,
            ),
            AttemptModel(attempt_id="attempt_a", session_id="session_a", quiz_id="quiz_a", learner_id="learner_a"),
            AttemptModel(attempt_id="attempt_b", session_id="session_b", quiz_id="quiz_b", learner_id="learner_b"),
            AttemptModel(attempt_id="exam_attempt_b", session_id="session_b", exam_set_id="exam_b", learner_id="learner_b"),
            AnswerRecordModel(
                session_id="session_b", attempt_id="attempt_b", question_id="question_b",
                student_answer="B", total_score=0, error_explanation=_SENTINEL,
            ),
        ])
        db.commit()
    finally:
        db.close()


def main() -> None:
    _seed()
    assessment._trigger_post_submit_assessment = lambda **_kwargs: None
    with TestClient(app) as client:
        owner = _headers("learner_a")

        for method, path, body in (
            ("get", "/api/quizzes/quiz_a", None),
            ("post", "/api/quizzes", {"sessionId": "session_a"}),
            ("post", "/api/attempts", {"sessionId": "session_a", "quizId": "quiz_a"}),
            ("get", "/api/exam-sets/exam_a", None),
            ("post", "/api/exam-sets", {"sessionId": "session_a"}),
        ):
            response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
            assert response.status_code == 401
            _assert_private(response)

        blocked = [
            ("get", "/api/quizzes?sessionId=session_b", None),
            ("post", "/api/quizzes", {"sessionId": "session_b"}),
            ("get", "/api/quizzes/quiz_b", None),
            ("post", "/api/quizzes/quiz_b/attempts", {"sessionId": "session_b"}),
            ("get", "/api/quizzes/quiz_b/attempts", None),
            ("get", "/api/quizzes/quiz_b/results", None),
            ("post", "/api/quizzes/quiz_b/submit", {"sessionId": "session_b", "answers": []}),
            ("delete", "/api/quizzes/quiz_b", None),
            ("post", "/api/sections/section_b/quiz/generate", {"sessionId": "session_b"}),
            ("post", "/api/attempts", {"sessionId": "session_b", "quizId": "quiz_b"}),
            ("get", "/api/attempts/attempt_b", None),
            ("patch", "/api/attempts/attempt_b", {"status": "submitted"}),
            ("post", "/api/attempts/attempt_b/submit", {"answers": []}),
            ("get", "/api/exam-sets?sessionId=session_b", None),
            ("post", "/api/exam-sets", {"sessionId": "session_b"}),
            ("get", "/api/exam-sets/exam_b", None),
            ("patch", "/api/exam-sets/exam_b", {"title": "attacker"}),
            ("post", "/api/exam-sets/exam_b/attempts", {"sessionId": "session_b"}),
            ("post", "/api/exam-sets/generate", {"sessionId": "session_b"}),
            ("post", "/api/exam-sets/exam_b/submit", {"sessionId": "session_b", "answers": []}),
            ("get", "/api/exam-sets/exam_b/results?attemptId=exam_attempt_b", None),
            ("get", "/api/exam-sets/exam_b/attempts", None),
            ("delete", "/api/exam-sets/exam_b", None),
        ]
        for method, path, body in blocked:
            response = getattr(client, method)(path, headers=owner, json=body) if body is not None else getattr(client, method)(path, headers=owner)
            assert response.status_code == 403, (method, path, response.text)
            _assert_private(response)

        response = client.get("/api/quizzes/not-a-real-quiz", headers=owner)
        assert response.status_code == 403
        response = client.get("/api/quizzes/quiz_a/results?attemptId=not-a-real-attempt", headers=owner)
        assert response.status_code == 404

        response = client.get("/api/quizzes?sessionId=session_a", headers=owner)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["data"]["quizzes"]] == ["quiz_a"]
        response = client.get("/api/exam-sets?sessionId=session_a", headers=owner)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["data"]["examSets"]] == ["exam_a"]

        response = client.post("/api/quizzes/quiz_a/attempts", headers=owner, json={"sessionId": "session_b"})
        assert response.status_code == 403
        response = client.post("/api/attempts", headers=owner, json={"sessionId": "session_b", "quizId": "quiz_a"})
        assert response.status_code == 403

        response = client.post(
            "/api/attempts", headers=owner,
            json={"sessionId": "session_a", "quizId": "quiz_a", "learnerId": "learner_b"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["attempt"]["learnerId"] == "learner_a"

        response = client.post(
            "/api/quizzes/quiz_a/submit", headers=owner,
            json={"sessionId": "session_a", "answers": [{"questionId": "question_a", "answer": "A"}]},
        )
        assert response.status_code == 200
        assert response.json()["data"]["totalScore"] == 100

        response = client.post(
            "/api/exam-sets/exam_a/submit", headers=owner,
            json={"sessionId": "session_a", "answers": [{"questionId": "exam_question_a", "answer": "A"}]},
        )
        assert response.status_code == 200
        assert response.json()["data"]["totalScore"] == 100

    print("assessment authorization: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
