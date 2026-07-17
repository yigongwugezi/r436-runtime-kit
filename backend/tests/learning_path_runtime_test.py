"""Isolated regression check for path validation and persistence."""

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base
from app.db.repository import get_latest_learning_path
from app.routers import product


def main() -> None:
    app = FastAPI()
    app.include_router(product.router, prefix="/api")
    client = TestClient(app)
    quoted = client.get("/api/learning-path/validate-course", params={"courseName": " O'Reilly "})
    assert quoted.status_code == 200
    assert quoted.json() == {"valid": True, "normalizedCourseName": "O'Reilly", "reason": None}
    assert product.validate_course("  数据结构  ") == {
        "valid": True, "normalizedCourseName": "数据结构", "reason": None,
    }
    assert not product.validate_course(" \t ")["valid"]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    result = {
        "course_id": "custom_ds", "course": {"course_name": "数据结构"},
        "learning_path": [{"title": "线性表", "duration": "3天", "tasks": ["顺序表"]}],
        "estimatedDays": 3,
    }
    with patch.object(product, "SessionLocal", session_factory), \
         patch.object(product, "_ensure_session_linked"), \
         patch.object(product, "_run_agents", return_value=result):
        response = product._generate_learning_path(
            {"sessionId": "session-test", "subjectId": "subject-test", "userMessage": "学习数据结构", "pathMode": "textbook"}, None
        )
    path = response["data"]["path"]
    db = session_factory()
    try:
        saved = get_latest_learning_path(db, "session-test")
        assert saved and saved.id == path["id"] and saved.stages
    finally:
        db.close()

    with patch.object(product, "_ensure_session_linked"), patch.object(product, "_run_agents", return_value={"learning_path": []}):
        try:
            product._generate_learning_path({"sessionId": "empty", "userMessage": "学习"}, None)
            raise AssertionError("empty path was accepted")
        except RuntimeError as exc:
            assert exc.error_code == "LEARNING_PATH_UNAVAILABLE"

    print("learning path runtime tests: ok")


if __name__ == "__main__":
    main()
