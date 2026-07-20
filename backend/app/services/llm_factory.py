"""统一 LLM 工厂 — 所有大模型调用从这里走。

凭据来自**每用户配置**（系统设置 → AI 模型配置，见 user_ai_config.py），
.env 只保留技术项（角色模型微调、温度等）。支持：
  - DeepSeek (deepseek-v4-pro)
  - Qwen / Qwen-Coder / Qwen-VL (DashScope)
  - GLM 5.2 (智谱)
  - GPT-4o (OpenAI 原生)
  - 未来只需加 provider 即可扩展

使用方式：
  from app.services.llm_factory import get_planner, get_coder, get_critic
  response, usage = get_planner()(prompt, max_tokens=8000)
"""

from __future__ import annotations
import json
import os
# Ensure .env is loaded before reading config (technical vars only)
from app.config import load_backend_env
load_backend_env()
import time
import random
import base64
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from openai import OpenAI

from app.services.user_ai_config import (
    PROVIDER_DEFAULTS,
    get_llm_credentials,
    resolve_provider_key,
)
from app.utils.errors import AIConfigMissingError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════════════════════════

TokenFunc = Callable[..., Tuple[Any, Dict[str, int]]]
VisionFunc = Callable[..., Tuple[Any, Dict[str, int]]]


# ═══════════════════════════════════════════════════════════════════════
# 统一客户端构建
# ═══════════════════════════════════════════════════════════════════════

def _make_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


def _make_text_func(client: OpenAI, model: str) -> TokenFunc:
    """创建标准文本补全函数，返回 (response, usage_dict)"""
    def func(prompt: str, max_tokens: int = 8000, max_retries: int = 3, **kwargs) -> Tuple[Any, Dict[str, int]]:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=kwargs.get("temperature", 0.3),
                )
                if completion.usage:
                    usage["prompt_tokens"] = completion.usage.prompt_tokens
                    usage["completion_tokens"] = completion.usage.completion_tokens
                    usage["total_tokens"] = completion.usage.total_tokens
                return completion, usage
            except Exception as e:
                if attempt >= max_retries - 1:
                    logger.warning(f"LLM API failed ({model}): {e}")
                    return None, usage
                time.sleep((2 ** attempt) * 0.5 + random.random() * 0.5)
        return None, usage
    return func


def _make_vision_func(client: OpenAI, model: str) -> VisionFunc:
    """创建视觉评审函数，输入图片路径列表，返回 (response, usage_dict)"""
    def func(prompt: str, image_paths: List[str], max_tokens: int = 8000, max_retries: int = 3, **kwargs) -> Tuple[Any, Dict[str, int]]:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        content = [{"type": "text", "text": prompt}]
        for img_path in image_paths:
            try:
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })
            except Exception as e:
                logger.warning(f"Failed to encode image {img_path}: {e}")
        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=max_tokens,
                )
                if completion.usage:
                    usage["prompt_tokens"] = completion.usage.prompt_tokens
                    usage["completion_tokens"] = completion.usage.completion_tokens
                    usage["total_tokens"] = completion.usage.total_tokens
                return completion, usage
            except Exception as e:
                if attempt >= max_retries - 1:
                    logger.warning(f"Vision API failed ({model}): {e}")
                    return None, usage
                time.sleep((2 ** attempt) * 1.0 + random.random() * 1.0)
        return None, usage
    return func


# ═══════════════════════════════════════════════════════════════════════
# 注册 Provider
# ═══════════════════════════════════════════════════════════════════════

# Base URL 与默认模型固化在 user_ai_config.PROVIDER_DEFAULTS（代码内官方默认，
# 不再从 .env 读取）；key 一律来自每用户配置。
PROVIDERS = PROVIDER_DEFAULTS


def _get_provider_config(provider: str, *, config: dict | None = None) -> Dict:
    """解析指定 provider 的配置——key 来自用户配置，URL/模型用代码内默认值。"""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown LLM provider: {provider}")
    api_key = resolve_provider_key(provider, config=config)
    return {**cfg, "api_key": api_key, "base_url": cfg["default_url"]}


def _get_role_provider(role: str) -> str:
    """读取角色对应的 provider，如 LLM_PLANNER_PROVIDER=deepseek（.env 技术项）"""
    env_var = f"LLM_{role.upper()}_PROVIDER"
    return os.getenv(env_var, role_defaults.get(role, "deepseek"))


role_defaults = {
    "planner": "deepseek",
    # Auxiliary roles must follow the configured main provider unless an
    # operator explicitly overrides them in the environment.
    "coder": "qwen",
    "critic": "qwen",
}


# ═══════════════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════════════

