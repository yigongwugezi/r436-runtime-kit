import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.multimodal_agent import MultimodalAgent
from app.config import load_backend_env
from app.services import multimodal_provider as provider_mod
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


def extracted_question_vision() -> dict:
    result = vision_result(question=zh(r"\u7b2c1\u9898\uff1a1+1=?\n\u7b2c2\u9898\uff1a2+3=?"))
    result["extracted_questions"] = [
        {
            "index": 1,
            "question_text": zh(r"\u7b2c1\u9898\uff1a1+1=?"),
            "knowledge_points": [zh(r"\u52a0\u6cd5")],
            "answer": "2",
            "explanation_steps": [zh(r"\u628a 1 \u548c 1 \u76f8\u52a0")],
            "common_mistakes": [],
        },
        {
            "index": 2,
            "question_text": zh(r"\u7b2c2\u9898\uff1a2+3=?"),
            "knowledge_points": [zh(r"\u52a0\u6cd5")],
            "answer": "5",
            "explanation_steps": [zh(r"\u628a 2 \u548c 3 \u76f8\u52a0")],
            "common_mistakes": [zh(r"\u628a 2+3 \u7b97\u6210 4")],
        },
    ]
    return result


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


def test_backend_env_loader_populates_qwen_env_without_override() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env_path = Path(tmp) / ".env"
        env_path.write_text(
            "\n".join([
                "DASHSCOPE_API_KEY=from-file",
                "QWEN_BASE_URL=https://example.com/v1",
                "QWEN_VL_MODEL=qwen3-vl-plus",
                "QWEN_IMAGE_ENDPOINT=https://example.com/images",
            ]),
            encoding="utf-8",
        )
        with EnvPatch(
            DASHSCOPE_API_KEY=None,
            QWEN_BASE_URL="https://system.example/v1",
            QWEN_VL_MODEL=None,
            QWEN_IMAGE_ENDPOINT=None,
        ):
            assert_true(load_backend_env(env_path) is True, "backend env should load")
            assert_true(os.environ["DASHSCOPE_API_KEY"] == "from-file", "key should load from env file")
            assert_true(os.environ["QWEN_BASE_URL"] == "https://system.example/v1", "existing env must not be overridden")
            assert_true(os.environ["QWEN_VL_MODEL"] == "qwen3-vl-plus", "model should load from env file")
            assert_true(os.environ["QWEN_IMAGE_ENDPOINT"] == "https://example.com/images", "image endpoint should load")

    assert_true(load_backend_env(Path(tempfile.gettempdir()) / "missing-eduagent.env") is False, "missing env should not crash")


def test_image_url_and_base64_classify_as_image_understanding() -> None:
    agent = MultimodalAgent()
    task_type, _ = agent.classify_task(zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), [], {"image_url": "https://example.com/a.png"})
    assert_true(task_type == "image_understanding", "image_url should enter vision task")
    task_type, _ = agent.classify_task("", [], {"image_base64": "dGVzdA=="})
    assert_true(task_type == "image_understanding", "image_base64 should enter vision task")


