"""科大讯飞 星火多模态 Provider — 图片生成 + 视频生成."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib import request, parse, error as urllib_error

from app.config import settings

logger = logging.getLogger(__name__)

SPARK_IMAGE_URL = settings.spark_image_host_url
SPARK_APP_ID = settings.spark_app_id
SPARK_API_KEY = settings.spark_api_key
SPARK_API_SECRET = settings.spark_api_secret


def _build_auth_url(host_url: str, api_key: str = "", api_secret: str = "") -> str:
    """构建带 HMAC 签名的请求 URL."""
    key = api_key or SPARK_API_KEY
    secret = api_secret or SPARK_API_SECRET
    url_parsed = parse.urlparse(host_url)
    host = url_parsed.hostname or ""
    path = url_parsed.path or "/"

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    signature_origin = f"host: {host}\ndate: {date_str}\nPOST {path} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(
            secret.encode(),
            signature_origin.encode(),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode()

    authorization = (
        f'api_key="{key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    from urllib.parse import quote
    auth = base64.b64encode(authorization.encode()).decode()
    return f"{host_url}?authorization={quote(auth)}&date={quote(date_str)}&host={quote(host)}"


def _request(url: str, body: dict) -> dict | None:
    """带重试的 HTTP POST."""
    req = request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SPARK_API_KEY}:{SPARK_APP_ID}",
    })
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                logger.warning("Spark API failed: %s", e)
                return None
            time.sleep(1)
    return None


def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
) -> dict[str, Any]:
    """星火绘画：文本生成图片，返回 base64 图片数据。"""
    if not SPARK_APP_ID or not SPARK_API_KEY:
        return {"status": "provider_not_configured", "provider": "spark_image"}

    try:
        url = _build_auth_url(SPARK_IMAGE_URL)
        body = {
            "header": {"app_id": SPARK_APP_ID},
            "parameter": {
                "chat": {
                    "domain": "general",
                    "width": width,
                    "height": height,
                }
            },
            "payload": {
                "message": {
                    "text": [
                        {"role": "user", "content": prompt}
                    ]
                }
            },
        }
        result = _request(url, body)
        if result and result.get("header", {}).get("code") == 0:
            payload = result.get("payload", {})
            choices = payload.get("choices", {})
            content_list = choices.get("text", []) if isinstance(choices, dict) else []
            image_base64 = ""
            for item in content_list:
                if isinstance(item, dict) and item.get("content"):
                    image_base64 = str(item["content"])
                    break
            if image_base64:
                return {
                    "status": "success",
                    "provider": "spark_image",
                    "image_base64": image_base64,
                    "format": "png",
                }
        error_msg = str(result.get("header", {}).get("message", "unknown")) if result else "no response"
        return {"status": "failed", "provider": "spark_image", "error": error_msg}
    except Exception as e:
        return {"status": "failed", "provider": "spark_image", "error": str(e)}


def generate_video(prompt: str) -> dict[str, Any]:
    """星火视频生成：文本生成短视频。

    当前讯飞视频 API 需要异步提交+轮询，这里返回脚本草案作为第一版实现。
    后续可接真实的视频生成 API。
    """
    if not SPARK_APP_ID or not SPARK_API_KEY:
        return {"status": "provider_not_configured", "provider": "spark_video"}

    try:
        # 第一版：返回视频脚本（后续可接真实视频生成 API）
        return {
            "status": "script_ready",
            "provider": "spark_video",
            "script": f"【视频脚本：{prompt}】\n"
                      f"1. 开场引入（15秒）：用动画展示本节核心概念\n"
                      f"2. 核心讲解（90秒）：分步骤讲解关键知识点，配图解\n"
                      f"3. 总结回顾（15秒）：关键词总结 + 思考题",
            "duration_estimate": "2分钟",
        }
    except Exception as e:
        return {"status": "failed", "provider": "spark_video", "error": str(e)}


# ── 与 multimodal_provider.py 兼容的 Tool 接口 ──

class SparkImageProvider:
    """兼容 MultimodalAgent 的图片生成工具接口。"""

    def __init__(self) -> None:
        pass

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            str(context.get("user_message", ""))
            or f"为「{context.get('subject_name', '学习内容')}」生成一张教学配图"
        )[:500]
        result = generate_image(prompt)
        return result


class SparkVideoProvider:
    """兼容 MultimodalAgent 的视频生成工具接口。"""

    def __init__(self) -> None:
        pass

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            str(context.get("user_message", ""))
            or f"为「{context.get('subject_name', '学习内容')}」生成讲解微课视频"
        )[:500]
        result = generate_video(prompt)
        return result
