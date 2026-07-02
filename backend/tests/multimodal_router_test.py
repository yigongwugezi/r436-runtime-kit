import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.multimodal import run_multimodal


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_run_endpoint_calls_mindmap_tool() -> None:
    result = run_multimodal({
        "message": "生成这个学习路径的思维导图",
        "context": {
            "topic": "数据结构",
            "learning_path": [{"title": "链表", "tasks": ["单链表"]}],
        },
    })
    assert_true(result["agent"] == "MultimodalAgent", "endpoint should return agent result")
    assert_true(result["status"] == "success", "mindmap endpoint should succeed")
    assert_true(result["tool"] == "MindMapTool", "registry should select MindMapTool")


def test_run_endpoint_returns_unified_structure() -> None:
    result = run_multimodal({"message": "生成思维导图"})
    for key in ("agent", "status", "task_type", "tool", "provider", "result", "warnings", "trace"):
        assert_true(key in result, f"missing result field: {key}")


def test_unconfigured_provider_does_not_fake_success() -> None:
    result = run_multimodal({"message": "生成一个微课视频"})
    assert_true(result["status"] == "provider_not_configured", "missing video env should be explicit")
    assert_true(result["result"] is None, "provider placeholder must not fake output")


if __name__ == "__main__":
    test_run_endpoint_calls_mindmap_tool()
    test_run_endpoint_returns_unified_structure()
    test_unconfigured_provider_does_not_fake_success()
    print("PASS multimodal_router_test")