def test_image_task_classifier_covers_learning_workflow() -> None:
    agent = MultimodalAgent()
    cases = [
        (zh(r"\u5206\u6790\u8fd9\u5f20\u9519\u9898\u56fe"), "image_wrong_question_analysis"),
        (zh(r"\u628a\u8fd9\u9875\u7b14\u8bb0\u6574\u7406\u6210\u603b\u7ed3"), "image_note_summary"),
        (zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u4e00\u4e2a\u5b66\u4e60\u8ba1\u5212"), "image_to_learning_plan"),
        (zh(r"\u6839\u636e\u8fd9\u9053\u9898\u518d\u51fa\u51e0\u9053\u53d8\u5f0f\u9898"), "image_to_variant_questions"),
        (zh(r"\u4e00\u952e\u6574\u7406\u8fd9\u5f20\u56fe\u6210\u5b66\u4e60\u8d44\u6e90\u5305"), "image_to_resource_bundle"),
    ]
    for message, expected in cases:
        task_type, _ = agent.classify_task(message, [{"image_url": "https://example.com/a.png"}], {})
        assert_true(task_type == expected, f"{message} should classify as {expected}")


def test_qwen_vision_provider_task_specific_json_response() -> None:
    payloads: dict[str, dict] = {}

    responses = {
        "explain_image_question": '{"question_text":"What is 1+1?","answer":"2","explanation_steps":["add one and one"],"knowledge_points":["addition"],"confidence":0.9,"needs_manual_review":false}',
        "image_wrong_question_analysis": '{"question_text":"What is 1+1?","mistake_type":"calculation","mistake_reason":"added incorrectly","weak_knowledge_points":["addition"],"remediation_plan":["practice addition"],"confidence":0.88,"needs_manual_review":false}',
        "image_note_summary": '{"title":"Limit notes","summary":"Notes about limits","key_points":["limit definition"],"formulas":["lim"],"definitions":["limit"],"pitfalls":["missing condition"],"next_actions":["review examples"],"confidence":0.9,"needs_manual_review":false}',
        "image_to_learning_plan": '{"diagnosed_level":"beginner","weak_points":["limit"],"recommended_path":[{"stage_title":"Limits","objective":"master basics","knowledge_points":["limit"],"estimated_minutes":30,"practice_suggestions":["do 5 questions"]}],"confidence":0.9,"needs_manual_review":false}',
        "image_to_variant_questions": '{"source_question_summary":"addition","target_knowledge_points":["addition"],"variants":[{"question":"1+2=?","answer":"3","explanation":"add","difficulty":"easy","variation_type":"number_change"},{"question":"2+2=?","answer":"4","explanation":"add","difficulty":"easy","variation_type":"number_change"},{"question":"3+2=?","answer":"5","explanation":"add","difficulty":"easy","variation_type":"number_change"}],"confidence":0.9,"needs_manual_review":false}',
        "image_to_resource_bundle": '{"understanding":{"summary":"addition image"},"next_actions":["review"],"knowledge_candidates":[{"knowledge_point":"addition","confidence":0.8}],"confidence":0.9,"needs_manual_review":false}',
    }

    def post_json(_url: str, payload: dict, _api_key: str, _timeout: int) -> dict:
        prompt = payload["messages"][0]["content"][0]["text"]
        task = prompt.split("task_type=", 1)[1].split("。", 1)[0]
        payloads[task] = payload
        return {"choices": [{"message": {"content": responses[task]}}]}

    results: dict[str, dict] = {}
    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        for task_type in responses:
            result = QwenVisionProvider(post_json=post_json).run({"task_type": task_type, "image_url": "https://example.com/q.png"})
            results[task_type] = result
            assert_true(result["status"] == "success", f"{task_type} should succeed")
            assert_true(result["result"], f"{task_type} should return result")

    assert_true(payloads["explain_image_question"]["messages"][0]["content"][1]["image_url"]["url"] == "https://example.com/q.png", "image URL should stay in payload")
    bundle = results["image_to_resource_bundle"]
    assert_true(bundle["result"]["resource_save_candidate"]["review_status"] == "pending", "resource candidate should be pending")
    assert_true(bundle["result"]["knowledge_candidates"][0]["review_status"] == "pending", "knowledge candidate should be pending")


def test_qwen_vision_provider_mock_json_response() -> None:
    captured: dict = {}

    def post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
        captured.update({"url": url, "payload": payload, "api_key": api_key, "timeout": timeout})
        return {"choices": [{"message": {"content": '{"image_type":"question_image","subject":"math","detected_text":"Find the limit of the displayed expression","question_text":"Find the limit of the displayed expression","possible_knowledge_points":["limit"],"summary":"limit question","confidence":0.9,"needs_manual_review":false}'}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_BASE_URL="https://example.com/v1", QWEN_VL_MODEL="qwen-test"):
        result = QwenVisionProvider(post_json=post_json).run({"image_url": "https://example.com/q.png"})

    assert_true(result["status"] == "success", "mock JSON should parse")
    assert_true(result["provider"] == "qwen_vl", "provider should be qwen_vl")
    assert_true(result["result"]["question_text"].startswith("Find the limit"), "question text should parse")
    assert_true(captured["url"] == "https://example.com/v1/chat/completions", "OpenAI-compatible endpoint should be used")
    assert_true(captured["api_key"] == "test-key", "configured key should be used")
    image_part = captured["payload"]["messages"][0]["content"][1]
    assert_true(image_part["image_url"]["url"] == "https://example.com/q.png", "remote image_url should pass through unchanged")


def test_qwen_vision_provider_data_url_passes_through() -> None:
    captured: dict = {}

    def post_json(_url: str, payload: dict, _api_key: str, _timeout: int) -> dict:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"detected_text":"clear image text for testing","summary":"ok","needs_manual_review":false}'}}]}

    data_url = "data:image/png;base64,dGVzdA=="
    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_base64": data_url})

    assert_true(result["status"] == "success", "data URL should be accepted")
    image_part = captured["payload"]["messages"][0]["content"][1]
    assert_true(image_part["image_url"]["url"] == data_url, "data URL should pass through unchanged")


def test_qwen_vision_provider_wraps_bare_base64() -> None:
    captured: dict = {}

    def post_json(_url: str, payload: dict, _api_key: str, _timeout: int) -> dict:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"detected_text":"clear image text for testing","summary":"ok","needs_manual_review":false}'}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_base64": "dGVzdA=="})

    assert_true(result["status"] == "success", "bare base64 should be accepted")
    image_part = captured["payload"]["messages"][0]["content"][1]
    assert_true(image_part["image_url"]["url"] == "data:image/png;base64,dGVzdA==", "bare base64 should be wrapped")


def test_qwen_vision_provider_missing_local_path_is_explicit() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        raise AssertionError("provider should not call HTTP when local image is missing")

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_url": "uploads/multimodal/missing.png"})

    assert_true(result["status"] == "needs_input", "missing local path should be explicit")
    assert_true("not found" in " ".join(result["warnings"]), "warning should explain missing local file")


def test_qwen_vision_provider_uploaded_local_path_becomes_data_url() -> None:
    captured: dict = {}

    def post_json(_url: str, payload: dict, _api_key: str, _timeout: int) -> dict:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"detected_text":"clear image text for testing","summary":"ok","needs_manual_review":false}'}}]}

    old_root = provider_mod.UPLOAD_ROOT
    old_project = provider_mod.settings.project_root
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        provider_mod.settings.project_root = project
        provider_mod.UPLOAD_ROOT = project / "uploads" / "multimodal"
        local = provider_mod.UPLOAD_ROOT / "s" / "a.png"
        local.parent.mkdir(parents=True)
        local.write_bytes(b"\x89PNG\r\n\x1a\n")
        try:
            with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
                result = QwenVisionProvider(post_json=post_json).run({
                    "attachments": [{"local_path": "uploads/multimodal/s/a.png"}],
                })
        finally:
            provider_mod.UPLOAD_ROOT = old_root
            provider_mod.settings.project_root = old_project

    assert_true(result["status"] == "success", "uploaded local image should be accepted")
    image_part = captured["payload"]["messages"][0]["content"][1]
    assert_true(image_part["image_url"]["url"].startswith("data:image/png;base64,"), "uploaded local file should be converted to data URL")


