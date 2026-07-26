"""Deterministic v1 review-task proposal for a failed path quiz."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any

from app.db.models import AnswerRecordModel, AttemptModel, LearningEventModel, LearningPathModel, PracticeQuestionModel, SessionModel
from app.services.conversation_state import conversation_store


PASS_THRESHOLD = 60


def _task_id(learner_id: str, session_id: str, path_id: str, attempt_id: str) -> str:
    raw = f"{learner_id}|{session_id}|{path_id}|{attempt_id}|adaptive_review_v1"
    return "review_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _weak_points(db, attempt: AttemptModel) -> list[str]:
    answers = db.query(AnswerRecordModel).filter(AnswerRecordModel.attempt_id == attempt.attempt_id).all()
    questions = {item.question_id: item for item in db.query(PracticeQuestionModel).filter(
        PracticeQuestionModel.question_set_id == attempt.quiz_id,
        PracticeQuestionModel.session_id == attempt.session_id,
    ).all()}
    return list(dict.fromkeys(
        str((questions.get(answer.question_id).knowledge_points or [""])[0]).strip()
        for answer in answers if (answer.total_score or 0) < PASS_THRESHOLD and questions.get(answer.question_id)
        and (questions[answer.question_id].knowledge_points or [""])[0]
    ))


def _find_task(stages: list[dict], stage_id: str, task_id: str) -> tuple[dict, dict | None, dict] | None:
    for stage in stages:
        if str(stage.get("id") or stage.get("stage_id") or "") != stage_id:
            continue
        for day in stage.get("days", []) if isinstance(stage.get("days"), list) else []:
            for task in day.get("tasks", []) if isinstance(day, dict) else []:
                if str(task.get("id") or task.get("task_id") or "") == task_id:
                    return stage, day, task
        for task in stage.get("tasks", []) if isinstance(stage.get("tasks"), list) else []:
            if str(task.get("id") or task.get("task_id") or "") == task_id:
                return stage, None, task
    return None


def create_failed_quiz_revision(db, attempt: AttemptModel) -> dict[str, Any] | None:
    """Create one review proposal from a persisted, failed task-quiz attempt."""
    if not attempt.path_id or not attempt.stage_id or not attempt.task_id or (attempt.total_score or 0) >= PASS_THRESHOLD:
        return None
    session = db.get(SessionModel, attempt.session_id)
    path = db.query(LearningPathModel).filter(
        LearningPathModel.id == attempt.path_id, LearningPathModel.session_id == attempt.session_id,
    ).first()
    if not path or not session or session.learner_id != attempt.learner_id or not isinstance(path.stages, list):
        return None
    trigger_key = f"{attempt.learner_id}|{attempt.session_id}|{path.id}|{attempt.attempt_id}|adaptive_review_v1"
    if isinstance(path.pending_revision, dict) and path.pending_revision.get("idempotency_key") == trigger_key:
        return path.pending_revision
    located = _find_task(path.stages, attempt.stage_id, attempt.task_id)
    if not located:
        return None
    stage, day, failed_task = located
    review_id = _task_id(attempt.learner_id or "", attempt.session_id, path.id, attempt.attempt_id)
    all_ids = {str(task.get("id") or task.get("task_id") or "") for item in path.stages for task in (
        [t for d in item.get("days", []) for t in d.get("tasks", [])] if item.get("days") else item.get("tasks", [])
    ) if isinstance(task, dict)}
    if review_id in all_ids:
        return None
    weak_points = _weak_points(db, attempt) or [str(failed_task.get("title") or "review")]
    event = db.query(LearningEventModel).filter(
        LearningEventModel.attempt_id == attempt.attempt_id, LearningEventModel.event_type == "quiz_result",
    ).first()
    timestamp = (event.created_at if event else datetime.now(timezone.utc)).isoformat()
    proposed = copy.deepcopy(path.stages)
    target = _find_task(proposed, attempt.stage_id, attempt.task_id)
    assert target is not None
    target_stage, target_day, _ = target
    review = {
        "id": review_id, "task_id": review_id, "type": "review", "task_type": "review",
        "title": f"Review: {weak_points[0]}", "knowledge_points": weak_points,
        "estimated_minutes": 15, "status": "available", "adaptiveRevision": True,
        "sourceAttemptId": attempt.attempt_id, "originalTaskId": attempt.task_id,
    }
    if target_day is not None:
        target_day.setdefault("tasks", []).append(review)
    else:
        target_stage.setdefault("tasks", []).append(review)
    evidence = {
        "learnerId": attempt.learner_id, "subjectId": attempt.subject_id or session.subject_id,
        "sessionId": attempt.session_id, "pathId": path.id, "stageId": attempt.stage_id,
        "taskId": attempt.task_id, "quizAttemptId": attempt.attempt_id, "score": attempt.total_score,
        "passThreshold": PASS_THRESHOLD, "attemptIndex": attempt.attempt_number,
        "bestScore": attempt.total_score, "weakKPs": weak_points, "eventTimestamp": timestamp,
        "evidenceType": "quiz_result", "triggerReason": "fresh quiz score below passing threshold",
    }
    trace = [
        {"stage": name, "status": "completed", "durationMs": 0, "service": service,
         "inputSummary": "failed task quiz", "outputSummary": output, "fallbackUsed": fallback, "errorCode": ""}
        for name, service, output, fallback in [
            ("QUIZ_ATTEMPT_RECORDED", "assessment", "attempt persisted", False),
            ("LEARNING_EVIDENCE_CREATED", "learning_events", "quiz_result evidence", False),
            ("DIAGNOSIS_UPDATED", "DiagnosisAgent", "weak knowledge points updated", False),
            ("REVISION_GENERATION_STARTED", "adaptive_revision", "review proposal started", True),
            ("REVISION_GENERATED", "adaptive_revision", "one review task added", True),
            ("REVISION_PENDING", "ConversationStore", "awaiting learner decision", True),
        ]
    ]
    explainability = {
        "summary": "Add one focused review task after the failed quiz.", "reason": evidence["triggerReason"],
        "evidence": evidence, "expectedOutcome": "Reinforce the weakest knowledge point before continuing.",
        "affectedStageIds": [attempt.stage_id], "affectedTaskIds": [attempt.task_id, review_id],
        "addedTasks": [review], "removedTasks": [], "durationDelta": 15, "riskFlags": ["adds_time"],
        "generatedBy": "adaptive_revision_v1_fallback", "triggerEventId": event.event_id if event else "",
    }
    active = conversation_store.get(attempt.session_id).pending_revision
    if active and active.get("idempotency_key") != trigger_key:
        active["status"] = "superseded"
        active["superseded_at"] = datetime.now(timezone.utc).isoformat()
        conversation_store.get(attempt.session_id).pending_revision = None
        path.pending_revision = None
        db.commit()
    revision = conversation_store.set_pending_revision(
        attempt.session_id, proposed, {"summary": explainability["summary"], "changed_stages": [attempt.stage_id],
        "changed_tasks": [review_id], "addedTasks": [review], "removedTasks": [], "total_duration_change": 15},
        reason=explainability["reason"], path_id=path.id, subject_id=attempt.subject_id or session.subject_id,
        trigger_source="assessment", trigger_id=attempt.attempt_id, revision_id=f"rev_{review_id[7:]}",
        idempotency_key=trigger_key, explainability=explainability, workflow_trace=trace,
    )
    return revision
