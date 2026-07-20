"""Regression checks for persisted path progress and stage access."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base
from app.db.repository import get_latest_learning_path, upsert_learning_path
from app.routers import product


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    stages = [
        {"stage_id": "s1", "tasks": [
            {"task_id": "t1", "status": "not_started"},
            {"task_id": "optional-map", "required": False, "status": "not_started"},
        ]},
        {"stage_id": "s2", "tasks": [{"task_id": "t2", "status": "not_started"}]},
        {"stage_id": "empty", "tasks": []},
    ]
    with patch.object(product, "SessionLocal", factory):
        db = factory()
        try:
            upsert_learning_path(db, "session-a", {"id": "path-a", "stages": stages})
        finally:
            db.close()
        assert [s["progressStatus"] for s in product._apply_stage_progress(stages)] == ["current", "locked", "locked"]
        product.update_node_progress("t1", {"sessionId": "session-a", "status": "completed", "mastery": 100})
        db = factory()
        try:
            saved = get_latest_learning_path(db, "session-a")
            assert saved.stages[0]["tasks"][0]["status"] == "completed"
        finally:
            db.close()
        refreshed = product._apply_stage_progress(saved.stages)
        assert [s["progressStatus"] for s in refreshed[:2]] == ["completed", "current"]
        assert refreshed[0]["requiredTaskCount"] == 1
        assert product._apply_stage_progress([{"tasks": [{"required": False}]}])[0]["progressStatus"] == "completed"
        product._require_stage_access("session-a", "s1")
        product._require_stage_access("session-a", "s2")
        try:
            product._require_stage_access("session-a", "empty")
            raise AssertionError("locked stage accepted")
        except HTTPException as exc:
            assert exc.status_code == 403
        product.update_node_progress("t1", {"sessionId": "session-a", "status": "completed", "mastery": 100})
    print("learning path stage lock tests: ok")


if __name__ == "__main__":
    main()