def test_qwen_vision_provider_non_json_is_partial_success() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        return {"choices": [{"message": {"content": "This image contains derivative notes."}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_base64": "dGVzdA=="})

    assert_true(result["status"] == "partial_success", "non-JSON model output should not crash")
    assert_true(result["raw_text"] == "This image contains derivative notes.", "raw text should be preserved")
    assert_true(result["result"]["summary"] == "This image contains derivative notes.", "summary should fall back to raw text")


def test_qwen_vision_provider_review_metadata_is_actionable() -> None:
    def post_json(_url: str, _payload: dict, _api_key: str, _timeout: int) -> dict:
        return {"choices": [{"message": {"content": '{"detected_text":"第12题公式不清晰","summary":"错题图","confidence":0.4,"needs_manual_review":true,"review_reasons":["第12题公式 OCR 可能不完整"],"uncertain_question_indices":[12],"uncertain_fields":["cards[11].back","formula_text"]}'}}]}

    with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
        result = QwenVisionProvider(post_json=post_json).run({"image_base64": "dGVzdA=="})

    data = result["result"]
    assert_true(result["status"] == "needs_manual_review", "uncertain image should be marked for review")
    assert_true(data["review_reasons"], "review reasons should be present")
    assert_true(data["uncertain_question_indices"] == [12], "uncertain question index should be present")
    assert_true("formula_text" in data["uncertain_fields"], "uncertain fields should be present")
    assert_true(data["review_level"] in {"medium", "high"}, "review level should be actionable")
    assert_true("can_continue" in data, "can_continue should be present")


def test_image_to_mindmap_from_vision_result() -> None:
    agent = MultimodalAgent(llm_client=FailingMindmapLLM())
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


def test_cached_image_context_can_continue_specific_question() -> None:
    result = MultimodalAgent(llm_client=FailingMindmapLLM()).run({
        "user_message": zh(r"\u7ee7\u7eed\u8bb2\u7b2c2\u9898"),
        "last_vision_result": extracted_question_vision(),
        "last_extracted_questions": extracted_question_vision()["extracted_questions"],
    })

    assert_true(result["task_type"] == "explain_image_question", "follow-up question should route to explanation")
    assert_true(result["provider"] == "session_cache", "follow-up should reuse cached vision result")
    assert_true(result["status"] == "success", "cached question explanation should succeed")
    assert_true(result["result"]["selected_question_indices"] == [2], "requested question index should be selected")
    assert_true(zh(r"\u7b2c2\u9898") in result["result"]["chat_text"], "chat text should explain the requested question")
    assert_true(result["result"]["display_text"] == result["result"]["chat_text"], "first-class display text should be present")


def test_cached_image_context_can_generate_mindmap_without_new_upload() -> None:
    result = MultimodalAgent(llm_client=FailingMindmapLLM()).run({
        "user_message": zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u601d\u7ef4\u5bfc\u56fe"),
        "last_vision_result": extracted_question_vision(),
        "last_extracted_questions": extracted_question_vision()["extracted_questions"],
    })

    assert_true(result["task_type"] == "image_to_mindmap", "cached image mindmap task should be selected")
    assert_true(result["provider"] == "session_cache", "mindmap should reuse cached vision result")
    assert_true(result["status"] == "success", "cached image mindmap should succeed")
    assert_true("markdown" in result["result"], "mindmap markdown should be available")
    assert_true(zh(r"\u52a0\u6cd5") in result["result"]["markdown"], "cached knowledge point should enter mindmap")


def test_cached_image_context_can_generate_flashcards_without_new_upload() -> None:
    result = MultimodalAgent(llm_client=FailingMindmapLLM()).run({
        "user_message": zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u590d\u4e60\u5361\u7247"),
        "last_vision_result": extracted_question_vision(),
        "last_extracted_questions": extracted_question_vision()["extracted_questions"],
    })

    assert_true(result["task_type"] == "image_to_flashcards", "cached image flashcard task should be selected")
    assert_true(result["provider"] == "session_cache", "flashcards should reuse cached vision result")
    assert_true(result["status"] == "success", "cached image flashcards should succeed")
    assert_true(len(result["result"]["cards"]) >= 5, "flashcards should be enough for a multi-question image")
    assert_true(result["workflow_trace"]["vision_context_reused"] is True, "trace should show reused image context")


def test_image_to_flashcards_from_vision_result() -> None:
    agent = MultimodalAgent()
    agent.registry.register_tool("QwenVisionProvider", FakeVisionTool(vision_result()))
    result = agent.run({
        "user_message": zh(r"\u6839\u636e\u8fd9\u5f20\u56fe\u751f\u6210\u590d\u4e60\u5361\u7247"),
        "attachments": [{"image_url": "https://example.com/note.png"}],
    })
    assert_true(result["task_type"] == "image_to_flashcards", "flashcard task should be selected")
    assert_true(result["status"] == "success", "flashcards should succeed from vision result")
    assert_true(len(result["result"]["cards"]) >= 5, "should generate at least five cards")


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
    test_backend_env_loader_populates_qwen_env_without_override()
    test_image_url_and_base64_classify_as_image_understanding()
    test_image_task_classifier_covers_learning_workflow()
    test_qwen_vision_provider_task_specific_json_response()
    test_qwen_vision_provider_mock_json_response()
    test_qwen_vision_provider_data_url_passes_through()
    test_qwen_vision_provider_wraps_bare_base64()
    test_qwen_vision_provider_missing_local_path_is_explicit()
    test_qwen_vision_provider_uploaded_local_path_becomes_data_url()
    test_qwen_vision_provider_non_json_is_partial_success()
    test_qwen_vision_provider_review_metadata_is_actionable()
    test_image_to_mindmap_from_vision_result()
    test_cached_image_context_can_continue_specific_question()
    test_cached_image_context_can_generate_mindmap_without_new_upload()
    test_cached_image_context_can_generate_flashcards_without_new_upload()
    test_image_to_flashcards_from_vision_result()
    test_explain_image_question_needs_manual_review_when_question_missing()
    test_unconfigured_image_provider_no_fake_url()
    test_qwen_image_provider_mock_response()
    test_unconfigured_video_provider_returns_script_no_fake_url()
    test_wan_video_provider_mock_task_response()
    test_task_classifier()
    print("PASS multimodal_agent_test")
