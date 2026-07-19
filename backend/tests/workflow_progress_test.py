"""Focused regression checks for the in-process workflow registry."""

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.workflow_tasks import WorkflowCancelled, WorkflowTaskManager


def wait_for(task, status: str) -> None:
    for _ in range(200):
        if task.status == status:
            return
        time.sleep(0.005)
    raise AssertionError(f"task did not reach {status}: {task.status}")


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

    payload = {
        "sessionId": "session-d", "subjectId": "subject-d", "pathId": "path-d",
        "stageId": "stage-d", "chapterId": "chapter-d", "sectionId": "section-d",
        "resourceType": "summary_card", "mode": "generate", "topic": "递归调用栈",
        "requirements": "private prompt text",
    }
    canonical = manager.canonical_task_payload("generated_resource", "learner-d", "session-d", "subject-d", payload)
    assert "private prompt text" not in str(canonical) and "requirements" not in canonical
    reordered = dict(reversed(list(payload.items())))
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) == manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", reordered)
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", {**payload, "topic": "递归"})
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-d", "session-e", "subject-d", payload)
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("lecture_generation", "learner-d", "session-d", "subject-d", payload)
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-e", "session-d", "subject-d", payload)
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", {**payload, "mode": "regenerate"})
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", {**payload, "resourceType": "worked_example"})
    assert manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", payload) != manager.canonical_task_key("generated_resource", "learner-d", "session-d", "subject-d", {**payload, "chapterId": "chapter-e"})
    lecture_payload = {**payload, "taskId": "task-d"}
    assert manager.canonical_task_key("lecture_generation", "learner-d", "session-d", "subject-d", lecture_payload) == manager.canonical_task_key("lecture_generation", "learner-d", "session-d", "subject-d", {**lecture_payload, "requirements": "changed", "sectionTitle": "changed"})
    assert manager.canonical_task_key("lecture_generation", "learner-d", "session-d", "subject-d", lecture_payload) != manager.canonical_task_key("lecture_generation", "learner-d", "session-d", "subject-d", {**lecture_payload, "taskId": "task-e"})
    path_payload = {"mode": "regenerate", "pathId": "temporary-name", "targetTopics": ["calculus"]}
    assert manager.canonical_task_key("learning_path_generation", "learner-d", "session-d", "subject-d", path_payload) == manager.canonical_task_key("learning_path_generation", "learner-d", "session-d", "subject-d", {"mode": "preview", "targetTopics": ["linear algebra"]})
    assert manager.canonical_task_key("learning_path_generation", "learner-d", "session-d", "subject-d", path_payload) != manager.canonical_task_key("learning_path_generation", "learner-d", "session-e", "subject-d", path_payload)

    dedupe = WorkflowTaskManager()
    gate = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def runner(task):
        nonlocal calls
        with calls_lock:
            calls += 1
        gate.wait(1)
        return {"ok": True}

    def request():
        task, reused = dedupe.get_or_create("generated_resource", "learner-d", "session-d", "subject-d", payload=payload)
        if not reused:
            dedupe.start(task, runner)
        return task, reused

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: request(), range(8)))
    task_ids = {task.task_id for task, _ in results}
    assert len(task_ids) == 1 and sum(not reused for _, reused in results) == 1
    wait_for(results[0][0], "running")
    assert calls == 1 and len(dedupe._active_task_ids) == 1
    gate.set()
    wait_for(results[0][0], "completed")
    next_task, reused = dedupe.get_or_create("generated_resource", "learner-d", "session-d", "subject-d", payload=payload)
    assert not reused and next_task.task_id not in task_ids

    failed, reused = dedupe.get_or_create("generated_resource", "learner-f", "session-f", "subject-f", payload=payload)
    assert not reused
    dedupe.start(failed, lambda task: (_ for _ in ()).throw(RuntimeError("fake failure")))
    wait_for(failed, "failed")
    retry_gate = threading.Event()

    def retry_request():
        task, reused = dedupe.get_or_create("generated_resource", "learner-f", "session-f", "subject-f", payload=payload)
        if not reused:
            dedupe.start(task, lambda current: retry_gate.wait(1))
        return task, reused

    with ThreadPoolExecutor(max_workers=2) as pool:
        retries = list(pool.map(lambda _: retry_request(), range(2)))
    assert len({task.task_id for task, _ in retries}) == 1
    assert sum(not reused for _, reused in retries) == 1 and retries[0][0].task_id != failed.task_id
    retry_gate.set()

    cancelled, reused = dedupe.get_or_create("lecture_generation", "learner-g", "session-g", "subject-g", payload=payload)
    assert not reused
    cancel_gate = threading.Event()
    dedupe.start(cancelled, lambda task: cancel_gate.wait(1))
    wait_for(cancelled, "running")
    dedupe.cancel(cancelled)
    cancel_gate.set()
    replacement, reused = dedupe.get_or_create("lecture_generation", "learner-g", "session-g", "subject-g", payload=payload)
    assert not reused and replacement.task_id != cancelled.task_id

    startup, reused = dedupe.get_or_create("profile_sync", "learner-h", "session-h", "subject-h", payload=payload)
    assert not reused
    with patch("app.services.workflow_tasks.threading.Thread") as thread:
        thread.return_value.start.side_effect = RuntimeError("fake start failure")
        try:
            dedupe.start(startup, lambda task: {"ok": True})
            raise AssertionError("start failure was swallowed")
        except RuntimeError:
            pass
    assert startup.status == "failed" and startup.active_key not in dedupe._active_task_ids
    print("workflow progress tests: ok")


if __name__ == "__main__":
    main()
