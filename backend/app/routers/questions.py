"""Canonical, owner-scoped student question routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import AnswerRecordModel, PracticeQuestionModel, StudentQuestionModel
from app.db.repository import (
    get_answer_history,
    get_answer_stats,
    get_questions,
    get_weak_records,
    save_answer_record,
    upsert_questions,
)
from app.middleware.auth import AuthContext, get_auth, require_auth
from app.services.agent_service import run_agents
from app.services.conversation_state import conversation_store
from app.services.intent_router import get_agent_ids
from app.services.question_access import (
    require_owned_session,
    resolve_owned_practice_question,
    resolve_question_learner,
)

router = APIRouter(tags=["questions"])


class GenerateRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    learner_id: str = Field("", alias="learnerId")
    message: str = ""


class GradeRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    learner_id: str = Field("", alias="learnerId")
    answer: str = ""


class ReviewAction(BaseModel):
    question_id: str
    action: str
    revision_note: str = ""


def _response(data: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "data": data}


def _practice_question_dict(question: PracticeQuestionModel, *, reveal: bool = False) -> dict[str, Any]:
    data = {
        "question_id": question.question_id,
        "type": question.type,
        "stem": question.stem,
        "question_set_id": question.question_set_id,
        "options": question.options,
        "difficulty": question.difficulty,
        "knowledge_points": question.knowledge_points,
        "tags": question.tags,
        "source": question.source,
        "quality_status": question.quality_status,
        "created_at": str(question.created_at) if question.created_at else None,
    }
    if reveal:
        data.update({
            "correct": question.correct,
            "explanation": question.explanation,
            "scoring_rubric": question.scoring_rubric,
            "reference_answer": question.reference_answer,
        })
    return data


def _require_reviewer(auth: AuthContext) -> None:
    if not auth.is_teacher:
        raise HTTPException(status_code=403, detail="review access denied")


def _grade(session_id: str, question: dict[str, Any], answer: str) -> dict[str, Any]:
    from app.agents.grading_agent import GradingAgent
    from app.services.llm_client import get_llm_client

    result = GradingAgent(mock_data={}, llm_client=get_llm_client()).run({
        "session_id": session_id,
        "question": question,
        "student_answer": answer,
        "profile_facts": {"_raw_user_message": answer},
    })
    return result.get("grading_result", {}) if isinstance(result, dict) else {}


@router.post("/questions/generate")
def generate_questions(body: GenerateRequest, auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    learner_id = resolve_question_learner(auth, body.learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, body.session_id, learner_id)
    finally:
        db.close()

    conversation_store.append_message(body.session_id, "user", body.message)
    result = run_agents(
        session_id=body.session_id,
        user_message=body.message,
        agents_filter=get_agent_ids("generate_questions"),
    )
    questions = result.get("questions", []) if isinstance(result, dict) else []
    question_set_id = str(result.get("question_set_id", "")) if isinstance(result, dict) else ""
    if questions:
        db = SessionLocal()
        try:
            for question in questions:
                if isinstance(question, dict):
                    question["question_set_id"] = question_set_id
            upsert_questions(db, body.session_id, questions)
        finally:
            db.close()
    return _response({"questionSetId": question_set_id, "questions": questions, "count": len(questions)})


@router.get("/questions")
def list_questions(
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    knowledge_point: str = Query("", alias="knowledgePoint"),
    difficulty: str = Query(""),
    qtype: str = Query(""),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, session_id, current_learner)
        rows = get_questions(db, session_id, knowledge_point=knowledge_point, difficulty=difficulty, qtype=qtype)
        return _response({"questions": [_practice_question_dict(row) for row in rows], "count": len(rows)})
    finally:
        db.close()


@router.get("/questions/sets")
def question_sets(
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, session_id, current_learner)
        questions = get_questions(db, session_id, limit=500)
        graded_ids = {record.question_id for record in get_answer_history(db, session_id, limit=500)}
        grouped: dict[str, list[PracticeQuestionModel]] = {}
        for question in questions:
            grouped.setdefault(question.question_set_id or "default", []).append(question)
        sets = []
        for set_id, members in grouped.items():
            first = members[0]
            knowledge_points = list(dict.fromkeys(
                point for question in members if isinstance(question.knowledge_points, list)
                for point in question.knowledge_points
            ))[:5]
            sets.append({
                "questionSetId": set_id,
                "title": (first.stem or set_id)[:30],
                "knowledgePoints": knowledge_points,
                "count": len(members),
                "completed": sum(question.question_id in graded_ids for question in members),
                "createdAt": int(first.created_at.timestamp() * 1000) if first.created_at else 0,
            })
        return _response({"sets": sets})
    finally:
        db.close()


@router.delete("/questions/sets/{set_id}")
def delete_question_set(
    set_id: str,
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, session_id, current_learner)
        questions = [question for question in get_questions(db, session_id, limit=500) if question.question_set_id == set_id]
        if not questions:
            raise HTTPException(status_code=404, detail="resource not found")
        question_ids = [question.question_id for question in questions]
        db.query(AnswerRecordModel).filter(
            AnswerRecordModel.session_id == session_id,
            AnswerRecordModel.question_id.in_(question_ids),
        ).delete(synchronize_session=False)
        db.query(PracticeQuestionModel).filter(
            PracticeQuestionModel.session_id == session_id,
            PracticeQuestionModel.question_id.in_(question_ids),
        ).delete(synchronize_session=False)
        db.commit()
        return _response({"deleted": True, "count": len(question_ids)})
    finally:
        db.close()


@router.get("/questions/weak")
def weak_questions(
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    error_type: str = Query("", alias="errorType"),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, session_id, current_learner)
        records = get_weak_records(db, session_id, error_type=error_type, limit=limit)
        rows = []
        for record in records:
            question = resolve_owned_practice_question(
                db, record.question_id, current_learner, session_id=session_id
            )
            rows.append({
                "question": _practice_question_dict(question, reveal=True),
                "last_answer": record.student_answer,
                "grading_result": {
                    "total_score": record.total_score,
                    "dimension_scores": record.dimension_scores,
                    "dimension_feedback": record.dimension_feedback,
                    "error_type": record.error_type,
                    "error_label": record.error_label,
                    "error_explanation": record.error_explanation,
                    "error_action": record.error_action,
                    "suggestions": record.suggestions,
                    "strengths": record.strengths,
                },
                "attempted_at": int(record.created_at.timestamp() * 1000) if record.created_at else 0,
            })
        return _response({"records": rows, "total": len(rows)})
    finally:
        db.close()


@router.get("/questions/history")
def answer_history(
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        require_owned_session(db, session_id, current_learner)
        records = get_answer_history(db, session_id, limit=limit)
        stats = get_answer_stats(db, session_id)
        rows = []
        for record in records:
            question = resolve_owned_practice_question(
                db, record.question_id, current_learner, session_id=session_id
            )
            rows.append({
                "question_id": record.question_id,
                "question": _practice_question_dict(question, reveal=True),
                "answer": record.student_answer,
                "grading_result": {
                    "total_score": record.total_score,
                    "dimension_scores": record.dimension_scores,
                    "dimension_feedback": record.dimension_feedback,
                    "error_type": record.error_type,
                    "error_label": record.error_label,
                },
                "created_at": int(record.created_at.timestamp() * 1000) if record.created_at else 0,
            })
        return _response({"records": rows, "totalCorrect": stats["totalCorrect"], "totalAttempted": stats["totalAttempted"]})
    finally:
        db.close()


@router.get("/questions/review-queue")
def get_review_queue(status: str = Query("pending"), auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    _require_reviewer(auth)
    db = SessionLocal()
    try:
        query = db.query(StudentQuestionModel)
        if status == "pending":
            query = query.filter(StudentQuestionModel.needs_review.is_(True))
        elif status in {"approved", "rejected"}:
            query = query.filter(StudentQuestionModel.review_status == status)
        rows = query.order_by(StudentQuestionModel.created_at.desc()).limit(50).all()
        questions = [{
            "question_id": row.question_id,
            "stem": row.stem,
            "type": row.type,
            "difficulty": row.difficulty,
            "review_reason": row.review_reason,
            "review_status": row.review_status or "pending",
            "created_at": int(row.created_at.timestamp() * 1000) if row.created_at else 0,
        } for row in rows]
        return _response({"questions": questions, "total": len(questions)})
    finally:
        db.close()


@router.post("/questions/review-action")
def submit_review_action(body: ReviewAction, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    _require_reviewer(auth)
    if body.action not in {"approve", "reject", "revise"}:
        raise HTTPException(status_code=422, detail="unsupported review action")
    db = SessionLocal()
    try:
        question = db.query(StudentQuestionModel).filter(
            StudentQuestionModel.question_id == body.question_id
        ).first()
        if question is None:
            raise HTTPException(status_code=404, detail="resource not found")
        if body.action == "approve":
            question.review_status, question.quality_status = "approved", "reviewed_passed"
        elif body.action == "reject":
            question.review_status, question.quality_status = "rejected", "reviewed_rejected"
        else:
            question.review_status = "pending_revision"
            if body.revision_note:
                question.revision_note = body.revision_note
        db.commit()
        return {"status": "success", "message": "review updated"}
    finally:
        db.close()


@router.get("/questions/{question_id}")
def get_question(
    question_id: str,
    session_id: str = Query(..., alias="sessionId"),
    learner_id: str = Query("", alias="learnerId"),
    reveal: bool = Query(False),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    current_learner = resolve_question_learner(auth, learner_id)
    db = SessionLocal()
    try:
        question = resolve_owned_practice_question(
            db, question_id, current_learner, session_id=session_id
        )
        return _response({"question": _practice_question_dict(question, reveal=reveal)})
    finally:
        db.close()


@router.post("/questions/{question_id}/grade")
def grade_answer(question_id: str, body: GradeRequest, auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    if not body.answer.strip():
        raise HTTPException(status_code=422, detail="answer is required")
    current_learner = resolve_question_learner(auth, body.learner_id)
    db = SessionLocal()
    try:
        question = resolve_owned_practice_question(
            db, question_id, current_learner, session_id=body.session_id
        )
        question_payload = _practice_question_dict(question, reveal=True)
    finally:
        db.close()

    grading_result = _grade(body.session_id, question_payload, body.answer.strip())
    db = SessionLocal()
    try:
        save_answer_record(db, {
            "session_id": body.session_id,
            "question_id": question_id,
            "student_answer": body.answer.strip(),
            **grading_result,
        })
    finally:
        db.close()
    return _response({"gradingResult": grading_result})
