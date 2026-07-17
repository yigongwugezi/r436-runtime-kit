"""Authenticated API for reusable long-running workflow progress."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.middleware.auth import AuthContext, reject_parent
from app.services.workflow_tasks import TERMINAL_STATUSES, WorkflowTask, workflow_task_manager

router = APIRouter(prefix="/workflows", tags=["workflows"])

SUPPORTED_WORKFLOWS = {
    "resource_search", "generated_resource", "generated_resource_regeneration",
    "profile_sync", "profile_rebuild", "learning_path_generation", "lecture_generation", "general_resource_generation", "video_generation",
    "assessment_processing", "diagnosis_refresh",
}
CANCELLABLE_WORKFLOWS = {
    "resource_search", "generated_resource", "generated_resource_regeneration",
    "lecture_generation", "general_resource_generation",
    "video_generation", "learning_path_generation",
    "assessment_processing", "diagnosis_refresh",
}


def _session(payload: dict[str, Any], auth: AuthContext) -> tuple[str, str]:
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    subject_id = str(payload.get("subjectId") or payload.get("subject_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId required")
    db = SessionLocal()
    try:
        row = db.get(SessionModel, session_id)
        if row is not None:
            # Allow anonymous→real learner transition (normal login flow)
            from app.db.repository import try_upgrade_anonymous_session
            try_upgrade_anonymous_session(db, session_id, auth.learner_id)
            db.refresh(row)
            if row.learner_id and row.learner_id != auth.learner_id:
                raise HTTPException(status_code=403, detail="无权访问该任务")
    finally:
        db.close()
    return session_id, subject_id


def _emit_stage(task: WorkflowTask, stage_id: str, label: str, status: str = "running", **data: Any) -> None:
    workflow_task_manager.check_cancelled(task)
    workflow_task_manager.emit(task, f"stage_{'completed' if status == 'completed' else 'started'}", stage_id, status, label=label, **data)


def _runner_diagnosis_refresh(
    session_id: str, learner_id: str, subject_id: str, attempt_id: str = "",
):
    """Build a runner that isolates the DiagnosisAgent → snapshot persistence step."""
    def run(workflow_task: WorkflowTask) -> Any:
        wfm = workflow_task_manager

        # ── Stage 1: Build diagnosis context ──────────────────────
        wfm.emit(workflow_task, "stage_started", "context", "running",
                 label="正在收集学习数据")
        from app.services.assessment_loop import _build_diagnosis_context
        diagnosis_context = _build_diagnosis_context(session_id)

        # ── Stage 2: Run DiagnosisAgent ──────────────────────────
        wfm.check_cancelled(workflow_task)
        wfm.emit(workflow_task, "stage_started", "analysis", "running",
                 label="正在运行诊断分析")
        diagnosis_agent = None
        try:
            from app.services.assessment_loop import _get_or_create_factory
            factory = _get_or_create_factory()
            diagnosis_agent = factory.get("diagnosis_agent")
        except Exception:
            pass
        if diagnosis_agent is None:
            from app.agents.diagnosis_agent import DiagnosisAgent
            diagnosis_agent = DiagnosisAgent(mock_data={})
        result = diagnosis_agent.run(diagnosis_context)
        new_diagnosis = result.get("diagnosis", {})

        # ── Stage 3: Persist snapshot + evidence ─────────────────
        wfm.check_cancelled(workflow_task)
        wfm.emit(workflow_task, "stage_started", "persist", "running",
                 label="正在保存诊断快照")
        from app.db.engine import SessionLocal
        from app.services.diagnosis_snapshot_service import persist_diagnosis_result
        db = SessionLocal()
        try:
            snap = persist_diagnosis_result(
                db,
                learner_id=learner_id,
                subject_id=subject_id,
                session_id=session_id,
                diagnosis_result=new_diagnosis,
                source_attempt_ids=[attempt_id] if attempt_id else [],
                active_task_id=workflow_task.task_id,
            )
            db.commit()
            wfm.emit(workflow_task, "stage_completed", "persist", "completed",
                     label="诊断快照已保存",
                     safe_metadata={
                         "snapshotId": snap.diagnosis_snapshot_id,
                         "version": snap.version,
                     })
        except Exception as exc:
            db.rollback()
            raise
        finally:
            db.close()

        return {
            "status": "completed",
            "snapshotId": snap.diagnosis_snapshot_id,
            "version": snap.version,
        }
    return run


def _runner_assessment_processing(attempt_id: str, quiz_id: str, exam_set_id: str, session_id: str):
    """Build a runner that wraps the post-quiz assessment loop with SSE progress."""
    def run(workflow_task: WorkflowTask) -> Any:
        from app.db.engine import SessionLocal
        from app.db.models import AttemptModel
        from app.db.repository import update_attempt

        wfm = workflow_task_manager

        # ── Stage 1: Verify attempt is persisted ────────────────────
        wfm.emit(workflow_task, "stage_started", "verification", "running",
                 label="正在验证提交记录")
        db = SessionLocal()
        try:
            attempt = db.query(AttemptModel).filter(
                AttemptModel.attempt_id == attempt_id,
            ).first()
            if attempt is None:
                raise RuntimeError("Attempt not found")

            update_attempt(db, attempt_id, {"status": "processing"})
            db.commit()
            wfm.emit(workflow_task, "stage_completed", "verification", "completed",
                     label="提交记录已验证")

            # ── Stage 2: KP analysis (already done sync — signal complete) ──
            wfm.emit(workflow_task, "stage_completed", "kp_analysis", "completed",
                     label="知识点分析已完成")

            # ── Stage 3: Run diagnosis + profile + resource loop ────
            wfm.check_cancelled(workflow_task)
            wfm.emit(workflow_task, "stage_started", "diagnosis", "running",
                     label="正在更新学习诊断")
            from app.services.assessment_loop import run_post_quiz_assessment
            quiz_title = ""
            try:
                if quiz_id:
                    from app.db.models import QuizModel
                    q = db.query(QuizModel).filter(QuizModel.id == quiz_id).first()
                    if q:
                        quiz_title = q.title or ""
                elif exam_set_id:
                    from app.db.models import ExamSetModel
                    e = db.query(ExamSetModel).filter(ExamSetModel.id == exam_set_id).first()
                    if e:
                        quiz_title = e.title or ""
            except Exception:
                pass

            run_post_quiz_assessment(
                session_id=session_id,
                quiz_title=quiz_title,
                quiz_score=attempt.total_score,
                weak_points=None,
            )
            wfm.check_cancelled(workflow_task)
            wfm.emit(workflow_task, "stage_completed", "diagnosis", "completed",
                     label="诊断已更新")

            # ── Stage 4: Finalize ──────────────────────────────────
            db2 = SessionLocal()
            try:
                update_attempt(db2, attempt_id, {"status": "completed"})
                db2.commit()
            finally:
                db2.close()

            wfm.emit(workflow_task, "stage_completed", "finalize", "completed",
                     label="处理完成")
        finally:
            db.close()

        return {"status": "completed", "attempt_id": attempt_id}
    return run


def _runner(workflow_type: str, payload: dict[str, Any], auth: AuthContext):
    def run(task: WorkflowTask) -> Any:
        # Runtime import avoids coupling the product router back to this API.
        from app.routers import product

        if workflow_type == "diagnosis_refresh":
            return _runner_diagnosis_refresh(
                task.session_scope, task.user_scope, task.subject_scope,
                str(payload.get("attemptId") or payload.get("attempt_id") or "").strip(),
            )(task)

        if workflow_type == "assessment_processing":
            attempt_id = str(payload.get("attemptId") or payload.get("attempt_id") or "").strip()
            quiz_id = str(payload.get("quizId") or payload.get("quiz_id") or "").strip()
            exam_set_id = str(payload.get("examSetId") or payload.get("exam_set_id") or "").strip()
            return _runner_assessment_processing(
                attempt_id, quiz_id, exam_set_id, task.session_scope,
            )(task)

        if workflow_type == "resource_search":
            section_id = str(payload.get("sectionId") or "").strip()
            labels = {
                "topic_analysis": "分析搜索主题", "cache": "检查已有结果",
                "primary_search": "搜索首选来源", "fallback_search": "搜索备用来源",
                "stale_cache": "读取可用缓存", "quality_filter": "检查候选资源",
                "personalized_ranking": "排序学习资源", "completed": "搜索完成",
            }

            def progress(event: dict[str, Any]) -> None:
                workflow_task_manager.check_cancelled(task)
                stage = str(event.get("stage") or "search")
                status = str(event.get("status") or "running")
                workflow_task_manager.emit(
                    task, "stage_completed" if status == "completed" else "stage_progress",
                    stage, status, label=labels.get(stage, "搜索学习资源"),
                    used_fallback=bool(event.get("fallback_used")),
                    safe_metadata={key: event[key] for key in ("candidate_count", "result_count", "source_count") if key in event},
                )

            result = product._recommend_section_resources(section_id, payload, progress, task.cancel_event)
            workflow_task_manager.check_cancelled(task)
            return product._product_response({"recommendations": result}, session_id=task.session_scope, source="search")

        if workflow_type == "video_generation":
            section_id = str(payload.get("sectionId") or "").strip()
            if not section_id:
                raise ValueError("sectionId required")
            labels = {
                "rag_retrieval": "检索知识内容", "outline": "生成教学大纲",
                "storyboard": "设计分镜脚本", "rendering": "生成动画视频",
                "critic": "评审优化画面", "narration": "生成讲解配音",
                "saving": "保存到资源库", "completed": "视频生成完成",
            }
            def progress(event):
                workflow_task_manager.check_cancelled(task)
                stage = str(event.get("stage") or "video")
                status = str(event.get("status") or "running")
                completed = int(event.get("completed_units") or 0)
                total = int(event.get("total_units") or 5)
                workflow_task_manager.emit(
                    task, "stage_completed" if status == "completed" else "stage_progress",
                    stage, status, label=labels.get(stage, "生成视频"),
                    completed_units=completed, total_units=total,
                )
            section_title = str(payload.get("sectionTitle") or "").strip()
            course_name = str(payload.get("courseName") or section_title)
            kp_text = str(payload.get("knowledgePoints") or "")
            result = product._generate_video_sync(
                section_id, section_title, course_name, kp_text,
                task.session_scope, progress, task.cancel_event
            )
            workflow_task_manager.check_cancelled(task)
            if result.get("status") == "error":
                raise RuntimeError(result.get("message", "视频生成失败"))
            video_url = str(((result.get("data") or {}).get("video") or {}).get("url") or "")
            if video_url:
                workflow_task_manager.emit(task, "preview_updated", "saving", "completed",
                    label="视频已生成", text_delta=video_url)
            return result

        _emit_stage(task, "input_validation", "检查任务输入", "completed")
        _emit_stage(task, "execution", {
            "generated_resource": "生成结构化学习资源",
            "generated_resource_regeneration": "根据反馈重新生成资源",
            "profile_sync": "提取对话中的画像事实",
            "profile_rebuild": "重建学习画像",
            "learning_path_generation": "规划学习路径",
            "lecture_generation": "生成讲义内容",
            "general_resource_generation": "生成指定类型的学习资源",
        }[workflow_type])

        try:
            if workflow_type == "general_resource_generation":
                result = product._generate_general_resource(payload, task)
            elif workflow_type in {"generated_resource", "generated_resource_regeneration"}:
                result = product._generate_section_resource(str(payload.get("sectionId") or ""), payload, task)
            elif workflow_type == "profile_sync":
                result = product.sync_profile_from_conversation(str(payload.get("subjectId") or ""), payload, auth)
            elif workflow_type == "profile_rebuild":
                result = product.build_profile(payload, auth)
            elif workflow_type == "learning_path_generation":
                result = product.generate_learning_path(payload, auth)
            else:
                result = product._generate_section_lecture(str(payload.get("sectionId") or ""), payload, task)
        except RuntimeError as exc:
            if str(exc) == "provider_not_configured":
                task.error_code = "PROVIDER_NOT_CONFIGURED"
                task.safe_error_message = "所选的多媒体生成能力尚未配置，未生成伪造资源。"
            raise

        workflow_task_manager.check_cancelled(task)
        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError("workflow returned error")
        preview = ""
        if workflow_type in {"generated_resource", "generated_resource_regeneration", "general_resource_generation"}:
            preview = str(((result.get("data") or {}).get("resource") or {}).get("content") or "")
        elif workflow_type == "lecture_generation":
            preview = str(((result.get("data") or {}).get("lecture") or {}).get("content") or "")
        if preview:
            workflow_task_manager.emit(task, "preview_updated", "content_validation", "completed", label="内容已生成，正在确认最终结果", text_delta=preview)
        _emit_stage(task, "save_result", "结果已安全保存", "completed")
        return result

    return run


def _start(workflow_type: str, payload: dict[str, Any], auth: AuthContext) -> tuple[WorkflowTask, bool]:
    if workflow_type not in SUPPORTED_WORKFLOWS:
        raise HTTPException(status_code=404, detail="unsupported workflow type")
    if workflow_type == "general_resource_generation":
        # Validate before a runner or task is created; resource type is a contract field, not prompt text.
        from app.routers import product
        payload = product.normalize_general_resource_request(payload)
    elif workflow_type == "resource_search":
        from app.routers import product
        try:
            payload = product.normalize_resource_search_request(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    session_id, subject_id = _session(payload, auth)
    safe_metadata = {"resource_type": str(payload.get("resourceType") or payload.get("type") or "")[:40]}
    try:
        task, reused_existing = workflow_task_manager.get_or_create(
            workflow_type, auth.learner_id, session_id, subject_id,
            payload=payload, metadata=safe_metadata, retry_payload=dict(payload),
        )
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if not reused_existing:
        workflow_task_manager.start(task, _runner(workflow_type, dict(payload), auth))
    return task, reused_existing


@router.post("/{workflow_type}/start")
def start_workflow(workflow_type: str, payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    task, reused_existing = _start(workflow_type, payload, auth)
    base = f"/api/workflows/{task.task_id}"
    return {
        "task_id": task.task_id, "workflow_type": task.workflow_type, "status": task.status,
        "events_url": f"{base}/events", "status_url": base, "cancel_url": f"{base}/cancel",
        "supports_streaming_preview": False, "supports_cancellation": workflow_type in CANCELLABLE_WORKFLOWS,
        "reused_existing": reused_existing,
    }


@router.post("/general_resource_generation/batch/start")
def start_general_resource_batch(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """Start one independent, deduplicated child task per requested resource type."""
    raw_types = payload.get("resourceTypes")
    if not isinstance(raw_types, list) or not raw_types:
        raise HTTPException(status_code=422, detail={"code": "RESOURCE_TYPES_REQUIRED", "message": "resourceTypes is required"})
    if len(raw_types) > settings.workflow_max_concurrent_tasks_per_user:
        raise HTTPException(status_code=422, detail={"code": "TOO_MANY_RESOURCE_TYPES", "message": "too many resource types in one batch"})
    from app.routers import product
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_type in raw_types:
        request = product.normalize_general_resource_request({**payload, "resourceType": raw_type})
        if request["resourceType"] in seen:
            continue
        seen.add(request["resourceType"])
        normalized.append(request)
    if not normalized:
        raise HTTPException(status_code=422, detail={"code": "RESOURCE_TYPES_REQUIRED", "message": "resourceTypes is required"})
    tasks: list[dict[str, Any]] = []
    for request in normalized:
        task, reused_existing = _start("general_resource_generation", request, auth)
        base = f"/api/workflows/{task.task_id}"
        tasks.append({
            "task_id": task.task_id, "workflow_type": task.workflow_type, "resource_type": request["resourceType"],
            "status": task.status, "events_url": f"{base}/events", "status_url": base,
            "cancel_url": f"{base}/cancel", "reused_existing": reused_existing,
        })
    return {"tasks": tasks}


@router.get("/{task_id}")
def get_workflow(task_id: str, sessionId: str = Query(default=""), auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    try:
        return workflow_task_manager.get(task_id, auth.learner_id, sessionId or None).public(include_result=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc


@router.post("/{task_id}/cancel")
def cancel_workflow(task_id: str, payload: dict[str, Any] | None = None, auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    try:
        task = workflow_task_manager.get(task_id, auth.learner_id, str((payload or {}).get("sessionId") or "") or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    if task.workflow_type not in CANCELLABLE_WORKFLOWS:
        raise HTTPException(status_code=409, detail="该任务当前只能安全展示阶段进度")
    return workflow_task_manager.cancel(task).public()


@router.post("/{task_id}/retry")
def retry_workflow(task_id: str, auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    try:
        old = workflow_task_manager.get(task_id, auth.learner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    if old.status not in {"failed", "cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="只有失败、取消或过期任务可以重试")
    task, reused_existing = _start(old.workflow_type, dict(old.retry_payload), auth)
    return {"task_id": task.task_id, "workflow_type": task.workflow_type, "status": task.status, "reused_existing": reused_existing}


@router.get("/{task_id}/events")
def workflow_events(
    task_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(reject_parent),
) -> StreamingResponse:
    try:
        task = workflow_task_manager.get(task_id, auth.learner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    try:
        cursor = max(after, int(request.headers.get("Last-Event-ID", "0") or 0))
    except ValueError:
        cursor = after

    def stream():
        nonlocal cursor
        while True:
            with task.condition:
                pending = [event for event in task.events if event["sequence"] > cursor]
                if not pending and task.status not in TERMINAL_STATUSES:
                    task.condition.wait(timeout=settings.workflow_heartbeat_seconds)
                    pending = [event for event in task.events if event["sequence"] > cursor]
                terminal = task.status in TERMINAL_STATUSES
            if pending:
                for event in pending:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif not terminal:
                yield f"event: heartbeat\ndata: {json.dumps({'event': 'heartbeat', 'task_id': task.task_id, 'sequence': cursor, 'elapsed_ms': task.elapsed_ms})}\n\n"
            if terminal and not any(event["sequence"] > cursor for event in task.events):
                break

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
