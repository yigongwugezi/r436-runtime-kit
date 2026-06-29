"""LLM client abstraction with retry, timeout, and error handling.

Provides:
- BaseLLMClient: abstract interface
- MockLLMClient: returns deterministic mock responses (dev only)
- DeepSeekLLMClient: OpenAI-compatible HTTP client with retry logic
- get_llm_client(): factory function
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable
from urllib import error, request

from app.config import settings

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class LLMClientError(Exception):
    """Raised when an LLM API call fails after all retries are exhausted."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ── Abstract base ──────────────────────────────────────────────────────────


class BaseLLMClient(ABC):
    """Abstract contract for LLM clients used by stage agents."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send a chat completion request and return the response text.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            **kwargs: Provider-specific overrides (model, temperature, timeout).

        Returns:
            The model's response text.

        Raises:
            LLMClientError: On any failure.
        """
        ...

    def is_available(self) -> bool:
        """Quick health check — returns True if the provider is reachable."""
        return True


# ── Mock client ────────────────────────────────────────────────────────────


class MockLLMClient(BaseLLMClient):
    """Deterministic mock client for development and testing."""

    def set_chunk_callback(self, callback: Callable[[str], None] | None) -> None:
        """No-op: mock client does not stream."""
        pass

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        # Return a structured JSON response so agents can parse it as real output.
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = str(msg.get("content", ""))
                break

        return json.dumps(
            {
                "major_background": {
                    "label": "专业背景",
                    "value": "计算机相关专业学生",
                    "confidence": 0.8,
                    "source": "inferred",
                    "evidence": user_text[:80],
                },
                "knowledge_base": {
                    "label": "知识基础",
                    "value": "有一定编程基础",
                    "confidence": 0.7,
                    "source": "inferred",
                    "evidence": user_text[:80],
                },
                "learning_goal": {
                    "label": "学习目标",
                    "value": "系统学习课程内容",
                    "confidence": 0.75,
                    "source": "user_input",
                    "evidence": user_text[:80],
                },
                "cognitive_style": {
                    "label": "认知风格",
                    "value": "未提及",
                    "confidence": 0.5,
                    "source": "inferred",
                    "evidence": "无明确信息",
                },
                "error_patterns": {
                    "label": "易错模式",
                    "value": "未提及",
                    "confidence": 0.5,
                    "source": "inferred",
                    "evidence": "无明确信息",
                },
                "coding_ability": {
                    "label": "编程能力",
                    "value": "基础水平",
                    "confidence": 0.6,
                    "source": "inferred",
                    "evidence": user_text[:80],
                },
                "learning_progress": {
                    "label": "学习进度",
                    "value": "未开始",
                    "confidence": 0.9,
                    "source": "inferred",
                    "evidence": "首次对话",
                },
                "interest_direction": {
                    "label": "兴趣方向",
                    "value": "未提及",
                    "confidence": 0.5,
                    "source": "inferred",
                    "evidence": "无明确信息",
                },
                "learning_rhythm": {
                    "label": "学习节奏",
                    "value": "暂未确定",
                    "confidence": 0.5,
                    "source": "inferred",
                    "evidence": "暂无数据",
                },
            },
            ensure_ascii=False,
        )

    def is_available(self) -> bool:
        return True


# ── DeepSeek client ────────────────────────────────────────────────────────


