"""Admin routes — question bank, knowledge graph, system config, user stats.
Protected by require_admin: only teacher/admin roles can access."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import (
    KnowledgePointModel,
    LearnerModel,
    MessageModel,
    QuestionModel,
    SessionModel,
    SystemConfigModel,
)
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ═══════════════════════════════════════════════════════════════════════════
# Auth guard
# ═══════════════════════════════════════════════════════════════════════════


def require_admin(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    if auth.role not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="需要管理员或教师权限")
    return auth


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class QuestionCreate(BaseModel):
    subject: str = ""
    knowledge_point: str = ""
    type: str = "choice"
    difficulty: str = "medium"
    content: dict = Field(default_factory=dict)
    tags: list[str] | None = None


class QuestionUpdate(BaseModel):
    subject: str | None = None
    knowledge_point: str | None = None
    type: str | None = None
    difficulty: str | None = None
    content: dict | None = None
    tags: list[str] | None = None
    status: str | None = None


class KPCreate(BaseModel):
    subject: str = ""
    name: str = ""
    description: str | None = None
    prerequisites: list[str] | None = None
    difficulty: str = "medium"
    importance: int = 5
    chapter: str | None = None
    grade_level: str | None = None


class KPUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prerequisites: list[str] | None = None
    difficulty: str | None = None
    importance: int | None = None
    chapter: str | None = None
    grade_level: str | None = None


class ConfigUpdate(BaseModel):
    value: str
    description: str | None = None
    category: str | None = None


class QuestionReview(BaseModel):
    action: str  # "submit" | "approve" | "reject"
    comment: str | None = None


class QuestionBatchStatus(BaseModel):
    question_ids: list[str]
    action: str  # "submit_review" | "approve" | "reject" | "publish" | "archive"
    comment: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _question_dict(q: QuestionModel) -> dict:
    return {
        "id": q.id,
        "subject": q.subject,
        "knowledge_point": q.knowledge_point,
        "type": q.type,
        "difficulty": q.difficulty,
        "content": q.content,
        "tags": q.tags or [],
        "status": q.status,
        "usage_count": q.usage_count,
        "avg_score": q.avg_score,
        "created_by": q.created_by,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        # Review workflow
        "review_status": q.review_status,
        "review_comment": q.review_comment,
        "reviewed_at": q.reviewed_at.isoformat() if q.reviewed_at else None,
        # Difficulty calibration
        "calibrated_difficulty": q.calibrated_difficulty,
    }


def _kp_dict(kp: KnowledgePointModel) -> dict:
    return {
        "id": kp.id,
        "subject": kp.subject,
        "name": kp.name,
        "description": kp.description,
        "prerequisites": kp.prerequisites or [],
        "difficulty": kp.difficulty,
        "importance": kp.importance,
        "chapter": kp.chapter,
        "grade_level": kp.grade_level,
        "metadata": kp.metadata_ or {},
        "created_at": kp.created_at.isoformat() if kp.created_at else None,
        "updated_at": kp.updated_at.isoformat() if kp.updated_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# QUESTION BANK
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/admin/questions")
def list_questions(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
    knowledge_point: str = Query(default=""),
    type: str = Query(default=""),
    difficulty: str = Query(default=""),
    status: str = Query(default="published"),
    review_status: str = Query(default=""),
    tags: str = Query(default=""),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    db = SessionLocal()
    try:
        q = db.query(QuestionModel)
        if subject:
            q = q.filter(QuestionModel.subject == subject)
        if knowledge_point:
            q = q.filter(QuestionModel.knowledge_point == knowledge_point)
        if type:
            q = q.filter(QuestionModel.type == type)
        if difficulty:
            q = q.filter(QuestionModel.difficulty == difficulty)
        if status:
            q = q.filter(QuestionModel.status == status)
        if review_status:
            q = q.filter(QuestionModel.review_status == review_status)
        if tags:
            # Filter questions that contain ALL specified tags (comma-separated)
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tag_list:
                q = q.filter(QuestionModel.tags.contains(tag))
        if search:
            like = f"%{search}%"
            q = q.filter(QuestionModel.content.contains(search))

        total = q.count()
        rows = q.order_by(QuestionModel.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return {
            "questions": [_question_dict(r) for r in rows],
            "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": max(1, (total + page_size - 1) // page_size)},
        }
    finally:
        db.close()


@router.post("/admin/questions")
def create_question(body: QuestionCreate, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        q = QuestionModel(
            id=f"q_{uuid.uuid4().hex[:12]}",
            subject=body.subject,
            knowledge_point=body.knowledge_point,
            type=body.type,
            difficulty=body.difficulty,
            content=body.content,
            tags=body.tags or [],
            created_by=auth.learner_id,
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        return {"question": _question_dict(q)}
    finally:
        db.close()


@router.post("/admin/questions/batch")
def batch_import(body: list[QuestionCreate], auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        created = 0
        for item in body:
            q = QuestionModel(
                id=f"q_{uuid.uuid4().hex[:12]}",
                subject=item.subject,
                knowledge_point=item.knowledge_point,
                type=item.type,
                difficulty=item.difficulty,
                content=item.content,
                tags=item.tags or [],
                created_by=auth.learner_id,
            )
            db.add(q)
            created += 1
        db.commit()
        return {"ok": True, "imported": created}
    finally:
        db.close()


@router.get("/admin/questions/export")
def export_questions(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
    status: str = Query(default="published"),
) -> dict:
    db = SessionLocal()
    try:
        q = db.query(QuestionModel).filter(QuestionModel.status == status)
        if subject:
            q = q.filter(QuestionModel.subject == subject)
        return {"questions": [_question_dict(r) for r in q.all()]}
    finally:
        db.close()


# ── Question review workflow ─────────────────────────────────────────


@router.post("/admin/questions/batch-review")
def batch_review_questions(body: QuestionBatchStatus, auth: AuthContext = Depends(require_admin)) -> dict:
    """Batch review/status-change for multiple questions."""
    db = SessionLocal()
    try:
        updated = 0
        now = datetime.now(timezone.utc)
        for qid in body.question_ids:
            q = db.get(QuestionModel, qid)
            if q is None:
                continue
            if body.action == "submit_review":
                q.review_status = "pending_review"
            elif body.action == "approve":
                q.review_status = "approved"
                q.status = "published"
                q.review_comment = body.comment or q.review_comment
                q.reviewed_by = auth.learner_id
                q.reviewed_at = now
            elif body.action == "reject":
                q.review_status = "rejected"
                q.status = "draft"
                q.review_comment = body.comment or q.review_comment
                q.reviewed_by = auth.learner_id
                q.reviewed_at = now
            elif body.action == "publish":
                q.status = "published"
            elif body.action == "archive":
                q.status = "archived"
            updated += 1
        db.commit()
        return {"ok": True, "updated": updated}
    finally:
        db.close()


# ── Tag management ────────────────────────────────────────────────────


@router.get("/admin/questions/tags")
def list_question_tags(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
) -> dict:
    """Return all unique tags across questions with usage counts."""
    db = SessionLocal()
    try:
        q = db.query(QuestionModel)
        if subject:
            q = q.filter(QuestionModel.subject == subject)
        rows = q.all()

        tag_counts: dict[str, dict] = {}
        for r in rows:
            for tag in (r.tags or []):
                tag = tag.strip()
                if not tag:
                    continue
                if tag not in tag_counts:
                    tag_counts[tag] = {"name": tag, "count": 0, "subjects": []}
                tag_counts[tag]["count"] += 1
                if r.subject and r.subject not in tag_counts[tag]["subjects"]:
                    tag_counts[tag]["subjects"].append(r.subject)

        tags_list = sorted(tag_counts.values(), key=lambda t: -t["count"])
        return {"tags": tags_list}
    finally:
        db.close()


# ── Difficulty calibration ────────────────────────────────────────────


@router.post("/admin/questions/calibrate-difficulty")
def calibrate_difficulty(auth: AuthContext = Depends(require_admin)) -> dict:
    """Recalibrate question difficulty based on AnswerRecord student performance.

    For each published question, computes actual accuracy from AnswerRecord data
    and maps it to a calibrated_difficulty value (0.0-1.0 scale).
    """
    db = SessionLocal()
    try:
        from app.db.models import AnswerRecordModel, StudentQuestionModel

        all_questions = db.query(QuestionModel).all()
        calibrated = 0
        skipped = 0

        for admin_q in all_questions:
            # Find student questions linked to this admin question
            student_qs = db.query(StudentQuestionModel).filter(
                StudentQuestionModel.source_question_id == admin_q.id
            ).all()
            student_q_ids = [sq.question_id for sq in student_qs]

            if not student_q_ids:
                skipped += 1
                continue

            # Get all answer records for these student questions
            records = db.query(AnswerRecordModel).filter(
                AnswerRecordModel.question_id.in_(student_q_ids),
                AnswerRecordModel.total_score.isnot(None),
            ).all()

            if not records:
                skipped += 1
                continue

            # Compute average accuracy
            total_correct = sum(1 for r in records if (r.total_score or 0) >= 60)
            accuracy = total_correct / len(records)

            # Map accuracy to calibrated difficulty (0.0 easy - 1.0 hard)
            if accuracy >= 0.8:
                calibrated_val = 0.2
            elif accuracy >= 0.6:
                calibrated_val = 0.5
            elif accuracy >= 0.4:
                calibrated_val = 0.7
            else:
                calibrated_val = 0.9

            admin_q.calibrated_difficulty = calibrated_val
            # Also update the text difficulty label
            if calibrated_val <= 0.3:
                admin_q.difficulty = "easy"
            elif calibrated_val <= 0.6:
                admin_q.difficulty = "medium"
            elif calibrated_val <= 0.8:
                admin_q.difficulty = "hard"
            else:
                admin_q.difficulty = "challenge"

            calibrated += 1

        db.commit()
        return {"calibrated": calibrated, "skipped": skipped}
    finally:
        db.close()


# ── Question detail / review (parameterised — MUST be after static paths) ─


@router.get("/admin/questions/{question_id}")
def get_question(question_id: str, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        q = db.get(QuestionModel, question_id)
        if q is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        return {"question": _question_dict(q)}
    finally:
        db.close()


@router.patch("/admin/questions/{question_id}")
def update_question(question_id: str, body: QuestionUpdate, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        q = db.get(QuestionModel, question_id)
        if q is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        updates = body.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(q, key, value)
        db.commit()
        db.refresh(q)
        return {"question": _question_dict(q)}
    finally:
        db.close()


@router.delete("/admin/questions/{question_id}")
def archive_question(question_id: str, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        q = db.get(QuestionModel, question_id)
        if q is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        q.status = "archived"
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/admin/questions/{question_id}/review")
def review_question(question_id: str, body: QuestionReview, auth: AuthContext = Depends(require_admin)) -> dict:
    """Submit a question for review, approve, or reject it.

    Workflow:
    - submit: sets review_status to pending_review (status stays draft)
    - approve: sets review_status to approved, status to published
    - reject: sets review_status to rejected, status back to draft
    """
    db = SessionLocal()
    try:
        q = db.get(QuestionModel, question_id)
        if q is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        valid_actions = {"submit", "approve", "reject"}
        if body.action not in valid_actions:
            raise HTTPException(status_code=400, detail=f"无效操作，可选值: {', '.join(valid_actions)}")

        now = datetime.now(timezone.utc)

        if body.action == "submit":
            q.review_status = "pending_review"
            q.status = "draft"
        elif body.action == "approve":
            q.review_status = "approved"
            q.status = "published"
            q.review_comment = body.comment or q.review_comment
            q.reviewed_by = auth.learner_id
            q.reviewed_at = now
        elif body.action == "reject":
            q.review_status = "rejected"
            q.status = "draft"
            q.review_comment = body.comment or q.review_comment
            q.reviewed_by = auth.learner_id
            q.reviewed_at = now

        db.commit()
        db.refresh(q)
        return {"question": _question_dict(q)}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# MODEL EFFECT MONITORING
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/admin/monitor/overview")
def monitor_overview(auth: AuthContext = Depends(require_admin)) -> dict:
    """Model monitoring overview — key metrics for the dashboard."""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        from app.db.models import AnswerRecordModel, StudentQuestionModel

        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total_answered = db.query(AnswerRecordModel).count()
        questions_today = db.query(StudentQuestionModel).filter(
            StudentQuestionModel.created_at >= today
        ).count()

        # Overall accuracy
        all_records = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.total_score.isnot(None)
        ).all()
        total_with_score = len(all_records)
        if total_with_score > 0:
            total_score_sum = sum(r.total_score or 0 for r in all_records)
            overall_accuracy = round(total_score_sum / total_with_score, 1)
        else:
            overall_accuracy = 0.0

        # Daily answer count trend (last 30 days)
        since = now - timedelta(days=30)
        daily_rows = (
            db.query(
                func.date(AnswerRecordModel.created_at).label("day"),
                func.count(AnswerRecordModel.id).label("count"),
            )
            .filter(AnswerRecordModel.created_at >= since)
            .group_by("day")
            .order_by("day")
            .all()
        )
        daily_answer_count = [{"date": str(r.day), "count": r.count} for r in daily_rows]

        # Accuracy trend
        accuracy_rows = (
            db.query(
                func.date(AnswerRecordModel.created_at).label("day"),
                func.avg(AnswerRecordModel.total_score).label("avg_score"),
            )
            .filter(
                AnswerRecordModel.created_at >= since,
                AnswerRecordModel.total_score.isnot(None),
            )
            .group_by("day")
            .order_by("day")
            .all()
        )
        accuracy_trend = [{"date": str(r.day), "accuracy": round(float(r.avg_score or 0), 1)} for r in accuracy_rows]

        # Subject breakdown
        subject_qs = db.query(StudentQuestionModel).all()
        subject_map: dict[str, dict] = {}
        for sq in subject_qs:
            sid = sq.session_id or "unknown"
            # Infer subject from knowledge_points or tags
            subj = "未分类"
            if sq.knowledge_points:
                kps = sq.knowledge_points
                if isinstance(kps, list) and len(kps) > 0:
                    subj = str(kps[0])
                elif isinstance(kps, dict):
                    subj = str(list(kps.keys())[0]) if kps else "未分类"
            if subj not in subject_map:
                subject_map[subj] = {"subject": subj, "count": 0, "total_score": 0}
            subject_map[subj]["count"] += 1
            # Get score for this question
            answers = db.query(AnswerRecordModel).filter(
                AnswerRecordModel.question_id == sq.question_id,
                AnswerRecordModel.total_score.isnot(None),
            ).all()
            if answers:
                subject_map[subj]["total_score"] += sum(a.total_score or 0 for a in answers) / len(answers)

        subject_breakdown = []
        for s in subject_map.values():
            if s["count"] > 0:
                s["accuracy"] = round(s["total_score"], 1)
                del s["total_score"]
                subject_breakdown.append(s)

        return {
            "total_answered": total_answered,
            "active_students": db.query(AnswerRecordModel.session_id).distinct().count(),
            "overall_accuracy": overall_accuracy,
            "questions_generated_today": questions_today,
            "daily_answer_count": daily_answer_count,
            "accuracy_trend": accuracy_trend,
            "subject_breakdown": subject_breakdown,
        }
    finally:
        db.close()


@router.get("/admin/monitor/diagnostic-accuracy")
def monitor_diagnostic_accuracy(auth: AuthContext = Depends(require_admin)) -> dict:
    """Diagnostic accuracy — overall + by subject + trend."""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        from app.db.models import AnswerRecordModel

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=30)

        all_records = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.total_score.isnot(None)
        ).all()

        total = len(all_records)
        if total == 0:
            return {
                "total_diagnoses": 0,
                "avg_accuracy": 0.0,
                "accuracy_distribution": [],
                "trend": [],
            }

        avg_accuracy = round(sum(r.total_score or 0 for r in all_records) / total, 1)

        # Distribution
        ranges = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for r in all_records:
            s = r.total_score or 0
            if s < 20: ranges["0-20"] += 1
            elif s < 40: ranges["20-40"] += 1
            elif s < 60: ranges["40-60"] += 1
            elif s < 80: ranges["60-80"] += 1
            else: ranges["80-100"] += 1
        distribution = [{"range": k, "count": v} for k, v in ranges.items()]

        # Trend
        trend_rows = (
            db.query(
                func.date(AnswerRecordModel.created_at).label("day"),
                func.avg(AnswerRecordModel.total_score).label("avg_score"),
                func.count(AnswerRecordModel.id).label("count"),
            )
            .filter(
                AnswerRecordModel.created_at >= since,
                AnswerRecordModel.total_score.isnot(None),
            )
            .group_by("day")
            .order_by("day")
            .all()
        )
        trend = [{"date": str(r.day), "avg_accuracy": round(float(r.avg_score or 0), 1), "count": r.count} for r in trend_rows]

        return {
            "total_diagnoses": total,
            "avg_accuracy": avg_accuracy,
            "accuracy_distribution": distribution,
            "trend": trend,
        }
    finally:
        db.close()


@router.get("/admin/monitor/question-quality")
def monitor_question_quality(auth: AuthContext = Depends(require_admin)) -> dict:
    """Question quality metrics — score distribution, type stats, weak questions."""
    db = SessionLocal()
    try:
        from app.db.models import AnswerRecordModel, StudentQuestionModel

        all_qs = db.query(StudentQuestionModel).all()
        total_questions = len(all_qs)

        if total_questions == 0:
            return {
                "total_questions": 0,
                "avg_score": 0.0,
                "score_distribution": [],
                "difficulty_calibration": [],
                "type_distribution": [],
                "top_weak_questions": [],
            }

        # Avg score across all questions (each question's avg from its answers)
        q_scores = []
        type_stats: dict[str, dict] = {}
        for sq in all_qs:
            answers = db.query(AnswerRecordModel).filter(
                AnswerRecordModel.question_id == sq.question_id,
                AnswerRecordModel.total_score.isnot(None),
            ).all()
            if answers:
                avg = sum(a.total_score or 0 for a in answers) / len(answers)
                q_scores.append(avg)

            qtype = sq.type or "unknown"
            if qtype not in type_stats:
                type_stats[qtype] = {"type": qtype, "count": 0, "total_score": 0}
            type_stats[qtype]["count"] += 1
            if answers:
                type_stats[qtype]["total_score"] += sum(a.total_score or 0 for a in answers) / len(answers)

        avg_q_score = round(sum(q_scores) / len(q_scores), 1) if q_scores else 0.0

        # Score distribution
        ranges = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
        for s in q_scores:
            if s < 25: ranges["0-25"] += 1
            elif s < 50: ranges["25-50"] += 1
            elif s < 75: ranges["50-75"] += 1
            else: ranges["75-100"] += 1
        score_dist = [{"range": k, "count": v} for k, v in ranges.items()]

        # Type distribution with avg score
        type_dist = []
        for t in type_stats.values():
            if t["count"] > 0:
                type_dist.append({
                    "type": t["type"],
                    "count": t["count"],
                    "avg_score": round(t["total_score"], 1),
                })
                del t["total_score"]

        # Difficulty calibration comparison
        diff_map = {"easy": 75, "medium": 50, "hard": 25}
        diff_actual: dict[str, list[float]] = {"easy": [], "medium": [], "hard": []}
        for sq in all_qs:
            answers = db.query(AnswerRecordModel).filter(
                AnswerRecordModel.question_id == sq.question_id,
                AnswerRecordModel.total_score.isnot(None),
            ).all()
            if answers and sq.difficulty in diff_actual:
                avg = sum(a.total_score or 0 for a in answers) / len(answers)
                diff_actual[sq.difficulty].append(avg)

        calibration = []
        for diff, expected in diff_map.items():
            actual_list = diff_actual[diff]
            actual = round(sum(actual_list) / len(actual_list), 1) if actual_list else 0.0
            _diff_labels = {"easy": "简单", "medium": "中等", "hard": "困难", "challenge": "挑战"}
            calibration.append({"label": _diff_labels.get(diff, diff), "expected": expected, "actual": actual})

        # Top weak questions (most attempts, lowest avg score)
        weak_qs = []
        for sq in all_qs:
            answers = db.query(AnswerRecordModel).filter(
                AnswerRecordModel.question_id == sq.question_id,
                AnswerRecordModel.total_score.isnot(None),
            ).all()
            if answers:
                avg = sum(a.total_score or 0 for a in answers) / len(answers)
                weak_qs.append({
                    "question_id": sq.question_id,
                    "stem": sq.stem[:60] + ("..." if len(sq.stem or "") > 60 else ""),
                    "avg_score": round(avg, 1),
                    "attempt_count": len(answers),
                })
        weak_qs.sort(key=lambda x: x["avg_score"])
        top_weak = weak_qs[:10]

        return {
            "total_questions": total_questions,
            "avg_score": avg_q_score,
            "score_distribution": score_dist,
            "difficulty_calibration": calibration,
            "type_distribution": type_dist,
            "top_weak_questions": top_weak,
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GRAPH
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/admin/knowledge")
def list_knowledge_points(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
    chapter: str = Query(default=""),
    grade_level: str = Query(default=""),
) -> dict:
    db = SessionLocal()
    try:
        q = db.query(KnowledgePointModel)
        if subject:
            q = q.filter(KnowledgePointModel.subject == subject)
        if chapter:
            q = q.filter(KnowledgePointModel.chapter == chapter)
        if grade_level:
            q = q.filter(KnowledgePointModel.grade_level == grade_level)
        rows = q.order_by(KnowledgePointModel.chapter, KnowledgePointModel.name).all()
        return {"knowledge_points": [_kp_dict(r) for r in rows]}
    finally:
        db.close()


@router.get("/admin/knowledge/graph")
def get_knowledge_graph(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
) -> dict:
    """Return full DAG: nodes + edges for frontend visualization."""
    db = SessionLocal()
    try:
        q = db.query(KnowledgePointModel)
        if subject:
            q = q.filter(KnowledgePointModel.subject == subject)
        rows = q.all()

        node_ids = {r.id for r in rows}
        nodes = []
        edges = []
        for r in rows:
            nodes.append({"id": r.id, "name": r.name, "difficulty": r.difficulty, "importance": r.importance, "chapter": r.chapter})
            for pre in (r.prerequisites or []):
                if pre in node_ids:
                    edges.append({"source": pre, "target": r.id})

        return {"nodes": nodes, "edges": edges}
    finally:
        db.close()


@router.post("/admin/knowledge")
def create_knowledge_point(body: KPCreate, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        kp = KnowledgePointModel(
            id=f"kp_{uuid.uuid4().hex[:12]}",
            subject=body.subject,
            name=body.name,
            description=body.description,
            prerequisites=body.prerequisites or [],
            difficulty=body.difficulty,
            importance=body.importance,
            chapter=body.chapter,
            grade_level=body.grade_level,
        )
        db.add(kp)
        db.commit()
        db.refresh(kp)
        return {"knowledge_point": _kp_dict(kp)}
    finally:
        db.close()


@router.patch("/admin/knowledge/{kp_id}")
def update_knowledge_point(kp_id: str, body: KPUpdate, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        kp = db.get(KnowledgePointModel, kp_id)
        if kp is None:
            raise HTTPException(status_code=404, detail="知识点不存在")
        updates = body.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(kp, key, value)
        db.commit()
        db.refresh(kp)
        return {"knowledge_point": _kp_dict(kp)}
    finally:
        db.close()


@router.delete("/admin/knowledge/{kp_id}")
def delete_knowledge_point(kp_id: str, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        kp = db.get(KnowledgePointModel, kp_id)
        if kp is None:
            raise HTTPException(status_code=404, detail="知识点不存在")
        # Remove references from other KPs that list this one as prerequisite
        for other in db.query(KnowledgePointModel).all():
            preqs = list(other.prerequisites or [])
            if kp_id in preqs:
                preqs.remove(kp_id)
                other.prerequisites = preqs
        db.delete(kp)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/admin/knowledge/validate")
def validate_graph(
    auth: AuthContext = Depends(require_admin),
    subject: str = Query(default=""),
) -> dict:
    """Check DAG for cycles (topological sort)."""
    db = SessionLocal()
    try:
        q = db.query(KnowledgePointModel)
        if subject:
            q = q.filter(KnowledgePointModel.subject == subject)
        rows = q.all()

        node_ids = {r.id for r in rows}
        adj: dict[str, list[str]] = {r.id: [] for r in rows}
        in_degree: dict[str, int] = {r.id: 0 for r in rows}

        for r in rows:
            for pre in (r.prerequisites or []):
                if pre in node_ids:
                    adj[pre].append(r.id)
                    in_degree[r.id] += 1

        # Kahn's algorithm
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes = []
        while queue:
            node = queue.pop(0)
            sorted_nodes.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        has_cycle = len(sorted_nodes) != len(rows)
        orphans = [nid for nid, deg in in_degree.items() if deg > 0] if has_cycle else []

        return {
            "valid": not has_cycle,
            "total_nodes": len(rows),
            "has_cycle": has_cycle,
            "cycle_nodes": orphans,
            "message": "DAG 结构正常" if not has_cycle else f"检测到环，涉及 {len(orphans)} 个节点",
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM CONFIG
# ═══════════════════════════════════════════════════════════════════════════


def _seed_config(db) -> None:
    """Seed default config entries from settings if the table is empty."""
    existing = db.query(SystemConfigModel).count()
    if existing > 0:
        return
    from app.config import settings

    defaults = [
        ("llm_provider", settings.llm_provider, "LLM provider name", "llm"),
        ("llm_model", settings.llm_model, "LLM model identifier", "llm"),
        ("llm_temperature", str(settings.llm_temperature), "LLM sampling temperature", "llm"),
        ("agent_timeout", str(settings.agent_timeout), "Per-agent timeout seconds", "agent"),
        ("llm_retry_count", str(settings.llm_retry_count), "LLM call retry count", "agent"),
        ("rag_enabled", str(settings.rag_enabled).lower(), "Enable RAG knowledge base", "feature"),
        ("enable_mock_fallback", str(settings.enable_mock_fallback).lower(), "Use mock demo data", "feature"),
    ]
    for key, value, desc, cat in defaults:
        db.add(SystemConfigModel(key=key, value=value, description=desc, category=cat))
    db.commit()


@router.get("/admin/config")
def list_config(auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        _seed_config(db)
        rows = db.query(SystemConfigModel).order_by(SystemConfigModel.category, SystemConfigModel.key).all()
        configs = {}
        for r in rows:
            cat = r.category or "general"
            configs.setdefault(cat, []).append({
                "key": r.key, "value": r.value, "description": r.description,
                "category": cat, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return {"configs": configs}
    finally:
        db.close()


@router.delete("/admin/config/{key}")
def delete_config(key: str, auth: AuthContext = Depends(require_admin)) -> dict:
    """Delete a system configuration entry."""
    db = SessionLocal()
    try:
        cfg = db.get(SystemConfigModel, key)
        if cfg is None:
            raise HTTPException(status_code=404, detail="配置项不存在")
        db.delete(cfg)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.patch("/admin/config/{key}")
def update_config(key: str, body: ConfigUpdate, auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        cfg = db.get(SystemConfigModel, key)
        if cfg is None:
            # Create new config entry
            cfg = SystemConfigModel(key=key, value=body.value, description=body.description or "", category=body.category or "general", updated_by=auth.learner_id)
            db.add(cfg)
        else:
            cfg.value = body.value
            if body.description is not None:
                cfg.description = body.description
            if body.category is not None:
                cfg.category = body.category
            cfg.updated_by = auth.learner_id
        db.commit()
        db.refresh(cfg)
        return {"config": {"key": cfg.key, "value": cfg.value, "description": cfg.description, "category": cfg.category}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# USER STATS
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/admin/stats/overview")
def stats_overview(auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        total_learners = db.query(LearnerModel).count()
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        active_today = db.query(LearnerModel).filter(LearnerModel.updated_at >= today).count()
        total_sessions = db.query(SessionModel).count()
        total_messages = db.query(MessageModel).filter(MessageModel.role == "user").count()

        return {
            "total_learners": total_learners,
            "active_today": active_today,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
        }
    finally:
        db.close()


@router.get("/admin/stats/users")
def stats_users(
    auth: AuthContext = Depends(require_admin),
    sort_by: str = Query(default="updated_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    db = SessionLocal()
    try:
        q = db.query(LearnerModel)
        if sort_by == "updated_at":
            q = q.order_by(LearnerModel.updated_at.desc())
        elif sort_by == "created_at":
            q = q.order_by(LearnerModel.created_at.desc())

        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()

        users = []
        for learner in rows:
            session_count = db.query(SessionModel).filter(SessionModel.learner_id == learner.id).count()
            msg_count = db.query(MessageModel).filter(MessageModel.session.has(learner_id=learner.id)).count()
            users.append({
                "id": learner.id,
                "nickname": learner.nickname,
                "role": learner.role,
                "grade": learner.grade,
                "session_count": session_count,
                "message_count": msg_count,
                "last_active": learner.updated_at.isoformat() if learner.updated_at else None,
            })

        return {"users": users, "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": max(1, (total + page_size - 1) // page_size)}}
    finally:
        db.close()


@router.get("/admin/stats/daily")
def stats_daily(
    auth: AuthContext = Depends(require_admin),
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    db = SessionLocal()
    try:
        from sqlalchemy import func

        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(
                func.date(MessageModel.created_at).label("day"),
                func.count(MessageModel.id).label("count"),
            )
            .filter(MessageModel.role == "user", MessageModel.created_at >= since)
            .group_by("day")
            .order_by("day")
            .all()
        )

        return {"trend": [{"date": str(r.day), "count": r.count} for r in rows]}
    finally:
        db.close()


@router.get("/admin/stats/subjects")
def stats_subjects(auth: AuthContext = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        from sqlalchemy import func

        rows = (
            db.query(SessionModel.subject_id, func.count(SessionModel.id))
            .filter(SessionModel.subject_id.isnot(None))
            .group_by(SessionModel.subject_id)
            .all()
        )
        return {"subjects": [{"subject_id": r[0] or "unknown", "count": r[1]} for r in rows]}
    finally:
        db.close()
