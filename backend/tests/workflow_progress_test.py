"""Focused regression checks for the in-process workflow registry."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.workflow_tasks import WorkflowCancelled, WorkflowTaskManager


def main() -> None:
    manager = WorkflowTaskManager()
    first = manager.create("generated_resource", "learner-a", "session-a")
    second = manager.create("generated_resource", "learner-a", "session-a")
    assert first.task_id != second.task_id and len(first.task_id) >= 32
    try:
        manager.get(first.task_id, "learner-b")
        raise AssertionError("cross-user task read was allowed")
    except KeyError:
        pass
    try:
        manager.get(first.task_id, "learner-a", "session-b")
        raise AssertionError("cross-session task read was allowed")
    except KeyError:
        pass

    manager.emit(first, "stage_started", "generate", label="生成内容")
    manager.emit(first, "stage_progress", "generate", label="生成内容")
    sequences = [event["sequence"] for event in first.events]
    assert sequences == sorted(set(sequences))

    blocker = threading.Event()
    cancellable = manager.create("lecture_generation", "learner-b", "session-b")

    def slow(task):
        blocker.wait(1)
        manager.check_cancelled(task)
        return {"must_not": "become available"}

    manager.start(cancellable, slow)
    while cancellable.status == "queued":
        time.sleep(0.005)
    manager.cancel(cancellable)
    manager.cancel(cancellable)  # idempotent
    blocker.set()
    time.sleep(0.02)
    assert cancellable.status == "cancelled"
    assert not cancellable.result_available
    assert [event["event"] for event in cancellable.events].count("workflow_cancelled") == 1

    completed = manager.create("profile_sync", "learner-c", "session-c")
    manager.start(completed, lambda task: {"ok": True})
    for _ in range(100):
        if completed.status == "completed":
            break
        time.sleep(0.005)
    assert completed.status == "completed" and completed.result_available
    assert completed.events[-1]["event"] == "workflow_completed"
    assert completed.elapsed_ms >= 0
    print("workflow progress tests: ok")


if __name__ == "__main__":
    main()
