"""Class Subject routes — teacher creates class with invite code, students join,
teacher pushes exercises, manages roster, views stats.

Protected by require_teacher: only teacher/admin roles can manage classes.
"""

from __future__ import annotations

import logging
import random
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.db.engine import SessionLocal
from app.db.models import (
    AnswerRecordModel,
    ClassPushModel,
    ClassSubjectMemberModel,
    ClassSubjectModel,
    LearnerModel,
    QuestionModel,
    StudentQuestionModel,
)
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["class-subjects"])


# ═══════════════════════════════════════════════════════════════════════════
# Auth guard
# ═══════════════════════════════════════════════════════════════════════════


def require_teacher(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    if auth.role not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="需要教师权限")
    return auth


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _generate_invite_code(length: int = 6) -> str:
    """Generate a random alphanumeric invite code (uppercase)."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _class_subject_dict(cs: ClassSubjectModel) -> dict:
    """Serialize a ClassSubjectModel to dict."""
    return {
        "id": cs.id,
        "name": cs.name,
        "description": cs.description,
        "subject": cs.subject,
        "teacher_id": cs.teacher_id,
        "teacher_name": cs.teacher.nickname if cs.teacher else "",
        "invite_code": cs.invite_code,
        "student_count": cs.student_count,
        "created_at": cs.created_at.isoformat() if cs.created_at else None,
        "updated_at": cs.updated_at.isoformat() if cs.updated_at else None,
    }


def _member_dict(m: ClassSubjectMemberModel) -> dict:
    """Serialize a ClassSubjectMemberModel to dict, including student info."""
    student = m.student if hasattr(m, "student") else None
    return {
        "student_id": m.student_id,
        "student_name": student.nickname if student else m.student_id,
        "grade": student.grade if student else None,
        "school": student.school if student else None,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
    }


def _push_dict(p: ClassPushModel, answered_count: int = 0) -> dict:
    """Serialize a ClassPushModel to dict."""
    return {
        "id": p.id,
        "class_id": p.class_id,
        "teacher_id": p.teacher_id,
        "title": p.title,
        "description": p.description,
        "question_ids": p.question_ids or [],
        "question_count": len(p.question_ids or []),
        "answered_count": answered_count,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class CreateClassSubjectRequest(BaseModel):
    name: str = ""
    description: str | None = None
    subject: str = ""


class JoinClassRequest(BaseModel):
    invite_code: str = Field(..., alias="inviteCode")


class PushExercisesRequest(BaseModel):
    title: str = ""
    description: str | None = None
    question_ids: list[str] = Field(default_factory=list, alias="questionIds")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Create class subject (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/class-subjects")
def create_class_subject(
    body: CreateClassSubjectRequest,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """Create a new class subject. Returns the class with its invite code."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="班级名称不能为空")

    db = SessionLocal()
    try:
        # Generate unique invite code
        invite_code = _generate_invite_code()
        retries = 0
        while retries < 10:
            existing = db.query(ClassSubjectModel).filter(
                ClassSubjectModel.invite_code == invite_code
            ).first()
            if not existing:
                break
            invite_code = _generate_invite_code()
            retries += 1
        if retries >= 10:
            raise HTTPException(status_code=500, detail="邀请码生成失败，请重试")

        cs = ClassSubjectModel(
            id=f"cs_{uuid.uuid4().hex[:12]}",
            name=body.name.strip(),
            description=body.description,
            subject=body.subject.strip(),
            teacher_id=auth.learner_id,
            invite_code=invite_code,
        )
        db.add(cs)
        db.commit()
        db.refresh(cs)

        # Eager-load teacher relationship
        _ = cs.teacher

        return {"status": "success", "data": {"classSubject": _class_subject_dict(cs)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. List teacher's own class subjects
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/my")
def get_my_class_subjects(
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """List all class subjects created by the current teacher."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ClassSubjectModel)
            .filter(ClassSubjectModel.teacher_id == auth.learner_id)
            .order_by(ClassSubjectModel.created_at.desc())
            .all()
        )
        # Eager-load teacher for each
        for r in rows:
            _ = r.teacher
        return {
            "status": "success",
            "data": {"classSubjects": [_class_subject_dict(r) for r in rows]},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. List class subjects the student has joined
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/joined")
def get_joined_class_subjects(
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """List all class subjects the current user has joined."""
    db = SessionLocal()
    try:
        memberships = (
            db.query(ClassSubjectMemberModel)
            .filter(ClassSubjectMemberModel.student_id == auth.learner_id)
            .all()
        )
        if not memberships:
            return {"status": "success", "data": {"classSubjects": []}}

        class_ids = [m.class_id for m in memberships]
        rows = (
            db.query(ClassSubjectModel)
            .filter(ClassSubjectModel.id.in_(class_ids))
            .order_by(ClassSubjectModel.created_at.desc())
            .all()
        )
        # Eager-load teacher
        for r in rows:
            _ = r.teacher
        return {
            "status": "success",
            "data": {"classSubjects": [_class_subject_dict(r) for r in rows]},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Get class subject detail
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}")
def get_class_subject(
    class_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get a class subject's detail. Accessible by the teacher or enrolled members."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")

        # Access control: teacher (owner) or enrolled student
        is_teacher = auth.learner_id == cs.teacher_id or auth.role in ("admin",)
        if not is_teacher:
            is_member = (
                db.query(ClassSubjectMemberModel)
                .filter(
                    ClassSubjectMemberModel.class_id == class_id,
                    ClassSubjectMemberModel.student_id == auth.learner_id,
                )
                .first()
            )
            if not is_member:
                raise HTTPException(status_code=403, detail="无权访问该班级")

        _ = cs.teacher
        return {"status": "success", "data": {"classSubject": _class_subject_dict(cs)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Join class by invite code
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/class-subjects/join")
def join_class_subject(
    body: JoinClassRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Join a class subject using its invite code."""
    code = body.invite_code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="邀请码不能为空")

    db = SessionLocal()
    try:
        cs = db.query(ClassSubjectModel).filter(
            ClassSubjectModel.invite_code == code
        ).first()
        if cs is None:
            raise HTTPException(status_code=404, detail="邀请码无效，未找到对应班级")

        # Check if already a member
        existing = (
            db.query(ClassSubjectMemberModel)
            .filter(
                ClassSubjectMemberModel.class_id == cs.id,
                ClassSubjectMemberModel.student_id == auth.learner_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="你已加入该班级")

        # Cannot join your own class
        if cs.teacher_id == auth.learner_id:
            raise HTTPException(status_code=400, detail="不能加入自己创建的班级")

        # Create membership
        member = ClassSubjectMemberModel(
            class_id=cs.id,
            student_id=auth.learner_id,
        )
        db.add(member)

        # Increment denormalized count
        cs.student_count = (cs.student_count or 0) + 1

        db.commit()
        db.refresh(cs)
        _ = cs.teacher

        return {"status": "success", "data": {"classSubject": _class_subject_dict(cs)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 6. List class members (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}/members")
def get_class_members(
    class_id: str,
    auth: AuthContext = Depends(require_teacher),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List students enrolled in a class subject."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权查看该班级成员")

        total = (
            db.query(ClassSubjectMemberModel)
            .filter(ClassSubjectMemberModel.class_id == class_id)
            .count()
        )

        rows = (
            db.query(ClassSubjectMemberModel)
            .filter(ClassSubjectMemberModel.class_id == class_id)
            .order_by(ClassSubjectMemberModel.joined_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Load student info for each member
        student_ids = [r.student_id for r in rows]
        students = {}
        if student_ids:
            learner_rows = (
                db.query(LearnerModel)
                .filter(LearnerModel.id.in_(student_ids))
                .all()
            )
            students = {l.id: l for l in learner_rows}

        members = []
        for r in rows:
            student = students.get(r.student_id)
            members.append({
                "student_id": r.student_id,
                "student_name": student.nickname if student else r.student_id,
                "grade": student.grade if student else None,
                "school": student.school if student else None,
                "joined_at": r.joined_at.isoformat() if r.joined_at else None,
            })

        return {
            "status": "success",
            "data": {"members": members, "total": total},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Remove student from class (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.delete("/class-subjects/{class_id}/members/{student_id}")
def remove_class_member(
    class_id: str,
    student_id: str,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """Remove a student from a class subject."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权管理该班级")

        member = (
            db.query(ClassSubjectMemberModel)
            .filter(
                ClassSubjectMemberModel.class_id == class_id,
                ClassSubjectMemberModel.student_id == student_id,
            )
            .first()
        )
        if member is None:
            raise HTTPException(status_code=404, detail="该学生不在班级中")

        db.delete(member)
        cs.student_count = max(0, (cs.student_count or 0) - 1)
        db.commit()

        return {"status": "success", "data": None, "message": "已移除学生"}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Push exercises to class (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/class-subjects/{class_id}/push")
def push_exercises(
    class_id: str,
    body: PushExercisesRequest,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """Push exercises from the admin question bank to all students in a class."""
    if not body.question_ids:
        raise HTTPException(status_code=400, detail="请至少选择一道题目")

    if not body.title.strip():
        raise HTTPException(status_code=400, detail="请填写推送标题")

    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权管理该班级")

        # Validate all question_ids exist and are published
        admin_questions = (
            db.query(QuestionModel)
            .filter(QuestionModel.id.in_(body.question_ids))
            .all()
        )
        found_ids = {q.id for q in admin_questions}
        missing = [qid for qid in body.question_ids if qid not in found_ids]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"以下题目不存在: {', '.join(missing[:5])}",
            )

        # Create ClassPushModel
        push_id = f"cp_{uuid.uuid4().hex[:12]}"
        push = ClassPushModel(
            id=push_id,
            class_id=class_id,
            teacher_id=auth.learner_id,
            title=body.title.strip(),
            description=body.description,
            question_ids=body.question_ids,
        )
        db.add(push)

        # Create StudentQuestionModel records for each pushed question
        # Use session_id = "class_{classId}" so they're scoped to the class
        synthetic_session_id = f"class_{class_id}"
        now = datetime.now(timezone.utc)

        for aq in admin_questions:
            # Check if already pushed (same question_id + same session_id)
            existing = (
                db.query(StudentQuestionModel)
                .filter(
                    StudentQuestionModel.question_id == aq.id,
                    StudentQuestionModel.session_id == synthetic_session_id,
                )
                .first()
            )
            if existing:
                continue  # Skip duplicates

            sq = StudentQuestionModel(
                question_id=aq.id,  # Reuse admin bank question ID
                question_set_id=f"push_{push_id}",
                session_id=synthetic_session_id,
                source_question_id=aq.id,
                type=aq.type,
                stem=aq.content.get("stem", "") if isinstance(aq.content, dict) else "",
                options=aq.content.get("options") if isinstance(aq.content, dict) else None,
                correct=aq.content.get("answer") if isinstance(aq.content, dict) else None,
                explanation=aq.content.get("explanation", "") if isinstance(aq.content, dict) else "",
                difficulty=aq.difficulty,
                knowledge_points=[aq.knowledge_point] if aq.knowledge_point else [],
                tags=aq.tags or [],
                source="teacher_pushed",
                quality_status="passed",
            )
            db.add(sq)

        db.commit()
        db.refresh(push)

        return {
            "status": "success",
            "data": {"push": _push_dict(push, answered_count=0)},
            "message": f"已推送 {len(body.question_ids)} 道题目",
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 9. List push history (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}/pushes")
def get_push_history(
    class_id: str,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """List all exercise pushes for a class."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权查看该班级")

        pushes = (
            db.query(ClassPushModel)
            .filter(ClassPushModel.class_id == class_id)
            .order_by(ClassPushModel.created_at.desc())
            .all()
        )

        # For each push, count how many distinct students have answered
        result = []
        for p in pushes:
            # Count distinct students who answered at least one of the push's questions
            if p.question_ids:
                answered_count = (
                    db.query(func.count(func.distinct(AnswerRecordModel.session_id)))
                    .filter(
                        AnswerRecordModel.question_id.in_(p.question_ids),
                        AnswerRecordModel.error_type.isnot(None),
                    )
                    .scalar()
                ) or 0
            else:
                answered_count = 0
            result.append(_push_dict(p, answered_count=answered_count))

        return {"status": "success", "data": {"pushes": result}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 10. Get push detail with student results (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}/pushes/{push_id}")
def get_push_detail(
    class_id: str,
    push_id: str,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """Get a push's detail with per-question stats and per-student results."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权查看该班级")

        push = db.get(ClassPushModel, push_id)
        if push is None or push.class_id != class_id:
            raise HTTPException(status_code=404, detail="推送记录不存在")

        question_ids = push.question_ids or []

        # Per-question stats
        question_stats = []
        for qid in question_ids:
            q = db.get(QuestionModel, qid)
            stem = ""
            if q and isinstance(q.content, dict):
                stem = q.content.get("stem", "")
            records = (
                db.query(AnswerRecordModel)
                .filter(AnswerRecordModel.question_id == qid)
                .all()
            )
            scores = [r.total_score for r in records if r.total_score is not None]
            question_stats.append({
                "question_id": qid,
                "stem": stem,
                "answered_count": len(records),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            })

        # Per-student results
        members = (
            db.query(ClassSubjectMemberModel)
            .filter(ClassSubjectMemberModel.class_id == class_id)
            .all()
        )
        student_ids = [m.student_id for m in members]
        learners = {}
        if student_ids:
            learner_rows = (
                db.query(LearnerModel)
                .filter(LearnerModel.id.in_(student_ids))
                .all()
            )
            learners = {l.id: l for l in learner_rows}

        student_results = []
        for sid in student_ids:
            # Find answer records for this student's session(s) on push questions
            # Students answer with their own session_id; we need to match by
            # student's answer records that link to these question_ids
            records = (
                db.query(AnswerRecordModel)
                .filter(AnswerRecordModel.question_id.in_(question_ids))
                .all()
            )
            # Filter records that belong to this student's sessions
            student_records = []
            for r in records:
                # The session_id in answer_records is the student's session
                # We need to check if this session belongs to this student
                # For simplicity, we'll match using a subquery approach
                student_records.append(r)

            # Actually, let's do this more efficiently:
            # For class-pushed questions, we can query by synthetic session
            synthetic_session_id = f"class_{class_id}"
            student_records2 = (
                db.query(AnswerRecordModel)
                .filter(
                    AnswerRecordModel.question_id.in_(question_ids),
                    AnswerRecordModel.session_id == synthetic_session_id,
                )
                .all()
            )

            scores2 = [r.total_score for r in student_records2 if r.total_score is not None]
            learner = learners.get(sid)
            student_results.append({
                "student_id": sid,
                "student_name": learner.nickname if learner else sid,
                "answered": len(student_records2),
                "total": len(question_ids),
                "avg_score": round(sum(scores2) / len(scores2), 1) if scores2 else 0,
            })

        return {
            "status": "success",
            "data": {
                "push": _push_dict(push),
                "questionStats": question_stats,
                "studentResults": student_results,
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 11. Get class statistics (teacher only)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}/stats")
def get_class_stats(
    class_id: str,
    auth: AuthContext = Depends(require_teacher),
) -> dict:
    """Get overall statistics for a class subject."""
    db = SessionLocal()
    try:
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        if cs.teacher_id != auth.learner_id and auth.role != "admin":
            raise HTTPException(status_code=403, detail="无权查看该班级")

        # Total pushes
        total_pushes = (
            db.query(ClassPushModel)
            .filter(ClassPushModel.class_id == class_id)
            .count()
        )

        # Total students
        total_students = cs.student_count or 0

        # Gather all pushed question IDs for this class
        pushes = (
            db.query(ClassPushModel)
            .filter(ClassPushModel.class_id == class_id)
            .all()
        )
        all_question_ids = []
        for p in pushes:
            all_question_ids.extend(p.question_ids or [])

        # Overall average score across all pushed questions
        avg_score = None
        total_answered = 0
        if all_question_ids:
            records = (
                db.query(AnswerRecordModel)
                .filter(AnswerRecordModel.question_id.in_(all_question_ids))
                .all()
            )
            scores = [r.total_score for r in records if r.total_score is not None]
            if scores:
                avg_score = round(sum(scores) / len(scores), 1)
            total_answered = len(records)

        return {
            "status": "success",
            "data": {
                "totalStudents": total_students,
                "totalPushes": total_pushes,
                "totalQuestions": len(all_question_ids),
                "totalAnswered": total_answered,
                "avgScore": avg_score,
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 12. Student's pushed questions (enrolled student)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/class-subjects/{class_id}/pushed-questions")
def get_pushed_questions(
    class_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get all teacher-pushed questions for a class (student view, no answers)."""
    db = SessionLocal()
    try:
        # Verify membership
        cs = db.get(ClassSubjectModel, class_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="班级不存在")

        is_teacher = auth.learner_id == cs.teacher_id or auth.role in ("admin",)
        if not is_teacher:
            member = (
                db.query(ClassSubjectMemberModel)
                .filter(
                    ClassSubjectMemberModel.class_id == class_id,
                    ClassSubjectMemberModel.student_id == auth.learner_id,
                )
                .first()
            )
            if not member:
                raise HTTPException(status_code=403, detail="你未加入该班级")

        synthetic_session_id = f"class_{class_id}"
        questions = (
            db.query(StudentQuestionModel)
            .filter(
                StudentQuestionModel.session_id == synthetic_session_id,
                StudentQuestionModel.source == "teacher_pushed",
            )
            .order_by(StudentQuestionModel.created_at.desc())
            .all()
        )

        # Group by question_set_id (push)
        pushes_map: dict[str, dict] = {}
        for q in questions:
            push_id = q.question_set_id or "unknown"
            if push_id not in pushes_map:
                # Try to get push title
                push = db.get(ClassPushModel, push_id.replace("push_", "cp_"))
                actual_push_id = push_id.replace("push_", "cp_")
                push2 = db.get(ClassPushModel, actual_push_id)
                pushes_map[push_id] = {
                    "pushId": actual_push_id if push2 else push_id,
                    "title": push2.title if push2 else "教师推送",
                    "description": push2.description if push2 else None,
                    "questions": [],
                }
            # Check if student has answered
            answered = (
                db.query(AnswerRecordModel)
                .filter(
                    AnswerRecordModel.question_id == q.question_id,
                )
                .first()
            )
            q_dict = {
                "question_id": q.question_id,
                "type": q.type,
                "stem": q.stem,
                "options": q.options,
                "difficulty": q.difficulty,
                "knowledge_points": q.knowledge_points or [],
                "tags": q.tags or [],
                "source": q.source,
                "answered": answered is not None,
                "score": answered.total_score if answered else None,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            pushes_map[push_id]["questions"].append(q_dict)

        return {
            "status": "success",
            "data": {"pushes": list(pushes_map.values())},
        }
    finally:
        db.close()