def get_planner(config: dict | None = None) -> TokenFunc:
    """获取 Planner（大纲+分镜）的 LLM 函数。默认 DeepSeek。"""
    provider = _get_role_provider("planner")
    cfg = _get_provider_config(provider, config=config)
    env_model = os.getenv("LLM_PLANNER_MODEL", "")
    model = env_model or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("planner provider=%s 但当前用户未配置该提供商的 API key", provider)
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def get_coder(config: dict | None = None) -> TokenFunc:
    """获取 Coder（Manim 代码生成）的 LLM 函数。默认 Qwen-Coder。"""
    provider = _get_role_provider("coder")
    cfg = _get_provider_config(provider, config=config)
    env_model = os.getenv("LLM_CODER_MODEL", "")
    model = env_model or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("coder provider=%s 但当前用户未配置该提供商的 API key", provider)
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def get_critic(config: dict | None = None) -> VisionFunc:
    """获取 Critic（视频画面评审）的 VLM 函数。默认 Qwen-VL。"""
    provider = _get_role_provider("critic")
    cfg = _get_provider_config(provider, config=config)
    env_model = os.getenv("LLM_CRITIC_MODEL", "")
    model = env_model or cfg["models"]["vision"] or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("critic provider=%s 但当前用户未配置该提供商的 API key", provider)
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_vision_func(client, model)


def get_narrator(config: dict | None = None) -> TokenFunc:
    """获取旁白生成的 LLM 函数。默认使用 DeepSeek。"""
    provider = os.getenv("LLM_NARRATOR_PROVIDER", "deepseek")
    cfg = _get_provider_config(provider, config=config)
    env_model = os.getenv("LLM_NARRATOR_MODEL", "")
    model = env_model or cfg["models"]["text"]
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def is_configured(config: dict | None = None) -> bool:
    """检查当前用户是否配置了主 LLM 的 API key（mock 视为已配置）"""
    creds = get_llm_credentials(config=config)
    return creds["provider"] == "mock" or bool(creds["api_key"])


# ═══════════════════════════════════════════════════════════════════════
# Chat Client（兼容 BaseLLMClient .chat() 接口）
# ═══════════════════════════════════════════════════════════════════════

class UnifiedChatClient:
    """统一的 chat 客户端 — 实现 .chat(messages) 接口，所有 agent 通用。

    凭据来自每用户配置（user_ai_config）；未配置 key 时构造成功但任何
    调用都会抛 AIConfigMissingError（惰性报错，引导用户去系统设置）。
    """

    def __init__(self, config: dict | None = None):
        creds = get_llm_credentials(config=config)
        self._provider = creds["provider"]
        self._api_key = creds["api_key"]
        self._base_url = creds["base_url"]
        self._model = creds["model"]
        self._temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key) if self._api_key else None

    def is_available(self) -> bool:
        return self._client is not None

    def _require_client(self) -> OpenAI:
        if not self._client:
            raise AIConfigMissingError(service="llm", provider=self._provider or "llm")
        return self._client

    def chat(self, messages: list[dict], **kwargs) -> str:
        client = self._require_client()
        max_tokens = kwargs.pop("max_tokens", 8000)
        temp = kwargs.pop("temperature", self._temperature)
        retries = kwargs.pop("retry_count", 2)
        for attempt in range(retries + 1):
            try:
                completion = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temp,
                    **kwargs,
                )
                return completion.choices[0].message.content
            except Exception as e:
                if attempt >= retries:
                    raise RuntimeError(f"LLM chat failed: {e}")
                time.sleep((2 ** attempt) * 0.5 + random.random() * 0.5)
        raise RuntimeError("LLM chat failed after retries")

    def stream_chat(self, messages: list[dict], **kwargs) -> Generator[str, None, None]:
        """流式聊天——边生成边 yield token。"""
        client = self._require_client()
        model = kwargs.pop("model", self._model) or self._model
        temp = kwargs.pop("temperature", self._temperature)
        _is_reasoner = "reasoner" in model

        if _is_reasoner:
            # deepseek-v4-pro: 绕过 OpenAI 库，用 httpx 流式读原始 SSE
            import httpx
            payload = {
                "model": model, "messages": messages,
                "temperature": temp, "stream": True,
            }
            with httpx.Client(timeout=30) as hc:
                with hc.stream("POST", f"{self._base_url}/chat/completions",
                              json=payload,
                              headers={"Authorization": f"Bearer {self._api_key}"}) as resp:
                    for line in resp.iter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        try:
                            d = json.loads(line[6:])
                            delta = d.get("choices", [{}])[0].get("delta", {})
                            rc = delta.get("reasoning_content", "") or ""
                            ct = delta.get("content", "") or ""
                            if rc:
                                yield f"<thinking>{rc}</thinking>"
                            if ct:
                                yield ct
                        except (json.JSONDecodeError, IndexError):
                            pass
            return

        # 非推理模型：用 OpenAI 客户端库
        stream = client.chat.completions.create(
            model=model, messages=messages, temperature=temp, stream=True, **kwargs,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def get_chat_client(config: dict | None = None) -> UnifiedChatClient:
    """返回统一 chat 客户端，绑定当前用户（或显式快照）的凭据。"""
    return UnifiedChatClient(config=config)
