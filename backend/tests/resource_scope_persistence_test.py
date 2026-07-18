import os
import tempfile
from pathlib import Path

handle, path = tempfile.mkstemp(prefix="resource-scope-", suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{path}"
os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, PersonalSubjectModel, SessionModel
from app.db.repository import get_resources, upsert_resource


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([LearnerModel(id="learner"), PersonalSubjectModel(id="math", learner_id="learner", name="Math"), SessionModel(id="session", learner_id="learner", subject_id="math")])
        db.commit()
        saved = upsert_resource(db, "session", {"id": "r1", "type": "lecture", "title": "t", "content": "body", "path_id": "path", "related_stage_id": "stage"})
        assert (saved.learner_id, saved.subject_id, saved.path_id, saved.generation_version) == ("learner", "math", "path", 1)
        db.commit(); db.expire_all()
        assert get_resources(db, "session")[0].id == "r1"
    finally:
        db.close(); engine.dispose(); Path(path).unlink(missing_ok=True)
    print("resource scope persistence: PASS")


if __name__ == "__main__":
    main()
