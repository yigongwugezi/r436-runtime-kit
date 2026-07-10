"""Assessment endpoints — quizzes, exam sets, and attempts.

Implements the data-layer CRUD for the M5 exercise/assessment system.
Generation, grading, and weak-point recording are added in later increments.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import AnswerRecordModel, PracticeQuestionModel
from app.db.repository import (
    create_attempt,
    get_attempt,
    get_attempt_answers,
    get_exam_set,
    get_quiz,
    list_attempts,
    list_exam_sets,
    list_quizzes,
    save_exam_set,
    save_quiz,
    update_attempt,
    update_exam_set,
)
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assessment"])


# ═══════════════════════════════════════════════════════════════════════
# Inline request schemas (follow the questions.py pattern)
# ═══════════════════════════════════════════════════════════════════════


class QuizCreateRequest(BaseModel):
    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: str = Field(default="knowledge_point", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    section_id: str | None = Field(default=None, alias="sectionId")
    knowledge_point_ids: list[str] | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    questions: list[dict] | None = None
    source: str = "llm_generated"


class ExamSetCreateRequest(BaseModel):
    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: str = Field(default="chapter", alias="scopeType")
    scope_id: str | None = Field(default=None, alias="scopeId")
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    knowledge_point_ids: list[str] | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    difficulty_distribution: dict[str, int] | None = Field(default=None, alias="difficultyDistribution")
    question_count: int = Field(default=0, alias="questionCount")
    questions: list[dict] | None = None
    estimated_minutes: int = Field(default=30, alias="estimatedMinutes")
    total_score: int = Field(default=100, alias="totalScore")
    source: str = "llm_generated"
    archive_policy: str = Field(default="archive", alias="archivePolicy")


class ExamSetUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    question_count: int | None = Field(default=None, alias="questionCount")
    questions: list[dict] | None = None
    difficulty_distribution: dict[str, int] | None = Field(default=None, alias="difficultyDistribution")
    estimated_minutes: int | None = Field(default=None, alias="estimatedMinutes")
    total_score: int | None = Field(default=None, alias="totalScore")


class AttemptCreateRequest(BaseModel):
    session_id: str = Field(default="", alias="sessionId")
    quiz_id: str | None = Field(default=None, alias="quizId")
    exam_set_id: str | None = Field(default=None, alias="examSetId")
    max_score: int = Field(default=100, alias="maxScore")


class AttemptUpdateRequest(BaseModel):
    answers: list[dict] | None = None
    status: str | None = None


class AttemptSubmitRequest(BaseModel):
    answers: list[dict] = Field(default_factory=list)
    total_score: int | None = Field(default=None, alias="totalScore")


# ═══════════════════════════════════════════════════════════════════════
# Serialisation helpers
# ═══════════════════════════════════════════════════════════════════════


def _quiz_dict(q) -> dict:
    """Serialise a QuizModel to the frontend shape."""
    return {
        "id": q.id,
        "title": q.title,
        "sessionId": q.session_id,
        "scopeType": q.scope_type,
        "scopeId": q.scope_id,
        "pathId": q.path_id,
        "stageId": q.stage_id,
        "chapterId": q.chapter_id,
        "sectionId": q.section_id,
        "knowledgePointIds": q.knowledge_point_ids or [],
        "difficulty": q.difficulty,
        "questionCount": q.question_count,
        "questions": q.questions or [],
        "source": q.source,
        "archivePolicy": q.archive_policy,
        "createdAt": q.created_at.isoformat() if q.created_at else None,
    }


def _exam_set_dict(e) -> dict:
    """Serialise an ExamSetModel to the frontend shape."""
    return {
        "id": e.id,
        "title": e.title,
        "sessionId": e.session_id,
        "scopeType": e.scope_type,
        "scopeId": e.scope_id,
        "pathId": e.path_id,
        "stageId": e.stage_id,
        "chapterId": e.chapter_id,
        "knowledgePointIds": e.knowledge_point_ids or [],
        "difficulty": e.difficulty,
        "difficultyDistribution": e.difficulty_distribution or {},
        "questionCount": e.question_count,
        "questions": e.questions or [],
        "estimatedMinutes": e.estimated_minutes,
        "totalScore": e.total_score,
        "status": e.status,
        "source": e.source,
        "archivePolicy": e.archive_policy,
        "createdAt": e.created_at.isoformat() if e.created_at else None,
        "updatedAt": e.updated_at.isoformat() if e.updated_at else None,
    }


def _attempt_dict(a) -> dict:
    """Serialise an AttemptModel to the frontend shape."""
    return {
        "id": a.id,
        "attemptId": a.attempt_id,
        "sessionId": a.session_id,
        "quizId": a.quiz_id,
        "examSetId": a.exam_set_id,
        "learnerId": a.learner_id,
        "answers": a.answers or [],
        "totalScore": a.total_score,
        "maxScore": a.max_score,
        "status": a.status,
        "startedAt": a.started_at.isoformat() if a.started_at else None,
        "submittedAt": a.submitted_at.isoformat() if a.submitted_at else None,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# Quiz endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.post("/quizzes")
def create_quiz_endpoint(
    body: QuizCreateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Create a new instant quiz."""
    db = SessionLocal()
    try:
        quiz = save_quiz(db, {
            "id": f"quiz_{uuid.uuid4().hex[:12]}",
            "title": body.title,
            "session_id": body.session_id,
            "scope_type": body.scope_type,
            "scope_id": body.scope_id,
            "path_id": body.path_id,
            "stage_id": body.stage_id,
            "chapter_id": body.chapter_id,
            "section_id": body.section_id,
            "knowledge_point_ids": body.knowledge_point_ids,
            "difficulty": body.difficulty,
            "question_count": len(body.questions) if body.questions else 0,
            "questions": body.questions,
            "source": body.source,
        })
        return {"status": "success", "data": {"quiz": _quiz_dict(quiz)}}
    finally:
        db.close()


