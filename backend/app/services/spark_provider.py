"""科大讯飞 星火多模态 Provider — 图片生成 + 视频生成.

凭据来自每用户配置（系统设置 → AI 模型配置，spark 服务条目），在调用时
解析——不再使用 import 时绑定的模块级常量（那会把进程启动时的一份凭据
共享给所有用户）。仅图像端点 URL 作为技术项保留在 settings。
"""

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


def _spark_credentials() -> tuple[str, str, str]:
    """当前用户的星火三元组 (app_id, api_key, api_secret)。"""
    from app.services.user_ai_config import get_credential

    return (
        get_credential("spark", "appId"),
        get_credential("spark", "apiKey"),
        get_credential("spark", "apiSecret"),
    )


def _build_auth_url(host_url: str, api_key: str = "", api_secret: str = "") -> str:
    """构建带 HMAC 签名的请求 URL."""
    if not api_key or not api_secret:
        _, user_key, user_secret = _spark_credentials()
        api_key = api_key or user_key
        api_secret = api_secret or user_secret
    key = api_key
    secret = api_secret
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


def _request(url: str, body: dict, app_id: str, api_key: str) -> dict | None:
    """带重试的 HTTP POST."""
    req = request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}:{app_id}",
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
    width: int = 1280,
    height: int = 1280,
) -> dict[str, Any]:
    """星火绘画：文本生成图片，返回 base64 图片数据。"""
    app_id, api_key, api_secret = _spark_credentials()
    if not app_id or not api_key:
        return {"status": "provider_not_configured", "provider": "spark_image"}

    try:
        url = _build_auth_url(settings.spark_image_host_url, api_key=api_key, api_secret=api_secret)
        body = {
            "header": {"app_id": app_id},
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
        result = _request(url, body, app_id, api_key)
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


# ── 与 multimodal_provider.py 兼容的 Tool 接口 ──

class SparkImageProvider:
    """兼容 MultimodalAgent 的图片生成工具接口。"""

    @staticmethod
    def is_configured() -> bool:
        app_id, api_key, _ = _spark_credentials()
        return bool(app_id) and bool(api_key)

    def __init__(self) -> None:
        pass

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            str(context.get("user_message", ""))
            or f"为「{context.get('subject_name', '学习内容')}」生成一张教学配图"
        )[:500]
        result = generate_image(prompt)
        return result