class DeepSeekLLMClient(BaseLLMClient):
    """OpenAI-compatible DeepSeek client with retry logic.

    Uses urllib.request directly (no external HTTP dependency).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self._on_chunk: Callable[[str], None] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    def set_chunk_callback(self, callback: Callable[[str], None] | None) -> None:
        """Set a callback for token-level streaming on the next ``chat()`` call.

        When a callback is set, ``chat()`` automatically passes ``stream=True``
        to the API and invokes *callback* for each content delta chunk.
        Set to ``None`` to clear.
        """
        self._on_chunk = callback

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send a chat completion request with retry on transient failures.

        Args:
            messages: Chat message list.
            **kwargs: Optional overrides for model, temperature, timeout, retry_count.

        Returns:
            The model's response text.

        Raises:
            LLMClientError: When all retries are exhausted or on permanent errors.
        """
        if not self.api_key:
            raise LLMClientError("DEEPSEEK_API_KEY is not configured.")

        timeout = kwargs.get("timeout", settings.llm_request_timeout)
        max_retries = kwargs.get("retry_count", settings.llm_retry_count)
        retry_delay = kwargs.get("retry_delay", settings.llm_retry_delay)

        # Automatically enable streaming when a chunk callback is set
        if self._on_chunk is not None and "stream" not in kwargs:
            kwargs = {**kwargs, "on_chunk": self._on_chunk, "stream": True}

        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            start_time = time.monotonic()
            try:
                result = self._send_request(messages, timeout, **kwargs)
                duration = (time.monotonic() - start_time) * 1000
                logger.info(
                    "LLM call succeeded | model=%s duration=%.0fms attempt=%d/%d max_tokens=%s",
                    kwargs.get("model", self.model),
                    duration,
                    attempt + 1,
                    max_retries + 1,
                    kwargs.get("max_tokens", "default"),
                )
                return result
            except error.HTTPError as exc:
                last_error = exc
                status = exc.code if hasattr(exc, "code") else None
                duration = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "LLM call attempt %d/%d failed | duration=%.0fms status=%s error=%s",
                    attempt + 1,
                    max_retries + 1,
                    duration,
                    status,
                    str(exc)[:120],
                )
                # 4xx errors (except 429) are not retryable
                if status is not None and 400 <= status < 500 and status != 429:
                    raise LLMClientError(
                        f"DeepSeek API returned HTTP {status}: {self._read_error_body(exc)}",
                        cause=exc,
                    ) from exc
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
            except (error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                duration = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "LLM call attempt %d/%d failed | duration=%.0fms error=%s",
                    attempt + 1,
                    max_retries + 1,
                    duration,
                    str(exc)[:120],
                )
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
            except json.JSONDecodeError as exc:
                last_error = exc
                duration = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "LLM call attempt %d/%d failed | duration=%.0fms error=%s",
                    attempt + 1,
                    max_retries + 1,
                    duration,
                    str(exc)[:120],
                )
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))

            # On retry, fall back to non-streaming to avoid mid-stream restart complexity
            kwargs.pop("on_chunk", None)
            kwargs.pop("stream", None)

        raise LLMClientError(
            f"DeepSeek API call failed after {max_retries + 1} attempts: {last_error}",
            cause=last_error,
        )

    def is_available(self) -> bool:
        """Test connectivity with a minimal request."""
        if not self.api_key:
            return False
        try:
            self._send_blocking(
                self._build_request(
                    [{"role": "user", "content": "ping"}],
                    max_tokens=1,
                ),
                timeout=10,
            )
            return True
        except Exception:
            logger.debug("LLM availability check failed")
            return False

    def _build_request(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> request.Request:
        """Build an HTTP Request object for the chat completions endpoint."""
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
        }
        for key in ("max_tokens", "top_p", "stop", "stream"):
            if key in kwargs:
                payload[key] = kwargs[key]

        return request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    # ── Internal ───────────────────────────────────────────────────────

    def _send_request(
        self,
        messages: list[dict[str, str]],
        timeout: int,
        **kwargs,
    ) -> str:
        """Route to streaming or blocking path based on *on_chunk* + *stream*."""
        req = self._build_request(messages, **kwargs)

        on_chunk = kwargs.get("on_chunk")
        # Check the stream flag we just built into the request data
        payload = json.loads(req.data.decode("utf-8"))
        use_stream = payload.get("stream", False) and callable(on_chunk)

        if use_stream:
            return self._send_streaming(req, timeout, on_chunk)
        return self._send_blocking(req, timeout)

    def _send_blocking(self, req: request.Request, timeout: int) -> str:
        """Send a non-streaming request and return the full response text."""
        with request.urlopen(req, timeout=timeout) as response:  # type: ignore[arg-type]
            body = json.loads(response.read().decode("utf-8"))
        usage = body.get("usage", {})
        if usage:
            logger.debug("Token usage: %s", usage)
        return body["choices"][0]["message"]["content"]

    def _send_streaming(
        self,
        req: request.Request,
        timeout: int,
        on_chunk: Callable[[str], None],
    ) -> str:
        """Send a streaming request, calling *on_chunk* for each content delta.

        Returns the concatenated full response text.
        """
        full_text = ""
        with request.urlopen(req, timeout=timeout) as response:  # type: ignore[arg-type]
            while True:
                line = response.readline().decode("utf-8")
                if not line:
                    break
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        full_text += delta
                        on_chunk(delta)
                except json.JSONDecodeError:
                    continue
        return full_text

    @staticmethod
    def _read_error_body(exc: error.HTTPError) -> str:
        try:
            return exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            return str(exc)


# ── Factory ────────────────────────────────────────────────────────────────


def get_llm_client(provider: str = "mock") -> BaseLLMClient:
    """Return an LLM client instance for the given provider.

    Args:
        provider: ``"mock"`` or ``"deepseek"``.

    Returns:
        A BaseLLMClient subclass instance.

    Raises:
        ValueError: If the provider name is unrecognised.
    """
    if provider == "mock":
        return MockLLMClient()
    if provider == "deepseek":
        return DeepSeekLLMClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")
