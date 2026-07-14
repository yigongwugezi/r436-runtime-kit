"""Small in-process task registry for long-running product workflows."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import settings


TERMINAL_STATUSES = {"completed", "partial", "cancelled", "failed", "expired"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowTask:
    task_id: str
    workflow_type: str
    user_scope: str
    session_scope: str
    subject_scope: str = ""
    status: str = "queued"
    current_stage: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    updated_at: str = field(default_factory=_now)
    completed_at: str | None = None
    cancelled_at: str | None = None
    failed_at: str | None = None
    completed_units: int | None = None
    total_units: int | None = None
    result_available: bool = False
    error_code: str = ""
    safe_error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    sequence: int = 0
    events: deque[dict[str, Any]] = field(default_factory=deque)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    runner: Callable | None = field(default=None, repr=False)
    retry_payload: dict[str, Any] = field(default_factory=dict, repr=False)
    started_monotonic: float | None = field(default=None, repr=False)
    finished_elapsed_ms: int | None = field(default=None, repr=False)

    @property
    def elapsed_ms(self) -> int:
        if self.started_monotonic is None:
            return 0
        if self.finished_elapsed_ms is not None:
            return self.finished_elapsed_ms
        return max(0, int((time.monotonic() - self.started_monotonic) * 1000))

    def public(self, include_result: bool = False) -> dict[str, Any]:
        data = {
            "task_id": self.task_id,
            "workflow_type": self.workflow_type,
            "status": self.status,
            "current_stage": self.current_stage,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "cancelled_at": self.cancelled_at,
            "failed_at": self.failed_at,
            "elapsed_ms": self.elapsed_ms,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "result_available": self.result_available,
            "error_code": self.error_code,
            "safe_error_message": self.safe_error_message,
            "metadata": self.metadata,
        }
        if include_result and self.result_available:
            data["result"] = self.result
        return data


class WorkflowCancelled(Exception):
    pass


class WorkflowTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, WorkflowTask] = {}
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()

    def create(
        self,
        workflow_type: str,
        user_scope: str,
        session_scope: str,
        subject_scope: str = "",
        *,
        metadata: dict[str, Any] | None = None,
        runner: Callable | None = None,
        retry_payload: dict[str, Any] | None = None,
    ) -> WorkflowTask:
        self.cleanup()
        with self._lock:
            running = sum(
                task.user_scope == user_scope and task.status in {"queued", "running"}
                for task in self._tasks.values()
            )
            if running >= settings.workflow_max_concurrent_tasks_per_user:
                raise ValueError("当前运行中的任务较多，请等待一个任务结束后再试")
            if len(self._tasks) >= settings.workflow_task_max_entries:
                oldest = min(self._tasks.values(), key=lambda item: item.created_at)
                if oldest.status not in {"queued", "running"}:
                    self._tasks.pop(oldest.task_id, None)
                else:
                    raise ValueError("任务服务暂时繁忙，请稍后重试")
            task = WorkflowTask(
                task_id=uuid.uuid4().hex,
                workflow_type=workflow_type,
                user_scope=user_scope,
                session_scope=session_scope,
                subject_scope=subject_scope,
                metadata=metadata or {},
                runner=runner,
                retry_payload=retry_payload or {},
            )
            task.events = deque(maxlen=settings.workflow_event_buffer_max)
            self._tasks[task.task_id] = task
            return task

    def get(self, task_id: str, user_scope: str, session_scope: str | None = None) -> WorkflowTask:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None or task.user_scope != user_scope or (session_scope and task.session_scope != session_scope):
            raise KeyError(task_id)
        return task

    def emit(self, task: WorkflowTask, event: str, stage_id: str = "", status: str = "running", **data: Any) -> dict[str, Any]:
        with task.condition:
            if task.status in TERMINAL_STATUSES and event not in {"heartbeat"}:
                return {}
            task.sequence += 1
            task.current_stage = stage_id or task.current_stage
            task.updated_at = _now()
            if "completed_units" in data:
                task.completed_units = data["completed_units"]
            if "total_units" in data:
                task.total_units = data["total_units"]
            item = {
                "event": event,
                "task_id": task.task_id,
                "workflow_type": task.workflow_type,
                "stage_id": stage_id,
                "parent_stage_id": data.pop("parent_stage_id", None),
                "status": status,
                "label": str(data.pop("label", ""))[:160],
                "summary": str(data.pop("summary", ""))[:500],
                "completed_units": task.completed_units,
                "total_units": task.total_units,
                "elapsed_ms": task.elapsed_ms,
                "used_fallback": bool(data.pop("used_fallback", False)),
                "sequence": task.sequence,
                "timestamp": _now(),
                "safe_metadata": data.pop("safe_metadata", {}),
            }
            if event in {"content_delta", "preview_updated"}:
                item["text_delta"] = str(data.pop("text_delta", ""))[: settings.workflow_preview_max_chars]
            item.update({key: value for key, value in data.items() if key in {"error_code", "safe_error_message"}})
            task.events.append(item)
            task.condition.notify_all()
            return item

    def check_cancelled(self, task: WorkflowTask) -> None:
        if task.cancel_event.is_set() or task.status == "cancelled":
            raise WorkflowCancelled()

    def start(self, task: WorkflowTask, runner: Callable[[WorkflowTask], Any]) -> None:
        task.runner = runner

        def work() -> None:
            task.status = "running"
            task.started_at = task.updated_at = _now()
            task.started_monotonic = time.monotonic()
            self.emit(task, "workflow_started", "input_validation", label="任务已开始")
            try:
                result = runner(task)
                self.check_cancelled(task)
                task.result = result
                task.result_available = True
                task.finished_elapsed_ms = task.elapsed_ms
                task.status = "completed"
                task.completed_at = task.updated_at = _now()
                self.emit_terminal(task, "workflow_completed", "completed", label="任务已完成")
            except WorkflowCancelled:
                self._mark_cancelled(task)
            except Exception:
                if task.cancel_event.is_set():
                    self._mark_cancelled(task)
                else:
                    task.status = "failed"
                    task.finished_elapsed_ms = task.elapsed_ms
                    task.error_code = "WORKFLOW_FAILED"
                    task.safe_error_message = "任务执行失败，请重试"
                    task.failed_at = task.updated_at = _now()
                    self.emit_terminal(task, "workflow_failed", "failed", label="任务执行失败", error_code=task.error_code, safe_error_message=task.safe_error_message)

        threading.Thread(target=work, daemon=True, name=f"workflow-{task.task_id[:8]}").start()

    def emit_terminal(self, task: WorkflowTask, event: str, status: str, **data: Any) -> None:
        # Terminal status is already set; append directly so the final event is never suppressed.
        with task.condition:
            task.sequence += 1
            item = {
                "event": event, "task_id": task.task_id, "workflow_type": task.workflow_type,
                "stage_id": task.current_stage, "parent_stage_id": None, "status": status,
                "label": data.get("label", ""), "summary": "", "completed_units": task.completed_units,
                "total_units": task.total_units, "elapsed_ms": task.elapsed_ms, "used_fallback": False,
                "sequence": task.sequence, "timestamp": _now(), "safe_metadata": {},
            }
            item.update({key: data[key] for key in ("error_code", "safe_error_message") if key in data})
            task.events.append(item)
            task.condition.notify_all()

    def cancel(self, task: WorkflowTask) -> WorkflowTask:
        if task.status in TERMINAL_STATUSES:
            return task
        task.cancel_event.set()
        self._mark_cancelled(task)
        return task

    def _mark_cancelled(self, task: WorkflowTask) -> None:
        if task.status == "cancelled":
            return
        task.status = "cancelled"
        task.finished_elapsed_ms = task.elapsed_ms
        task.cancelled_at = task.updated_at = _now()
        self.emit_terminal(task, "workflow_cancelled", "cancelled", label="任务已取消")

    def cleanup(self) -> None:
        cutoff = time.time() - settings.workflow_task_ttl_seconds
        with self._lock:
            for task_id, task in list(self._tasks.items()):
                try:
                    updated = datetime.fromisoformat(task.updated_at).timestamp()
                except ValueError:
                    updated = 0
                if task.status in TERMINAL_STATUSES and updated < cutoff:
                    self._tasks.pop(task_id, None)


workflow_task_manager = WorkflowTaskManager()
