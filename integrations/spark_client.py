"""
讯飞星火 Spark LLM 客户端
OpenAI 兼容接口，支持同步/异步/流式调用
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger("spark-client")


class SparkClient:
    """讯飞星火 OpenAI 兼容接口客户端"""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        app_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SPARK_API_KEY", "")
        self.api_secret = api_secret or os.getenv("SPARK_API_SECRET", "")
        self.app_id = app_id or os.getenv("SPARK_APP_ID", "")
        self.base_url = base_url or os.getenv("SPARK_BASE_URL", "https://spark-api-open.xf-yun.com/v1")
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

    # ── 同步风格（内部 async）──

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "spark-4.0",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """单轮对话，返回完整响应文本"""
        if not self.configured:
            return ""

        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error("Spark chat failed: %s", exc)
            return ""

    # ── 流式调用 ──

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str = "spark-4.0",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """流式对话，逐 token 返回"""
        if not self.configured:
            return

        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError):
                            continue
        except Exception as exc:
            logger.error("Spark stream failed: %s", exc)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
