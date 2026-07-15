"""Isolated regression checks for learner/session/Profile V2 boundaries."""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LearnerModel, SessionModel
from app.db.repository import get_or_create_session
from app.middleware.auth import AuthContext
from app.routers import product
from app.services import langgraph_orchestrator
from app.services.profile_v2 import build_profile_v2, merge_profile_scopes, update_fact_control


def main() -> None:
    handle, path = tempfile.mkstemp(prefix="edu-learner-profile-", suffix=".db")
    os.close(handle)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)
    old_session_local, old_get_profile = product.SessionLocal, product.ag_get_profile
    product.SessionLocal, product.ag_get_profile = factory, lambda _session_id: {}
    try:
        learner_a = AuthContext(learner_id="learner-a")
        product.create_chat_session({"sessionId": "session-a"}, learner_a)
        product.create_chat_session({"sessionId": "session-b"}, learner_a)
        product.create_chat_session({"sessionId": "subject-a", "subjectId": "subject-a"}, learner_a)
        product.create_chat_session({"sessionId": "subject-b", "subjectId": "subject-b"}, learner_a)
        product.create_chat_session({"sessionId": "legacy-no-learner"}, AuthContext())

        db = factory()
        try:
            assert db.get(SessionModel, "session-a").learner_id == "learner-a"
            assert db.get(SessionModel, "session-b").learner_id == "learner-a"
            assert db.get(SessionModel, "legacy-no-learner").learner_id is None
            assert db.query(LearnerModel).count() == 1
        finally:
            db.close()

        global_profile = build_profile_v2(
            facts={"background": "大二学生", "preference": "视频/动画"}, session_id="session-a"
        )
        product._save_profile_v2("session-a", global_profile, {"dimensions": []})
        session_b_profile = product._profile_v2("session-b")
        assert session_b_profile["subject_context"]["background"] == "大二学生"
        assert session_b_profile["subject_context"]["resource_preferences"] == ["视频"]
        assert "路径" not in str(session_b_profile)
        assert "大二学生" in langgraph_orchestrator._profile_query_reply("我现在是什么年级", session_b_profile, {})
        assert "视频" in langgraph_orchestrator._profile_query_reply("我偏好什么学习方式", session_b_profile, {})
        corrected = build_profile_v2(facts={"background": "大三学生"}, existing=session_b_profile, session_id="session-b")
        assert corrected["fact_records"]["background"]["supersedes"] == "大二学生"
        product._save_profile_v2("session-b", corrected, {"dimensions": []})
        assert product._profile_v2("session-a")["subject_context"]["background"] == "大三学生"

        subject_profile = build_profile_v2(
            facts={"learning_goal": "准备期末"}, course={"course_id": "subject-a", "course_name": "数据结构"}, session_id="subject-a"
        )
        product._save_profile_v2("subject-a", subject_profile, {"dimensions": []})
        assert product._profile_v2("subject-a")["subject_context"]["learning_goal"] == "准备期末"
        assert not product._profile_v2("subject-b")["subject_context"].get("learning_goal")

        product.create_chat_session({"sessionId": "session-other"}, AuthContext(learner_id="learner-b"))
        other_profile = product._profile_v2("session-other")
        assert not other_profile["subject_context"].get("background")
        assert not other_profile["subject_context"].get("resource_preferences")
        try:
            product.create_chat_session({"sessionId": "session-a"}, AuthContext(learner_id="learner-b"))
            raise AssertionError("another learner reused a session")
        except HTTPException as exc:
            assert exc.status_code == 403

        inferred = {"profile_version": 2, "subject_context": {"background": "大学生"}, "fact_records": {"background": {"value": "大学生", "fact_type": "inferred", "status": "active"}}}
        assert merge_profile_scopes(corrected, inferred)["subject_context"]["background"] == "大三学生"

        disabled = update_fact_control(session_b_profile, "resource_preferences", "disable")
        product._save_profile_v2("session-b", disabled, {"dimensions": []})
        disabled_profile = product._profile_v2("session-a")
        assert "视频" not in langgraph_orchestrator._profile_query_reply("我偏好什么学习方式", disabled_profile, {})

        locked = update_fact_control(disabled_profile, "background", "lock")
        locked = build_profile_v2(facts={"background": "大三学生"}, existing=locked, session_id="session-a")
        assert locked["subject_context"]["background"] == "大三学生"
        deleted = update_fact_control(locked, "background", "delete")
        product._save_profile_v2("session-a", deleted, {"dimensions": []})
        assert not product._profile_v2("session-b")["subject_context"].get("background")

        def create_concurrently() -> str | None:
            db = factory()
            try:
                return get_or_create_session(db, "concurrent-session", learner_id="learner-concurrent").learner_id
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert set(pool.map(lambda _item: create_concurrently(), range(2))) == {"learner-concurrent"}
        db = factory()
        try:
            assert db.query(LearnerModel).filter(LearnerModel.id == "learner-concurrent").count() == 1
        finally:
            db.close()
    finally:
        product.SessionLocal, product.ag_get_profile = old_session_local, old_get_profile
        engine.dispose()
        os.unlink(path)
    print("learner session profile: PASS")


if __name__ == "__main__":
    main()
