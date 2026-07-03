import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.multimodal import run_multimodal
from app.services import multimodal_provider as provider_mod


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


class UploadRootPatch:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name)
        self.upload_root = self.project_root / "uploads" / "multimodal"
        self.old_project_root = provider_mod.settings.project_root
        self.old_upload_root = provider_mod.UPLOAD_ROOT
        provider_mod.settings.project_root = self.project_root
        provider_mod.UPLOAD_ROOT = self.upload_root
        return self

    def __exit__(self, exc_type, exc, tb):
        provider_mod.settings.project_root = self.old_project_root
        provider_mod.UPLOAD_ROOT = self.old_upload_root
        self.tmp.cleanup()


def test_run_endpoint_calls_mindmap_tool() -> None:
    result = run_multimodal({
        "message": zh(r"\u751f\u6210\u8fd9\u4e2a\u5b66\u4e60\u8def\u5f84\u7684\u601d\u7ef4\u5bfc\u56fe"),
        "context": {
            "topic": zh(r"\u6570\u636e\u7ed3\u6784"),
            "learning_path": [{"title": zh(r"\u94fe\u8868"), "tasks": [zh(r"\u5355\u94fe\u8868")]}],
        },
    })
    assert_true(result["agent"] == "MultimodalAgent", "endpoint should return agent result")
    assert_true(result["status"] == "success", "mindmap endpoint should succeed")
    assert_true(result["tool"] == "MindMapTool", "registry should select MindMapTool")
    assert_true("markdown" in result["result"], "mindmap should include markdown")


def test_run_endpoint_returns_unified_structure() -> None:
    result = run_multimodal({"message": zh(r"\u751f\u6210\u601d\u7ef4\u5bfc\u56fe")})
    for key in ("agent", "status", "task_type", "tool", "provider", "result", "warnings", "trace", "workflow_trace"):
        assert_true(key in result, f"missing result field: {key}")


def test_run_endpoint_accepts_image_url_and_base64() -> None:
    with EnvPatch(DASHSCOPE_API_KEY=None, QWEN_API_KEY=None):
        by_url = run_multimodal({
            "message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"),
            "image_url": "https://example.com/test.png",
        })
        by_base64 = run_multimodal({
            "message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"),
            "image_base64": "dGVzdA==",
        })
    assert_true(by_url["task_type"] == "image_understanding", "image_url should route to vision")
    assert_true(by_base64["task_type"] == "image_understanding", "image_base64 should route to vision")
    assert_true(by_url["status"] == "provider_not_configured", "unconfigured provider should be explicit")
    assert_true(by_base64["status"] == "provider_not_configured", "unconfigured provider should be explicit")


