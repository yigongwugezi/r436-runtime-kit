"""Semantic quiz ensure never reuses positional task IDs across revisions."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearningPathModel, PracticeQuestionModel, QuizModel, SessionModel
from app.db.repository import upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import assessment


SESSION, SUBJECT, PATH, STAGE, TASK = "semantic-session", "subject", "semantic-path", "stage", "stable-task"


def task(title: str, points: list[str]) -> dict:
    return {"id": TASK, "type": "quiz_prac", "title": title, "description": title, "knowledge_points": points}


def replace_task(factory, title: str, points: list[str]) -> None:
    db = factory()
    try:
        path = db.get(LearningPathModel, PATH)
        path.stages = [{"id": STAGE, "title": "Course design", "days": [{"id": "day-1", "globalDayIndex": 1, "tasks": [task(title, points)]}]}]
        path.current_version += 1
        flag_modified(path, "stages")
        db.commit()
    finally:
        db.close()


def main() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    app = FastAPI(); app.include_router(assessment.router, prefix="/api")
    app.dependency_overrides[assessment.require_auth] = lambda: AuthContext(learner_id="learner")
    scope = {"sessionId": SESSION, "subjectId": SUBJECT, "pathId": PATH, "stageId": STAGE, "dayId": f"{STAGE}_d1", "globalDayIndex": 1, "taskId": TASK}
    with patch.object(assessment, "SessionLocal", factory):
        db = factory()
        try:
            db.add(SessionModel(id=SESSION, learner_id="learner", subject_id=SUBJECT))
            upsert_learning_path(db, SESSION, {"id": PATH, "stages": [{"id": STAGE, "title": "Algorithms", "days": [{"id": "day-1", "globalDayIndex": 1, "tasks": [task("Complexity practice", ["time complexity", "linked list"])]}]}]})
            db.add(QuizModel(id="legacy-empty", session_id=SESSION, path_id=PATH, stage_id=STAGE, section_id=TASK, title="legacy"))
            db.add_all([PracticeQuestionModel(question_id=f"{TASK}-q{i}", question_set_id="legacy-questions", session_id=SESSION, type="choice", stem=f"old {i}", options=["A", "B", "C", "D"], correct="A", explanation="old") for i in range(1, 6)])
            db.commit()
        finally:
            db.close()
        with TestClient(app, raise_server_exceptions=False) as client:
            old = client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope)
            assert old.status_code == 200 and len(old.json()["data"]["quiz"]["questions"]) == 5, old.text
            old_quiz = old.json()["data"]["quiz"]
            replace_task(factory, "Outline element matching", ["learning objectives", "course content", "assessment methods"])
            new = client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope)
            assert new.status_code == 200 and len(new.json()["data"]["quiz"]["questions"]) == 5, new.text
            new_quiz = new.json()["data"]["quiz"]
            assert new_quiz["quizId"] != old_quiz["quizId"]
            assert len({q["questionId"] for q in new_quiz["questions"]}) == 5
            assert all(not q["questionId"].startswith(f"{TASK}-q") for q in new_quiz["questions"])
            assert not any(word in " ".join(q["stem"] for q in new_quiz["questions"]).lower() for word in ("complexity", "linked list", "o(n)"))
            repeated = client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope)
            assert repeated.status_code == 200 and repeated.json()["data"]["quiz"] == new_quiz
            with ThreadPoolExecutor(max_workers=2) as pool:
                concurrent = list(pool.map(lambda _index: client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope), range(2)))
            assert all(response.status_code == 200 and response.json()["data"]["quiz"]["quizId"] == new_quiz["quizId"] for response in concurrent)

            replace_task(factory, "Atomic outline", ["learning objectives", "course structure", "teaching methods"])
            inserts = {"count": 0}
            def fail_third(_mapper, _connection, _target):
                inserts["count"] += 1
                if inserts["count"] == 3:
                    raise RuntimeError("injected question write failure")
            event.listen(PracticeQuestionModel, "before_insert", fail_third)
            failed = client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope)
            event.remove(PracticeQuestionModel, "before_insert", fail_third)
            assert failed.status_code >= 500
            db = factory()
            try:
                assert db.query(QuizModel).count() == 3
                assert db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_set_id.like("quiz_%")).count() == 10
            finally:
                db.close()
            recovered = client.post(f"/api/learning-path/tasks/{TASK}/quiz/ensure", json=scope)
            assert recovered.status_code == 200 and len(recovered.json()["data"]["quiz"]["questions"]) == 5

        db = factory()
        try:
            assert db.get(QuizModel, "legacy-empty") is not None
            assert db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_set_id == "legacy-questions").count() == 5
            assert db.query(QuizModel).count() == 4
            assert db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_set_id == recovered.json()["data"]["quiz"]["quizId"]).count() == 5
        finally:
            db.close()
    engine.dispose()
    print("learning path quiz semantic ensure: PASS")


if __name__ == "__main__":
    main()
