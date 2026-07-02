"""Learner profile routes — academic info, role switching, session list."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import LearnerModel, SessionModel
from app.middleware.auth import AuthContext, get_auth, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["learner"])


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=128)
    grade: str | None = Field(default=None, max_length=16)
    target_exam: str | None = Field(default=None, max_length=64)
    school: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=512)


class SwitchRoleRequest(BaseModel):
    role: str = Field(..., pattern=r"^(student|parent|teacher)$")
    target_learner_id: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

GRADE_OPTIONS = [
    "小学一年级", "小学二年级", "小学三年级", "小学四年级", "小学五年级", "小学六年级",
    "初中一年级", "初中二年级", "初中三年级",
    "高中一年级", "高中二年级", "高中三年级",
    "大一", "大二", "大三", "大四",
]

EXAM_OPTIONS = ["中考", "高考", "考研", "雅思", "托福", "期末", "竞赛"]


def _learner_full(learner: LearnerModel) -> dict[str, Any]:
    updated = learner.updated_at
    return {
        "id": learner.id,
        "nickname": learner.nickname,
        "name": learner.nickname,  # backward compat alias
        "phone": (_mask_phone(learner.phone or "") if learner.phone else None),
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
# Routes — own profile
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/learner/me")
def get_my_profile(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Get the current learner's full profile."""
    learner = _load_learner(auth.learner_id)
    return {"learner": _learner_full(learner)}


@router.patch("/learner/me")
def update_my_profile(
    body: UpdateProfileRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Update the current learner's academic profile fields."""
    db = SessionLocal()
    try:
        learner = db.get(LearnerModel, auth.learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        updates = body.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(learner, key, value)

        db.commit()
        db.refresh(learner)
        return {"learner": _learner_full(learner)}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Routes — other learners (teacher/parent view)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/learner/{learner_id}")
def get_learner_profile(
    learner_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Get a learner's profile. Teachers can view any student; parents can view their children."""
    db = SessionLocal()
    try:
        learner = db.get(LearnerModel, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        # Authorization: teachers and admins can view anyone
        if auth.role in ("teacher", "admin"):
            return {"learner": _learner_full(learner)}

        # Parents can view their children
        if auth.role == "parent" and learner.parent_id == auth.learner_id:
            return {"learner": _learner_full(learner)}

        # Self
        if learner_id == auth.learner_id:
            return {"learner": _learner_full(learner)}

        raise HTTPException(status_code=403, detail="无权查看该用户信息")
    finally:
        db.close()


@router.get("/learner/{learner_id}/sessions")
def get_learner_sessions(
    learner_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Get a learner's session list (most recent first)."""
    db = SessionLocal()
    try:
        learner = db.get(LearnerModel, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        # Auth check same as above
        if not _can_view(auth, learner):
            raise HTTPException(status_code=403, detail="无权查看")

        sessions = (
            db.query(SessionModel)
            .filter(SessionModel.learner_id == learner_id, SessionModel.status == "active")
            .order_by(SessionModel.updated_at.desc())
            .limit(50)
            .all()
        )

        return {
            "learner_id": learner_id,
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "subject_id": s.subject_id,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in sessions
            ],
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Routes — role switching
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/learner/switch-role")
def switch_role(
    body: SwitchRoleRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Switch the active role context. Parents select a child; teachers select a student."""
    db = SessionLocal()
    try:
        learner = db.get(LearnerModel, auth.learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        if body.role == "parent":
            if learner.role != "parent":
                raise HTTPException(status_code=403, detail="只有家长角色可以切换到家长视图")
            # List children
            children = (
                db.query(LearnerModel)
                .filter(LearnerModel.parent_id == auth.learner_id)
                .all()
            )
            target = None
            if body.target_learner_id:
                target = next((c for c in children if c.id == body.target_learner_id), None)
            else:
                target = children[0] if children else None

            return {
                "role": "parent",
                "children": [_learner_full(c) for c in children],
                "active_child": _learner_full(target) if target else None,
            }

        if body.role == "teacher":
            if learner.role not in ("teacher", "admin"):
                raise HTTPException(status_code=403, detail="只有教师角色可以切换到教师视图")
            return {
                "role": "teacher",
                "message": "教师视图已激活",
            }

        # student — just return self
        return {
            "role": "student",
            "learner": _learner_full(learner),
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Routes — metadata
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/learner/meta/options")
def get_meta_options() -> dict[str, list[str]]:
    """Return available grade and exam options for the profile form."""
    return {
        "grades": GRADE_OPTIONS,
        "exams": EXAM_OPTIONS,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _load_learner(learner_id: str) -> LearnerModel:
    db = SessionLocal()
    try:
        learner = db.get(LearnerModel, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        return learner
    finally:
        db.close()


def _can_view(auth: AuthContext, target: LearnerModel) -> bool:
    if auth.learner_id == target.id:
        return True
    if auth.role in ("teacher", "admin"):
        return True
    if auth.role == "parent" and target.parent_id == auth.learner_id:
        return True
    return False
