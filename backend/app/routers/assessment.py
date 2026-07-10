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
    save_quiz,
    update_attempt,
    update_exam_set,
)
from app.middleware.auth import AuthContext, require_auth
from app.services.llm_client import get_llm_client
from app.utils.llm_json import parse_safe

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


class SectionQuizGenerateRequest(BaseModel):
    """Payload for generating a quiz from a section context."""
    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    knowledge_points: list[str] = Field(default_factory=list, alias="knowledgePoints")
    lecture_summary: str = Field(default="", alias="lectureSummary")
    difficulty: str = "medium"
    path_id: str | None = Field(default=None, alias="pathId")
    stage_id: str | None = Field(default=None, alias="stageId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    section_id: str | None = Field(default=None, alias="sectionId")


class QuizSubmitRequest(BaseModel):
    """Payload for submitting all answers to a quiz at once."""
    session_id: str = Field(default="", alias="sessionId")
    answers: list[dict] = Field(default_factory=list)
    # Each answer: {"questionId": "...", "answer": "..."}


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


@router.get("/quizzes/{quiz_id}/results")
def get_quiz_results(
    quiz_id: str,
    auth: AuthContext = Depends(require_auth),
    attempt_id: str = Query(default="", alias="attemptId"),
) -> dict:
    """Get quiz results with answers and grading after submission."""
    db = SessionLocal()
    try:
        quiz = get_quiz(db, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="小测不存在")
        # Resolve linked questions with answers revealed
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
                "correctAnswer": pq.correct,
                "explanation": pq.explanation,
            })
        result = _quiz_dict(quiz)
        result["linkedQuestions"] = question_list

        # If attempt_id provided, include grading results
        if attempt_id:
            attempt = get_attempt(db, attempt_id)
            if attempt:
                result["attempt"] = _attempt_dict(attempt)
                answer_records = get_attempt_answers(db, attempt_id)
                result["gradingResults"] = []
                for ar in answer_records:
                    result["gradingResults"].append({
                        "questionId": ar.question_id,
                        "studentAnswer": ar.student_answer,
                        "score": ar.total_score,
                        "errorType": ar.error_type,
                        "errorLabel": ar.error_label,
                        "errorExplanation": ar.error_explanation,
                        "suggestions": ar.suggestions or [],
                    })

        return {"status": "success", "data": {"quiz": result}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Section quiz generation
# ═══════════════════════════════════════════════════════════════════════


@router.post("/sections/{section_id}/quiz/generate")
def generate_section_quiz(
    section_id: str,
    body: SectionQuizGenerateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Generate 3–5 quiz questions from section context via LLM.

    Questions are persisted as PracticeQuestionModel rows linked to a new
    QuizModel. Correct answers are NEVER returned until after submission.
    """
    db = SessionLocal()
    try:
        # ── Build LLM prompt ────────────────────────────────────
        kp_text = "\n".join(f"- {kp}" for kp in body.knowledge_points[:8])
        summary = body.lecture_summary[:2000] if body.lecture_summary else "暂无讲义摘要"

        prompt = f"""你是 EduAgent 的试题生成智能体。根据以下小节内容生成 {3 + (body.difficulty == 'hard') * 2}～{4 + (body.difficulty == 'easy') * 2} 道练习题。

## 小节标题
{body.title}

## 知识点
{kp_text or '根据小节标题推断'}

## 讲义摘要
{summary}

## 要求
- 难度：{body.difficulty}
- 题型混合：选择题（至少1道）、判断题（至少1道）、简答题（可选1道）
- 选择题的干扰项要有迷惑性但明确错误
- 每题解析需写清楚正确答案和解题思路

## 输出格式（只输出 JSON）
{{"questions": [
  {{"question_id": "q1", "type": "choice", "stem": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct": "A", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}},
  {{"question_id": "q2", "type": "truefalse", "stem": "...", "correct": "true", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}},
  {{"question_id": "q3", "type": "shortanswer", "stem": "...", "reference_answer": "...", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}}
]}}"""

        # ── Call LLM ───────────────────────────────────────────
        llm = get_llm_client()
        raw = llm.chat(
            messages=[
                {"role": "system", "content": "你是专业的试题生成专家。只输出JSON，不要Markdown包裹。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        parsed = parse_safe(raw)
        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or len(questions) == 0:
            raise HTTPException(status_code=500, detail="题目生成失败，请重试")

        # ── Create QuizModel ───────────────────────────────────
        quiz_id = f"quiz_{uuid.uuid4().hex[:12]}"
        quiz = save_quiz(db, {
            "id": quiz_id,
            "title": body.title + " 小测" if body.title else "即时小测",
            "session_id": body.session_id,
            "scope_type": "section",
            "scope_id": section_id,
            "path_id": body.path_id,
            "stage_id": body.stage_id,
            "chapter_id": body.chapter_id,
            "section_id": section_id,
            "knowledge_point_ids": body.knowledge_points,
            "difficulty": body.difficulty,
            "question_count": len(questions),
            "questions": questions,
            "source": "llm_generated",
        })

        # ── Persist questions (without revealing answers) ──────
        for q in questions:
            pq = PracticeQuestionModel(
                question_id=q.get("question_id", f"q_{uuid.uuid4().hex[:12]}"),
                question_set_id=quiz_id,
                session_id=body.session_id,
                type=q.get("type", "choice"),
                stem=q.get("stem", ""),
                options=q.get("options"),
                correct=q.get("correct", ""),
                explanation=q.get("explanation", ""),
                difficulty=q.get("difficulty", body.difficulty),
                knowledge_points=[q.get("knowledge_point", "")] if q.get("knowledge_point") else body.knowledge_points,
                reference_answer=q.get("reference_answer"),
                source="llm_generated",
                quality_status="passed",
            )
            db.add(pq)
        db.commit()

        # ── Return WITHOUT answers ─────────────────────────────
        safe_questions = []
        for q in questions:
            safe_questions.append({
                "questionId": q.get("question_id", ""),
                "type": q.get("type", "choice"),
                "stem": q.get("stem", ""),
                "options": q.get("options"),
                "difficulty": q.get("difficulty", body.difficulty),
                "knowledgePoints": [q.get("knowledge_point", "")] if q.get("knowledge_point") else body.knowledge_points,
            })

        return {
            "status": "success",
            "data": {
                "quiz": _quiz_dict(quiz),
                "questions": safe_questions,
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Quiz submit & grade
# ═══════════════════════════════════════════════════════════════════════


@router.post("/quizzes/{quiz_id}/submit")
def submit_quiz(
    quiz_id: str,
    body: QuizSubmitRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Submit all answers for a quiz — grade each and return results.

    Choice/truefalse are rule-graded. Shortanswer uses the GradingAgent LLM.
    An AttemptModel is created to group the answer records.
    """
    db = SessionLocal()
    try:
        quiz = get_quiz(db, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="小测不存在")

        # ── Load linked questions with answers ──────────────────
        linked = (
            db.query(PracticeQuestionModel)
            .filter(PracticeQuestionModel.question_set_id == quiz_id)
            .all()
        )
        if not linked:
            raise HTTPException(status_code=400, detail="该小测没有题目")
        questions_by_id = {pq.question_id: pq for pq in linked}

        # ── Create attempt ─────────────────────────────────────
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": body.session_id,
            "quiz_id": quiz_id,
            "max_score": 100 * len(linked),
            "learner_id": auth.learner_id if auth else None,
        })

        # ── Grade each answer ──────────────────────────────────
        results = []
        total_score = 0
        max_possible = 0

        for ans in body.answers:
            qid = ans.get("questionId", "")
            student_answer = str(ans.get("answer", "")).strip()
            pq = questions_by_id.get(qid)
            if pq is None:
                continue

            max_possible += 100
            q_dict = {
                "question_id": pq.question_id,
                "type": pq.type,
                "stem": pq.stem,
                "options": pq.options,
                "correct": pq.correct,
                "explanation": pq.explanation,
                "reference_answer": pq.reference_answer,
                "scoring_rubric": pq.scoring_rubric,
                "knowledge_points": pq.knowledge_points,
            }

            # Rule-based for choice/truefalse
            if pq.type in ("choice", "truefalse"):
                correct = str(pq.correct or "").strip().upper()
                student = student_answer.upper()
                is_correct = student[:1] == correct[:1] if pq.type == "choice" else (
                    student in ("TRUE", "对", "正确", "YES", "T") and correct in ("TRUE", "对", "正确", "YES", "T")
                )
                score = 100 if is_correct else 0
                error_type = None if is_correct else ("concept" if pq.type == "choice" else "misreading")
                feedback = "回答正确" if is_correct else "回答错误"
                error_expl = "" if is_correct else (pq.explanation or "")

                ar = AnswerRecordModel(
                    session_id=body.session_id,
                    question_id=qid,
                    attempt_id=attempt.attempt_id,
                    student_answer=student_answer,
                    total_score=score,
                    error_type=error_type,
                    error_label=None if is_correct else ("概念错误" if pq.type == "choice" else "审题不清"),
                    error_explanation=error_expl,
                    suggestions=[] if is_correct else ["建议复习相关知识点"],
                    strengths=["回答正确"] if is_correct else [],
                    source="auto_graded",
                )

            else:
                # Shortanswer/fill — try GradingAgent LLM
                try:
                    from app.agents.grading_agent import GradingAgent
                    ga = GradingAgent()
                    ga.llm_client = get_llm_client()
                    grade_result = ga._grade_with_llm(q_dict, student_answer)
                    if grade_result is None:
                        # LLM failed, use rule fallback
                        grade_result = ga._rule_based_grading(q_dict, student_answer)
                except Exception:
                    # If GradingAgent unavailable, use simple fallback
                    grade_result = {
                        "total_score": None,
                        "error_type": None,
                        "error_label": "需人工评阅",
                        "error_explanation": "简答题需LLM评阅，当前不可用",
                        "suggestions": [],
                        "strengths": [],
                    }

                score = grade_result.get("total_score", 0) or 0
                error_type = grade_result.get("error_type")
                if error_type == "null":
                    error_type = None
                feedback = grade_result.get("dimension_feedback", {}).get("reasoning", "")
                error_expl = grade_result.get("error_explanation", "")

                ar = AnswerRecordModel(
                    session_id=body.session_id,
                    question_id=qid,
                    attempt_id=attempt.attempt_id,
                    student_answer=student_answer,
                    total_score=score,
                    dimension_scores=grade_result.get("dimension_scores"),
                    dimension_feedback=grade_result.get("dimension_feedback"),
                    error_type=error_type,
                    error_label=grade_result.get("error_label"),
                    error_explanation=error_expl,
                    suggestions=grade_result.get("suggestions", []),
                    strengths=grade_result.get("strengths", []),
                    source=grade_result.get("source", "llm_generated"),
                )

            db.add(ar)
            total_score += score

            results.append({
                "questionId": qid,
                "studentAnswer": student_answer,
                "isCorrect": score >= 60,
                "score": score,
                "maxScore": 100,
                "correctAnswer": pq.correct,
                "explanation": pq.explanation,
                "feedback": feedback if 'feedback' in dir() else "",
                "errorType": ar.error_type,
                "errorLabel": ar.error_label,
                "knowledgePoint": (pq.knowledge_points or [""])[0] if pq.knowledge_points else "",
            })

        # ── Update attempt with results ─────────────────────────
        avg_score = round(total_score / max(1, max_possible) * 100)
        update_attempt(db, attempt.attempt_id, {
            "answers": body.answers,
            "total_score": avg_score,
            "status": "graded",
        })
        db.commit()

        # ── Compute section status suggestion ───────────────────
        if avg_score >= 80:
            suggestion = "mastered"
        elif avg_score >= 50:
            suggestion = "in_progress"
        else:
            suggestion = "needs_review"

        return {
            "status": "success",
            "data": {
                "attempt": _attempt_dict(get_attempt(db, attempt.attempt_id)),
                "results": results,
                "totalScore": avg_score,
                "maxScore": 100,
                "sectionStatusSuggestion": suggestion,
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Attempt endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.post("/attempts")
def create_attempt_endpoint(
    body: AttemptCreateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Create a new attempt for a quiz or exam set."""
    db = SessionLocal()
    try:
        if not body.quiz_id and not body.exam_set_id:
            raise HTTPException(status_code=400, detail="必须指定 quizId 或 examSetId")
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": body.session_id,
            "quiz_id": body.quiz_id,
            "exam_set_id": body.exam_set_id,
            "max_score": body.max_score,
            "learner_id": auth.learner_id if auth else None,
        })
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()


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
