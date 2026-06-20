import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.routers import product
from app.services import agent_service
from app.services.conversation_state import conversation_store


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _cleanup(session_id: str) -> None:
    conversation_store._sessions.pop(session_id, None)
    db = SessionLocal()
    try:
        session = db.get(SessionModel, session_id)
        if session:
            db.delete(session)
            db.commit()
    finally:
        db.close()


def test_resource_graph_missing_resource_is_empty() -> None:
    result = product.resource_knowledge_graph("missing_resource_for_test", sessionId="graph_missing_session")

    assert_true(result["mermaidDef"] == "", "missing resource should not return a hardcoded graph")
    assert_true(result["source"] == "none", "missing resource source should be none")
    assert_true("人工智能导论" not in str(result), "hardcoded AI intro graph must not leak")


def test_path_stage_estimated_days_come_from_duration() -> None:
    stages = product._raw_stages_to_nodes(
        [
            {"stage_id": "stage_1", "title": "A", "duration": "第 1 天", "tasks": ["task"]},
            {"stage_id": "stage_2", "title": "B", "duration": "第 2 天", "tasks": ["task"]},
            {"stage_id": "stage_3", "title": "C", "duration": "第 1-2 天", "tasks": ["task"]},
            {"stage_id": "stage_4", "title": "D", "duration": "48 小时", "tasks": ["task"]},
        ]
    )

    assert_true([stage["estimatedDays"] for stage in stages] == [1, 1, 2, 2], "stage days should be parsed from duration")
    assert_true(all(stage["estimatedDays"] != 3 for stage in stages[:2]), "single-day stages must not use fixed 3-day fallback")


def test_naive_db_datetime_is_treated_as_utc() -> None:
    naive_utc = "2026-06-18 13:21:24.947748"
    expected = int(
        datetime.fromisoformat(naive_utc)
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )

    assert_true(product._datetime_to_ms(naive_utc) == expected, "naive DB timestamps should be interpreted as UTC")


def test_resource_source_preserves_rule_fallback_label() -> None:
    resource = product._to_resource(
        {
            "resource_id": "res_fallback_source",
            "type": "lecture",
            "title": "Fallback source",
            "content": "content",
            "content_format": "markdown",
            "source": "rule_based_fallback",
            "related_stage_id": "stage_1",
        },
        session_id="product_source_session",
    )

    assert_true(resource["source"] == "rule_based_fallback", "resource source should not be overwritten as agent_generated")


def test_profile_route_preserves_structured_dimension_fields() -> None:
    session_id = "product_profile_roundtrip"
    conversation_store.enable_db()
    _cleanup(session_id)

    try:
        agent_service.run_agents(
            session_id=session_id,
            course_id="data_structures",
            user_message="我是软件工程大三学生，C 语言基础一般，想用 48 小时复习数据结构，希望多给图解和代码案例。",
        )
        profile = product.get_profile(sessionId=session_id)["profile"]
        dimensions = profile["dimensions"]

        assert_true(len(dimensions) == 10, "/profile should return 10 dimensions")
        assert_true(
            all(all(field in dim for field in ("value", "score", "confidence", "explanation", "evidence", "source")) for dim in dimensions),
            "/profile should preserve structured dimension fields",
        )
        assert_true(
            all(dim["key"] not in {"weak_points", "programming_ability", "interests"} for dim in dimensions),
            "/profile should not expose legacy 8-dimension keys",
        )
    finally:
        _cleanup(session_id)


if __name__ == "__main__":
    test_resource_graph_missing_resource_is_empty()
    test_path_stage_estimated_days_come_from_duration()
    test_naive_db_datetime_is_treated_as_utc()
    test_resource_source_preserves_rule_fallback_label()
    test_profile_route_preserves_structured_dimension_fields()
    print("PASS product_routes_test")