def test_run_endpoint_sends_public_image_url_to_qwen_payload() -> None:
    captured: dict = {}
    image_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
    base_url = "https://ws-k0ji0cx5vwxwrgx9n.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"{\\"detected_text\\":\\"clear image text for testing\\",\\"summary\\":\\"ok\\",\\"needs_manual_review\\":false}"}}]}'

        def json(self) -> dict:
            return json.loads(self.text)

    def fake_post(url, json=None, headers=None, timeout=0):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    def fail_local_file(_path: str):
        raise AssertionError("public image_url must not be handled as a local file")

    old_post = provider_mod.httpx.post
    old_local = provider_mod._local_file_data_url
    provider_mod.httpx.post = fake_post
    provider_mod._local_file_data_url = fail_local_file
    try:
        with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_BASE_URL=base_url, QWEN_VL_MODEL="qwen3-vl-plus"):
            result = run_multimodal({"message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), "image_url": image_url})
    finally:
        provider_mod.httpx.post = old_post
        provider_mod._local_file_data_url = old_local

    assert_true(result["status"] == "success", "mocked Qwen response should succeed")
    assert_true(captured["url"] == f"{base_url}/chat/completions", "Qwen endpoint should be chat/completions")
    assert_true(captured["headers"].get("Authorization") == "Bearer test-key", "request should carry Authorization header")
    image_part = captured["payload"]["messages"][0]["content"][1]
    assert_true(image_part == {"type": "image_url", "image_url": {"url": image_url}}, "public image URL should stay in payload")
    assert_true("test-key" not in str(result), "API key must not leak into result")


def test_run_endpoint_qwen_http_error_has_safe_trace() -> None:
    image_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
    base_url = "https://ws-k0ji0cx5vwxwrgx9n.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

    class ForbiddenResponse:
        status_code = 403
        text = '{"error":"forbidden"}'

        def json(self) -> dict:
            raise AssertionError("HTTP error responses should not be parsed as success")

    old_post = provider_mod.httpx.post
    provider_mod.httpx.post = lambda *args, **kwargs: ForbiddenResponse()
    try:
        with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_BASE_URL=base_url, QWEN_VL_MODEL="qwen3-vl-plus"):
            result = run_multimodal({"message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), "image_url": image_url})
    finally:
        provider_mod.httpx.post = old_post

    trace = result["trace"]["tool_trace"]
    assert_true(result["status"] == "failed", "simulated HTTP failure should fail")
    assert_true(trace["endpoint"] == f"{base_url}/chat/completions", "trace should expose endpoint")
    assert_true(trace["image_input_kind"] == "public_url", "trace should expose image input kind")
    assert_true(trace["payload_image_url_preview"] == image_url[:80], "trace should include safe image preview")
    assert_true(trace["exception_type"] == "HttpClientError", "trace should include exception type")
    assert_true(trace["http_status"] == 403, "trace should include HTTP status")
    assert_true(trace["response_body_preview"] == '{"error":"forbidden"}', "trace should include response body preview")
    assert_true("HTTP 403" in " ".join(result["warnings"]), "warnings should include HTTP status")
    assert_true("test-key" not in str(result), "API key must not leak into failure trace")


def test_run_endpoint_qwen_network_error_has_safe_trace() -> None:
    image_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
    base_url = "https://ws-k0ji0cx5vwxwrgx9n.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

    def fake_post(*_args, **_kwargs):
        raise provider_mod.httpx.ConnectError("network down")

    old_post = provider_mod.httpx.post
    provider_mod.httpx.post = fake_post
    try:
        with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None, QWEN_BASE_URL=base_url, QWEN_VL_MODEL="qwen3-vl-plus"):
            result = run_multimodal({"message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"), "image_url": image_url})
    finally:
        provider_mod.httpx.post = old_post

    trace = result["trace"]["tool_trace"]
    assert_true(result["status"] == "failed", "simulated network failure should fail")
    assert_true(trace["exception_type"] == "ConnectError", "trace should include exception type")
    assert_true("network down" in trace["exception_message"], "trace should include exception message")
    assert_true("test-key" not in str(result), "API key must not leak into failure trace")


def test_upload_save_uses_safe_file_id_and_rejects_invalid_type() -> None:
    with UploadRootPatch():
        result = provider_mod.save_multimodal_upload(
            b"\x89PNG\r\n\x1a\n",
            filename="../../note.png",
            content_type="image/png",
            session_id="session/unsafe",
        )
        saved = provider_mod.UPLOAD_ROOT / result["file_id"]
        assert_true(saved.exists(), "upload helper should write the image")
        assert_true(result["url"].startswith("/api/multimodal/file/"), "upload should return routed URL")
        assert_true(".." not in result["file_id"], "file_id should not contain traversal")
        assert_true(not Path(result["local_path"]).is_absolute(), "local_path should not expose absolute path")
        try:
            provider_mod.save_multimodal_upload(b"bad", filename="bad.txt", content_type="text/plain")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid upload type should be rejected")


def test_unconfigured_video_returns_script_not_fake_success() -> None:
    with EnvPatch(DASHSCOPE_API_KEY=None, WAN_API_KEY=None):
        result = run_multimodal({"message": zh(r"\u751f\u6210\u4e00\u4e2a\u6781\u9650\u5fae\u8bfe\u89c6\u9891")})
    assert_true(result["status"] == "script_ready_provider_not_configured", "missing Wan env should still return script")
    assert_true(result["result"]["script"], "script should be present")
    assert_true(not result["result"].get("video_url"), "provider placeholder must not fake video output")


def test_run_endpoint_resource_bundle_has_pending_candidates() -> None:
    image_url = "https://example.com/note.png"

    class FakeResponse:
        status_code = 200
        text = (
            '{"choices":[{"message":{"content":"'
            '{\\"understanding\\":{\\"summary\\":\\"limit notes\\"},'
            '\\"knowledge_candidates\\":[{\\"knowledge_point\\":\\"limit\\",\\"confidence\\":0.8}],'
            '\\"confidence\\":0.9,\\"needs_manual_review\\":false}'
            '"}}]}'
        )

        def json(self) -> dict:
            return json.loads(self.text)

    old_post = provider_mod.httpx.post
    provider_mod.httpx.post = lambda *args, **kwargs: FakeResponse()
    try:
        with EnvPatch(DASHSCOPE_API_KEY="test-key", QWEN_API_KEY=None):
            result = run_multimodal({"message": zh(r"\u4e00\u952e\u6574\u7406\u8fd9\u5f20\u56fe\u6210\u5b66\u4e60\u8d44\u6e90\u5305"), "image_url": image_url})
    finally:
        provider_mod.httpx.post = old_post

    assert_true(result["task_type"] == "image_to_resource_bundle", "bundle request should route to bundle")
    assert_true(result["status"] == "success", "mock bundle should succeed")
    assert_true("explanation" not in result["result"], "empty bundle sections should be omitted")
    assert_true("mindmap" not in result["result"], "empty mindmap section should be omitted")
    assert_true(result["result"].get("display_text"), "resource bundle should explain what the bundle means")
    assert_true(result["result"]["resource_save_candidate"]["review_status"] == "pending", "resource candidate should be pending")
    assert_true(result["result"]["resource_save_candidate"]["saved"] is False, "resource candidate should not fake save")
    assert_true(result["result"]["knowledge_candidates"][0]["review_status"] == "pending", "knowledge candidate should be pending")


if __name__ == "__main__":
    test_run_endpoint_calls_mindmap_tool()
    test_run_endpoint_returns_unified_structure()
    test_run_endpoint_accepts_image_url_and_base64()
    test_run_endpoint_sends_public_image_url_to_qwen_payload()
    test_run_endpoint_qwen_http_error_has_safe_trace()
    test_run_endpoint_qwen_network_error_has_safe_trace()
    test_upload_save_uses_safe_file_id_and_rejects_invalid_type()
    test_unconfigured_video_returns_script_not_fake_success()
    test_run_endpoint_resource_bundle_has_pending_candidates()
    print("PASS multimodal_router_test")
