"""Class Subject tests — verifies class creation, join, push, and member management.

Tests the class subject mechanism (班级科目) introduced for teacher-led classroom management.
"""

from __future__ import annotations

import os
import sys

# Disable RAG to avoid import errors when llama_index is not installed
os.environ["RAG_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.engine import SessionLocal
from app.db.models import (
    ClassSubjectModel,
    ClassSubjectMemberModel,
    LearnerModel,
)
from app.utils.auth import create_token

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _auth_header(learner_id: str, role: str = "student") -> dict:
    """Create an Authorization header with a signed token."""
    token = create_token(learner_id, role)
    return {"Authorization": f"Bearer {token}"}


def _create_learner(learner_id: str, role: str = "student", nickname: str = "") -> LearnerModel:
    """Create a learner directly in the database."""
    db = SessionLocal()
    try:
        learner = LearnerModel(
            id=learner_id,
            nickname=nickname or learner_id,
            role=role,
        )
        db.add(learner)
        db.commit()
        db.refresh(learner)
        return learner
    finally:
        db.close()


def _ensure_learner(learner_id: str, role: str = "student") -> None:
    """Ensure a learner exists, creating if needed."""
    db = SessionLocal()
    try:
        existing = db.get(LearnerModel, learner_id)
        if not existing:
            learner = LearnerModel(id=learner_id, nickname=learner_id, role=role)
            db.add(learner)
            db.commit()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Create class subject
# ═══════════════════════════════════════════════════════════════════════════


def test_create_class_subject_as_teacher():
    """Teacher can create a class subject and receive an invite code."""
    _ensure_learner("teacher_1", "teacher")
    resp = client.post(
        "/api/class-subjects",
        json={"name": "高一数学班", "subject": "数学", "description": "春季班"},
        headers=_auth_header("teacher_1", "teacher"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    cs = body["data"]["classSubject"]
    assert cs["name"] == "高一数学班"
    assert cs["teacher_id"] == "teacher_1"
    assert len(cs["invite_code"]) == 6
    assert cs["student_count"] == 0

    # Verify in database
    db = SessionLocal()
    try:
        model = db.get(ClassSubjectModel, cs["id"])
        assert model is not None
        assert model.invite_code == cs["invite_code"]
    finally:
        db.close()


def test_create_class_subject_as_student_forbidden():
    """Student cannot create a class subject."""
    _ensure_learner("student_1", "student")
    resp = client.post(
        "/api/class-subjects",
        json={"name": "尝试创建班级", "subject": "数学"},
        headers=_auth_header("student_1", "student"),
    )
    assert resp.status_code == 403


def test_create_class_subject_empty_name():
    """Cannot create a class with empty name."""
    _ensure_learner("teacher_2", "teacher")
    resp = client.post(
        "/api/class-subjects",
        json={"name": "", "subject": ""},
        headers=_auth_header("teacher_2", "teacher"),
    )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 2. List teacher's own classes
# ═══════════════════════════════════════════════════════════════════════════


def test_get_my_class_subjects():
    """Teacher sees only their own classes."""
    _ensure_learner("teacher_3", "teacher")
    # Create two classes
    client.post(
        "/api/class-subjects",
        json={"name": "班级A", "subject": "数学"},
        headers=_auth_header("teacher_3", "teacher"),
    )
    client.post(
        "/api/class-subjects",
        json={"name": "班级B", "subject": "英语"},
        headers=_auth_header("teacher_3", "teacher"),
    )

    resp = client.get("/api/class-subjects/my", headers=_auth_header("teacher_3", "teacher"))
    assert resp.status_code == 200
    cs_list = resp.json()["data"]["classSubjects"]
    assert len(cs_list) >= 2
    names = [c["name"] for c in cs_list]
    assert "班级A" in names
    assert "班级B" in names


# ═══════════════════════════════════════════════════════════════════════════
# 3. Join class by invite code
# ═══════════════════════════════════════════════════════════════════════════


def test_join_class_valid_code():
    """Student joins a class with a valid invite code."""
    _ensure_learner("teacher_join", "teacher")
    _ensure_learner("student_join", "student")

    # Teacher creates class
    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "测试班级", "subject": "物理"},
        headers=_auth_header("teacher_join", "teacher"),
    )
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    # Student joins
    resp = client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_join", "student"),
    )
    assert resp.status_code == 200
    cs = resp.json()["data"]["classSubject"]
    assert cs["id"] == class_id
    assert cs["student_count"] == 1

    # Verify membership in database
    db = SessionLocal()
    try:
        member = (
            db.query(ClassSubjectMemberModel)
            .filter(
                ClassSubjectMemberModel.class_id == class_id,
                ClassSubjectMemberModel.student_id == "student_join",
            )
            .first()
        )
        assert member is not None
    finally:
        db.close()


