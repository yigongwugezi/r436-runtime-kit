from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LearningEventModel, ResourceModel, SessionModel
from app.routers.product import _external_feedback_by_url, _upsert_external_feedback


def main() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([SessionModel(id="session_a", subject_id="subject_a"), SessionModel(id="session_b", subject_id="subject_b")])
    db.commit()

    first = _upsert_external_feedback(
        db, session_id="session_a", subject_id="subject_a", section_id="section_a",
        url="https://www.bilibili.com/video/BV1demo?utm_source=test", resource_type="video", feedback="not_relevant",
    )
    assert first["url_hash"] and first["domain"] == "bilibili.com"
    _upsert_external_feedback(
        db, session_id="session_a", subject_id="subject_a", section_id="section_a",
        url="https://www.bilibili.com/video/BV1demo", resource_type="video", feedback="helpful",
    )
    assert db.query(LearningEventModel).count() == 1
    assert _external_feedback_by_url(db, "session_a", "subject_a", "section_a")[first["url_hash"]] == "helpful"
    assert not _external_feedback_by_url(db, "session_a", "subject_a", "section_b")
    assert not _external_feedback_by_url(db, "session_b", "subject_b", "section_a")
    assert db.query(ResourceModel).count() == 0
    print("section resource feedback: PASS")


if __name__ == "__main__":
    main()
