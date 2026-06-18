import sys
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


if __name__ == "__main__":
    test_resource_graph_missing_resource_is_empty()
    print("PASS product_routes_test")
