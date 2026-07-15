"""API 请求层：支持 DeepSeek、Qwen、Qwen-VL

所有 API 函数签名统一为：
    func(prompt, max_tokens=..., max_retries=...) -> response
    func(prompt, max_tokens=..., max_retries=...) -> (response, usage_dict)
"""

import os
import time
import random
import base64
import json
import pathlib
import logging
from openai import OpenAI
from typing import Optional, List

logger = logging.getLogger(__name__)

_CFG_PATH = pathlib.Path(__file__).with_name("api_config.json")
if _CFG_PATH.exists():
    with _CFG_PATH.open("r", encoding="utf-8") as _f:
        _CFG = json.load(_f)
else:
    _CFG = {}


def _load_api_config():
    """Load API config from environment variables (primary) or api_config.json (fallback)."""
    import os as _os
    from pathlib import Path as _Path
    
    cfg_path = _Path(__file__).with_name("api_config.json")
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_CFG = _load_api_config()


# ═══════════════════════════════════════════════════════════════════════
# DeepSeek API
# ═══════════════════════════════════════════════════════════════════════

def request_deepseek_token(prompt, max_tokens=8000, max_retries=3, log_id=None):
    """DeepSeek API — OpenAI 兼容接口，返回 (response, usage_dict)"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY not configured")
    
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info
        except Exception as e:
            if attempt >= max_retries - 1:
                logger.warning(f"DeepSeek API failed after {max_retries} attempts: {e}")
                return None, usage_info
            delay = (2 ** attempt) * 0.5 + random.random() * 0.5
            time.sleep(delay)
    
    return None, usage_info


# ═══════════════════════════════════════════════════════════════════════
# Qwen Coder API (DashScope)
# ═══════════════════════════════════════════════════════════════════════

def request_qwen_token(prompt, max_tokens=8000, max_retries=3, log_id=None):
    """Qwen Coder API — DashScope OpenAI 兼容接口，返回 (response, usage_dict)"""
    api_key = os.getenv("QWEN_API_KEY", "")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("QWEN_CODER_MODEL", "qwen-coder-plus")
    
    if not api_key:
        raise ValueError("QWEN_API_KEY not configured")
    
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info
        except Exception as e:
            if attempt >= max_retries - 1:
                logger.warning(f"Qwen API failed after {max_retries} attempts: {e}")
                return None, usage_info
            delay = (2 ** attempt) * 0.5 + random.random() * 0.5
            time.sleep(delay)
    
    return None, usage_info


# ═══════════════════════════════════════════════════════════════════════
# Qwen-VL Vision API — 多帧截图评审（替代 Gemini 视频评审）
# ═══════════════════════════════════════════════════════════════════════

def request_qwen_vl_frames(prompt: str, image_paths: List[str], max_tokens=8000, max_retries=3):
    """Qwen-VL 多帧图片评审 — 输入图片路径列表，返回 completion 对象"""
    api_key = os.getenv("QWEN_API_KEY", "")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vl_model = os.getenv("QWEN_VL_MODEL", "qwen-vl-max")
    
    if not api_key:
        raise ValueError("QWEN_API_KEY not configured for Qwen-VL")
    
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    # Build content with images
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        try:
            with open(img_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_data}"}
            })
        except Exception as e:
            logger.warning(f"Failed to encode image {img_path}: {e}")
    
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=vl_model,
                messages=[{"role": "user", "content": content}],
                max_tokens=max_tokens,
            )
            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info
        except Exception as e:
            if attempt >= max_retries - 1:
                logger.warning(f"Qwen-VL API failed after {max_retries} attempts: {e}")
                return None, usage_info
            delay = (2 ** attempt) * 1.0 + random.random() * 1.0
            time.sleep(delay)
    
    return None, usage_info


# ═══════════════════════════════════════════════════════════════════════
# Convenience wrappers
# ═══════════════════════════════════════════════════════════════════════

def request_deepseek(prompt, max_tokens=8000, max_retries=3):
    """Simple wrapper — returns text string"""
    completion, _ = request_deepseek_token(prompt, max_tokens, max_retries)
    if completion:
        try:
            return completion.choices[0].message.content
        except Exception:
            return str(completion)
    return None


def request_qwen(prompt, max_tokens=8000, max_retries=3):
    """Simple wrapper — returns text string"""
    completion, _ = request_qwen_token(prompt, max_tokens, max_retries)
    if completion:
        try:
            return completion.choices[0].message.content
        except Exception:
            return str(completion)
    return None
