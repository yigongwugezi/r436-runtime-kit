"""Auth routes — registration, login, token refresh, logout."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import LearnerModel
from app.db.repository import get_or_create_learner
from app.middleware.auth import AuthContext, get_auth
from app.utils.auth import create_token, create_refresh_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20, pattern=r"^\d+$")
    password: str = Field(..., min_length=6, max_length=128)
    nickname: str = Field(default="学习者", max_length=128)
    role: str = Field(default="student", pattern=r"^(student|parent|teacher)$")
    grade: str | None = None
    target_exam: str | None = None
    student_no: str | None = Field(default=None, min_length=1, max_length=32)


class LoginRequest(BaseModel):
    phone: str | None = Field(default=None, min_length=11, max_length=20, pattern=r"^\d+$")
    student_no: str | None = Field(default=None, min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    learner: dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

BLACKLIST: set[str] = set()  # In-memory token blacklist (cleared on restart)


def _learner_dict(learner: LearnerModel) -> dict[str, Any]:
    updated = learner.updated_at
    return {
        "id": learner.id,
        "nickname": learner.nickname,
        "name": learner.nickname,  # backward compat alias
        "phone": _mask_phone(learner.phone or ""),
        "role": learner.role,
        "grade": learner.grade,
        "target_exam": learner.target_exam,
        "school": learner.school,
        "student_no": learner.student_no,
        "avatar_url": learner.avatar_url,
        "created_at": learner.created_at.isoformat() if learner.created_at else None,
        "updated_at": updated.isoformat() if updated else None,
        "lastLoginAt": int(updated.timestamp() * 1000) if updated else 0,
    }


def _mask_phone(phone: str) -> str:
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


# ═══════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/auth/register", response_model=TokenResponse)
def register(body: RegisterRequest) -> dict[str, Any]:
    """Register a new learner account with phone + password."""
    db = SessionLocal()
    try:
        # Check phone uniqueness
        existing = db.query(LearnerModel).filter(LearnerModel.phone == body.phone).first()
        if existing:
            raise HTTPException(status_code=409, detail="该手机号已注册")

        learner_id = f"learner_{uuid.uuid4().hex[:12]}"
        learner = LearnerModel(
            id=learner_id,
            nickname=body.nickname,
            phone=body.phone,
            password_hash=hash_password(body.password),
            role=body.role,
            grade=body.grade,
            target_exam=body.target_exam,
            student_no=body.student_no,
        )
        db.add(learner)
        db.commit()
        db.refresh(learner)

        access_token = create_token(learner_id, learner.role, ttl_seconds=900)
        refresh_token = create_refresh_token(learner_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "learner": _learner_dict(learner),
        }
    finally:
        db.close()


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> dict[str, Any]:
    """Login with phone + password or student_no + password."""
    if not body.phone and not body.student_no:
        raise HTTPException(status_code=422, detail="请提供手机号或学号")

    db = SessionLocal()
    try:
        learner = None
        if body.phone:
            learner = db.query(LearnerModel).filter(LearnerModel.phone == body.phone).first()
        if not learner and body.student_no:
            learner = db.query(LearnerModel).filter(LearnerModel.student_no == body.student_no).first()

        if not learner:
            raise HTTPException(status_code=401, detail="手机号/学号或密码错误")
        if not learner.password_hash:
            raise HTTPException(status_code=401, detail="该账号未设置密码，请使用其他方式登录")
        if not verify_password(body.password, learner.password_hash):
            raise HTTPException(status_code=401, detail="手机号/学号或密码错误")

        # Touch login timestamp
        from datetime import datetime, timezone
        learner.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(learner)

        access_token = create_token(learner.id, learner.role, ttl_seconds=900)
        refresh_token = create_refresh_token(learner.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "learner": _learner_dict(learner),
        }
    finally:
        db.close()


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    """Refresh access token using a valid refresh token."""
    if not auth.is_authenticated:
        raise HTTPException(status_code=401, detail="无效的 refresh token")
    if auth.learner is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    # Invalidate old token
    BLACKLIST.add(auth.learner_id)

    learner = auth.learner
    access_token = create_token(learner.id, learner.role, ttl_seconds=900)
    refresh_token = create_refresh_token(learner.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "learner": _learner_dict(learner),
    }


@router.post("/auth/logout")
def logout(auth: AuthContext = Depends(get_auth)) -> dict[str, str]:
    """Logout — blacklist current token."""
    if auth.learner_id:
        BLACKLIST.add(auth.learner_id)
    return {"status": "ok"}


@router.get("/auth/me")
def me(auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    """Return current authenticated learner info."""
    if not auth.is_authenticated or auth.learner is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return {"learner": _learner_dict(auth.learner)}
