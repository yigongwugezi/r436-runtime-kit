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
