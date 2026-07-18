"""Direct regression checks for the normal-chat DeepTutor fallback."""

from __future__ import annotations

import asyncio
import os
import ssl
import sys
import types
from urllib import error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.conversation_agent import ConversationAgent
from app.services import deeptutor_client, llm_client
from app.services.llm_factory import UnifiedChatClient
from app.services.llm_client import LLMClientError


def _install_runtime(chunks: list[str] | None = None, failure: Exception | None = None) -> dict[str, object | None]:
    saved = {name: sys.modules.get(name) for name in (
        "deeptutor", "deeptutor.runtime", "deeptutor.core", "deeptutor.core.context", "deeptutor.core.stream",
    )}
    root = types.ModuleType("deeptutor")
    root.__path__ = []
    core = types.ModuleType("deeptutor.core")
    core.__path__ = []
    runtime = types.ModuleType("deeptutor.runtime")
    context = types.ModuleType("deeptutor.core.context")
    stream = types.ModuleType("deeptutor.core.stream")

    class ChatOrchestrator:
        def handle(self, _context):
            async def events():
                if failure:
                    raise failure
                for chunk in chunks or []:
                    yield types.SimpleNamespace(type="content", content=chunk)
            return events()

    runtime.ChatOrchestrator = ChatOrchestrator
    context.UnifiedContext = lambda **kwargs: types.SimpleNamespace(**kwargs)
    stream.StreamEventType = types.SimpleNamespace(CONTENT="content")
    sys.modules.update({
        "deeptutor": root,
        "deeptutor.runtime": runtime,
        "deeptutor.core": core,
        "deeptutor.core.context": context,
        "deeptutor.core.stream": stream,
    })
    return saved


def _restore_modules(saved: dict[str, object | None]) -> None:
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def main() -> None:
    original_setup = deeptutor_client._setup_config
    original_fallback = deeptutor_client._direct_llm_fallback
    saved_modules = _install_runtime(["DeepTutor reply"])
    fallback_calls: list[str] = []

    async def configured_fallback(*_args) -> str:
        fallback_calls.append("called")
        return "Configured LLM reply"

    try:
        deeptutor_client._setup_config = lambda: True
        deeptutor_client._direct_llm_fallback = configured_fallback

        reply = asyncio.run(deeptutor_client.deeptutor_call_async("chat", "hello", fallback_to_configured_llm=True))
        assert reply == "DeepTutor reply" and not fallback_calls

        _restore_modules(saved_modules)
        saved_modules = _install_runtime(failure=RuntimeError("offline"))
        reply = asyncio.run(deeptutor_client.deeptutor_call_async("chat", "hello", fallback_to_configured_llm=True))
        assert reply == "Configured LLM reply" and len(fallback_calls) == 1

        _restore_modules(saved_modules)
        saved_modules = _install_runtime([])
        reply = asyncio.run(deeptutor_client.deeptutor_call_async("chat", "hello", fallback_to_configured_llm=True))
        assert reply == "Configured LLM reply" and len(fallback_calls) == 2

        deeptutor_client._setup_config = lambda: False
        reply = asyncio.run(deeptutor_client.deeptutor_call_async("deep_solve", "solve", fallback_to_configured_llm=True))
        assert reply == "" and len(fallback_calls) == 2

        original_get_client = llm_client.get_llm_client

        class ConfiguredClient:
            def __init__(self):
                self.kwargs = {}

            def chat(self, _messages, **kwargs):
                self.kwargs = kwargs
                return " configured response "

        class FailingClient:
            def chat(self, _messages, **_kwargs):
                raise RuntimeError("offline")

        configured_client = ConfiguredClient()
        llm_client.get_llm_client = lambda _provider: configured_client
        assert asyncio.run(original_fallback("hello", [], "", "")) == "configured response"
        assert configured_client.kwargs == {"timeout": 8, "retry_count": 1}
        llm_client.get_llm_client = lambda _provider: FailingClient()
        assert asyncio.run(original_fallback("hello", [], "", "")) == ""
        llm_client.get_llm_client = original_get_client

        # v1.1.0: credentials are per-user — an explicit config snapshot with a
        # key yields a real client; an empty config yields the lazy-raising
        # UnconfiguredLLMClient (never a silent mock fallback).
        configured = llm_client.get_llm_client(
            "deepseek", config={"llm": {"provider": "deepseek", "apiKey": "unit-test-key"}}
        )
        assert isinstance(configured, UnifiedChatClient)
        assert configured.is_available()
        from app.config import settings as _settings
        _old_provider = _settings.llm_provider
        _settings.llm_provider = "user"  # disable the mock escape hatch for this assertion
        try:
            unconfigured = llm_client.get_llm_client("user", config={})
        finally:
            _settings.llm_provider = _old_provider
        assert isinstance(unconfigured, llm_client.UnconfiguredLLMClient)
        assert not unconfigured.is_available()

        tls_calls: list[int] = []
        tls_client = llm_client.DeepSeekLLMClient("unit-test-key", "https://example.invalid", "test", 0)
        def tls_failure(*_args, **_kwargs):
            tls_calls.append(1)
            raise error.URLError(ssl.SSLEOFError("unexpected eof"))
        tls_client._send_request = tls_failure
        try:
            tls_client.chat([{"role": "user", "content": "ping"}], retry_count=9)
        except LLMClientError:
            pass
        assert len(tls_calls) == 1

        timeout_calls: list[int] = []
        def timeout_failure(*_args, **_kwargs):
            timeout_calls.append(1)
            raise TimeoutError("timeout")
        tls_client._send_request = timeout_failure
        try:
            tls_client.chat([{"role": "user", "content": "ping"}], retry_count=9)
        except LLMClientError:
            pass
        assert len(timeout_calls) == 2
    finally:
        deeptutor_client._setup_config = original_setup
        deeptutor_client._direct_llm_fallback = original_fallback
        _restore_modules(saved_modules)

    agent = ConversationAgent()
    agent._try_deeptutor_reply = lambda *_args, **_kwargs: ""
    agent._call_llm = lambda _messages: (_ for _ in ()).throw(LLMClientError("offline"))
    assert agent.run({"user_message": "hello", "session_id": "test", "profile_facts": {}}).get("reply")
    no_context_confirmation = agent._rule_fallback("可以", {"conversation_history": []})
    assert no_context_confirmation["action"] == "none"
    explicit_confirmation = agent._rule_fallback("可以", {"last_proposal": "plan"})
    assert explicit_confirmation["action"] == "plan"

    print("deeptutor client fallback: PASS")


if __name__ == "__main__":
    main()
