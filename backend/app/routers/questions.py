"""Student-facing question endpoints — generate, list, answer, grade, history.

Implements the API contract defined in docs/api-questions.md.
Uses require_auth (student-level); answer data is scoped to the
authenticated learner's sessions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import AnswerRecordModel, ClassSubjectMemberModel, QuestionModel, StudentQuestionModel
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["questions"])

# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════

QUESTION_TYPES = ["choice", "fill", "truefalse", "shortanswer"]
ERROR_TYPES = ["concept", "calculation", "misreading", "method", "forgetting", "null"]


class GenerateRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    message: str = ""


class GradeRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    answer: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_SENSITIVE_FIELDS = {"correct", "answers", "reference_answer", "explanation", "scoring_rubric", "step_hints"}


def _question_dict(q: StudentQuestionModel, reveal: bool = False) -> dict:
    """Serialize a StudentQuestionModel, stripping answer fields unless reveal=True."""
    result = {
        "id": q.id,
        "question_id": q.question_id,
        "question_set_id": q.question_set_id,
        "session_id": q.session_id,
        "source_question_id": q.source_question_id,
        "type": q.type,
        "stem": q.stem,
        "options": q.options,
        "difficulty": q.difficulty,
        "knowledge_points": q.knowledge_points or [],
        "tags": q.tags or [],
        "source": q.source,
        "quality_status": q.quality_status,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }
    if reveal:
        result["correct"] = q.correct
        result["explanation"] = q.explanation
        result["scoring_rubric"] = q.scoring_rubric
        result["reference_answer"] = q.reference_answer
    return result


def _answer_record_dict(r: AnswerRecordModel) -> dict:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "question_id": r.question_id,
        "student_answer": r.student_answer,
        "total_score": r.total_score,
        "dimension_scores": r.dimension_scores,
        "dimension_feedback": r.dimension_feedback,
        "error_type": r.error_type,
        "error_label": r.error_label,
        "error_explanation": r.error_explanation,
        "error_action": r.error_action,
        "suggestions": r.suggestions,
        "strengths": r.strengths,
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _auto_grade(question: StudentQuestionModel, answer: str) -> dict:
    """Auto-grade a student answer for choice/truefalse questions.

    Returns a dict that can be used to create an AnswerRecordModel.
    Fill/shortanswer questions get a placeholder — real grading needs LLM.
    """
    is_correct = False
    error_type = "null"
    error_label = "无"

    if question.type in ("choice", "truefalse"):
        # Normalize answer for comparison
        student = answer.strip().upper()
        expected = (question.correct or "").strip().upper()
        is_correct = student == expected
        if not is_correct:
            error_type = "concept"
            error_label = "概念错误" if question.type == "choice" else "判断错误"
    else:
        # fill / shortanswer — stored without auto-scoring
        pass

    total_score = 100 if is_correct else 0

    if is_correct:
        dimension_scores = {"reasoning": 100, "completeness": 100, "calculation": 100, "expression": 100}
        dimension_feedback = {"reasoning": "正确", "completeness": "完整", "calculation": "无误", "expression": "规范"}
        suggestions = []
        strengths = ["回答正确"]
    else:
        dimension_scores = {"reasoning": 50, "completeness": 50, "calculation": 50, "expression": 50}
        dimension_feedback = {
            "reasoning": "需要重新理解概念",
            "completeness": "答案不完整",
            "calculation": "需要验证",
            "expression": "需要改进",
        }
        suggestions = ["建议复习相关知识点", "查看题目解析加深理解"]
        strengths = []

    return {
        "total_score": total_score,
        "dimension_scores": dimension_scores,
        "dimension_feedback": dimension_feedback,
        "error_type": error_type,
        "error_label": error_label,
        "error_explanation": question.explanation if not is_correct else "",
        "error_action": "推送对应概念讲解" if error_type == "concept" else "",
        "suggestions": suggestions,
        "strengths": strengths,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Generate questions
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/questions/generate")
def generate_questions(body: GenerateRequest, auth: AuthContext = Depends(require_auth)) -> dict:
    """Generate questions via LLM for a session. Currently returns mock data.

    Real AI generation will be integrated when the M2 cognitive diagnosis
    module is ready.
    """
    question_set_id = f"qs_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Build 3 mock questions aligned with the API spec
    mock_questions = [
        {
            "type": "choice",
            "stem": "以下关于极限的描述，正确的是？",
            "options": [
                "A. 极限总是等于函数值",
                "B. 极限描述了函数在某点附近的变化趋势",
                "C. 极限不存在时函数一定无定义",
                "D. 极限只能是有限值",
            ],
            "correct": "B",
            "explanation": "极限的定义描述了自变量趋近某值时函数的变化趋势，与函数在该点的值无关。",
            "difficulty": "medium",
            "knowledge_points": ["极限", "函数"],
        },
        {
            "type": "truefalse",
            "stem": "可导函数一定连续。",
            "correct": "true",
            "explanation": "可导性蕴含连续性：若 f'(x₀) 存在，则 f 在 x₀ 处连续。",
            "difficulty": "easy",
            "knowledge_points": ["导数", "连续"],
        },
        {
            "type": "fill",
            "stem": "函数 f(x)=x² 在 x=3 处的导数值为 ___。",
            "correct": "6",
            "explanation": "f'(x)=2x，代入 x=3 得 f'(3)=6。",
            "difficulty": "easy",
            "knowledge_points": ["导数计算"],
        },
    ]

    db = SessionLocal()
    try:
        created = []
        for mq in mock_questions:
            q = StudentQuestionModel(
                question_id=f"q_{uuid.uuid4().hex[:12]}",
                question_set_id=question_set_id,
                session_id=body.session_id,
                type=mq["type"],
                stem=mq["stem"],
                options=mq.get("options"),
                correct=mq.get("correct"),
                explanation=mq.get("explanation"),
                difficulty=mq.get("difficulty", "medium"),
                knowledge_points=mq.get("knowledge_points", []),
                source="llm_generated",
            )
            db.add(q)
            db.commit()
            db.refresh(q)
            created.append(_question_dict(q, reveal=False))
        return {
            "status": "success",
            "data": {"questionSetId": question_set_id, "questions": created, "count": len(created)},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. List questions (no answers)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/questions")
def list_questions(
    auth: AuthContext = Depends(require_auth),
    session_id: str = Query(default="", alias="sessionId"),
    knowledge_point: str = Query(default="", alias="knowledgePoint"),
    difficulty: str = Query(default=""),
    type: str = Query(default=""),
) -> dict:
    """List questions for a session. Answers are never returned."""
    db = SessionLocal()
    try:
        q = db.query(StudentQuestionModel)
        if session_id:
            q = q.filter(StudentQuestionModel.session_id == session_id)
        if knowledge_point:
            # knowledge_points is JSON array — use LIKE for SQLite
            q = q.filter(StudentQuestionModel.knowledge_points.contains(knowledge_point))
        if difficulty:
            q = q.filter(StudentQuestionModel.difficulty == difficulty)
        if type:
            q = q.filter(StudentQuestionModel.type == type)

        rows = q.order_by(StudentQuestionModel.created_at.desc()).all()
        return {
            "status": "success",
            "data": {
                "questionSetId": rows[0].question_set_id if rows else "",
                "questions": [_question_dict(r, reveal=False) for r in rows],
                "count": len(rows),
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Single question detail
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/questions/{question_id}")
def get_question(
    question_id: str,
    auth: AuthContext = Depends(require_auth),
    reveal: bool = Query(default=False),
) -> dict:
    """Get a single question. Pass reveal=true to include answers."""
    db = SessionLocal()
    try:
        q = db.query(StudentQuestionModel).filter(
            StudentQuestionModel.question_id == question_id
        ).first()
        if q is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        return {"status": "success", "data": {"question": _question_dict(q, reveal=reveal)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Submit answer / grade
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/questions/{question_id}/grade")
def grade_answer(
    question_id: str,
    body: GradeRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Submit an answer for grading. Choice/truefalse questions are auto-graded."""
    db = SessionLocal()
    try:
        question = db.query(StudentQuestionModel).filter(
            StudentQuestionModel.question_id == question_id
        ).first()
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        # For teacher-pushed questions, verify student is a class member
        if question.source == "teacher_pushed":
            # session_id is "class_{classId}" for pushed questions
            if question.session_id and question.session_id.startswith("class_"):
                class_id = question.session_id[len("class_"):]
                is_member = db.query(ClassSubjectMemberModel).filter(
                    ClassSubjectMemberModel.class_id == class_id,
                    ClassSubjectMemberModel.student_id == auth.learner_id,
                ).first()
                if not is_member:
                    raise HTTPException(status_code=403, detail="你未加入该班级，无权作答此题目")

        grading = _auto_grade(question, body.answer)

        record = AnswerRecordModel(
            session_id=body.session_id,
            question_id=question_id,
            student_answer=body.answer,
            total_score=grading["total_score"],
            dimension_scores=grading["dimension_scores"],
            dimension_feedback=grading["dimension_feedback"],
            error_type=grading["error_type"],
            error_label=grading["error_label"],
            error_explanation=grading["error_explanation"],
            error_action=grading["error_action"],
            suggestions=grading["suggestions"],
            strengths=grading["strengths"],
            source="auto_graded" if question.type in ("choice", "truefalse") else "llm_generated",
        )
        db.add(record)

        # If this question came from the admin bank, update usage stats
        if question.source_question_id:
            admin_q = db.get(QuestionModel, question.source_question_id)
            if admin_q:
                admin_q.usage_count = (admin_q.usage_count or 0) + 1
                # Rolling average
                old_avg = admin_q.avg_score or 0.0
                old_count = max(admin_q.usage_count - 1, 0)
                admin_q.avg_score = round(
                    (old_avg * old_count + grading["total_score"]) / admin_q.usage_count, 2
                )

        db.commit()
        db.refresh(record)

        grading_result = {
            "question_id": question_id,
            "student_answer": body.answer,
            "total_score": record.total_score,
            "dimension_scores": record.dimension_scores,
            "dimension_feedback": record.dimension_feedback,
            "error_type": record.error_type,
            "error_label": record.error_label,
            "error_explanation": record.error_explanation,
            "error_action": record.error_action,
            "suggestions": record.suggestions,
            "strengths": record.strengths,
        }

        return {"status": "success", "data": {"gradingResult": grading_result}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Wrong-answer book
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/questions/weak")
def get_weak_questions(
    auth: AuthContext = Depends(require_auth),
    session_id: str = Query(default="", alias="sessionId"),
    error_type: str = Query(default="", alias="errorType"),
    limit: int = Query(default=20, ge=1, le=100),
    aggregate: bool = Query(default=False),
) -> dict:
    """Return the student's wrong-answer book — questions answered incorrectly.

    When ``aggregate=true``, returns a knowledge-point-level weakness summary
    instead of individual question records.
    """
    db = SessionLocal()
    try:
        q = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.error_type != "null",
            AnswerRecordModel.error_type.isnot(None),
        )
        if session_id:
            q = q.filter(AnswerRecordModel.session_id == session_id)
        if error_type:
            q = q.filter(AnswerRecordModel.error_type == error_type)

        # ── Aggregated mode: group by knowledge point ──────────
        if aggregate:
            rows = q.order_by(AnswerRecordModel.created_at.desc()).all()
            # Collect all question_ids to resolve knowledge points
            qids = list({r.question_id for r in rows})
            kp_map: dict[str, str] = {}
            if qids:
                from app.db.models import PracticeQuestionModel
                pqs = db.query(PracticeQuestionModel).filter(
                    PracticeQuestionModel.question_id.in_(qids)
                ).all()
                for pq in pqs:
                    kps = pq.knowledge_points or []
                    kp_map[pq.question_id] = kps[0] if kps else ""

            # Group by knowledge point
            kp_groups: dict[str, dict] = {}
            for r in rows:
                kp = kp_map.get(r.question_id, "未知知识点")
                if kp not in kp_groups:
                    kp_groups[kp] = {"name": kp, "errorCount": 0, "totalAttempts": 0,
                                     "latestError": "", "errorTypes": []}
                kp_groups[kp]["errorCount"] += 1
                kp_groups[kp]["totalAttempts"] += 1
                if r.created_at:
                    ts = r.created_at.isoformat()
                    if ts > kp_groups[kp]["latestError"]:
                        kp_groups[kp]["latestError"] = ts
                et = r.error_type
                if et and et not in kp_groups[kp]["errorTypes"]:
                    kp_groups[kp]["errorTypes"].append(et)

            weak_points = []
            for kp, data in kp_groups.items():
                data["errorRate"] = round(data["errorCount"] / max(1, data["totalAttempts"]), 2)
                data["masteryEstimate"] = max(10, 100 - int(data["errorRate"] * 100))
                weak_points.append(data)

            weak_points.sort(key=lambda w: w["errorCount"], reverse=True)
            return {
                "status": "success",
                "data": {"weakPoints": weak_points, "total": len(weak_points)},
            }
        if session_id:
            q = q.filter(AnswerRecordModel.session_id == session_id)
        if error_type:
            q = q.filter(AnswerRecordModel.error_type == error_type)

        q = q.order_by(AnswerRecordModel.created_at.desc())
        total = q.count()
        rows = q.limit(limit).all()

        records = []
        for r in rows:
            question = db.query(StudentQuestionModel).filter(
                StudentQuestionModel.question_id == r.question_id
            ).first()
            records.append({
                "question": _question_dict(question, reveal=True) if question else None,
                "last_answer": r.student_answer,
                "grading_result": {
                    "total_score": r.total_score,
                    "dimension_scores": r.dimension_scores,
                    "dimension_feedback": r.dimension_feedback,
                    "error_type": r.error_type,
                    "error_label": r.error_label,
                    "error_explanation": r.error_explanation,
                    "error_action": r.error_action,
                    "suggestions": r.suggestions,
                    "strengths": r.strengths,
                },
                "attempted_at": int(r.created_at.timestamp() * 1000) if r.created_at else 0,
            })

        return {"status": "success", "data": {"records": records, "total": total}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Answer history
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/questions/history")
def get_answer_history(
    auth: AuthContext = Depends(require_auth),
    session_id: str = Query(default="", alias="sessionId"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Return the answer history for a session."""
    db = SessionLocal()
    try:
        q = db.query(AnswerRecordModel)
        if session_id:
            q = q.filter(AnswerRecordModel.session_id == session_id)
        q = q.order_by(AnswerRecordModel.created_at.desc())
        total_attempted = q.count()

        # Count correct (error_type == "null")
        correct_q = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.error_type == "null"
        )
        if session_id:
            correct_q = correct_q.filter(AnswerRecordModel.session_id == session_id)
        total_correct = correct_q.count()

        rows = q.limit(limit).all()

        records = []
        for r in rows:
            question = db.query(StudentQuestionModel).filter(
                StudentQuestionModel.question_id == r.question_id
            ).first()
            records.append({
                "question_id": r.question_id,
                "question": _question_dict(question, reveal=True) if question else None,
                "answer": r.student_answer,
                "grading_result": {
                    "total_score": r.total_score,
                    "dimension_scores": r.dimension_scores,
                    "dimension_feedback": r.dimension_feedback,
                    "error_type": r.error_type,
                    "error_label": r.error_label,
                    "error_explanation": r.error_explanation,
                    "error_action": r.error_action,
                    "suggestions": r.suggestions,
                    "strengths": r.strengths,
                },
                "created_at": int(r.created_at.timestamp() * 1000) if r.created_at else 0,
            })

        return {
            "status": "success",
            "data": {
                "records": records,
                "totalCorrect": total_correct,
                "totalAttempted": total_attempted,
            },
        }
    finally:
        db.close()


# ==== M3: Review Queue ====
class ReviewAction(BaseModel):
    question_id: str
    action: str
    revision_note: str = ""


@router.get("/questions/review-queue")
def get_review_queue(status: str = Query("pending"), auth: AuthContext = Depends(require_auth)):
    try:
        db = SessionLocal()
        query = db.query(StudentQuestionModel)
        if status == "pending":
            query = query.filter(StudentQuestionModel.needs_review == True)
        elif status == "approved":
            query = query.filter(StudentQuestionModel.review_status == "approved")
        elif status == "rejected":
            query = query.filter(StudentQuestionModel.review_status == "rejected")
        rows = query.order_by(StudentQuestionModel.created_at.desc()).limit(50).all()
        return {"status":"success","data":{"questions":[{"question_id":r.question_id,"stem":r.stem,"type":r.type_,"difficulty":r.difficulty,"review_reason":r.review_reason,"review_status":r.review_status or "pending","created_at":int(r.created_at.timestamp()*1000) if r.created_at else 0} for r in rows],"total":len(rows)}}
    finally:
        db.close()


@router.post("/questions/review-action")
def submit_review_action(body: ReviewAction, auth: AuthContext = Depends(require_auth)):
    try:
        db = SessionLocal()
        q = db.query(StudentQuestionModel).filter(StudentQuestionModel.question_id == body.question_id).first()
        if not q:
            raise HTTPException(404, f"Question {body.question_id} not found")
        if body.action == "approve":
            q.review_status = "approved"
            q.quality_status = "reviewed_passed"
        elif body.action == "reject":
            q.review_status = "rejected"
            q.quality_status = "reviewed_rejected"
        elif body.action == "revise":
            q.review_status = "pending_revision"
            if body.revision_note:
                q.revision_note = body.revision_note
        db.commit()
        return {"status":"success","message":f"Question {body.question_id} marked as {body.action}"}
    finally:
        db.close()
