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


if __name__ == "__main__":
    test_run_endpoint_calls_mindmap_tool()
    test_run_endpoint_returns_unified_structure()
    test_run_endpoint_accepts_image_url_and_base64()
    test_upload_save_uses_safe_file_id_and_rejects_invalid_type()
    test_unconfigured_video_returns_script_not_fake_success()
    print("PASS multimodal_router_test")
