from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LearningEventModel, ResourceModel, SessionModel
from app.routers.product import (
    _external_feedback_by_url,
    _generated_feedback,
    _upsert_external_feedback,
    _upsert_generated_feedback,
)


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

    _upsert_generated_feedback(
        db, "session_a", "subject_a", "section_a", "code_trace", "too_hard", 2, "先用更小的例子",
    )
    _upsert_generated_feedback(
        db, "session_a", "subject_a", "section_a", "code_trace", "too_easy", 5, "补充边界条件",
    )
    assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "generated_resource_feedback").count() == 1
    saved = _generated_feedback(db, "session_a", "subject_a", "section_a", "code_trace")
    assert saved and saved["feedback"] == "too_easy" and saved["rating"] == 5 and saved["comment"] == "补充边界条件"
    assert not _generated_feedback(db, "session_a", "subject_b", "section_a", "code_trace")
    assert not _generated_feedback(db, "session_b", "subject_b", "section_a", "code_trace")
    print("section resource feedback: PASS")


if __name__ == "__main__":
    main()