def test_join_class_invalid_code():
    """Invalid invite code returns 404."""
    _ensure_learner("student_invalid", "student")
    resp = client.post(
        "/api/class-subjects/join",
        json={"inviteCode": "ZZZZZZ"},
        headers=_auth_header("student_invalid", "student"),
    )
    assert resp.status_code == 404


def test_join_class_duplicate():
    """Duplicate join returns 409."""
    _ensure_learner("teacher_dup", "teacher")
    _ensure_learner("student_dup", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "重复测试班", "subject": "数学"},
        headers=_auth_header("teacher_dup", "teacher"),
    )
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]

    # First join succeeds
    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_dup", "student"),
    )

    # Second join fails
    resp = client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_dup", "student"),
    )
    assert resp.status_code == 409


def test_teacher_cannot_join_own_class():
    """Teacher cannot join their own class."""
    _ensure_learner("teacher_self", "teacher")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "自己的班", "subject": "数学"},
        headers=_auth_header("teacher_self", "teacher"),
    )
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]

    resp = client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("teacher_self", "teacher"),
    )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 4. List joined classes (student)
# ═══════════════════════════════════════════════════════════════════════════


def test_get_joined_class_subjects():
    """Student sees only classes they've joined."""
    _ensure_learner("teacher_jl", "teacher")
    _ensure_learner("student_jl", "student")

    # Teacher creates two classes
    r1 = client.post(
        "/api/class-subjects",
        json={"name": "加入班1", "subject": "数学"},
        headers=_auth_header("teacher_jl", "teacher"),
    )
    r2 = client.post(
        "/api/class-subjects",
        json={"name": "加入班2", "subject": "英语"},
        headers=_auth_header("teacher_jl", "teacher"),
    )
    code1 = r1.json()["data"]["classSubject"]["invite_code"]

    # Student joins only one
    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": code1},
        headers=_auth_header("student_jl", "student"),
    )

    resp = client.get(
        "/api/class-subjects/joined",
        headers=_auth_header("student_jl", "student"),
    )
    assert resp.status_code == 200
    joined = resp.json()["data"]["classSubjects"]
    assert len(joined) == 1
    assert joined[0]["name"] == "加入班1"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Class detail access control
# ═══════════════════════════════════════════════════════════════════════════


def test_teacher_can_view_own_class():
    """Teacher can view detail of their own class."""
    _ensure_learner("teacher_view", "teacher")
    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "查看测试", "subject": "语文"},
        headers=_auth_header("teacher_view", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}",
        headers=_auth_header("teacher_view", "teacher"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["classSubject"]["name"] == "查看测试"


def test_non_member_cannot_view_class():
    """Non-member student cannot view class detail."""
    _ensure_learner("teacher_nm", "teacher")
    _ensure_learner("student_nm", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "非成员测试", "subject": "语文"},
        headers=_auth_header("teacher_nm", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}",
        headers=_auth_header("student_nm", "student"),
    )
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 6. Member management
# ═══════════════════════════════════════════════════════════════════════════


def test_list_members():
    """Teacher can list enrolled students."""
    _ensure_learner("teacher_mem", "teacher")
    _ensure_learner("student_m1", "student")
    _ensure_learner("student_m2", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "成员测试班", "subject": "数学"},
        headers=_auth_header("teacher_mem", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]

    # Two students join
    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_m1", "student"),
    )
    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_m2", "student"),
    )

    resp = client.get(
        f"/api/class-subjects/{class_id}/members",
        headers=_auth_header("teacher_mem", "teacher"),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["members"]) == 2