@router.get("/quizzes")
def list_quizzes_endpoint(
    auth: AuthContext = Depends(require_auth),
    session_id: str = Query(default="", alias="sessionId"),
    scope_type: str = Query(default="", alias="scopeType"),
) -> dict:
    """List quizzes, optionally filtered by session and scope type."""
    db = SessionLocal()
    try:
        quizzes = list_quizzes(db, session_id=session_id, scope_type=scope_type)
        return {
            "status": "success",
            "data": {"quizzes": [_quiz_dict(q) for q in quizzes]},
        }
    finally:
        db.close()


@router.get("/quizzes/{quiz_id}")
def get_quiz_endpoint(
    quiz_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get a quiz by ID, including its linked questions."""
    db = SessionLocal()
    try:
        quiz = get_quiz(db, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="小测不存在")
        # Resolve linked questions from practice_questions table
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(PracticeQuestionModel.question_set_id == quiz_id)
            .all()
        )
        question_list = []
        for pq in linked_questions:
            question_list.append({
                "questionId": pq.question_id,
                "type": pq.type,
                "stem": pq.stem,
                "options": pq.options,
                "difficulty": pq.difficulty,
                "knowledgePoints": pq.knowledge_points or [],
            })
        result = _quiz_dict(quiz)
        result["linkedQuestions"] = question_list
        return {"status": "success", "data": {"quiz": result}}
    finally:
        db.close()


@router.post("/quizzes/{quiz_id}/attempts")
def start_quiz_attempt(
    quiz_id: str,
    body: AttemptCreateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Start a new attempt on a quiz."""
    db = SessionLocal()
    try:
        quiz = get_quiz(db, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="小测不存在")
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": body.session_id,
            "quiz_id": quiz_id,
            "max_score": body.max_score,
            "learner_id": auth.learner_id if auth else None,
        })
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()


