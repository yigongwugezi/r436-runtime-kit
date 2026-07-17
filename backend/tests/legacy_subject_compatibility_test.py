"""Regression checks for legacy local-subject and session reads."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.middleware.auth import AuthContext
from app.routers import product, subjects
from app.services import agent_service


def main() -> None:
    handle, path = tempfile.mkstemp(prefix="edu-legacy-subject-", suffix=".db")
    os.close(handle)
    engine = create_engine(f"sqlite:///{path}")
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    old_subjects_session_local = subjects.SessionLocal
    old_product_session_local = product.SessionLocal
    old_agent_session_local = agent_service.SessionLocal
    subjects.SessionLocal = factory
    product.SessionLocal = factory
    agent_service.SessionLocal = factory
    legacy_subject_id = "subject_1700000000000_abc123"
    try:
        db = factory()
        try:
            db.add_all([
                LearnerModel(id="learner-a"),
                LearnerModel(id="learner-b"),
                SessionModel(id="legacy-session", learner_id=None, subject_id=legacy_subject_id),
                SessionModel(id="current-session", learner_id="learner-a", subject_id="ps-current"),
                SessionModel(id="unbound-session", learner_id="learner-a", subject_id=None),
                PersonalSubjectModel(id="ps-current", learner_id="learner-a", name="Current Subject"),
                PersonalSubjectModel(id="ps-no-session", learner_id="learner-a", name="No Session Subject"),
                LearningPathModel(
                    id="legacy-path",
                    session_id="legacy-session",
                    course_name="Legacy Course",
                    stages=[{"id": "stage-1", "title": "Legacy Stage", "chapters": []}],
                ),
                ResourceModel(id="legacy-resource", session_id="legacy-session", title="Legacy Resource"),
            ])
            db.commit()
        finally:
            db.close()

        migrated = subjects.migrate_subjects(
            subjects.MigrateSubjectsRequest(subjects=[{"id": legacy_subject_id, "name": "Legacy Course"}]),
            AuthContext(learner_id="learner-a"),
        )["data"]["subjects"]
        assert migrated[0]["id"] == legacy_subject_id
        assert any(item["id"] == legacy_subject_id for item in subjects.list_subjects(AuthContext(learner_id="learner-a"))["data"]["subjects"])

        assert subjects.get_subject_session(legacy_subject_id, AuthContext(learner_id="learner-a"))["data"]["session_id"] == "legacy-session"
        assert subjects.get_subject_session("ps-current", AuthContext(learner_id="learner-a"))["data"]["session_id"] == "current-session"
        assert subjects.get_subject_session("ps-no-session", AuthContext(learner_id="learner-a"))["data"]["session_id"] is None
        assert subjects.get_subject_session(legacy_subject_id, AuthContext(learner_id="learner-b"))["data"]["session_id"] is None

        db = factory()
        try:
            assert db.get(SessionModel, "legacy-session").learner_id is None
            assert db.get(SessionModel, "unbound-session").subject_id is None
        finally:
            db.close()

        sessions = product.list_sessions(legacy_subject_id, auth=AuthContext(learner_id="learner-a"))["data"]["sessions"]
        assert [item["id"] for item in sessions] == ["legacy-session"]
        assert product.get_chat_session("legacy-session", auth=AuthContext(learner_id="learner-a"))["data"]["sessionId"] == "legacy-session"
        try:
            product.get_chat_session("legacy-session", auth=AuthContext(learner_id="learner-b"))
            raise AssertionError("legacy session was visible to another learner")
        except HTTPException as exc:
            assert exc.status_code == 403

        path_response = product.get_learning_path(sessionId="legacy-session", subjectId=legacy_subject_id)
        assert path_response["data"]["path"]["id"] == "legacy-path"
        resources = product.get_resources(sessionId="legacy-session", subjectId=legacy_subject_id)["data"]["resources"]
        assert [item["id"] for item in resources] == ["legacy-resource"]
        product.get_profile(
            sessionId="legacy-session",
            subjectId=legacy_subject_id,
            auth=AuthContext(learner_id="learner-a"),
        )

        db = factory()
        try:
            assert db.get(SessionModel, "legacy-session").learner_id is None
        finally:
            db.close()
    finally:
        subjects.SessionLocal = old_subjects_session_local
        product.SessionLocal = old_product_session_local
        agent_service.SessionLocal = old_agent_session_local
        engine.dispose()
        os.unlink(path)
    print("legacy subject compatibility: PASS")


if __name__ == "__main__":
    main()
