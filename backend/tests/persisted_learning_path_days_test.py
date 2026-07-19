"""Regression: legacy one-day stages upgrade once into persisted 30-day paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-persisted-days-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearningPathModel, SessionModel
from app.main import app
from app.routers.product import normalize_learning_path

SESSION = "session_1784446310007_7d7aa03f-d55e-4aea-ae16-ff11c4c255ce"
PATH = f"path_{SESSION}"


def _legacy_stages() -> list[dict]:
    counts = [8, 6, 6, 5, 5, 5]
    minutes = [[30, 25, 20, 30, 30, 45, 20, 25], [30, 30, 45, 25, 40, 20], [30, 35, 50, 20, 25, 30], [30, 30, 50, 20, 25], [30, 35, 50, 25, 25], [30, 60, 40, 30, 30]]
    return [{
        "stage_id": f"{PATH}_s{stage_index}", "title": f"stage {stage_index}",
        "days": [{"day": 1, "tasks": [{
            "task_id": f"{PATH}_s{stage_index}_d1_t{task_index}", "title": f"task {stage_index}-{task_index}",
            "type": "review" if task_index == count - 1 else "read_doc", "estimated_minutes": minutes[stage_index][task_index], "status": "pending",
        } for task_index in range(count)]}],
    } for stage_index, count in enumerate(counts)]


def _assert_contract(path: dict) -> None:
    stages = path["stages"]
    days = [day for stage in stages for day in stage["days"]]
    tasks = [task for day in days for task in day["tasks"]]
    assert len(days) == 30 and [day["globalDayIndex"] for day in days] == list(range(1, 31))
    assert sum(stage["durationDays"] for stage in stages) == 30
    assert len(tasks) == 35 == len({task["id"] for task in tasks})
    assert all(1 <= len(day["tasks"]) <= 3 and 45 <= day["plannedMinutes"] <= 75 for day in days)
    assert tasks[0]["id"] == f"{PATH}_s0_d1_t0"


def main() -> None:
    raw = {"id": PATH, "estimatedDays": 30, "stages": _legacy_stages()}
    normalized = normalize_learning_path(raw)
    _assert_contract(normalized["path"])
    assert normalized["path"] == normalize_learning_path(normalized["path"])["path"]

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([SessionModel(id=SESSION), LearningPathModel(id=PATH, session_id=SESSION, stages=_legacy_stages(), estimated_days=30)])
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        response = client.get("/api/learning-path", params={"sessionId": SESSION})
        assert response.status_code == 200
        _assert_contract(response.json()["data"]["path"])
    db = SessionLocal()
    try:
        persisted = db.get(LearningPathModel, PATH)
        assert persisted is not None
        _assert_contract({"stages": persisted.stages})
    finally:
        db.close()
    print("persisted learning path days: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