@router.get("/quizzes/{quiz_id}/attempts")
def list_quiz_attempts(
    quiz_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """List all attempts for a quiz."""
    db = SessionLocal()
    try:
        attempts = list_attempts(db, quiz_id=quiz_id)
        return {
            "status": "success",
            "data": {"attempts": [_attempt_dict(a) for a in attempts]},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Attempt endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/attempts/{attempt_id}")
def get_attempt_endpoint(
    attempt_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get an attempt by ID, including its linked answer records."""
    db = SessionLocal()
    try:
        attempt = get_attempt(db, attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="作答记录不存在")
        # Resolve linked answer records
        answer_records = get_attempt_answers(db, attempt_id)
        linked_answers = []
        for ar in answer_records:
            linked_answers.append({
                "id": ar.id,
                "questionId": ar.question_id,
                "studentAnswer": ar.student_answer,
                "totalScore": ar.total_score,
                "errorType": ar.error_type,
                "errorLabel": ar.error_label,
                "errorExplanation": ar.error_explanation,
                "suggestions": ar.suggestions or [],
                "createdAt": ar.created_at.isoformat() if ar.created_at else None,
            })
        result = _attempt_dict(attempt)
        result["linkedAnswers"] = linked_answers
        return {"status": "success", "data": {"attempt": result}}
    finally:
        db.close()


@router.patch("/attempts/{attempt_id}")
def update_attempt_endpoint(
    attempt_id: str,
    body: AttemptUpdateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Update an attempt — save progress or change status."""
    db = SessionLocal()
    try:
        data = {}
        if body.answers is not None:
            data["answers"] = body.answers
        if body.status is not None:
            data["status"] = body.status
        attempt = update_attempt(db, attempt_id, data)
        if attempt is None:
            raise HTTPException(status_code=404, detail="作答记录不存在")
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt_endpoint(
    attempt_id: str,
    body: AttemptSubmitRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Submit an attempt for grading.

    Stores the answer snapshot and marks the attempt as submitted.
    Per-question grading is handled by the questions/{id}/grade endpoint
    and linked via answer_records.attempt_id.
    """
    db = SessionLocal()
    try:
        data = {
            "answers": body.answers,
            "total_score": body.total_score,
            "status": "submitted",
        }
        attempt = update_attempt(db, attempt_id, data)
        if attempt is None:
            raise HTTPException(status_code=404, detail="作答记录不存在")
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Exam Set endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.post("/exam-sets")
def create_exam_set_endpoint(
    body: ExamSetCreateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Create a new exam set."""
    db = SessionLocal()
    try:
        exam = save_exam_set(db, {
            "id": f"exam_{uuid.uuid4().hex[:12]}",
            "title": body.title,
            "session_id": body.session_id,
            "scope_type": body.scope_type,
            "scope_id": body.scope_id,
            "path_id": body.path_id,
            "stage_id": body.stage_id,
            "chapter_id": body.chapter_id,
            "knowledge_point_ids": body.knowledge_point_ids,
            "difficulty": body.difficulty,
            "difficulty_distribution": body.difficulty_distribution,
            "question_count": body.question_count,
            "questions": body.questions,
            "estimated_minutes": body.estimated_minutes,
            "total_score": body.total_score,
            "source": body.source,
            "archive_policy": body.archive_policy,
        })
        return {"status": "success", "data": {"examSet": _exam_set_dict(exam)}}
    finally:
        db.close()


@router.get("/exam-sets")
def list_exam_sets_endpoint(
    auth: AuthContext = Depends(require_auth),
    session_id: str = Query(default="", alias="sessionId"),
    scope_type: str = Query(default="", alias="scopeType"),
    status: str = Query(default=""),
) -> dict:
    """List exam sets, optionally filtered."""
    db = SessionLocal()
    try:
        exam_sets = list_exam_sets(
            db, session_id=session_id, scope_type=scope_type, status=status,
        )
        return {
            "status": "success",
            "data": {"examSets": [_exam_set_dict(e) for e in exam_sets]},
        }
    finally:
        db.close()


@router.get("/exam-sets/{exam_set_id}")
def get_exam_set_endpoint(
    exam_set_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get an exam set by ID, including linked questions."""
    db = SessionLocal()
    try:
        exam_set = get_exam_set(db, exam_set_id)
        if exam_set is None:
            raise HTTPException(status_code=404, detail="题集不存在")
        # Resolve linked questions
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(PracticeQuestionModel.question_set_id == exam_set_id)
            .all()
        )
        question_list = []
        for pq in linked_questions:
            question_list.append({
                "questionId": pq.question_id,
                "type": pq.type,
                "stem": pq.stem,
                "options": pq.options,
                "difficulty": pq.difficulty,
                "knowledgePoints": pq.knowledge_points or [],
            })
        result = _exam_set_dict(exam_set)
        result["linkedQuestions"] = question_list
        return {"status": "success", "data": {"examSet": result}}
    finally:
        db.close()


@router.patch("/exam-sets/{exam_set_id}")
def update_exam_set_endpoint(
    exam_set_id: str,
    body: ExamSetUpdateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Partial-update an exam set."""
    db = SessionLocal()
    try:
        data = {}
        if body.title is not None:
            data["title"] = body.title
        if body.status is not None:
            data["status"] = body.status
        if body.question_count is not None:
            data["question_count"] = body.question_count
        if body.questions is not None:
            data["questions"] = body.questions
        if body.difficulty_distribution is not None:
            data["difficulty_distribution"] = body.difficulty_distribution
        if body.estimated_minutes is not None:
            data["estimated_minutes"] = body.estimated_minutes
        if body.total_score is not None:
            data["total_score"] = body.total_score
        exam_set = update_exam_set(db, exam_set_id, data)
        if exam_set is None:
            raise HTTPException(status_code=404, detail="题集不存在")
        return {"status": "success", "data": {"examSet": _exam_set_dict(exam_set)}}
    finally:
        db.close()


@router.post("/exam-sets/{exam_set_id}/attempts")
def start_exam_set_attempt(
    exam_set_id: str,
    body: AttemptCreateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Start a new attempt on an exam set."""
    db = SessionLocal()
    try:
        exam_set = get_exam_set(db, exam_set_id)
        if exam_set is None:
            raise HTTPException(status_code=404, detail="题集不存在")
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": body.session_id,
            "exam_set_id": exam_set_id,
            "max_score": body.max_score or exam_set.total_score,
            "learner_id": auth.learner_id if auth else None,
        })
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()
