"""Assessment endpoints — quizzes, exam sets, and attempts.

Implements the data-layer CRUD for the M5 exercise/assessment system.
Generation, grading, and weak-point recording are added in later increments.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.db.engine import SessionLocal
from app.db.models import AnswerRecordModel, AttemptModel, ExamSetModel, LearningPathModel, PracticeQuestionModel, QuizModel, SessionModel
from app.db.repository import (
    check_quiz_result_event_exists,
    create_attempt,
    create_quiz_result_event,
    find_attempt_by_idempotency_key,
    get_attempt,
    get_attempt_answers,
    get_next_attempt_number,
    get_quiz_result_event,
    list_attempts,
    save_exam_set,
    save_quiz,
    update_attempt,
    update_exam_set,
)
from app.db.repository import save_profile_snapshot
from app.middleware.auth import AuthContext, require_auth
from app.agents.grading_agent import GradingAgent
from app.services.agent_factory import AgentFactory
from app.services.llm_client import get_llm_client
from app.services.assessment_access import (
    list_owned_exam_sets,
    list_owned_quizzes,
    require_matching_session,
    require_owned_attempt,
    require_owned_exam_set,
    require_owned_quiz,
    require_owned_session,
    require_parent_attempt,
)
from app.services.knowledge_point_service import (
    compute_all_results,
    get_highest_weight_label,
    resolve_mappings,
)
from app.utils.llm_json import parse_safe

# Module-level shared instances — one LLM client + one GradingAgent per process
_assessment_llm = get_llm_client()
_assessment_factory = AgentFactory(llm_client=_assessment_llm)

logger = logging.getLogger(__name__)


def _require_path_stage(payload: dict[str, Any]) -> None:
    """Apply path locking only when an existing path task supplies a stage."""
    stage_id = str(payload.get("stageId") or payload.get("stage_id") or "")
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "")
    if stage_id and session_id:
        from app.routers.product import _require_stage_access
        _require_stage_access(session_id, stage_id)


def _assessment_path_context(db, parent, body: "QuizSubmitRequest", learner_id: str, subject_id: str) -> dict[str, str] | None:
    """Accept only an explicit, owned assessment task; standalone practice stays standalone."""
    values = {"path_id": body.path_id.strip(), "stage_id": body.stage_id.strip(), "task_id": body.task_id.strip()}
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise HTTPException(status_code=400, detail="pathId, stageId and taskId are required together")
    if values["path_id"] != str(getattr(parent, "path_id", "") or "") or values["stage_id"] != str(getattr(parent, "stage_id", "") or ""):
        raise HTTPException(status_code=403, detail="assessment path context does not match its parent")
    from app.db.models import LearningPathModel, SessionModel
    from app.routers.product import _apply_stage_progress, _path_task_context
    session = db.get(SessionModel, parent.session_id)
    if not session or session.learner_id != learner_id or (subject_id and session.subject_id and session.subject_id != subject_id):
        raise HTTPException(status_code=403, detail="assessment session is not owned by learner")
    path = db.query(LearningPathModel).filter(
        LearningPathModel.id == values["path_id"], LearningPathModel.session_id == parent.session_id,
    ).first()
    context = _path_task_context(path.stages, values["task_id"]) if path and isinstance(path.stages, list) else None
    if not context or str(context[0].get("id") or context[0].get("stage_id") or "") != values["stage_id"]:
        raise HTTPException(status_code=403, detail="assessment task is not in the requested path stage")
    task_type = str(context[1].get("task_type") or context[1].get("type") or context[1].get("content_type") or "").lower()
    if task_type not in {"quiz", "do_quiz", "quiz_prac", "practice", "exam", "assessment", "test"}:
        raise HTTPException(status_code=403, detail="path task is not an assessment")
    stage = _apply_stage_progress(path.stages)[path.stages.index(context[0])]
    if stage["progressStatus"] == "locked":
        raise HTTPException(status_code=403, detail="please complete the current stage first")
    return values

router = APIRouter(tags=["assessment"])


def _task_quiz_questions(task: dict, task_id: str) -> list[dict]:
    """Small, persistent MCQ set for one path task; answers stay server-side."""
    return _build_domain_quiz_fallback(task, task_id)
    topic = str(task.get("title") or task.get("topic") or task.get("name") or task_id)
    return [{
        "id": f"{task_id}-q{i}", "type": "choice",
        "stem": f"关于“{topic}”，以下哪项最符合本任务的核心学习目标？",
        "options": [f"A. 理解并应用 {topic}", "B. 跳过关键概念", "C. 只记忆无关事实", "D. 不进行任何验证"],
        "correct": "A", "explanation": f"本题检验对“{topic}”核心概念的理解与应用。",
        "knowledge_points": [topic], "difficulty": "medium",
    } for i in range(1, 6)]


def _build_domain_quiz_fallback(task: dict, task_id: str) -> list[dict]:
    """Bounded deterministic fallback; task knowledge points choose the domain."""
    text = " ".join(map(str, [task.get("title", ""), task.get("description", ""), *(task.get("knowledge_points", []) or task.get("knowledgePoints", []) or [])])).lower()
    if not any(token in text for token in ("复杂度", "complexity", "big o", "链表", "顺序表")):
        text = "复杂度"
    rows = [
        ("单层循环执行 n 次常数操作，时间复杂度是？", ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n²)"], "C", "循环执行 n 次，所以是 O(n)。", "单层循环时间复杂度"),
        ("两层循环各执行 n 次，时间复杂度是？", ["A. O(n²)", "B. O(n)", "C. O(log n)", "D. O(1)"], "A", "总执行次数为 n×n。", "嵌套循环时间复杂度"),
        ("变量每轮乘 2 直到 n，循环次数是？", ["A. O(n)", "B. O(log n)", "C. O(n²)", "D. O(2ⁿ)"], "B", "规模每轮翻倍，轮数为 log₂n。", "对数循环"),
        ("时间复杂度与空间复杂度的正确区别是？", ["A. 都只衡量时间", "B. 时间衡量步骤增长，空间衡量额外存储", "C. 时间衡量内存，空间衡量步骤", "D. 二者总相同"], "B", "时间关注操作增长，空间关注额外内存。", "时间与空间复杂度"),
        ("顺序表按下标访问与单链表按位置访问的复杂度分别是？", ["A. O(1) 与 O(n)", "B. O(n) 与 O(1)", "C. 都是 O(1)", "D. 都是 O(log n)"], "A", "数组可直接索引，链表需遍历。", "顺序表与链表操作复杂度"),
    ]
    return [{"id": f"{task_id}-q{i + 1}", "type": "choice", "stem": stem, "options": options, "correct": correct, "explanation": explanation, "knowledge_points": [kp], "difficulty": "medium"} for i, (stem, options, correct, explanation, kp) in enumerate(rows)]


def _safe_task_quiz(quiz: QuizModel, db) -> dict:
    linked = db.query(PracticeQuestionModel).filter(
        PracticeQuestionModel.question_set_id == quiz.id,
        PracticeQuestionModel.session_id == quiz.session_id,
    ).all()
    return {
        "quizId": quiz.id, "taskId": quiz.section_id, "title": quiz.title,
        "passingScore": 60, "version": 1,
        "questions": [{"questionId": q.question_id, "type": q.type, "stem": q.stem,
                       "options": q.options or [], "difficulty": q.difficulty,
                       "knowledgePoints": q.knowledge_points or []} for q in linked],
    }


def _require_task_quiz_scope(db, task_id: str, payload: dict, learner_id: str) -> tuple[LearningPathModel, dict, str]:
    session_id, path_id, stage_id = (str(payload.get(key) or "") for key in ("sessionId", "pathId", "stageId"))
    subject_id = str(payload.get("subjectId") or "")
    if not all((session_id, path_id, stage_id, task_id)):
        raise HTTPException(status_code=400, detail="sessionId, pathId, stageId and taskId are required")
    session = require_owned_session(db, session_id, learner_id)
    if subject_id and session.subject_id and subject_id != session.subject_id:
        raise HTTPException(status_code=409, detail="subject scope does not match session")
    path = db.query(LearningPathModel).filter(LearningPathModel.id == path_id, LearningPathModel.session_id == session_id).first()
    if not path:
        raise HTTPException(status_code=404, detail="learning path not found")
    from app.routers.product import _apply_stage_progress, normalize_learning_path
    normalized = normalize_learning_path({"id": path.id, "estimatedDays": path.estimated_days, "stages": path.stages})
    entry = normalized["task_index"].get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="learning path task not found")
    if entry["stage_id"] != stage_id:
        raise HTTPException(status_code=409, detail="task scope does not match path stage")
    if payload.get("dayId") and str(payload["dayId"]) != entry["day_id"]:
        raise HTTPException(status_code=409, detail="task scope does not match day")
    if payload.get("globalDayIndex") is not None and int(payload["globalDayIndex"]) != entry["global_day_index"]:
        raise HTTPException(status_code=409, detail="task scope does not match day")
    stage = _apply_stage_progress(path.stages)[entry["_stage_index"]]
    if stage["progressStatus"] == "locked":
        raise HTTPException(status_code=403, detail="please complete the current stage first")
    if str(entry["task"].get("task_type") or entry["task"].get("type") or "").lower() not in {"quiz", "do_quiz", "quiz_prac", "assessment", "test"}:
        raise HTTPException(status_code=409, detail="task is not a quiz")
    return path, entry, session.subject_id or subject_id


@router.post("/learning-path/tasks/{task_id}/quiz/ensure")
def ensure_task_quiz(task_id: str, payload: dict, auth: AuthContext = Depends(require_auth)) -> dict:
    db = SessionLocal()
    try:
        path, entry, _ = _require_task_quiz_scope(db, task_id, payload, auth.learner_id)
        quiz = db.query(QuizModel).filter(QuizModel.session_id == path.session_id, QuizModel.path_id == path.id,
            QuizModel.stage_id == entry["stage_id"], QuizModel.section_id == task_id).order_by(QuizModel.created_at.desc()).first()
        if not quiz:
            questions = _task_quiz_questions(entry["task"], task_id)
            quiz = save_quiz(db, {"id": f"quiz_{uuid.uuid4().hex[:12]}", "title": str(entry["task"].get("title") or "Task quiz"),
                "session_id": path.session_id, "scope_type": "section", "scope_id": task_id, "path_id": path.id,
                "stage_id": entry["stage_id"], "section_id": task_id, "question_count": len(questions),
                "questions": {"version": 1, "passingScore": 60}, "source": "learning_path_task"})
            for item in questions:
                db.add(PracticeQuestionModel(question_id=item["id"], question_set_id=quiz.id, session_id=path.session_id,
                    type=item["type"], stem=item["stem"], options=item["options"], correct=item["correct"],
                    explanation=item["explanation"], knowledge_points=item["knowledge_points"], difficulty=item["difficulty"]))
            db.commit()
        return {"status": "success", "data": {"status": "ready", "quiz": _safe_task_quiz(quiz, db)}}
    finally:
        db.close()


@router.post("/learning-path/tasks/{task_id}/quiz/submit")
def submit_task_quiz(task_id: str, body: QuizSubmitRequest, auth: AuthContext = Depends(require_auth)) -> dict:
    db = SessionLocal()
    try:
        _, entry, _ = _require_task_quiz_scope(db, task_id, body.model_dump(by_alias=True), auth.learner_id)
        quiz = require_owned_quiz(db, body.quiz_id, auth.learner_id)
        if quiz.path_id != body.path_id or quiz.stage_id != body.stage_id or quiz.section_id != task_id:
            raise HTTPException(status_code=409, detail="quiz does not belong to task")
        body.task_id = task_id
        return submit_quiz(body.quiz_id, body, auth)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Inline request schemas (follow the questions.py pattern)
# ═══════════════════════════════════════════════════════════════════════


class QuizCreateRequest(BaseModel):
    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: str = Field(default="knowledge_point", alias="scopeType")
    scope_id: Annotated[str | None, Field(alias="scopeId")] = None
    path_id: Annotated[str | None, Field(alias="pathId")] = None
    stage_id: Annotated[str | None, Field(alias="stageId")] = None
    chapter_id: Annotated[str | None, Field(alias="chapterId")] = None
    section_id: Annotated[str | None, Field(alias="sectionId")] = None
    knowledge_point_ids: list[str] | None = Field(default=None, alias="knowledgePointIds")
    difficulty: str = "medium"
    questions: list[dict] | None = None
    source: str = "llm_generated"


class ExamSetCreateRequest(BaseModel):
    session_id: str = Field(default="", alias="sessionId")
    title: str = ""
    scope_type: Annotated[str, Field(alias="scopeType")] = "chapter"
    scope_id: Annotated[str | None, Field(alias="scopeId")] = None
    path_id: Annotated[str | None, Field(alias="pathId")] = None
    stage_id: Annotated[str | None, Field(alias="stageId")] = None
    chapter_id: Annotated[str | None, Field(alias="chapterId")] = None
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
    quiz_id: Annotated[str | None, Field(alias="quizId")] = None
    exam_set_id: Annotated[str | None, Field(alias="examSetId")] = None
    max_score: Annotated[int, Field(alias="maxScore")] = 100


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
    requirements: str = ""
    path_id: Annotated[str | None, Field(alias="pathId")] = None
    stage_id: Annotated[str | None, Field(alias="stageId")] = None
    chapter_id: Annotated[str | None, Field(alias="chapterId")] = None
    section_id: Annotated[str | None, Field(alias="sectionId")] = None


class QuizSubmitRequest(BaseModel):
    """Payload for submitting all answers to a quiz at once.

    idempotency_key is REQUIRED — the client must generate a unique key per
    submission intent.  Same key + same answers → idempotent replay of the
    original result.  Same key + different answers → 409 Conflict.
    """
    session_id: str = Field(default="", alias="sessionId")
    answers: list[dict] = Field(default_factory=list)
    # Each answer: {"questionId": "...", "answer": "..."}
    idempotency_key: str = Field(..., alias="idempotencyKey")
    answers_revealed: bool = Field(default=False, alias="answersRevealed")
    client_submitted_at: str | None = Field(default=None, alias="clientSubmittedAt")
    path_id: str = Field(default="", alias="pathId")
    stage_id: str = Field(default="", alias="stageId")
    task_id: str = Field(default="", alias="taskId")
    quiz_id: str = Field(default="", alias="quizId")
    subject_id: str = Field(default="", alias="subjectId")
    day_id: str = Field(default="", alias="dayId")
    global_day_index: int | None = Field(default=None, alias="globalDayIndex")


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
        "questions": [],
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
        "subjectId": a.subject_id,
        "pathId": a.path_id,
        "stageId": a.stage_id,
        "taskId": a.task_id,
        "quizId": a.quiz_id,
        "examSetId": a.exam_set_id,
        "learnerId": a.learner_id,
        "answers": a.answers or [],
        "totalScore": a.total_score,
        "maxScore": a.max_score,
        "status": a.status,
        "attemptNumber": a.attempt_number,
        "idempotencyKey": a.idempotency_key,
        "assessmentEligible": a.assessment_eligible,
        "startedAt": a.started_at.isoformat() if a.started_at else None,
        "submittedAt": a.submitted_at.isoformat() if a.submitted_at else None,
        "gradedAt": a.graded_at.isoformat() if a.graded_at else None,
        "answersRevealedAt": a.answers_revealed_at.isoformat() if a.answers_revealed_at else None,
        "processingTaskId": a.processing_task_id,
        "diagnosisTaskId": a.diagnosis_task_id,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# Weakness recording helper
# ═══════════════════════════════════════════════════════════════════════


def _record_quiz_weaknesses(
    db, session_id: str, linked_questions: list, results: list[dict], quiz_title: str = ""
) -> list[dict]:
    """Aggregate wrong-answer knowledge points into weakness records.

    Groups errors by knowledge point, computes error counts/rates,
    and persists a ProfileSnapshotModel with the aggregated weaknesses.
    Returns the weakness list for inclusion in the API response.
    """
    from datetime import datetime as _dt

    wrong = [r for r in results if not r.get("isCorrect")]
    if not wrong:
        return []

    # Group by knowledge point
    kp_errors: dict[str, dict] = {}
    kp_total: dict[str, int] = {}
    for pq in linked_questions:
        kp_name = (pq.knowledge_points or [""])[0] if pq.knowledge_points else ""
        if not kp_name:
            continue
        kp_total[kp_name] = kp_total.get(kp_name, 0) + 1

    for r in wrong:
        kp = r.get("knowledgePoint", "")
        if not kp:
            continue
        if kp not in kp_errors:
            kp_errors[kp] = {
                "name": kp,
                "error_count": 0,
                "error_types": [],
                "grading_evidence": [],
            }
        kp_errors[kp]["error_count"] += 1
        et = r.get("errorType")
        if et and et not in kp_errors[kp]["error_types"]:
            kp_errors[kp]["error_types"].append(et)
        kp_errors[kp]["grading_evidence"].append({
            "questionId": r.get("questionId", ""),
            "studentAnswer": r.get("studentAnswer", ""),
            "correctAnswer": r.get("correctAnswer", ""),
            "errorType": et,
        })

    # Build weakness records
    weaknesses: list[dict] = []
    now_iso = _dt.now().isoformat()
    for kp_name, err in kp_errors.items():
        total = kp_total.get(kp_name, err["error_count"])
        error_rate = round(err["error_count"] / max(1, total), 2)
        mastery_est = max(10, 100 - int(error_rate * 100))
        weaknesses.append({
            "name": kp_name,
            "error_count": err["error_count"],
            "total_attempts": total,
            "error_rate": error_rate,
            "last_error_at": now_iso,
            "error_types": err["error_types"],
            "grading_evidence": err["grading_evidence"],
            "mastery_estimate": mastery_est,
            "suggested_action": f"建议重新学习{kp_name}，重点理解相关概念",
            "source": "quiz_grading",
            "quiz_title": quiz_title,
        })

    # Persist to ProfileSnapshotModel
    try:
        save_profile_snapshot(db, session_id, weaknesses=weaknesses)
    except Exception:
        pass  # Non-critical — weakness display still works from results

    return weaknesses


# ═══════════════════════════════════════════════════════════════════════
# Post-submit closed-loop assessment trigger
# ═══════════════════════════════════════════════════════════════════════


def _trigger_post_submit_assessment(
    session_id: str,
    quiz_title: str = "",
    quiz_score: int | None = None,
    weak_points: list[dict] | None = None,
) -> None:
    """Fire-and-forget: run diagnosis + recommendation update after quiz submission.

    Runs in a daemon thread so the HTTP response is never delayed.
    """
    if not session_id:
        return

    def _run() -> None:
        try:
            from app.services.assessment_loop import run_post_quiz_assessment

            run_post_quiz_assessment(
                session_id=session_id,
                quiz_title=quiz_title,
                quiz_score=quiz_score,
                weak_points=weak_points,
            )
        except Exception:
            logger.exception(
                "Post-submit assessment failed for session=%s", session_id,
            )

    from app.services.user_ai_config import copy_context_wrap

    # copy_context_wrap: 后台线程带入当前用户的 AI 凭据上下文
    threading.Thread(target=copy_context_wrap(_run), daemon=True).start()


def _create_diagnosis_refresh_task(
    session_id: str,
    learner_id: str,
    subject_id: str,
    attempt_id: str,
) -> str | None:
    """Create and start a ``diagnosis_refresh`` workflow task.

    Runs DiagnosisAgent and persists a new versioned snapshot.
    Best-effort — grading result is preserved even if task creation fails.

    Returns the ``task_id``, or ``None`` if creation failed.
    """
    try:
        from app.services.workflow_tasks import workflow_task_manager
        payload: dict[str, Any] = {
            "operation": "diagnosis_refresh",
            "sessionId": session_id,
            "subjectId": subject_id,
            "attemptId": attempt_id,
        }
        task, reused = workflow_task_manager.get_or_create(
            "diagnosis_refresh",
            learner_id,
            session_id,
            subject_id,
            payload=payload,
            metadata={"attempt_id": attempt_id},
            retry_payload=dict(payload),
        )
        if not reused:
            from app.routers.workflows import _runner_diagnosis_refresh
            runner = _runner_diagnosis_refresh(
                session_id, learner_id, subject_id, attempt_id,
            )
            workflow_task_manager.start(task, runner)
        return task.task_id
    except Exception:
        logger.exception(
            "Failed to create diagnosis_refresh task for attempt=%s",
            attempt_id,
        )
        return None


def _create_assessment_processing_task(
    session_id: str,
    learner_id: str,
    subject_id: str,
    attempt_id: str,
    *,
    quiz_id: str = "",
    exam_set_id: str = "",
) -> str | None:
    """Create and start an ``assessment_processing`` workflow task.

    Called after synchronous grading is committed so the task always
    sees a persisted attempt.  Task creation is best-effort — if it
    fails the graded result is still returned to the user.

    Returns the ``task_id``, or ``None`` if creation failed.
    """
    try:
        from app.services.workflow_tasks import workflow_task_manager
        payload: dict[str, Any] = {
            "operation": "assessment_processing",
            "sessionId": session_id,
            "subjectId": subject_id,
            "attemptId": attempt_id,
            "quizId": quiz_id,
            "examSetId": exam_set_id,
        }
        task, reused = workflow_task_manager.get_or_create(
            "assessment_processing",
            learner_id,
            session_id,
            subject_id,
            payload=payload,
            metadata={
                "attempt_id": attempt_id,
                "quiz_id": quiz_id,
                "exam_set_id": exam_set_id,
            },
            retry_payload=dict(payload),
        )
        if not reused:
            from app.routers.workflows import _runner_assessment_processing
            runner = _runner_assessment_processing(
                attempt_id, quiz_id, exam_set_id, session_id,
            )
            workflow_task_manager.start(task, runner)
        return task.task_id
    except Exception:
        logger.exception(
            "Failed to create assessment_processing task for attempt=%s",
            attempt_id,
        )
        return None


# ═══════════════════════════════════════════════════════════════════════
# Idempotency helpers
# ═══════════════════════════════════════════════════════════════════════


def _answers_match(stored: list | None, incoming: list | None) -> bool:
    """Compare two answer sets for idempotency content matching.

    Returns True when both sets contain the same questionId→answer mappings,
    regardless of order.  Used to decide whether a resubmission with the same
    idempotency key should replay the original result (True) or return 409
    (False).
    """
    if stored is None and incoming is None:
        return True
    if stored is None or incoming is None:
        return False
    if len(stored) != len(incoming):
        return False
    stored_map = {a.get("questionId", ""): a.get("answer", "") for a in stored}
    incoming_map = {a.get("questionId", ""): a.get("answer", "") for a in incoming}
    return stored_map == incoming_map


def _build_idempotent_response(
    db,
    attempt: AttemptModel,
    quiz_title: str = "",
    quiz_id: str = "",
    exam_set_id: str = "",
    session_id: str = "",
    assessment_eligible: bool = True,
) -> dict:
    """Reconstruct the post-submit response from a previously-graded attempt.

    Reads existing AnswerRecords from the database rather than re-grading,
    so the response is identical to what the original submission returned.
    Also recomputes knowledge-point results from stored answer records and
    writes a quiz_result event if one does not already exist.
    """
    answer_records = (
        db.query(AnswerRecordModel)
        .filter(AnswerRecordModel.attempt_id == attempt.attempt_id)
        .order_by(AnswerRecordModel.created_at)
        .all()
    )
    results = []
    answer_records_by_qid: dict[str, AnswerRecordModel] = {}
    for ar in answer_records:
        answer_records_by_qid[ar.question_id] = ar
        results.append({
            "questionId": ar.question_id,
            "studentAnswer": ar.student_answer,
            "isCorrect": (ar.total_score or 0) >= 60,
            "score": ar.total_score or 0,
            "maxScore": 100,
            "correctAnswer": "",
            "explanation": ar.error_explanation or "",
            "feedback": "",
            "errorType": ar.error_type,
            "errorLabel": ar.error_label,
            "knowledgePoint": "",
        })

    total_score = attempt.total_score or 0
    if total_score >= 80:
        suggestion = "mastered"
    elif total_score >= 50:
        suggestion = "in_progress"
    else:
        suggestion = "needs_review"

    # ── Resolve subject_id from attempt's session ─────────────────
    subject_id: str | None = attempt.subject_id
    if not subject_id and session_id:
        try:
            from app.db.models import SessionModel
            sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if sess and sess.subject_id:
                subject_id = sess.subject_id
        except Exception:
            pass

    # ── Compute knowledge-point results ──────────────────────────
    kp_results: list[dict] = []
    qset_id = quiz_id or exam_set_id
    if qset_id and session_id:
        linked = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == qset_id,
                PracticeQuestionModel.session_id == session_id,
            )
            .all()
        )
        if linked:
            kp_results = compute_all_results(
                db, linked, answer_records_by_qid,
                attempt.attempt_id, subject_id,
                assessment_eligible,
            )
            # ── Resolve curriculum scope from quiz/exam set ──
            _path_id: str | None = None
            _stage_id: str | None = None
            _chapter_id: str | None = None
            _section_id: str | None = None
            if quiz_id:
                qset = db.query(QuizModel).filter(QuizModel.id == quiz_id).first()
                if qset:
                    _path_id = qset.path_id
                    _stage_id = qset.stage_id
                    _chapter_id = qset.chapter_id
                    _section_id = qset.section_id
            elif exam_set_id:
                eset = db.query(ExamSetModel).filter(ExamSetModel.id == exam_set_id).first()
                if eset:
                    _path_id = eset.path_id
                    _stage_id = eset.stage_id
                    _chapter_id = eset.chapter_id

            # Write quiz_result event on replay if missing
            _write_quiz_result_event(
                db,
                attempt=attempt,
                session_id=session_id,
                learner_id=attempt.learner_id or "",
                subject_id=subject_id,
                kp_results=kp_results,
                quiz_id=quiz_id,
                exam_set_id=exam_set_id,
                path_id=_path_id,
                stage_id=_stage_id,
                chapter_id=_chapter_id,
                section_id=_section_id,
            )
            db.commit()  # persist fallback mappings + event

            for r in results:
                pq = next((q for q in linked if q.question_id == r["questionId"]), None)
                if pq is not None:
                    mappings = resolve_mappings(db, pq, subject_id=subject_id)
                    r["knowledgePoint"] = get_highest_weight_label(mappings, fallback="")

    return {
        "status": "success",
        "data": {
            "attempt": _attempt_dict(attempt),
            "results": results,
            "totalScore": total_score,
            "maxScore": attempt.max_score,
            "sectionStatusSuggestion": suggestion,
            "weakPoints": [],
            "idempotentReplay": True,
            "knowledgePointResults": kp_results,
            "processingTaskId": attempt.processing_task_id,
            "diagnosisTaskId": attempt.diagnosis_task_id,
        },
    }


def _write_quiz_result_event(
    db,
    *,
    attempt: AttemptModel,
    session_id: str,
    learner_id: str,
    subject_id: str | None,
    kp_results: list[dict],
    quiz_id: str = "",
    exam_set_id: str = "",
    path_id: str | None = None,
    stage_id: str | None = None,
    chapter_id: str | None = None,
    section_id: str | None = None,
) -> str:
    """Write the canonical quiz_result event for an attempt.  Idempotent.

    Returns the event_id.  Silently skips if an event already exists for
    this attempt (the unique index guarantees at most one event).
    """
    # ── Check for existing event ─────────────────────────────────
    if check_quiz_result_event_exists(db, attempt.attempt_id):
        existing = get_quiz_result_event(db, attempt.attempt_id)
        if existing and existing.event_id:
            return existing.event_id
        return ""

    # ── Build event ──────────────────────────────────────────────
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    total_score = attempt.total_score or 0
    max_score = attempt.max_score or 100
    normalized = total_score / max(max_score, 1.0)

    try:
        create_quiz_result_event(
            db,
            event_id=event_id,
            session_id=session_id,
            learner_id=learner_id,
            subject_id=subject_id,
            idempotency_key=attempt.idempotency_key or "",
            attempt_id=attempt.attempt_id,
            quiz_id=quiz_id or exam_set_id,
            total_score=total_score,
            max_score=max_score,
            normalized_score=normalized,
            assessment_eligible=attempt.assessment_eligible,
            knowledge_point_results=kp_results,
            path_id=path_id,
            stage_id=stage_id,
            chapter_id=chapter_id,
            section_id=section_id,
        )
        db.flush()
        return event_id
    except IntegrityError:
        # Race: another concurrent request already wrote it
        db.rollback()
        existing2 = get_quiz_result_event(db, attempt.attempt_id)
        if existing2 and existing2.event_id:
            return existing2.event_id
        return ""


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
        require_owned_session(db, body.session_id, auth.learner_id)
        _require_path_stage(body.model_dump(by_alias=True))
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
        quizzes = list_owned_quizzes(
            db, auth.learner_id, session_id=session_id, scope_type=scope_type,
        )
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
        quiz = require_owned_quiz(db, quiz_id, auth.learner_id)
        # Resolve linked questions from practice_questions table
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == quiz_id,
                PracticeQuestionModel.session_id == quiz.session_id,
            )
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
        quiz = require_owned_quiz(db, quiz_id, auth.learner_id)
        session_id = require_matching_session(quiz.session_id, body.session_id)
        _require_path_stage({"sessionId": session_id, "stageId": quiz.stage_id})
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "quiz_id": quiz_id,
            "max_score": body.max_score,
            "learner_id": auth.learner_id,
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
        quiz = require_owned_quiz(db, quiz_id, auth.learner_id)
        attempts = list_attempts(db, session_id=quiz.session_id, quiz_id=quiz_id)
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
        quiz = require_owned_quiz(db, quiz_id, auth.learner_id)
        # Resolve linked questions with answers revealed
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == quiz_id,
                PracticeQuestionModel.session_id == quiz.session_id,
            )
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
            attempt = require_parent_attempt(
                db, attempt_id, auth.learner_id, quiz_id=quiz_id,
            )
            if attempt:
                result["attempt"] = _attempt_dict(attempt)
                answer_records = db.query(AnswerRecordModel).filter(
                    AnswerRecordModel.attempt_id == attempt_id,
                    AnswerRecordModel.session_id == quiz.session_id,
                ).all()
                # Resolve knowledge points from linked questions
                kp_map = {pq.question_id: (pq.knowledge_points or [""])[0]
                          for pq in linked_questions}
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
                        "knowledgePoint": kp_map.get(ar.question_id, ""),
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
        require_owned_session(db, body.session_id, auth.learner_id)
        _require_path_stage(body.model_dump(by_alias=True))
        # ── Build LLM prompt ────────────────────────────────────
        kp_text = "\n".join(f"- {kp}" for kp in body.knowledge_points[:8])
        summary = body.lecture_summary[:2000] if body.lecture_summary else "暂无讲义摘要"

        # ── Inject student profile for personalization ──
        profile_hint = ""
        try:
            from app.services.conversation_state import conversation_store
            state = conversation_store.get(body.session_id)
            facts = state.facts
            parts = []
            if facts.get("knowledge_base"):
                parts.append(f"学生基础: {facts['knowledge_base']}")
            if facts.get("weak_points"):
                parts.append(f"薄弱点: {facts['weak_points']}")
            if facts.get("learning_goal"):
                parts.append(f"学习目标: {facts['learning_goal']}")
            if parts:
                profile_hint = "学生画像: " + "; ".join(parts) + "\n请针对学生的薄弱点适当增加相关题目的数量和深度。\n\n"
        except Exception:
            pass

        prompt = f"""你是 EduAgent 的试题生成智能体。根据以下小节内容生成 {3 + (body.difficulty == 'hard') * 2}～{4 + (body.difficulty == 'easy') * 2} 道练习题。

