"""统一 LLM 工厂 — 所有大模型调用从这里走。

.env 控制一切，不需要改代码。支持：
  - DeepSeek (deepseek-chat)
  - Qwen / Qwen-Coder / Qwen-VL (DashScope)
  - GLM 5.2 (智谱)
  - GPT-4o (OpenAI 原生)
  - 未来只需加 provider 即可扩展

使用方式：
  from app.services.llm_factory import get_planner, get_coder, get_critic
  response, usage = get_planner()(prompt, max_tokens=8000)
"""

from __future__ import annotations
import os
# Ensure .env is loaded before reading config
from app.config import load_backend_env
load_backend_env()
import time
import random
import base64
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from openai import OpenAI

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

PROVIDERS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "env_url": "DEEPSEEK_BASE_URL",
        "default_url": "https://api.deepseek.com",
        "models": {
            "text": "deepseek-chat",
            "vision": None,
        },
    },
    "qwen": {
        "env_key": "QWEN_API_KEY",
        "env_url": "QWEN_BASE_URL",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "text": "qwen-coder-plus",
            "vision": "qwen-vl-max",
        },
    },
    "glm": {
        "env_key": "GLM_API_KEY",
        "env_url": "GLM_BASE_URL",
        "default_url": "https://open.bigmodel.cn/api/paas/v4/",
        "models": {
            "text": "glm-5.2",
            "vision": "glm-4v-plus",
        },
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "env_url": "OPENAI_BASE_URL",
        "default_url": "https://api.openai.com/v1/",
        "models": {
            "text": "gpt-4o",
            "vision": "gpt-4o",
        },
    },
}


def _get_provider_config(provider: str) -> Dict:
    """从 .env 读取指定 provider 的配置"""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown LLM provider: {provider}")
    api_key = os.getenv(cfg["env_key"], "")
    base_url = os.getenv(cfg["env_url"], cfg["default_url"])
    return {**cfg, "api_key": api_key, "base_url": base_url}


def _get_role_provider(role: str) -> str:
    """读取角色对应的 provider，如 LLM_PLANNER_PROVIDER=deepseek"""
    env_var = f"LLM_{role.upper()}_PROVIDER"
    return os.getenv(env_var, role_defaults.get(role, "deepseek"))


role_defaults = {
    "planner": "deepseek",
    "coder": "qwen",
    "critic": "qwen",
}


# ═══════════════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════════════

def get_planner() -> TokenFunc:
    """获取 Planner（大纲+分镜）的 LLM 函数。默认 DeepSeek。"""
    provider = _get_role_provider("planner")
    cfg = _get_provider_config(provider)
    env_model = os.getenv("LLM_PLANNER_MODEL", "")
    model = env_model or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("LLM_PLANNER_PROVIDER=%s but %s not set", provider, cfg["env_key"])
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def get_coder() -> TokenFunc:
    """获取 Coder（Manim 代码生成）的 LLM 函数。默认 Qwen-Coder。"""
    provider = _get_role_provider("coder")
    cfg = _get_provider_config(provider)
    env_model = os.getenv("LLM_CODER_MODEL", "")
    model = env_model or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("LLM_CODER_PROVIDER=%s but %s not set", provider, cfg["env_key"])
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def get_critic() -> VisionFunc:
    """获取 Critic（视频画面评审）的 VLM 函数。默认 Qwen-VL。"""
    provider = _get_role_provider("critic")
    cfg = _get_provider_config(provider)
    env_model = os.getenv("LLM_CRITIC_MODEL", "")
    model = env_model or cfg["models"]["vision"] or cfg["models"]["text"]
    if not cfg["api_key"]:
        logger.warning("LLM_CRITIC_PROVIDER=%s but %s not set", provider, cfg["env_key"])
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_vision_func(client, model)


def get_narrator() -> TokenFunc:
    """获取旁白生成的 LLM 函数。默认使用 DeepSeek。"""
    provider = os.getenv("LLM_NARRATOR_PROVIDER", "deepseek")
    cfg = _get_provider_config(provider)
    env_model = os.getenv("LLM_NARRATOR_MODEL", "")
    model = env_model or cfg["models"]["text"]
    client = _make_client(cfg["base_url"], cfg["api_key"])
    return _make_text_func(client, model)


def is_configured() -> bool:
    """检查是否至少有一个 provider 配置了 API key"""
    for name, cfg in PROVIDERS.items():
        if os.getenv(cfg["env_key"], ""):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# Chat Client（兼容 BaseLLMClient .chat() 接口）
# ═══════════════════════════════════════════════════════════════════════

class UnifiedChatClient:
    """统一的 chat 客户端 — 实现 .chat(messages) 接口，所有 agent 通用。

    读取 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL env，或从 settings 回退。
    """

    def __init__(self):
        import importlib
        prov = os.getenv("LLM_API_PROVIDER", "deepseek")
        cfg = _get_provider_config(prov)
        self._api_key = os.getenv("LLM_API_KEY") or cfg["api_key"]
        self._base_url = os.getenv("LLM_BASE_URL") or cfg["base_url"]
        self._model = os.getenv("LLM_MODEL") or cfg["models"]["text"]
        try:
            mod = importlib.import_module("app.config")
            settings = getattr(mod, "settings", None)
            if settings:
                self._api_key = self._api_key or getattr(settings, "deepseek_api_key", "")
                self._base_url = self._base_url or getattr(settings, "deepseek_base_url", "https://api.deepseek.com")
                self._model = self._model or getattr(settings, "llm_model", "deepseek-chat")
        except Exception:
            pass
        self._temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key) if self._api_key else None

    def is_available(self) -> bool:
        return self._client is not None

    def chat(self, messages: list[dict], **kwargs) -> str:
        if not self._client:
            raise RuntimeError("No LLM API key configured. Set LLM_API_KEY in .env")
        max_tokens = kwargs.pop("max_tokens", 8000)
        temp = kwargs.pop("temperature", self._temperature)
        retries = kwargs.pop("retry_count", 2)
        for attempt in range(retries + 1):
            try:
                completion = self._client.chat.completions.create(
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
        if not self._client:
            raise RuntimeError("No LLM API key configured")
        model = kwargs.pop("model", self._model) or self._model
        temp = kwargs.pop("temperature", self._temperature)
        # deepseek-reasoner 需要单独处理 reasoning_content
        _is_reasoner = "reasoner" in model
        if _is_reasoner:
            kwargs.pop("reasoning", None)
        stream = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temp,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # deepseek-reasoner: reasoning_content 没有 OpenAI 标准字段
            if _is_reasoner:
                # 尝试从原始响应中提取 reasoning_content
                try:
                    raw = chunk.model_dump() if hasattr(chunk, 'model_dump') else None
                    rc = raw and raw.get("choices", [{}])[0].get("delta", {}).get("reasoning_content", "")
                    if rc:
                        yield f"<thinking>{rc}</thinking>"
                except Exception:
                    pass
            if delta and delta.content:
                yield delta.content


def get_chat_client() -> UnifiedChatClient:
    """返回统一 chat 客户端，所有 agent 调用 LLM 的统一入口。"""
    return UnifiedChatClient()
