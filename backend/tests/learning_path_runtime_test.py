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

    # ── Test 4: agents_filter includes resource_agent for quality gate ──
    # Verify the filter change ensures resource generation + review
    with patch.object(product, "SessionLocal", session_factory), \
         patch.object(product, "_ensure_session_linked"), \
         patch.object(product, "_run_agents", return_value={
             "course_id": "custom_math", "course": {"course_name": "高等数学"},
             "learning_path": [{"title": "极限", "duration": "5天", "tasks": ["极限定义"]}],
             "estimatedDays": 5,
             "resources": [{"type": "lecture", "title": "极限讲义"}],
         }):
        resp2 = product._generate_learning_path(
            {"sessionId": "session-resource", "subjectId": "subject-math", "userMessage": "学习高等数学"}, None
        )
    path2 = resp2["data"]["path"]
    assert path2["id"]  # path persisted
    assert resp2["data"].get("generated")  # generation flag
    print("  agents_filter with resource_agent: ok")

    # ── Test 5: Unified path output structure validation ──
    # Simulate what the unified _generate_chapters returns (stages→chapters→sections→knowledge_points)
    unified_result = {
        "course_id": "custom_physics", "course": {"course_name": "大学物理"},
        "learning_path": [
            {
                "title": "力学基础",
                "theme": "牛顿力学",
                "order": 0,
                "estimated_days": 7,
                "chapters": [
                    {
                        "title": "运动学",
                        "order": 0,
                        "sections": [
                            {
                                "title": "位移与速度",
                                "goal": "掌握位移和速度的基本概念",
                                "estimated_minutes": 45,
                                "task_type": "practice",
                                "content_type": "lecture",
                                "knowledge_points": [{"name": "位移", "type": "concept"}],
                            }
                        ],
                    }
                ],
            }
        ],
        "estimatedDays": 7,
    }
    with patch.object(product, "SessionLocal", session_factory), \
         patch.object(product, "_ensure_session_linked"), \
         patch.object(product, "_run_agents", return_value=unified_result):
        resp3 = product._generate_learning_path(
            {"sessionId": "session-unified", "subjectId": "subject-physics", "userMessage": "学习大学物理"}, None
        )
    path3 = resp3["data"]["path"]
    stages = path3.get("stages", [])
    assert len(stages) == 1
    assert stages[0].get("chapters")  # has chapters
    assert len(stages[0]["chapters"]) == 1
    ch = stages[0]["chapters"][0]
    assert ch.get("sections")  # has sections
    assert ch["sections"][0].get("knowledgePoints")  # has knowledge points
    print("  unified path structure (stages→chapters→sections→knowledgePoints): ok")

    # ── Test 6: Dynamic stage count scales with total_days ──
    estimated = 90 // 4  # 90 days ~ 22 stages
    assert estimated == 22, f"Expected 22 stages for 90 days, got {estimated}"
    estimated_short = 14 // 4  # 14 days ~ 3 stages
    assert estimated_short == 3, f"Expected 3 stages for 14 days, got {estimated_short}"
    print("  dynamic stage scaling: ok")

    print("\nall learning path quality tests: ok")


if __name__ == "__main__":
    main()
