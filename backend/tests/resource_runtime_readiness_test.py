import importlib
import os
import sys
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["RAG_ENABLED"] = "false"


def test_safety_fallback():
    import app.services.content_safety as safety

    assert safety.ContentSafetyEngine().check_input("ISIS").blocked
    saved = sys.modules.get("ahocorasick")
    sys.modules["ahocorasick"] = None
    try:
        fallback = importlib.reload(safety)
        assert fallback.ContentSafetyEngine().check_input("ISIS").blocked
    finally:
        if saved is None:
            sys.modules.pop("ahocorasick", None)
        else:
            sys.modules["ahocorasick"] = saved
        importlib.reload(safety)


def test_config_and_capabilities():
    import app.config as config

    original_key = os.environ.pop("DEEPSEEK_API_KEY", None)
    with tempfile.TemporaryDirectory() as directory:
        env_file = Path(directory) / ".env"
        env_file.write_text("LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=test-only\n", encoding="utf-8")
        assert not config.load_backend_env(env_file)  # EDUAGENT_SKIP_ENV_FILE=1 is honoured
        previous_skip = config._skip_env_file
        config._skip_env_file = False
        try:
            assert config.load_backend_env(env_file)
        finally:
            config._skip_env_file = previous_skip
        config.settings.llm_provider = "deepseek"
        caps = config.runtime_capabilities()
        assert caps["llmProvider"] == "deepseek" and caps["llmConfigured"]
        assert "test-only" not in str(caps)
        assert {"llmProvider", "pptConfigured", "optionalDependencies"} <= caps.keys()
    os.environ.pop("DEEPSEEK_API_KEY", None)
    if original_key is not None:
        os.environ["DEEPSEEK_API_KEY"] = original_key


def test_no_provider_generation_is_explicit():
    from app.config import settings
    from app.routers import product

    old_provider = settings.llm_provider
    old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
    settings.llm_provider = "deepseek"
    original = product._ensure_session_linked
    product._ensure_session_linked = lambda *args, **kwargs: None
    try:
        result = product._generate_general_resource({"sessionId": "s", "topic": "calculus", "type": "lecture"})
        assert result["status"] == "error"
        assert result["data"]["errorCode"] == "provider_not_configured"
        assert result["data"]["resource"] is None
    finally:
        product._ensure_session_linked = original
        settings.llm_provider = old_provider
        if old_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = old_key


def test_missing_optional_modules_do_not_block_startup():
    saved = sys.modules.get("openai")
    sys.modules["openai"] = None
    try:
        import app.main  # noqa: F401
    finally:
        if saved is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = saved


def main():
    test_safety_fallback()
    test_config_and_capabilities()
    test_no_provider_generation_is_explicit()
    test_missing_optional_modules_do_not_block_startup()
    print("resource runtime readiness: PASS")


if __name__ == "__main__":
    main()