def test_remove_member():
    """Teacher can remove a student from class."""
    _ensure_learner("teacher_rm", "teacher")
    _ensure_learner("student_rm", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "移除测试班", "subject": "数学"},
        headers=_auth_header("teacher_rm", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]

    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_rm", "student"),
    )

    # Verify student count is 1
    cs_resp = client.get(
        f"/api/class-subjects/{class_id}",
        headers=_auth_header("teacher_rm", "teacher"),
    )
    assert cs_resp.json()["data"]["classSubject"]["student_count"] == 1

    # Remove
    resp = client.delete(
        f"/api/class-subjects/{class_id}/members/student_rm",
        headers=_auth_header("teacher_rm", "teacher"),
    )
    assert resp.status_code == 200

    # Verify student count decremented
    cs_resp = client.get(
        f"/api/class-subjects/{class_id}",
        headers=_auth_header("teacher_rm", "teacher"),
    )
    assert cs_resp.json()["data"]["classSubject"]["student_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. Push exercises
# ═══════════════════════════════════════════════════════════════════════════


def test_push_exercises():
    """Teacher can push exercises to a class."""
    _ensure_learner("teacher_push", "teacher")
    _ensure_learner("student_push", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "推送测试班", "subject": "数学"},
        headers=_auth_header("teacher_push", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    # Push requires admin question bank entries; testing with empty list
    resp = client.post(
        f"/api/class-subjects/{class_id}/push",
        json={"title": "测试推送", "questionIds": []},
        headers=_auth_header("teacher_push", "teacher"),
    )
    assert resp.status_code == 400  # Empty question list

    # Push with valid-looking but non-existent question IDs
    resp = client.post(
        f"/api/class-subjects/{class_id}/push",
        json={"title": "测试推送", "questionIds": ["q_nonexistent"]},
        headers=_auth_header("teacher_push", "teacher"),
    )
    assert resp.status_code == 400  # Invalid question IDs


def test_push_history():
    """Teacher can view push history."""
    _ensure_learner("teacher_ph", "teacher")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "历史测试班", "subject": "英语"},
        headers=_auth_header("teacher_ph", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}/pushes",
        headers=_auth_header("teacher_ph", "teacher"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["pushes"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. Student pushed questions
# ═══════════════════════════════════════════════════════════════════════════


def test_student_pushed_questions_requires_membership():
    """Non-member student cannot access pushed questions."""
    _ensure_learner("teacher_spq", "teacher")
    _ensure_learner("student_spq", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "权限测试班", "subject": "数学"},
        headers=_auth_header("teacher_spq", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}/pushed-questions",
        headers=_auth_header("student_spq", "student"),
    )
    assert resp.status_code == 403


def test_enrolled_student_can_access_pushed_questions():
    """Enrolled student can access pushed questions (empty list for new class)."""
    _ensure_learner("teacher_espq", "teacher")
    _ensure_learner("student_espq", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "学生访问班", "subject": "数学"},
        headers=_auth_header("teacher_espq", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]
    invite_code = create_resp.json()["data"]["classSubject"]["invite_code"]

    client.post(
        "/api/class-subjects/join",
        json={"inviteCode": invite_code},
        headers=_auth_header("student_espq", "student"),
    )

    resp = client.get(
        f"/api/class-subjects/{class_id}/pushed-questions",
        headers=_auth_header("student_espq", "student"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["pushes"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 9. Statistics
# ═══════════════════════════════════════════════════════════════════════════


def test_class_stats():
    """Teacher can view class statistics."""
    _ensure_learner("teacher_stats", "teacher")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "统计测试班", "subject": "数学"},
        headers=_auth_header("teacher_stats", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}/stats",
        headers=_auth_header("teacher_stats", "teacher"),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["totalStudents"] == 0
    assert data["totalPushes"] == 0


def test_stats_access_denied_for_non_teacher():
    """Student cannot view class statistics."""
    _ensure_learner("teacher_sa", "teacher")
    _ensure_learner("student_sa", "student")

    create_resp = client.post(
        "/api/class-subjects",
        json={"name": "统计权限班", "subject": "数学"},
        headers=_auth_header("teacher_sa", "teacher"),
    )
    class_id = create_resp.json()["data"]["classSubject"]["id"]

    resp = client.get(
        f"/api/class-subjects/{class_id}/stats",
        headers=_auth_header("student_sa", "student"),
    )
    assert resp.status_code == 403
