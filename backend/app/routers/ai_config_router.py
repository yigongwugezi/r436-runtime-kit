"""Per-user AI model credential endpoints — 系统设置 → AI 模型配置.

Credentials are stored per learner in the ``user_ai_config`` table and are
NEVER returned in full: every read goes through
``user_ai_config.to_safe_response`` which masks secrets (``sk-26****1d4f``)
and adds per-service ``configured`` flags.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.repository import get_user_ai_config, merge_user_ai_config
from app.middleware.auth import AuthContext, require_auth
from app.services.user_ai_config import to_safe_response, user_capabilities

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-config"])


class SaveAIConfigRequest(BaseModel):
    """Partial per-service update; see ``merge_user_ai_config`` semantics."""

    config: dict = Field(default_factory=dict)


@router.get("/learner/me/ai-config")
def get_my_ai_config(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """获取当前用户的 AI 模型配置（密钥已脱敏，完整 key 永不返回）。"""
    db = SessionLocal()
    try:
        raw = get_user_ai_config(db, auth.learner_id)
        return {"config": to_safe_response(raw)}
    finally:
        db.close()


@router.put("/learner/me/ai-config")
def save_my_ai_config(
    body: SaveAIConfigRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """保存 AI 模型配置（按服务部分合并；空字符串清除；脱敏占位值忽略）。"""
    db = SessionLocal()
    try:
        saved = merge_user_ai_config(db, auth.learner_id, body.config)
        logger.info("AI config updated for learner %s", auth.learner_id)
        return {"config": to_safe_response(saved)}
    finally:
        db.close()


@router.get("/learner/me/ai-config/capabilities")
def get_my_ai_capabilities(
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """按当前用户凭据计算的能力开关（供前端提示各功能是否可用）。"""
    db = SessionLocal()
    try:
        config = get_user_ai_config(db, auth.learner_id)
        return user_capabilities(config)
    finally:
        db.close()


# ── 讯飞语音听写（IAT）预签名 ────────────────────────────────────────
# 语音识别在浏览器端直连讯飞 WebSocket，但 HMAC 签名必须在后端完成：
# 用户的 apiKey/apiSecret 只存在于 user_ai_config，原始密钥永不下发前端。
# 签名 URL 按讯飞规则带 date，有效期约 5 分钟，前端每次开始录音前获取。

_ASR_HOST = "iat-api.xfyun.cn"
_ASR_PATH = "/v2/iat"


def _build_asr_ws_url(api_key: str, api_secret: str) -> str:
    """构建讯飞 IAT 的 HMAC-SHA256 预签名 wss URL（GET 动词）。"""
    import base64
    import hashlib
    import hmac
    from datetime import datetime, timezone
    from urllib.parse import quote

    date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    signing = f"host: {_ASR_HOST}\ndate: {date_str}\nGET {_ASR_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), signing.encode(), hashlib.sha256).digest()
    ).decode()
    auth_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    auth = base64.b64encode(auth_origin.encode()).decode()
    return (
        f"wss://{_ASR_HOST}{_ASR_PATH}"
        f"?authorization={quote(auth, safe='')}&date={quote(date_str, safe='')}&host={_ASR_HOST}"
    )


@router.get("/learner/me/ai-config/asr-ws-url")
def get_my_asr_ws_url(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """获取讯飞语音听写的预签名 WebSocket URL + appId。

    未配置 asr 凭据时返回 409 AI_CONFIG_MISSING，引导用户前往系统设置。
    appId 是非机密标识（首帧 common.app_id 需要），密钥不出后端。
    """
    from app.services.user_ai_config import get_credential
    from app.utils.errors import AIConfigMissingError

    db = SessionLocal()
    try:
        config = get_user_ai_config(db, auth.learner_id)
    finally:
        db.close()
    app_id = get_credential("asr", "appId", config=config)
    api_key = get_credential("asr", "apiKey", config=config)
    api_secret = get_credential("asr", "apiSecret", config=config)
    if not app_id or not api_key or not api_secret:
        raise AIConfigMissingError(service="asr", provider="讯飞语音听写")
    return {"url": _build_asr_ws_url(api_key, api_secret), "appId": app_id}
