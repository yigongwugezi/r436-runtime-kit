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
    "profile_sync", "profile_rebuild", "learning_path_generation", "lecture_generation",
}


def _session(payload: dict[str, Any], auth: AuthContext) -> tuple[str, str]:
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    subject_id = str(payload.get("subjectId") or payload.get("subject_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId required")
    db = SessionLocal()
    try:
        row = db.get(SessionModel, session_id)
        if row is not None and row.learner_id and row.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权访问该任务")
    finally:
        db.close()
    return session_id, subject_id


def _emit_stage(task: WorkflowTask, stage_id: str, label: str, status: str = "running", **data: Any) -> None:
    workflow_task_manager.check_cancelled(task)
    workflow_task_manager.emit(task, f"stage_{'completed' if status == 'completed' else 'started'}", stage_id, status, label=label, **data)


def _runner(workflow_type: str, payload: dict[str, Any], auth: AuthContext):
    def run(task: WorkflowTask) -> Any:
        # Runtime import avoids coupling the product router back to this API.
        from app.routers import product

        if workflow_type == "resource_search":
            section_id = str(payload.get("sectionId") or "").strip()
            if not section_id:
                raise ValueError("sectionId required")
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

        _emit_stage(task, "input_validation", "检查任务输入", "completed")
        _emit_stage(task, "execution", {
            "generated_resource": "生成结构化学习资源",
            "generated_resource_regeneration": "根据反馈重新生成资源",
            "profile_sync": "提取对话中的画像事实",
            "profile_rebuild": "重建学习画像",
            "learning_path_generation": "规划学习路径",
            "lecture_generation": "生成讲义内容",
        }[workflow_type])

        if workflow_type in {"generated_resource", "generated_resource_regeneration"}:
            result = product._generate_section_resource(str(payload.get("sectionId") or ""), payload, task)
        elif workflow_type == "profile_sync":
            result = product.sync_profile_from_conversation(str(payload.get("subjectId") or ""), payload, auth)
        elif workflow_type == "profile_rebuild":
            result = product.build_profile(payload, auth)
        elif workflow_type == "learning_path_generation":
            result = product.generate_learning_path(payload, auth)
        else:
            result = product._generate_section_lecture(str(payload.get("sectionId") or ""), payload, task)

        workflow_task_manager.check_cancelled(task)
        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError("workflow returned error")
        preview = ""
        if workflow_type in {"generated_resource", "generated_resource_regeneration"}:
            preview = str(((result.get("data") or {}).get("resource") or {}).get("content") or "")
        elif workflow_type == "lecture_generation":
            preview = str(((result.get("data") or {}).get("lecture") or {}).get("content") or "")
        if preview:
            workflow_task_manager.emit(task, "preview_updated", "content_validation", "completed", label="内容已生成，正在确认最终结果", text_delta=preview)
        _emit_stage(task, "save_result", "结果已安全保存", "completed")
        return result

    return run


def _start(workflow_type: str, payload: dict[str, Any], auth: AuthContext) -> WorkflowTask:
    if workflow_type not in SUPPORTED_WORKFLOWS:
        raise HTTPException(status_code=404, detail="unsupported workflow type")
    session_id, subject_id = _session(payload, auth)
    safe_metadata = {"resource_type": str(payload.get("resourceType") or payload.get("type") or "")[:40]}
    try:
        task = workflow_task_manager.create(
            workflow_type, auth.learner_id, session_id, subject_id,
            metadata=safe_metadata, retry_payload=dict(payload),
        )
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    workflow_task_manager.start(task, _runner(workflow_type, dict(payload), auth))
    return task


@router.post("/{workflow_type}/start")
def start_workflow(workflow_type: str, payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    task = _start(workflow_type, payload, auth)
    base = f"/api/workflows/{task.task_id}"
    return {
        "task_id": task.task_id, "workflow_type": task.workflow_type, "status": task.status,
        "events_url": f"{base}/events", "status_url": base, "cancel_url": f"{base}/cancel",
        "supports_streaming_preview": False, "supports_cancellation": True,
    }


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
    return workflow_task_manager.cancel(task).public()


@router.post("/{task_id}/retry")
def retry_workflow(task_id: str, auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    try:
        old = workflow_task_manager.get(task_id, auth.learner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    if old.status not in {"failed", "cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="只有失败、取消或过期任务可以重试")
    task = _start(old.workflow_type, dict(old.retry_payload), auth)
    return {"task_id": task.task_id, "workflow_type": task.workflow_type, "status": task.status}


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
