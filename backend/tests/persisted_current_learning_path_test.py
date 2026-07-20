"""Regression checks for durable, scope-safe generated learning paths."""

import sys
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearnerModel, LearningPathModel, SessionModel
from app.db.repository import (
    CurrentPathUnresolvedError,
    persist_generated_learning_path,
    resolve_current_learning_path,
)
from app.routers import knowledge_graph
from app.middleware.auth import AuthContext


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.add(LearnerModel(id="learner", nickname="Learner"))
        db.add(SessionModel(id="session", learner_id="learner", subject_id="subject"))
        db.commit()
        candidate = {"course_id": "course", "course_name": "Course", "stages": [{"id": "stage", "days": [{"id": "day", "tasks": [{"id": "task"}]}]}]}
        first = persist_generated_learning_path(
            db, learner_id="learner", session_id="session", subject_id="subject", workflow_id="workflow", path_data=candidate,
        )
        db.commit()
        same = persist_generated_learning_path(
            db, learner_id="learner", session_id="session", subject_id="subject", workflow_id="workflow", path_data=candidate,
        )
        db.commit()
        assert first.id == same.id
        assert resolve_current_learning_path(db, learner_id="learner", session_id="session", subject_id="subject").id == first.id
        assert resolve_current_learning_path(db, learner_id="learner", session_id="session", subject_id="subject", path_id=first.id).id == first.id
        assert resolve_current_learning_path(db, learner_id="learner", session_id="session", subject_id="other", path_id=first.id) is None
        assert resolve_current_learning_path(db, learner_id="other-learner", session_id="session", subject_id="subject", path_id=first.id) is None

        db.add(LearningPathModel(id="legacy", session_id="session", subject_id="", stages=[]))
        db.add(SessionModel(id="legacy-session", learner_id="learner", subject_id="legacy-subject"))
        db.add(LearningPathModel(id="legacy-only", session_id="legacy-session", subject_id="", stages=[]))
        db.commit()
        try:
            resolve_current_learning_path(db, learner_id="learner", session_id="legacy-session", subject_id="legacy-subject")
            raise AssertionError("legacy path was selected implicitly")
        except CurrentPathUnresolvedError:
            pass

        with patch.object(knowledge_graph, "ag_get_learning_path", side_effect=CurrentPathUnresolvedError()), \
             patch.object(knowledge_graph, "_resolve_session_id", return_value="legacy-session"), \
             patch.object(knowledge_graph, "_ensure_session_linked"), \
             patch.object(knowledge_graph, "_require_session_learner"):
            graph = knowledge_graph.get_knowledge_graph(
                sessionId="legacy-session", subjectId="legacy-subject", auth=AuthContext(learner_id="learner")
            )
            assert graph["data"]["nodes"] == []
    finally:
        db.close()
        engine.dispose()
    print("persisted current learning path: PASS")


if __name__ == "__main__":
    main()
