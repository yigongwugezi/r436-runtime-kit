"""Small runnable contract for the browser-QA seed; no normal DB is touched."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.seed_browser_qa import IDS, seed


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="eduagent-qa-") as temp:
        db = Path(temp) / ".qa" / "qa.db"
        result = seed(db)
        assert db.exists() and result["ids"] == IDS
        from app.db import SessionLocal
        from app.db.models import LearningPathModel, PracticeQuestionModel
        session = SessionLocal()
        try:
            assert session.get(LearningPathModel, IDS["path"]).pending_revision["diff"]["changed_tasks"] == []
            assert session.query(PracticeQuestionModel).filter_by(question_set_id=IDS["quiz"]).count() == 5
        finally:
            session.close()
            from app.db.engine import engine
            engine.dispose()
    print("browser QA sandbox seed: PASS")


if __name__ == "__main__":
    main()