{profile_hint}
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
{"## 学生特殊要求（必须严格遵循，优先级最高）\\n" + body.requirements + "\\n" if body.requirements else ""}
## 输出格式（只输出 JSON）
{{"questions": [
  {{"question_id": "q1", "type": "choice", "stem": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct": "A", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}},
  {{"question_id": "q2", "type": "truefalse", "stem": "...", "correct": "true", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}},
  {{"question_id": "q3", "type": "shortanswer", "stem": "...", "reference_answer": "...", "explanation": "...", "knowledge_point": "...", "difficulty": "..."}}
]}}"""

        # ── Call LLM ───────────────────────────────────────────
        try:
            raw = _assessment_llm.chat(
                messages=[
                    {"role": "system", "content": "你是专业的试题生成专家。只输出JSON，不要Markdown包裹。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )
        except Exception as e:
            logger.error("Section quiz LLM call failed: %s", e)
            raise HTTPException(status_code=500, detail="题目生成失败，LLM 调用异常，请重试")

        parsed = parse_safe(raw)
        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or len(questions) == 0:
            logger.error("Quiz parse failed: parsed_keys=%s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__)
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

        # ── Persist questions AND build safe return list ────────
        safe_questions = []
        for q in questions:
            qid = f"q_{uuid.uuid4().hex[:12]}"
            pq = PracticeQuestionModel(
                question_id=qid,
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
            # Return the DB-assigned UUID so frontend can match on submit
            safe_questions.append({
                "questionId": qid,
                "type": q.get("type", "choice"),
                "stem": q.get("stem", ""),
                "options": q.get("options"),
                "difficulty": q.get("difficulty", body.difficulty),
                "knowledgePoints": [q.get("knowledge_point", "")] if q.get("knowledge_point") else body.knowledge_points,
            })
        db.commit()

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

    Idempotency: same idempotencyKey + same answers → replay original result.
    Same idempotencyKey + different answers → 409 Conflict.
    """
    db = SessionLocal()
    try:
        quiz = require_owned_quiz(db, quiz_id, auth.learner_id)
        session_id = require_matching_session(quiz.session_id, body.session_id)

        # ── Idempotency check ─────────────────────────────────
        existing = find_attempt_by_idempotency_key(
            db, auth.learner_id, body.idempotency_key, quiz_id=quiz_id,
        )
        if existing is not None:
            if existing.status in ("graded", "processing", "completed", "failed") and _answers_match(existing.answers, body.answers):
                return _build_idempotent_response(
                    db, existing, quiz_title=quiz.title,
                    quiz_id=quiz_id, session_id=session_id,
                    assessment_eligible=not body.answers_revealed,
                )
            raise HTTPException(
                status_code=409,
                detail="该 idempotencyKey 已用于不同的答案内容，请检查是否重复提交",
            )

        # ── Load linked questions with answers ──────────────────
        linked = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == quiz_id,
                PracticeQuestionModel.session_id == session_id,
            )
            .all()
        )
        if not linked:
            raise HTTPException(status_code=400, detail="该小测没有题目")
        questions_by_id = {pq.question_id: pq for pq in linked}

        # ── Compute attempt number (server-side) ───────────────
        attempt_no = get_next_attempt_number(
            db, auth.learner_id, quiz_id=quiz_id,
        )

        # ── Resolve subject_id from session ────────────────────
        subject_id = quiz.session_id  # fallback; resolve from session if possible
        try:
            from app.db.models import SessionModel
            sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if sess and sess.subject_id:
                subject_id = sess.subject_id
        except Exception:
            pass

        path_context = _assessment_path_context(db, quiz, body, auth.learner_id, subject_id)

        # ── Create attempt ─────────────────────────────────────
        try:
            attempt = create_attempt(db, {
                "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
                "session_id": session_id,
                "subject_id": subject_id,
                "quiz_id": quiz_id,
                "max_score": 100 * len(linked),
                "learner_id": auth.learner_id,
                "idempotency_key": body.idempotency_key,
                "attempt_number": attempt_no,
                "assessment_eligible": not body.answers_revealed,
                **(path_context or {}),
            })
        except Exception:
            # Race: another request inserted between our SELECT and INSERT.
            # The unique index caught it.  Re-query and reconcile.
            db.rollback()
            existing2 = find_attempt_by_idempotency_key(
                db, auth.learner_id, body.idempotency_key, quiz_id=quiz_id,
            )
            if existing2 is not None and existing2.status in ("graded", "processing", "completed", "failed") and _answers_match(existing2.answers, body.answers):
                return _build_idempotent_response(
                    db, existing2, quiz_title=quiz.title,
                    quiz_id=quiz_id, session_id=session_id,
                    assessment_eligible=not body.answers_revealed,
                )
            raise HTTPException(
                status_code=409,
                detail="检测到重复提交，与已有答案不一致",
            )

        # ── Grade each answer ──────────────────────────────────
        results = []
        total_score = 0
        max_possible = 0
        answer_records_by_qid: dict[str, AnswerRecordModel] = {}

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
                student = student_answer.strip().upper()
                if pq.type == "choice":
                    is_correct = student[:1] == correct[:1]
                else:
                    # Normalize both to boolean before comparing
                    student_bool = student in ("TRUE", "对", "正确", "YES", "T", "1")
                    correct_bool = correct in ("TRUE", "对", "正确", "YES", "T", "1")
                    is_correct = student_bool == correct_bool
                score = 100 if is_correct else 0
                error_type = None if is_correct else ("concept" if pq.type == "choice" else "misreading")
                expl = (pq.explanation or "").strip()
                if is_correct:
                    feedback = f"回答正确。{expl}" if expl else "回答正确"
                else:
                    correct_ans = str(pq.correct or "")
                    feedback = f"回答错误。正确答案：{correct_ans}。" + (f"\n解析：{expl}" if expl else "")
                error_expl = "" if is_correct else (expl or f"正确答案是 {correct_ans}")

                ar = AnswerRecordModel(
                    session_id=session_id,
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
                    ga = _assessment_factory.get("grading_agent")
                    if ga is not None:
                        grade_result = ga._grade_with_llm(q_dict, student_answer)
                        if grade_result is None:
                            grade_result = ga._rule_based_grading(q_dict, student_answer)
                    else:
                        grade_result = None
                except Exception:
                    # If GradingAgent unavailable, use simple fallback
                    expl = (pq.explanation or "").strip()
                    grade_result = {
                        "total_score": None,
                        "error_type": None,
                        "error_label": "需人工评阅",
                        "error_explanation": expl or "简答题需LLM评阅，当前不可用",
                        "suggestions": [],
                        "strengths": [],
                        "dimension_feedback": {"reasoning": f"简答题已记录。{expl}" if expl else "简答题已记录，需人工评阅"},
                    }

                score = grade_result.get("total_score", 0) or 0
                error_type = grade_result.get("error_type")
                if error_type == "null":
                    error_type = None
                feedback = grade_result.get("dimension_feedback", {}).get("reasoning", "") or f"参考解析：{pq.explanation}" if pq.explanation else ""
                error_expl = grade_result.get("error_explanation", "") or (pq.explanation or "")

                ar = AnswerRecordModel(
                    session_id=session_id,
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
            answer_records_by_qid[qid] = ar

            results.append({
                "questionId": qid,
                "studentAnswer": student_answer,
                "isCorrect": score >= 60,
                "score": score,
                "maxScore": 100,
                "correctAnswer": pq.correct,
                "explanation": pq.explanation or feedback,
                "feedback": feedback,
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

        # ── Compute knowledge-point results ────────────────────
        kp_results = compute_all_results(
            db, linked, answer_records_by_qid,
            attempt.attempt_id, subject_id,
            not body.answers_revealed,
        )
        # ── Write canonical quiz_result event ──────────────────
        _write_quiz_result_event(
            db,
            attempt=attempt,
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            kp_results=kp_results,
            quiz_id=quiz_id,
            path_id=quiz.path_id,
            stage_id=quiz.stage_id,
            chapter_id=quiz.chapter_id,
            section_id=quiz.section_id,
        )
        db.commit()  # persist fallback mappings + event
        prior_scores = [row[0] for row in db.query(AttemptModel.total_score).filter(
            AttemptModel.session_id == session_id, AttemptModel.path_id == (path_context or {}).get("path_id"),
            AttemptModel.stage_id == (path_context or {}).get("stage_id"), AttemptModel.task_id == (path_context or {}).get("task_id"),
            AttemptModel.total_score.isnot(None),
        ).all()]
        best_score = max(prior_scores or [avg_score])
        attempt_passed, ever_passed = avg_score >= 60, best_score >= 60
        path_completion = {"pathTaskCompleted": False, "stageCompleted": False, "nextStageUnlocked": False, "pathProgress": None}
        if path_context and ever_passed:
            from app.routers.product import complete_path_task
            path_completion = complete_path_task(
                db, session_id=session_id, subject_id=subject_id, source="assessment_submission", **path_context,
            )
            db.commit()

        # Update per-result knowledgePoint to highest-weight label
        for i, r in enumerate(results):
            pq = questions_by_id.get(r["questionId"])
            if pq is not None:
                mappings = resolve_mappings(db, pq, subject_id=subject_id)
                r["knowledgePoint"] = get_highest_weight_label(mappings, fallback="")

        # ── Compute section status suggestion ───────────────────
        if avg_score >= 80:
            suggestion = "mastered"
        elif avg_score >= 50:
            suggestion = "in_progress"
        else:
            suggestion = "needs_review"

        # ── Record weaknesses ─────────────────────────────────
        weak_points = _record_quiz_weaknesses(
            db, session_id, linked, results,
            quiz_title=quiz.title,
        )

        # ── Create assessment_processing workflow task ──────────
        processing_task_id = _create_assessment_processing_task(
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            attempt_id=attempt.attempt_id,
            quiz_id=quiz_id,
        )
        if processing_task_id:
            try:
                update_attempt(db, attempt.attempt_id, {
                    "processing_task_id": processing_task_id,
                })
                db.commit()
            except Exception:
                pass  # best-effort — grading result is preserved

        # ── Create diagnosis_refresh workflow task ───────────────
        diagnosis_task_id = _create_diagnosis_refresh_task(
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            attempt_id=attempt.attempt_id,
        )
        if diagnosis_task_id:
            try:
                update_attempt(db, attempt.attempt_id, {
                    "diagnosis_task_id": diagnosis_task_id,
                })
                db.commit()
            except Exception:
                pass  # best-effort

        # ── Trigger closed-loop assessment (fire-and-forget) ────
        _trigger_post_submit_assessment(
            session_id=session_id,
            quiz_title=quiz.title,
            quiz_score=avg_score,
            weak_points=weak_points,
        )

        response_attempt = _attempt_dict(get_attempt(db, attempt.attempt_id))
        response_attempt["processingTaskId"] = processing_task_id
        response_attempt["diagnosisTaskId"] = diagnosis_task_id

        return {
            "status": "success",
            "data": {
                "attempt": response_attempt,
                "results": results,
                "totalScore": avg_score,
                "maxScore": 100,
                "score": avg_score,
                "passingScore": 60,
                "passed": avg_score >= 60,
                "attemptPassed": attempt_passed,
                "everPassed": ever_passed,
                "latestAttemptScore": avg_score,
                "bestScore": best_score,
                "correctCount": sum(1 for item in results if item["isCorrect"]),
                "totalCount": len(linked),
                "sectionStatusSuggestion": suggestion,
                "weakPoints": weak_points,
                "knowledgePointResults": kp_results,
                "processingTaskId": processing_task_id,
                "diagnosisTaskId": diagnosis_task_id,
                "assessmentCompleted": True,
                **path_completion,
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
            raise HTTPException(status_code=400, detail="assessment parent required")
        if body.quiz_id and body.exam_set_id:
            raise HTTPException(status_code=400, detail="select one assessment")
        parent = (
            require_owned_quiz(db, body.quiz_id, auth.learner_id)
            if body.quiz_id
            else require_owned_exam_set(db, body.exam_set_id, auth.learner_id)
        )
        session_id = require_matching_session(parent.session_id, body.session_id)
        _require_path_stage({"sessionId": session_id, "stageId": getattr(parent, "stage_id", "")})
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "quiz_id": body.quiz_id,
            "exam_set_id": body.exam_set_id,
            "max_score": body.max_score,
            "learner_id": auth.learner_id,
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
        attempt = require_owned_attempt(db, attempt_id, auth.learner_id)
        # Resolve linked answer records
        answer_records = db.query(AnswerRecordModel).filter(
            AnswerRecordModel.attempt_id == attempt_id,
            AnswerRecordModel.session_id == attempt.session_id,
        ).all()
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
        require_owned_attempt(db, attempt_id, auth.learner_id)
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
        require_owned_attempt(db, attempt_id, auth.learner_id)
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
        require_owned_session(db, body.session_id, auth.learner_id)
        _require_path_stage(body.model_dump(by_alias=True))
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
        exam_sets = list_owned_exam_sets(
            db, auth.learner_id, session_id=session_id, scope_type=scope_type, status=status,
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
        exam_set = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        # Resolve linked questions
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == exam_set_id,
                PracticeQuestionModel.session_id == exam_set.session_id,
            )
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
        require_owned_exam_set(db, exam_set_id, auth.learner_id)
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
        exam_set = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        session_id = require_matching_session(exam_set.session_id, body.session_id)
        _require_path_stage({"sessionId": session_id, "stageId": exam_set.stage_id})
        attempt = create_attempt(db, {
            "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "exam_set_id": exam_set_id,
            "max_score": body.max_score or exam_set.total_score,
            "learner_id": auth.learner_id,
        })
        return {"status": "success", "data": {"attempt": _attempt_dict(attempt)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Exam Set generation
# ═══════════════════════════════════════════════════════════════════════


class ExamSetGenerateRequest(BaseModel):
    session_id: Annotated[str, Field(alias="sessionId")] = ""
    title: str = ""
    scope_type: Annotated[str, Field(alias="scopeType")] = "chapter"
    scope_id: Annotated[str | None, Field(alias="scopeId")] = None
    path_id: Annotated[str | None, Field(alias="pathId")] = None
    stage_id: Annotated[str | None, Field(alias="stageId")] = None
    chapter_id: Annotated[str | None, Field(alias="chapterId")] = None
    knowledge_point_ids: Annotated[list[str], Field(default_factory=list, alias="knowledgePointIds")]
    knowledge_points: Annotated[list[str], Field(default_factory=list, alias="knowledgePoints")]
    difficulty: str = "medium"
    question_count: Annotated[int, Field(alias="questionCount")] = 0


@router.post("/exam-sets/generate")
def generate_exam_set(
    body: ExamSetGenerateRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Generate an archived exam set via LLM for a chapter/stage/path.

    Question count is determined by scope_type if not specified:
    - chapter → 10–12, stage → 15–18, path → 20–25
    """
    db = SessionLocal()
    try:
        require_owned_session(db, body.session_id, auth.learner_id)
        # ── Determine question count ──────────────────────────
        if body.question_count > 0:
            count = min(body.question_count, 30)
        elif body.scope_type == "path":
            count = 22
        elif body.scope_type == "stage":
            count = 15
        else:
            count = 12

        # ── Build LLM prompt ──────────────────────────────────
        kp_list = body.knowledge_points or body.knowledge_point_ids
        kp_text = "\n".join(f"- {kp}" for kp in kp_list[:15]) if kp_list else "根据标题推断"
        difficulty_dist = {"easy": max(2, count // 4), "medium": count // 2, "hard": max(1, count // 4)}

        prompt = f"""你是 EduAgent 的试题生成智能体。请生成 {count} 道练习题组成一套完整题集。

## 题集标题
{body.title}

## 覆盖范围
范围类型：{body.scope_type}
知识点：{kp_text}

## 要求
- 难度：{body.difficulty}
- 难度分布：简单 {difficulty_dist['easy']} 道、中等 {difficulty_dist['medium']} 道、困难 {difficulty_dist['hard']} 道
- 题型混合：选择题（约50%）、判断题（约30%）、简答题（约20%）
- 选择题的干扰项要有迷惑性但明确错误
- 每道题的解析需写清楚正确答案和解题思路
- 题目之间不要重复，尽量覆盖不同子知识点

## 输出格式（只输出 JSON）
{{"questions": [{{"question_id": "q1", "type": "choice", "stem": "...", "options": ["A. ...", "B. ..."], "correct": "A", "explanation": "...", "knowledge_point": "...", "difficulty": "easy"}}, ...]}}"""

        # ── Call LLM ──────────────────────────────────────────
        # 20+ questions need more tokens: ~500 tokens/question with explanations
        max_tok = max(8000, count * 500)
        try:
            raw = _assessment_llm.chat(
                messages=[
                    {"role": "system", "content": "你是专业的试题生成专家。只输出JSON，不要Markdown包裹。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max_tok,
            )
        except Exception as e:
            logger.error("Exam set LLM call failed: %s", e)
            raise HTTPException(status_code=500, detail="题集生成失败，LLM 调用异常，请重试")

        logger.info("Exam set LLM raw response (first 200 chars): %s", raw[:200])
        parsed = parse_safe(raw)
        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or len(questions) == 0:
            logger.error("Exam set parse failed: parsed_keys=%s, questions_type=%s",
                         list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
                         type(questions).__name__ if questions else None)
            raise HTTPException(status_code=500, detail="题集生成失败，请重试")

        # ── Compute metadata ──────────────────────────────────
        questions = questions[:count]
        actual_count = len(questions)

        diff_counts = {"easy": 0, "medium": 0, "hard": 0}
        for q in questions:
            d = q.get("difficulty", "medium")
            if d in diff_counts:
                diff_counts[d] += 1

        estimated_minutes = actual_count * 3
        total_score = actual_count * 10

        # ── Create ExamSetModel ───────────────────────────────
        exam_id = f"exam_{uuid.uuid4().hex[:12]}"
        exam = save_exam_set(db, {
            "id": exam_id,
            "title": body.title or "综合题集",
            "session_id": body.session_id,
            "scope_type": body.scope_type,
            "scope_id": body.scope_id or body.chapter_id or body.stage_id or body.path_id,
            "path_id": body.path_id,
            "stage_id": body.stage_id,
            "chapter_id": body.chapter_id,
            "knowledge_point_ids": kp_list,
            "difficulty": body.difficulty,
            "difficulty_distribution": diff_counts,
            "question_count": actual_count,
            "questions": questions,
            "estimated_minutes": estimated_minutes,
            "total_score": total_score,
            "source": "llm_generated",
            "archive_policy": "archive",
        })

        # ── Persist questions AND build safe return list ──────
        safe_questions = []
        for q in questions:
            # Always generate unique IDs — LLM may return hardcoded placeholders
            qid = f"q_{uuid.uuid4().hex[:12]}"
            pq = PracticeQuestionModel(
                question_id=qid,
                question_set_id=exam_id,
                session_id=body.session_id,
                type=q.get("type", "choice"),
                stem=q.get("stem", ""),
                options=q.get("options"),
                correct=q.get("correct", ""),
                explanation=q.get("explanation", ""),
                difficulty=q.get("difficulty", body.difficulty),
                knowledge_points=[q.get("knowledge_point", "")] if q.get("knowledge_point") else [],
                reference_answer=q.get("reference_answer"),
                source="llm_generated",
                quality_status="passed",
            )
            db.add(pq)
            safe_questions.append({
                "questionId": qid,
                "type": q.get("type", "choice"),
                "stem": q.get("stem", ""),
                "options": q.get("options"),
                "difficulty": q.get("difficulty", body.difficulty),
                "knowledgePoints": [q.get("knowledge_point", "")] if q.get("knowledge_point") else [],
            })
        db.commit()

        return {
            "status": "success",
            "data": {
                "examSet": _exam_set_dict(exam),
                "questions": safe_questions,
            },
        }
    finally:
        db.close()


@router.post("/exam-sets/{exam_set_id}/submit")
def submit_exam_set(
    exam_set_id: str,
    body: QuizSubmitRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Submit all answers for an exam set — grade each and return results.

    Idempotency: same idempotencyKey + same answers → replay original result.
    Same idempotencyKey + different answers → 409 Conflict.
    """
    db = SessionLocal()
    try:
        exam_set = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        session_id = require_matching_session(exam_set.session_id, body.session_id)

        # ── Idempotency check ─────────────────────────────────
        existing = find_attempt_by_idempotency_key(
            db, auth.learner_id, body.idempotency_key, exam_set_id=exam_set_id,
        )
        if existing is not None:
            if existing.status in ("graded", "processing", "completed", "failed") and _answers_match(existing.answers, body.answers):
                return _build_idempotent_response(
                    db, existing, quiz_title=exam_set.title,
                    exam_set_id=exam_set_id, session_id=session_id,
                    assessment_eligible=not body.answers_revealed,
                )
            raise HTTPException(
                status_code=409,
                detail="该 idempotencyKey 已用于不同的答案内容，请检查是否重复提交",
            )

        linked = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == exam_set_id,
                PracticeQuestionModel.session_id == session_id,
            )
            .all()
        )
        if not linked:
            raise HTTPException(status_code=400, detail="该题集没有题目")
        questions_by_id = {pq.question_id: pq for pq in linked}

        # ── Compute attempt number (server-side) ───────────────
        attempt_no = get_next_attempt_number(
            db, auth.learner_id, exam_set_id=exam_set_id,
        )

        # ── Resolve subject_id from session ────────────────────
        subject_id = exam_set.session_id
        try:
            from app.db.models import SessionModel
            sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if sess and sess.subject_id:
                subject_id = sess.subject_id
        except Exception:
            pass

        path_context = _assessment_path_context(db, exam_set, body, auth.learner_id, subject_id)

        # ── Create attempt ─────────────────────────────────────
        try:
            attempt = create_attempt(db, {
                "attempt_id": f"att_{uuid.uuid4().hex[:12]}",
                "session_id": session_id,
                "subject_id": subject_id,
                "exam_set_id": exam_set_id,
                "max_score": 100 * len(linked),
                "learner_id": auth.learner_id,
                "idempotency_key": body.idempotency_key,
                "attempt_number": attempt_no,
                "assessment_eligible": not body.answers_revealed,
                **(path_context or {}),
            })
        except Exception:
            db.rollback()
            existing2 = find_attempt_by_idempotency_key(
                db, auth.learner_id, body.idempotency_key, exam_set_id=exam_set_id,
            )
            if existing2 is not None and existing2.status in ("graded", "processing", "completed", "failed") and _answers_match(existing2.answers, body.answers):
                return _build_idempotent_response(
                    db, existing2, quiz_title=exam_set.title,
                    exam_set_id=exam_set_id, session_id=session_id,
                    assessment_eligible=not body.answers_revealed,
                )
            raise HTTPException(
                status_code=409,
                detail="检测到重复提交，与已有答案不一致",
            )

        results = []
        total_score = 0
        answer_records_by_qid: dict[str, AnswerRecordModel] = {}

        for ans in body.answers:
            qid = ans.get("questionId", "")
            student_answer = str(ans.get("answer", "")).strip()
            pq = questions_by_id.get(qid)
            if pq is None:
                continue

            # Build question dict for grading agent
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

            if pq.type in ("choice", "truefalse"):
                correct = str(pq.correct or "").strip().upper()
                student = student_answer.strip().upper()
                if pq.type == "choice":
                    is_correct = student[:1] == correct[:1]
                else:
                    student_bool = student in ("TRUE", "对", "正确", "YES", "T", "1")
                    correct_bool = correct in ("TRUE", "对", "正确", "YES", "T", "1")
                    is_correct = student_bool == correct_bool
                score = 100 if is_correct else 0
                error_type = None if is_correct else ("concept" if pq.type == "choice" else "misreading")
                expl = (pq.explanation or "").strip()
                if is_correct:
                    feedback = f"回答正确。{expl}" if expl else "回答正确"
                else:
                    correct_ans = str(pq.correct or "")
                    feedback = f"回答错误。正确答案：{correct_ans}。" + (f"\n解析：{expl}" if expl else "")
                grade_result = None
                error_label = None if is_correct else ("概念错误" if pq.type == "choice" else "审题不清")
                error_expl = "" if is_correct else (expl or f"正确答案是 {correct_ans}")
                suggestions = [] if is_correct else ["建议复习相关知识点"]
                strengths = ["回答正确"] if is_correct else []
            else:
                # Shortanswer/fill — try GradingAgent LLM
                grade_result = None
                try:
                    ga = _assessment_factory.get("grading_agent")
                    if ga is not None:
                        grade_result = ga._grade_with_llm(q_dict, student_answer)
                        if grade_result is None:
                            grade_result = ga._rule_based_grading(q_dict, student_answer)
                except Exception:
                    grade_result = None

                if grade_result and grade_result.get("total_score") is not None:
                    score = grade_result.get("total_score", 50)
                    is_correct = score >= 60
                    error_type = grade_result.get("error_type")
                    if error_type == "null":
                        error_type = None
                    feedback = grade_result.get("dimension_feedback", {}).get("reasoning", "")
                    error_label = grade_result.get("error_label")
                    error_expl = grade_result.get("error_explanation", "")
                    suggestions = grade_result.get("suggestions", [])
                    strengths = grade_result.get("strengths", [])
                else:
                    score = 50
                    is_correct = True
                    error_type = None
                    expl = (pq.explanation or "").strip()
                    feedback = f"简答题已记录。{expl}" if expl else "简答题已记录，需人工评阅"
                    error_label = "需人工评阅"
                    error_expl = expl or "简答题需LLM评阅，当前不可用"
                    suggestions = []
                    strengths = []

            ar = AnswerRecordModel(
                session_id=session_id,
                question_id=qid,
                attempt_id=attempt.attempt_id,
                student_answer=student_answer,
                total_score=score,
                dimension_scores=grade_result.get("dimension_scores") if grade_result else None,
                dimension_feedback=grade_result.get("dimension_feedback") if grade_result else None,
                error_type=error_type,
                error_label=error_label,
                error_explanation=error_expl,
                suggestions=suggestions,
                strengths=strengths,
                source="auto_graded",
            )
            db.add(ar)
            total_score += score
            answer_records_by_qid[qid] = ar

            results.append({
                "questionId": qid,
                "studentAnswer": student_answer,
                "isCorrect": is_correct,
                "score": score,
                "maxScore": 100,
                "correctAnswer": pq.correct,
                "explanation": pq.explanation or feedback,
                "feedback": feedback,
                "errorType": error_type,
                "knowledgePoint": (pq.knowledge_points or [""])[0] if pq.knowledge_points else "",
            })

        avg_score = round(total_score / max(1, len(results) * 100) * 100)
        update_attempt(db, attempt.attempt_id, {
            "answers": body.answers,
            "total_score": avg_score,
            "status": "graded",
        })

        update_exam_set(db, exam_set_id, {"status": "completed"})
        db.commit()

        # ── Compute knowledge-point results ────────────────────
        kp_results = compute_all_results(
            db, linked, answer_records_by_qid,
            attempt.attempt_id, subject_id,
            not body.answers_revealed,
        )
        # ── Write canonical quiz_result event ──────────────────
        _write_quiz_result_event(
            db,
            attempt=attempt,
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            kp_results=kp_results,
            exam_set_id=exam_set_id,
            path_id=exam_set.path_id,
            stage_id=exam_set.stage_id,
            chapter_id=exam_set.chapter_id,
        )
        db.commit()  # persist fallback mappings + event
        path_completion = {"pathTaskCompleted": False, "stageCompleted": False, "nextStageUnlocked": False, "pathProgress": None}
        if path_context:
            from app.routers.product import complete_path_task
            path_completion = complete_path_task(
                db, session_id=session_id, subject_id=subject_id, source="assessment_submission", **path_context,
            )
            db.commit()

        # Update per-result knowledgePoint to highest-weight label
        for i, r in enumerate(results):
            pq = questions_by_id.get(r["questionId"])
            if pq is not None:
                mappings = resolve_mappings(db, pq, subject_id=subject_id)
                r["knowledgePoint"] = get_highest_weight_label(mappings, fallback="")

        weak_points = _record_quiz_weaknesses(
            db, session_id, linked, results, quiz_title=exam_set.title,
        )

        suggestion = "mastered" if avg_score >= 80 else ("in_progress" if avg_score >= 50 else "needs_review")

        # ── Create assessment_processing workflow task ──────────
        processing_task_id = _create_assessment_processing_task(
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            attempt_id=attempt.attempt_id,
            exam_set_id=exam_set_id,
        )
        if processing_task_id:
            try:
                update_attempt(db, attempt.attempt_id, {
                    "processing_task_id": processing_task_id,
                })
                db.commit()
            except Exception:
                pass  # best-effort

        # ── Create diagnosis_refresh workflow task ───────────────
        diagnosis_task_id = _create_diagnosis_refresh_task(
            session_id=session_id,
            learner_id=auth.learner_id,
            subject_id=subject_id,
            attempt_id=attempt.attempt_id,
        )
        if diagnosis_task_id:
            try:
                update_attempt(db, attempt.attempt_id, {
                    "diagnosis_task_id": diagnosis_task_id,
                })
                db.commit()
            except Exception:
                pass  # best-effort

        # ── Trigger closed-loop assessment (fire-and-forget) ────
        _trigger_post_submit_assessment(
            session_id=session_id,
            quiz_title=exam_set.title,
            quiz_score=avg_score,
            weak_points=weak_points,
        )

        response_attempt = _attempt_dict(get_attempt(db, attempt.attempt_id))
        response_attempt["processingTaskId"] = processing_task_id
        response_attempt["diagnosisTaskId"] = diagnosis_task_id

        return {
            "status": "success",
            "data": {
                "attempt": response_attempt,
                "results": results,
                "totalScore": avg_score,
                "maxScore": 100,
                "sectionStatusSuggestion": suggestion,
                "weakPoints": weak_points,
                "knowledgePointResults": kp_results,
                "processingTaskId": processing_task_id,
                "diagnosisTaskId": diagnosis_task_id,
                "assessmentCompleted": True,
                **path_completion,
            },
        }
    finally:
        db.close()


@router.get("/exam-sets/{exam_set_id}/results")
def get_exam_set_results(
    exam_set_id: str,
    auth: AuthContext = Depends(require_auth),
    attempt_id: str = Query(default="", alias="attemptId"),
) -> dict:
    """Get exam set results with answers and grading after submission."""
    db = SessionLocal()
    try:
        exam_set = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        linked_questions = (
            db.query(PracticeQuestionModel)
            .filter(
                PracticeQuestionModel.question_set_id == exam_set_id,
                PracticeQuestionModel.session_id == exam_set.session_id,
            )
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

        result = _exam_set_dict(exam_set)
        result["linkedQuestions"] = question_list

        if attempt_id:
            attempt = require_parent_attempt(
                db, attempt_id, auth.learner_id, exam_set_id=exam_set_id,
            )
            if attempt:
                result["attempt"] = _attempt_dict(attempt)
                answer_records = db.query(AnswerRecordModel).filter(
                    AnswerRecordModel.attempt_id == attempt_id,
                    AnswerRecordModel.session_id == exam_set.session_id,
                ).all()
                kp_map = {pq.question_id: (pq.knowledge_points or [""])[0] for pq in linked_questions}
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
                        "knowledgePoint": kp_map.get(ar.question_id, ""),
                    })

        return {"status": "success", "data": {"examSet": result}}
    finally:
        db.close()


@router.get("/exam-sets/{exam_set_id}/attempts")
def list_exam_set_attempts(
    exam_set_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """List all attempts for an exam set."""
    db = SessionLocal()
    try:
        exam_set = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        attempts = list_attempts(
            db, session_id=exam_set.session_id, exam_set_id=exam_set_id,
        )
        return {
            "status": "success",
            "data": {"attempts": [_attempt_dict(a) for a in attempts]},
        }
    finally:
        db.close()


@router.delete("/exam-sets/{exam_set_id}")
def delete_exam_set(
    exam_set_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Delete an exam set and its associated records."""
    db = SessionLocal()
    try:
        es = require_owned_exam_set(db, exam_set_id, auth.learner_id)
        # Delete related answer records, attempts, and practice questions
        db.query(AnswerRecordModel).filter(
            AnswerRecordModel.attempt_id.in_(
                db.query(AttemptModel.attempt_id).filter(AttemptModel.exam_set_id == exam_set_id)
            )
        ).delete(synchronize_session=False)
        db.query(AttemptModel).filter(AttemptModel.exam_set_id == exam_set_id).delete(synchronize_session=False)
        db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_set_id == exam_set_id).delete(synchronize_session=False)
        db.delete(es)
        db.commit()
        return {"status": "success", "data": {"deleted": True}}
    finally:
        db.close()


@router.delete("/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Delete a quiz and its associated records."""
    db = SessionLocal()
    try:
        q = require_owned_quiz(db, quiz_id, auth.learner_id)
        db.query(AnswerRecordModel).filter(
            AnswerRecordModel.attempt_id.in_(
                db.query(AttemptModel.attempt_id).filter(AttemptModel.quiz_id == quiz_id)
            )
        ).delete(synchronize_session=False)
        db.query(AttemptModel).filter(AttemptModel.quiz_id == quiz_id).delete(synchronize_session=False)
        db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_set_id == quiz_id).delete(synchronize_session=False)
        db.delete(q)
        db.commit()
        return {"status": "success", "data": {"deleted": True}}
    finally:
        db.close()
