import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import product


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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


if __name__ == "__main__":
    test_resource_graph_missing_resource_is_empty()
    test_path_stage_estimated_days_come_from_duration()
    test_naive_db_datetime_is_treated_as_utc()
    print("PASS product_routes_test")
