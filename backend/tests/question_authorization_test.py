"""Isolated authorization checks for canonical question routes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-question-auth-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "question-auth-test-secret"

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import AnswerRecordModel, Base, LearnerModel, PracticeQuestionModel, SessionModel
from app.main import app
from app.routers import product, questions
from app.services.question_access import resolve_owned_practice_question
from app.utils.auth import create_token

_SENTINEL = "SYNTHETIC_PRIVATE_FIELD"


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _question_route_pairs(router) -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"} and route.path.startswith("/questions")
    ]


def _seed() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="learner_a", nickname="A"),
            LearnerModel(id="learner_b", nickname="B"),
            LearnerModel(id="anon_00000000-0000-4000-8000-000000000003", nickname="Anonymous"),
            SessionModel(id="session_a", learner_id="learner_a"),
            SessionModel(id="session_b", learner_id="learner_b"),
            SessionModel(
                id="session_anon",
                learner_id="anon_00000000-0000-4000-8000-000000000003",
            ),
            PracticeQuestionModel(
                question_id="question_a", question_set_id="set_a", session_id="session_a",
                type="choice", stem="synthetic owner question", correct=_SENTINEL,
                explanation=_SENTINEL, scoring_rubric={"sentinel": _SENTINEL}, reference_answer=_SENTINEL,
            ),
            PracticeQuestionModel(
                question_id="question_b", question_set_id="set_b", session_id="session_b",
                type="choice", stem="synthetic other question", correct=_SENTINEL,
                explanation=_SENTINEL, scoring_rubric={"sentinel": _SENTINEL}, reference_answer=_SENTINEL,
            ),
            PracticeQuestionModel(
                question_id="question_anon", question_set_id="set_anon", session_id="session_anon",
                type="choice", stem="synthetic anonymous question", correct=_SENTINEL,
                explanation=_SENTINEL, scoring_rubric={"sentinel": _SENTINEL}, reference_answer=_SENTINEL,
            ),
            AnswerRecordModel(
                session_id="session_a", question_id="question_a", student_answer="synthetic-a",
                total_score=0, error_type="concept", error_explanation=_SENTINEL,
            ),
            AnswerRecordModel(
                session_id="session_b", question_id="question_b", student_answer="synthetic-b",
                total_score=0, error_type="concept", error_explanation=_SENTINEL,
            ),
        ])
        db.commit()
    finally:
        db.close()


def _assert_no_sensitive(response) -> None:
    assert _SENTINEL not in response.text
    assert "correct" not in response.text
    assert "explanation" not in response.text
    assert "scoring_rubric" not in response.text


def main() -> None:
    _seed()
    pairs = _question_route_pairs(questions.router)
    assert len(pairs) == len(set(pairs)), "canonical router has duplicate method/path pairs"
    assert not _question_route_pairs(product.router), "product router still registers question routes"
    openapi = app.openapi()["paths"]
    assert all(f"/api{path}" in openapi for _, path in pairs), "canonical question routes are not registered"

    with TestClient(app) as client:
        own = _headers("learner_a")

        for path in (
            "/api/questions?sessionId=session_a",
            "/api/questions/sets?sessionId=session_a",
            "/api/questions/history?sessionId=session_a",
            "/api/questions/weak?sessionId=session_a",
            "/api/questions/question_a?sessionId=session_a",
            "/api/questions/question_a?sessionId=session_a&reveal=true",
        ):
            response = client.get(path)
            assert response.status_code == 401
            _assert_no_sensitive(response)

        for method, path, body in (
            ("post", "/api/questions/generate", {"sessionId": "session_a", "message": "Synthetic request"}),
            ("post", "/api/questions/question_a/grade", {"sessionId": "session_a", "answer": "Synthetic answer"}),
            ("delete", "/api/questions/sets/set_a?sessionId=session_a", None),
        ):
            response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
            assert response.status_code == 401
            _assert_no_sensitive(response)

        response = client.get(
            "/api/questions?sessionId=session_anon&learnerId=anon_00000000-0000-4000-8000-000000000003"
        )
        assert response.status_code == 200
        assert [row["question_id"] for row in response.json()["data"]["questions"]] == ["question_anon"]
        _assert_no_sensitive(response)

        response = client.get("/api/questions?sessionId=session_a", headers=own)
        assert response.status_code == 200
        assert [row["question_id"] for row in response.json()["data"]["questions"]] == ["question_a"]
        _assert_no_sensitive(response)

        response = client.get("/api/questions?sessionId=session_b", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/question_b?sessionId=session_b&reveal=true", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/question_b?sessionId=session_a&reveal=true", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/history?sessionId=session_b", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/weak?sessionId=session_b", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/question_a?sessionId=session_a&reveal=true", headers=own)
        assert response.status_code == 200
        assert response.json()["data"]["question"]["correct"] == _SENTINEL

        response = client.get("/api/questions/history?sessionId=session_a", headers=own)
        assert response.status_code == 200
        assert [row["question_id"] for row in response.json()["data"]["records"]] == ["question_a"]

        response = client.get("/api/questions/weak?sessionId=session_a", headers=own)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

        response = client.get("/api/questions?sessionId=session_a&learnerId=learner_b", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.delete("/api/questions/sets/set_b?sessionId=session_b", headers=own)
        assert response.status_code == 403
        _assert_no_sensitive(response)

        response = client.get("/api/questions/review-queue")
        assert response.status_code == 401

        response = client.get("/api/questions/review-queue", headers=own)
        assert response.status_code == 403

        response = client.post(
            "/api/questions/review-action",
            json={"question_id": "question_a", "action": "approve"},
        )
        assert response.status_code == 401

        response = client.post(
            "/api/questions/review-action",
            headers=own,
            json={"question_id": "question_a", "action": "approve"},
        )
        assert response.status_code == 403

        response = client.get("/api/questions/missing?sessionId=session_a", headers=own)
        assert response.status_code == 404

        response = client.post(
            "/api/questions/question_b/grade",
            headers=own,
            json={"sessionId": "session_b", "answer": "synthetic", "learnerId": "learner_a"},
        )
        assert response.status_code == 403
        _assert_no_sensitive(response)

        original_grade = questions._grade
        original_run_agents = questions.run_agents
        original_append_message = questions.conversation_store.append_message
        try:
            questions._grade = lambda _session_id, _question, _answer: {"total_score": 100, "error_type": "null"}
            response = client.post(
                "/api/questions/question_a/grade",
                headers=own,
                json={"sessionId": "session_a", "answer": "synthetic"},
            )
            assert response.status_code == 200
            assert response.json()["data"]["gradingResult"]["total_score"] == 100

            questions.conversation_store.append_message = lambda *_args, **_kwargs: None
            questions.run_agents = lambda **_kwargs: {
                "question_set_id": "set_generated",
                "questions": [{
                    "question_id": "question_generated",
                    "type": "choice",
                    "stem": "synthetic generated question",
                    "correct": "A",
                }],
            }
            response = client.post(
                "/api/questions/generate",
                headers=own,
                json={"sessionId": "session_a", "message": "synthetic"},
            )
            assert response.status_code == 200
            assert response.json()["data"]["questionSetId"] == "set_generated"
        finally:
            questions._grade = original_grade
            questions.run_agents = original_run_agents
            questions.conversation_store.append_message = original_append_message

        response = client.delete("/api/questions/sets/set_a?sessionId=session_a", headers=own)
        assert response.status_code == 200
        remaining = client.get("/api/questions?sessionId=session_a", headers=own).json()["data"]["questions"]
        assert [row["question_id"] for row in remaining] == ["question_generated"]
        response = client.get("/api/questions?sessionId=session_b", headers=_headers("learner_b"))
        assert [row["question_id"] for row in response.json()["data"]["questions"]] == ["question_b"]

    db = SessionLocal()
    try:
        try:
            resolve_owned_practice_question(db, "question_b", "learner_a", session_id="session_a")
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("direct question resolver bypassed ownership")
    finally:
        db.close()

    print("question authorization: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
