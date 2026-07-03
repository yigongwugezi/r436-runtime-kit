import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.multimodal_agent import MultimodalAgent
from app.services.multimodal_provider import QwenImageProvider, QwenVisionProvider, WanVideoProvider


def zh(escaped: str) -> str:
    return escaped.encode("ascii").decode("unicode_escape")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class EnvPatch:
    def __init__(self, **values: str | None) -> None:
        self.values = values
        self.originals: dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.originals[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.originals.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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


class FakeVisionTool:
    provider = "qwen_vl"

    def __init__(self, result: dict) -> None:
        self.result = result

    def run(self, context: dict) -> dict:
        return {
            "status": "success",
            "provider": self.provider,
            "result": self.result,
            "warnings": [],
            "trace": {"model": "fake-vl"},
        }


def sample_path() -> list[dict]:
    return [
        {
            "stage_id": "s1",
            "title": zh(r"\u590d\u6742\u5ea6\u57fa\u7840"),
            "tasks": [zh(r"\u65f6\u95f4\u590d\u6742\u5ea6"), zh(r"\u7a7a\u95f4\u590d\u6742\u5ea6")],
        },
        {"stage_id": "s2", "title": zh(r"\u94fe\u8868"), "tasks": [zh(r"\u5355\u94fe\u8868"), zh(r"\u53cc\u6307\u9488")]},
    ]


def vision_result(*, question: str = "") -> dict:
    return {
        "image_type": "question_image" if question else "note_image",
        "subject": "math",
        "detected_text": question or zh(r"\u6781\u9650\u3001\u5bfc\u6570\u3001\u79ef\u5206\u7b14\u8bb0"),
        "question_text": question,
        "student_answer": "",
        "formula_text": "",
        "diagram_description": "",
        "possible_knowledge_points": [zh(r"\u6781\u9650"), zh(r"\u5bfc\u6570"), zh(r"\u79ef\u5206")],
        "summary": zh(r"\u8fd9\u5f20\u56fe\u6574\u7406\u4e86\u5fae\u79ef\u5206\u6838\u5fc3\u77e5\u8bc6"),
        "confidence": 0.86,
        "needs_manual_review": False,
    }


def test_mindmap_from_learning_path() -> None:
    result = MultimodalAgent().run({
        "user_message": zh(r"\u751f\u6210\u8fd9\u4e2a\u5b66\u4e60\u8def\u5f84\u7684\u601d\u7ef4\u5bfc\u56fe"),
        "topic": zh(r"\u6570\u636e\u7ed3\u6784"),
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "mindmap should succeed with learning_path")
    assert_true(result["result"]["mindmap_json"]["title"] == zh(r"\u6570\u636e\u7ed3\u6784"), "topic should be root")
    assert_true("mindmap" in result["result"]["mermaid"], "mermaid should be generated")
    assert_true(zh(r"\u590d\u6742\u5ea6\u57fa\u7840") in result["result"]["mermaid"], "stage title should appear")
    assert_true("markdown" in result["result"], "markdown should be available for Markmap")


def test_mindmap_without_context_does_not_invent_points() -> None:
    result = MultimodalAgent().run({"user_message": zh(r"\u751f\u6210\u601d\u7ef4\u5bfc\u56fe")})
    assert_true(result["status"] == "needs_input", "missing inputs should be explicit")
    assert_true(result["result"] is None, "missing input should not return fake content")


def test_mindmap_can_use_injected_llm() -> None:
    result = MultimodalAgent(llm_client=FakeMindmapLLM()).run({
        "user_message": zh(r"\u751f\u6210\u601d\u7ef4\u5bfc\u56fe"),
        "topic": "Data Structures",
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "LLM enhanced mindmap should still succeed")
    assert_true(result["result"]["llm_enhanced"] is True, "mindmap should mark LLM enhancement")
    assert_true(result["result"]["mindmap_json"]["children"][0]["title"] == "Linear Lists", "LLM JSON should be used")
    assert_true(result["trace"]["tool_trace"]["llm_enhanced"] is True, "trace should expose LLM enhancement")


def test_mindmap_llm_failure_falls_back_to_local_result() -> None:
    result = MultimodalAgent(llm_client=FailingMindmapLLM()).run({
        "user_message": zh(r"\u751f\u6210\u601d\u7ef4\u5bfc\u56fe"),
        "topic": "Data Structures",
        "learning_path": sample_path(),
    })
    assert_true(result["status"] == "success", "LLM failure should not break local mindmap")
    assert_true(result["trace"]["tool_trace"]["llm_enhanced"] is False, "trace should record fallback")
    assert_true("mermaid" in result["result"], "local mermaid should remain available")


def test_unconfigured_vision_provider() -> None:
    with EnvPatch(DASHSCOPE_API_KEY=None, QWEN_API_KEY=None):
        result = MultimodalAgent().run({
            "user_message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"),
            "attachments": [{"image_url": "https://example.com/question.png"}],
        })
    assert_true(result["status"] == "provider_not_configured", "vision provider should require env")
    assert_true("fake" not in str(result).lower(), "must not return fake recognition text")


def test_image_url_and_base64_classify_as_image_understanding() -> None:
    agent = MultimodalAgent()
    task_type, _ = agent.classify_task(zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), [], {"image_url": "https://example.com/a.png"})
    assert_true(task_type == "image_understanding", "image_url should enter vision task")
    task_type, _ = agent.classify_task("", [], {"image_base64": "dGVzdA=="})
    assert_true(task_type == "image_understanding", "image_base64 should enter vision task")


def test_qwen_vision_provider_mock_json_response() -> None:
    captured: dict = {}

    def post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
        captured.update({"url": url, "payload": payload, "api_key": api_key, "timeout": timeout})
        return {"choices": [{"message": {"content": '{"image_type":"question_image","subject":"math","detected_text":"lim x","question_text":"lim x","possible_knowledge_points":["limit"],"summary":"limit question","confidence":0.9,"needs_manual_review":false}'}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_BASE_URL="https://example.com/v1", QWEN_VL_MODEL="qwen-test"):
        result = QwenVisionProvider(post_json=post_json).run({"image_url": "https://example.com/q.png"})

    assert_true(result["status"] == "success", "mock JSON should parse")
    assert_true(result["provider"] == "qwen_vl", "provider should be qwen_vl")
    assert_true(result["result"]["question_text"] == "lim x", "question text should parse")
    assert_true(captured["url"] == "https://example.com/v1/chat/completions", "OpenAI-compatible endpoint should be used")
    assert_true(captured["api_key"] == "test-key", "configured key should be used")


def test_qwen_vision_provider_non_json_is_partial_success() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        return {"choices": [{"message": {"content": "This image contains derivative notes."}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_base64": "dGVzdA=="})

    assert_true(result["status"] == "partial_success", "non-JSON model output should not crash")
    assert_true(result["raw_text"] == "This image contains derivative notes.", "raw text should be preserved")
    assert_true(result["result"]["summary"] == "This image contains derivative notes.", "summary should fall back to raw text")


def test_image_to_mindmap_from_vision_result() -> None:
    agent = MultimodalAgent()
    agent.registry.register_tool("QwenVisionProvider", FakeVisionTool(vision_result()))
    result = agent.run({
        "user_message": zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u601d\u7ef4\u5bfc\u56fe"),
        "attachments": [{"image_url": "https://example.com/note.png"}],
    })
    assert_true(result["task_type"] == "image_to_mindmap", "image mindmap task should be selected")
    assert_true(result["status"] == "success", "image mindmap should succeed from vision result")
    assert_true("markdown" in result["result"], "image mindmap should return markdown")
    assert_true(zh(r"\u6781\u9650") in result["result"]["markdown"], "knowledge points should enter markdown")
    assert_true(result["workflow_trace"]["steps"][1]["step"] == "vision_understanding", "trace should include vision step")


def test_image_to_flashcards_from_vision_result() -> None:
    agent = MultimodalAgent()
    agent.registry.register_tool("QwenVisionProvider", FakeVisionTool(vision_result()))
    result = agent.run({
        "user_message": zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u590d\u4e60\u5361\u7247"),
        "attachments": [{"image_url": "https://example.com/note.png"}],
    })
    assert_true(result["task_type"] == "image_to_flashcards", "flashcard task should be selected")
    assert_true(result["status"] == "success", "flashcards should succeed from vision result")
    assert_true(len(result["result"]["cards"]) >= 3, "should generate at least three cards")


def test_explain_image_question_needs_manual_review_when_question_missing() -> None:
    agent = MultimodalAgent()
    agent.registry.register_tool("QwenVisionProvider", FakeVisionTool(vision_result(question="")))
    result = agent.run({
        "user_message": zh(r"\u8bb2\u4e00\u4e0b\u8fd9\u9053\u9898"),
        "attachments": [{"image_url": "https://example.com/question.png"}],
    })
    assert_true(result["task_type"] == "explain_image_question", "explain task should be selected")
    assert_true(result["status"] == "needs_manual_review", "missing recognized question should ask for review")
    assert_true("answer" not in str(result["result"]) or not result["result"].get("answer"), "must not invent an answer")


def test_unconfigured_image_provider_no_fake_url() -> None:
    with EnvPatch(DASHSCOPE_API_KEY=None, QWEN_API_KEY=None):
        result = MultimodalAgent().run({"user_message": zh(r"\u751f\u6210\u4e00\u5f20\u77e5\u8bc6\u5361\u7247")})
    assert_true(result["status"] == "provider_not_configured", "image provider should require env")
    assert_true("image_url" not in str(result), "must not return fake image url")


def test_qwen_image_provider_mock_response() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        return {"data": [{"url": "https://cdn.example.com/generated.png"}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_IMAGE_ENDPOINT="https://example.com/images"):
        result = QwenImageProvider(post_json=post_json).run({"prompt": "limit concept card"})

    assert_true(result["status"] == "success", "configured Qwen image mock should succeed")
    assert_true(result["result"]["image_urls"] == ["https://cdn.example.com/generated.png"], "real URL from API should pass through")


def test_unconfigured_video_provider_returns_script_no_fake_url() -> None:
    with EnvPatch(DASHSCOPE_API_KEY=None, WAN_API_KEY=None):
        result = MultimodalAgent().run({"user_message": zh(r"\u751f\u6210\u4e00\u4e2a\u6781\u9650\u5fae\u8bfe\u89c6\u9891")})
    assert_true(result["status"] == "script_ready_provider_not_configured", "Wan provider should still return a script")
    assert_true(result["result"]["script"], "script should be present")
    assert_true(not result["result"].get("video_url"), "must not return fake video url")


def test_wan_video_provider_mock_task_response() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        return {"output": {"task_id": "task-1", "task_status": "submitted"}}

    with EnvPatch(DASHSCOPE_API_KEY=None, WAN_API_KEY="wan-key", WAN_VIDEO_ENDPOINT="https://example.com/video"):
        result = WanVideoProvider(post_json=post_json).run({"topic": "limit"})

    assert_true(result["status"] == "success", "configured Wan mock should submit")
    assert_true(result["result"]["task_id"] == "task-1", "task id should pass through")
    assert_true(not result["result"].get("video_url"), "missing video_url should not be faked")


def test_task_classifier() -> None:
    agent = MultimodalAgent()
    cases = [
        (zh(r"\u753b\u4e2a\u601d\u7ef4\u5bfc\u56fe"), "mindmap_generation"),
        (zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), "image_understanding"),
        (zh(r"\u751f\u6210\u56fe\u7247"), "image_generation"),
        (zh(r"\u751f\u6210\u89c6\u9891"), "video_generation"),
        (zh(r"\u751f\u6210\u5206\u955c\u811a\u672c"), "video_script_generation"),
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
    test_image_url_and_base64_classify_as_image_understanding()
    test_qwen_vision_provider_mock_json_response()
    test_qwen_vision_provider_non_json_is_partial_success()
    test_image_to_mindmap_from_vision_result()
    test_image_to_flashcards_from_vision_result()
    test_explain_image_question_needs_manual_review_when_question_missing()
    test_unconfigured_image_provider_no_fake_url()
    test_qwen_image_provider_mock_response()
    test_unconfigured_video_provider_returns_script_no_fake_url()
    test_wan_video_provider_mock_task_response()
    test_task_classifier()
    print("PASS multimodal_agent_test")
