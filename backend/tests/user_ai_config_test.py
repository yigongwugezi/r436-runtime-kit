"""Per-user AI config tests — isolation, masking, merge semantics, errors.

Covers the v1.1.0 per-user credential system (docs/api/api-contract.md §3):
- repository merge semantics (partial update / empty-string clear / masked
  placeholder ignore);
- masking format and full-key non-leakage in safe responses;
- per-user isolation (user A's key never resolves for user B);
- missing-key behaviour (AIConfigMissingError, no mock fallback);
- ContextVar propagation into worker threads via copy_context_wrap.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("EDUAGENT_SKIP_ENV_FILE", "1")
_TEMP_DIR = tempfile.mkdtemp(prefix="user-ai-config-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEMP_DIR) / 'user_ai_config_test.db'}"
os.environ["LLM_PROVIDER"] = "user"  # disable mock escape hatch — we assert error paths
os.environ["RAG_ENABLED"] = "false"

from app.db import init_db  # noqa: E402
from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import LearnerModel  # noqa: E402
from app.db.repository import get_user_ai_config, merge_user_ai_config  # noqa: E402
from app.services import user_ai_config as uac  # noqa: E402
from app.services.llm_client import MockLLMClient, UnconfiguredLLMClient, get_llm_client  # noqa: E402
from app.utils.errors import AIConfigMissingError  # noqa: E402


def _seed_learner(db, learner_id: str) -> None:
    if db.get(LearnerModel, learner_id) is None:
        db.add(LearnerModel(id=learner_id, nickname=learner_id, role="student"))
        db.commit()


def test_repository_merge_semantics() -> None:
    db = SessionLocal()
    try:
        _seed_learner(db, "learner_a")
        # New learner starts empty
        assert get_user_ai_config(db, "learner_a") == {}

        # Partial update creates the service block
        saved = merge_user_ai_config(db, "learner_a", {"llm": {"provider": "deepseek", "apiKey": "sk-aaaa1111bbbb2222"}})
        assert saved["llm"]["apiKey"] == "sk-aaaa1111bbbb2222"

        # Masked placeholder must NOT overwrite the stored key
        saved = merge_user_ai_config(db, "learner_a", {"llm": {"apiKey": "sk-aa****2222"}})
        assert saved["llm"]["apiKey"] == "sk-aaaa1111bbbb2222"

        # Updating one service leaves others untouched
        saved = merge_user_ai_config(db, "learner_a", {"tavily": {"apiKey": "tvly-12345678"}})
        assert saved["llm"]["apiKey"] == "sk-aaaa1111bbbb2222"
        assert saved["tavily"]["apiKey"] == "tvly-12345678"

        # Empty string clears the field; empty service blocks are removed
        saved = merge_user_ai_config(db, "learner_a", {"tavily": {"apiKey": ""}})
        assert "tavily" not in saved
        assert saved["llm"]["apiKey"] == "sk-aaaa1111bbbb2222"
    finally:
        db.close()
    print("merge semantics: PASS")


def test_masking_and_no_full_key_leak() -> None:
    assert uac.mask_secret("sk-2601ceed7cc6490daed9118f3adf1d4f") == "sk-26****1d4f"
    assert uac.mask_secret("short") == "******"
    assert uac.mask_secret("") == ""

    config = {
        "llm": {"provider": "deepseek", "apiKey": "sk-aaaa1111bbbb2222"},
        "spark": {"appId": "app12345", "apiKey": "key12345", "apiSecret": "sec12345"},
    }
    safe = uac.to_safe_response(config)
    import json

    blob = json.dumps(safe)
    assert "sk-aaaa1111bbbb2222" not in blob, "full key leaked in safe response"
    assert safe["llm"]["configured"] is True
    assert safe["llm"]["provider"] == "deepseek"
    assert safe["spark"]["configured"] is True  # all three fields present
    assert safe["qwen"] == {"apiKey": "", "configured": False}  # full skeleton
    # spark with a missing field is not configured
    partial = uac.to_safe_response({"spark": {"appId": "app12345"}})
    assert partial["spark"]["configured"] is False
    print("masking: PASS")


def test_per_user_isolation() -> None:
    db = SessionLocal()
    try:
        _seed_learner(db, "learner_a")
        _seed_learner(db, "learner_b")
        merge_user_ai_config(db, "learner_a", {"llm": {"provider": "deepseek", "apiKey": "sk-user-a-key-0001"}})
    finally:
        db.close()

    # User A's context resolves A's key
    uac.set_current_learner("learner_a")
    assert uac.get_credential("llm") == "sk-user-a-key-0001"

    # User B's context resolves nothing — A's key must never appear
    uac.set_current_learner("learner_b")
    assert uac.get_credential("llm") == ""
    creds_b = uac.get_llm_credentials()
    assert creds_b["api_key"] == ""

    # Anonymous context resolves nothing either
    uac.set_current_learner("")
    assert uac.get_credential("llm") == ""
    print("isolation: PASS")


def test_missing_key_raises_not_mocks() -> None:
    from app.config import settings

    old = settings.llm_provider
    settings.llm_provider = "user"  # disable mock escape hatch — assert the error path
    try:
        uac.set_current_learner("learner_b")  # exists, but has no config
        client = get_llm_client("user")
        assert isinstance(client, UnconfiguredLLMClient)
        assert not isinstance(client, MockLLMClient)
        try:
            client.chat([{"role": "user", "content": "hi"}])
            raise AssertionError("expected AIConfigMissingError")
        except AIConfigMissingError as exc:
            assert exc.code == "AI_CONFIG_MISSING"
            assert exc.status_code == 409
            assert exc.is_user_error is True
            assert "系统设置" in exc.message

        # With a configured user, a real client is returned instead
        uac.set_current_learner("learner_a")
        real = get_llm_client("user")
        assert real.is_available()
    finally:
        settings.llm_provider = old
    print("missing-key error: PASS")


def test_mock_escape_hatch() -> None:
    from app.config import settings

    old = settings.llm_provider
    settings.llm_provider = "mock"
    try:
        # No user key + mock provider → MockLLMClient
        uac.set_current_learner("learner_b")
        assert isinstance(get_llm_client(settings.llm_provider), MockLLMClient)
        # A configured user key always wins over the mock switch
        uac.set_current_learner("learner_a")
        assert not isinstance(get_llm_client(settings.llm_provider), MockLLMClient)
    finally:
        settings.llm_provider = old
    print("mock escape hatch: PASS")


def test_thread_context_propagation() -> None:
    uac.set_current_learner("learner_a")
    seen: dict[str, str] = {}

    def worker() -> None:
        seen["in_thread"] = uac.get_credential("llm")

    # Bare thread does NOT inherit the ContextVar…
    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert seen["in_thread"] == ""

    # …copy_context_wrap carries it across
    t2 = threading.Thread(target=uac.copy_context_wrap(worker))
    t2.start(); t2.join()
    assert seen["in_thread"] == "sk-user-a-key-0001"
    print("thread propagation: PASS")


def main() -> None:
    init_db()
    test_repository_merge_semantics()
    test_masking_and_no_full_key_leak()
    test_per_user_isolation()
    test_missing_key_raises_not_mocks()
    test_mock_escape_hatch()
    test_thread_context_propagation()
    print("user ai config: PASS")


if __name__ == "__main__":
    main()
