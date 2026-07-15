"""Isolated regression checks for personal-subject identity."""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LearnerModel, PersonalSubjectModel, SessionModel
from app.middleware.auth import AuthContext
from app.routers import subjects
from app.services.subject_identity import (
    canonical_subject_name,
    get_or_create_personal_subject,
    subject_deduplication_dry_run,
)


def main() -> None:
    handle, path = tempfile.mkstemp(prefix="edu-subject-identity-", suffix=".db")
    os.close(handle)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)
    old_session_local = subjects.SessionLocal
    subjects.SessionLocal = factory
    try:
        db = factory()
        try:
            db.add_all([LearnerModel(id="learner-a"), LearnerModel(id="learner-b")])
            db.commit()
        finally:
            db.close()

        variants = ["\u6570\u636e\u7ed3\u6784", "\u6570\u636e\u7ed3\u6784\u3001", " \u6570\u636e\u7ed3\u6784 ", "\u6570\u636e\u7ed3\u6784\uff0c"]
        ids = [
            subjects.create_subject(subjects.CreateSubjectRequest(name=name), AuthContext(learner_id="learner-a"))["data"]["subject"]["id"]
            for name in variants
        ]
        assert len(set(ids)) == 1
        assert canonical_subject_name("\u9012\u5f52\u8c03\u7528\u6808") == "\u9012\u5f52\u8c03\u7528\u6808"
        assert canonical_subject_name("C++") == "C++"
        assert canonical_subject_name("\u6982\u7387\u8bba\u4e0e\u6570\u7406\u7edf\u8ba1") == "\u6982\u7387\u8bba\u4e0e\u6570\u7406\u7edf\u8ba1"
        other = subjects.create_subject(subjects.CreateSubjectRequest(name=variants[0]), AuthContext(learner_id="learner-b"))
        assert other["data"]["subject"]["id"] != ids[0]

        def create_concurrently() -> str:
            db = factory()
            try:
                return get_or_create_personal_subject(db, "learner-a", "\u9012\u5f52\u8c03\u7528\u6808")[0].id
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            assert len(set(pool.map(lambda _item: create_concurrently(), range(8)))) == 1

        db = factory()
        try:
            db.add_all([
                PersonalSubjectModel(id="legacy-1", learner_id="learner-a", name="\u7ebf\u6027\u4ee3\u6570\uff0c"),
                PersonalSubjectModel(id="legacy-2", learner_id="learner-a", name="\u7ebf\u6027\u4ee3\u6570"),
                SessionModel(id="legacy-session", learner_id="learner-a", subject_id="legacy-1"),
            ])
            db.commit()
            before = db.query(PersonalSubjectModel).count()
            report = subject_deduplication_dry_run(db, "learner-a")
            assert len(report) == 1 and report[0]["dry_run"] is True
            assert report[0]["canonical_subject_id"] == "legacy-2"
            assert report[0]["impact"]["sessions"] == 1
            assert db.query(PersonalSubjectModel).count() == before
        finally:
            db.close()
    finally:
        subjects.SessionLocal = old_session_local
        engine.dispose()
        os.unlink(path)
    print("subject identity: PASS")


if __name__ == "__main__":
    main()
