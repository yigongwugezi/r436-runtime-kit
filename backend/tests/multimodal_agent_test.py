import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.multimodal_agent import MultimodalAgent


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sample_path() -> list[dict]:
    return [
        {"stage_id": "s1", "title": "复杂度基础", "tasks": ["时间复杂度", "空间复杂度"]},
        {"stage_id": "s2", "title": "链表", "tasks": ["单链表", "双指针"]},
    ]


class FakeMindmapLLM:
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        return '{"title":"Data Structures","children":[{"title":"Linear Lists","children":[{"title":"Linked List"}]}]}'

    def is_available(self) -> bool:
        return True


class FailingMindmapLLM:
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        raise RuntimeError("boom")

    def is_available(self) -> bool:
        return False


def test_mindmap_from_learning_path() -> None:
    result = MultimodalAgent().run({
        "user_message": "生成这个学习路径的思维导图",
        "topic": "数据结构",
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "mindmap should succeed with learning_path")
    assert_true(result["result"]["mindmap_json"]["title"] == "数据结构", "topic should be root")
    assert_true("mindmap" in result["result"]["mermaid"], "mermaid should be generated")
    assert_true("复杂度基础" in result["result"]["mermaid"], "stage title should appear")


def test_mindmap_without_context_does_not_invent_points() -> None:
    result = MultimodalAgent().run({"user_message": "生成思维导图"})
    assert_true(result["status"] == "needs_input", "missing inputs should be explicit")
    assert_true(result["result"] is None, "missing input should not return fake content")


def test_mindmap_can_use_injected_llm() -> None:
    result = MultimodalAgent(llm_client=FakeMindmapLLM()).run({
        "user_message": "\u751f\u6210\u601d\u7ef4\u5bfc\u56fe",
        "topic": "Data Structures",
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "LLM enhanced mindmap should still succeed")
    assert_true(result["result"]["llm_enhanced"] is True, "mindmap should mark LLM enhancement")
    assert_true(result["result"]["mindmap_json"]["children"][0]["title"] == "Linear Lists", "LLM JSON should be used")
    assert_true(result["trace"]["tool_trace"]["llm_enhanced"] is True, "trace should expose LLM enhancement")


def test_mindmap_llm_failure_falls_back_to_local_result() -> None:
    result = MultimodalAgent(llm_client=FailingMindmapLLM()).run({
        "user_message": "\u751f\u6210\u601d\u7ef4\u5bfc\u56fe",
        "topic": "Data Structures",
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "LLM failure should not break local mindmap")
    assert_true(result["trace"]["tool_trace"]["llm_enhanced"] is False, "trace should record fallback")
    assert_true("mermaid" in result["result"], "local mermaid should remain available")


def test_unconfigured_vision_provider() -> None:
    os.environ.pop("QWEN_API_KEY", None)
    result = MultimodalAgent().run({
        "user_message": "识别这张图片",
        "attachments": [{"name": "question.png"}],
    })
    assert_true(result["status"] == "provider_not_configured", "vision provider should require env")
    assert_true("question_text" not in str(result), "must not return fake recognition text")


def test_unconfigured_image_provider_no_fake_url() -> None:
    os.environ.pop("QWEN_API_KEY", None)
    result = MultimodalAgent().run({"user_message": "生成一张知识卡片"})
    assert_true(result["status"] == "provider_not_configured", "image provider should require env")
    assert_true("image_url" not in str(result), "must not return fake image url")


def test_unconfigured_video_provider_no_fake_url() -> None:
    os.environ.pop("WAN_API_KEY", None)
    result = MultimodalAgent().run({"user_message": "生成一个微课视频"})
    assert_true(result["status"] == "provider_not_configured", "video provider should require env")
    assert_true("video_url" not in str(result), "must not return fake video url")


def test_task_classifier() -> None:
    agent = MultimodalAgent()
    cases = [
        ("画个思维导图", "mindmap_generation"),
        ("识别这张图片", "image_understanding"),
        ("生成图片", "image_generation"),
        ("生成视频", "video_generation"),
    ]
    for message, expected in cases:
        task_type, _reason = agent.classify_task(message, [], {})
        assert_true(task_type == expected, f"{message} should classify as {expected}")


if __name__ == "__main__":
    test_mindmap_from_learning_path()
    test_mindmap_can_use_injected_llm()
    test_mindmap_llm_failure_falls_back_to_local_result()
    test_mindmap_without_context_does_not_invent_points()
    test_unconfigured_vision_provider()
    test_unconfigured_image_provider_no_fake_url()
    test_unconfigured_video_provider_no_fake_url()
    test_task_classifier()
    print("PASS multimodal_agent_test")
