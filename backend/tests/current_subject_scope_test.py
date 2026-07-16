"""Regression checks for current-session subject binding with a temporary SQLite DB."""

from __future__ import annotations

import asyncio
import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, PersonalSubjectModel, SessionModel
from app.db.repository import get_or_create_session
from app.routers import chat_router, product
from app.services.conversation_state import conversation_store


async def _fake_pipeline(**_state: object) -> dict[str, object]:
    return {"final_reply": "recorded", "agents_run": ["fake_conversation"]}


def main() -> None:
    handle, path = tempfile.mkstemp(prefix="edu-current-subject-", suffix=".db")
    os.close(handle)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    old_product_session, old_profile = product.SessionLocal, product.ag_get_profile
    old_chat_session, old_pipeline = chat_router.SessionLocal, chat_router.run_pipeline
    old_extract = conversation_store.extract_facts_with_llm
    session_ids = ("history", "empty", "explicit", "other-learner", "manual-subject")
    product.SessionLocal, product.ag_get_profile = factory, lambda _session_id: {}
    chat_router.SessionLocal, chat_router.run_pipeline = factory, _fake_pipeline
    conversation_store.extract_facts_with_llm = lambda state, message: conversation_store.extract_facts(state, message)
    try:
        db = factory()
        try:
            get_or_create_session(db, "history", learner_id="learner-a", subject_id="historical-subject", require_learner=True)
            get_or_create_session(db, "empty", learner_id="learner-a", require_learner=True)
            get_or_create_session(db, "explicit", learner_id="learner-a", require_learner=True)
            get_or_create_session(db, "other-learner", learner_id="learner-b", require_learner=True)
            get_or_create_session(db, "manual-subject", learner_id="learner-a", subject_id="manual-subject", require_learner=True)
            assert db.query(PersonalSubjectModel).count() == 0
        finally:
            db.close()

        # A topic-less session stays unbound and must not inherit history.
        asyncio.run(chat_router._run_chat("你好", "empty"))
        db = factory()
        try:
            assert db.get(SessionModel, "empty").subject_id is None
            assert db.query(PersonalSubjectModel).count() == 0
        finally:
            db.close()
        assert not product._profile_v2("empty")["subject_context"].get("subject_id")

        # An explicit current message creates/reuses one learner-owned subject.
        _, result = asyncio.run(chat_router._run_chat("我想学习数据结构", "explicit"))
        bound = result.get("current_subject") or {}
        assert bound.get("name") == "数据结构"
        db = factory()
        try:
            assert db.get(SessionModel, "explicit").subject_id == bound["id"]
            assert db.query(PersonalSubjectModel).filter_by(learner_id="learner-a", name="数据结构").count() == 1
        finally:
            db.close()
        assert product._profile_v2("explicit")["subject_context"]["subject_id"] == bound["id"]

        # A manually scoped session is never overwritten by a later message.
        asyncio.run(chat_router._run_chat("我想学习算法", "manual-subject"))
        db = factory()
        try:
            assert db.get(SessionModel, "manual-subject").subject_id == "manual-subject"
            assert db.query(PersonalSubjectModel).filter_by(learner_id="learner-a").count() == 1
        finally:
            db.close()

        # The same visible name is private to its learner.
        _, other = asyncio.run(chat_router._run_chat("我想学习数据结构", "other-learner"))
        assert other["current_subject"]["id"] != bound["id"]
    finally:
        product.SessionLocal, product.ag_get_profile = old_product_session, old_profile
        chat_router.SessionLocal, chat_router.run_pipeline = old_chat_session, old_pipeline
        conversation_store.extract_facts_with_llm = old_extract
        for session_id in session_ids:
            conversation_store._sessions.pop(session_id, None)
        engine.dispose()
        os.unlink(path)
    print("current subject scope: PASS")


if __name__ == "__main__":
    main()
