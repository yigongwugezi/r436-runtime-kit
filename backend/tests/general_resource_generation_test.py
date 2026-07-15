"""Regression checks for general, type-specific resource generation."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_bootstrap = tempfile.TemporaryDirectory()
os.environ.setdefault("EDUAGENT_SKIP_ENV_FILE", "1")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_bootstrap.name) / 'bootstrap.db'}")


def main() -> None:
    # Imports happen after the test-only configuration above; no provider is used.
    from app.db.engine import SessionLocal
    from app.db.models import ResourceModel
    from app.routers import product, workflows
    from app.services.workflow_tasks import WorkflowTaskManager, workflow_task_manager

    payload = {
        "sessionId": "general-resource-test", "learnerId": "learner-test", "subjectId": "subject-test",
        "topic": "递归调用栈", "difficulty": "medium", "operation": "generate",
        "mode": "general_resource_generation", "generationOptions": {},
    }
    assert product.normalize_general_resource_request({**payload, "resourceType": "mind-map"})["resourceType"] == "mindmap"
    try:
        product.normalize_general_resource_request({**payload, "resourceType": "unknown"})
        raise AssertionError("unsupported resource type was accepted")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422

    generated = {}
    for resource_type in ("lecture", "mindmap", "quiz"):
        response = product._generate_general_resource({**payload, "resourceType": resource_type})
        resource = response["data"]["resource"]
        generated[resource_type] = resource
        assert resource["type"] == resource_type
        assert resource["id"] and resource["title"]
    assert generated["mindmap"]["mermaidDef"].startswith("mindmap")
    assert generated["quiz"]["questions"] and all(question["answer"] and question["explanation"] for question in generated["quiz"]["questions"])

    repeated = product._generate_general_resource({**payload, "resourceType": "quiz"})["data"]["resource"]
    assert repeated["id"] == generated["quiz"]["id"], "same scope/type/options must upsert instead of duplicating"
    db = SessionLocal()
    try:
        rows = db.query(ResourceModel).filter(ResourceModel.session_id == payload["sessionId"]).all()
        assert len(rows) == 3
        assert {row.type for row in rows} == {"lecture", "mindmap", "quiz"}
        assert all(row.resource_metadata and row.resource_metadata.get("general_generation") for row in rows)
    finally:
        db.close()

    # A deleted persisted resource must not be revived from the current
    # conversation's last_result cache on a later resource-list read.
    from app.services.conversation_state import conversation_store
    state = conversation_store.get(payload["sessionId"])
    state.last_result = {"course_id": "course-test", "resources": [generated["lecture"]]}
    deleted = product.delete_resource(generated["lecture"]["id"], payload["sessionId"])
    assert deleted["data"]["deleted"] is True
    assert state.last_result["resources"] == []
    listed = product.get_resources(sessionId=payload["sessionId"])
    assert generated["lecture"]["id"] not in {item["id"] for item in listed["data"]["resources"]}

    # Deletion is always constrained to the session supplied by the caller.
    other_payload = {**payload, "sessionId": "other-general-resource-test"}
    other_resource = product._generate_general_resource({**other_payload, "resourceType": "lecture"})["data"]["resource"]
    denied = product.delete_resource(other_resource["id"], payload["sessionId"])
    assert denied["data"]["deleted"] is False
    db = SessionLocal()
    try:
        assert db.query(ResourceModel).filter(ResourceModel.id == other_resource["id"], ResourceModel.session_id == other_payload["sessionId"]).first()
    finally:
        db.close()

    with patch("app.services.multimodal_registry.default_registry", return_value=SimpleNamespace(select_tool=lambda _: (None, None))):
        try:
            product._generate_general_resource({**payload, "resourceType": "video"})
            raise AssertionError("unavailable provider returned a fake resource")
        except RuntimeError as exc:
            assert str(exc) == "provider_not_configured"

    # The workflow surfaces an actionable, safe failure instead of claiming that
    # a Manim animation was generated when the local renderer is unavailable.
    workflow_task_manager.clear()
    auth = SimpleNamespace(learner_id="learner-test")
    with patch("app.services.multimodal_registry.default_registry", return_value=SimpleNamespace(select_tool=lambda _: (None, None))):
        unavailable, reused = workflows._start(
            "general_resource_generation", {**payload, "resourceType": "manim"}, auth,
        )
        assert not reused
        for _ in range(100):
            if unavailable.status in {"failed", "completed", "cancelled"}:
                break
            time.sleep(0.01)
        assert unavailable.status == "failed"
        assert unavailable.error_code == "PROVIDER_NOT_CONFIGURED"
        assert "未生成伪造资源" in unavailable.safe_error_message
    workflow_task_manager.clear()

    manager = WorkflowTaskManager()
    blocker = threading.Event()
    task, reused = manager.get_or_create("general_resource_generation", "learner-test", payload["sessionId"], payload["subjectId"], payload={**payload, "resourceType": "quiz"})
    assert not reused
    manager.start(task, lambda current: blocker.wait(1))
    for _ in range(100):
        if task.status == "running":
            break
        time.sleep(0.005)
    manager.cancel(task)
    blocker.set()
    assert task.status == "cancelled"
    replacement, reused = manager.get_or_create("general_resource_generation", "learner-test", payload["sessionId"], payload["subjectId"], payload={**payload, "resourceType": "quiz"})
    assert not reused and replacement.task_id != task.task_id

    workflow_task_manager.clear()
    original_start = workflow_task_manager.start
    try:
        workflow_task_manager.start = lambda task, runner: setattr(task, "runner", runner)  # type: ignore[method-assign]
        batch = workflows.start_general_resource_batch({**payload, "resourceTypes": ["lecture", "mindmap", "quiz"]}, auth)
        assert len(batch["tasks"]) == 3
        assert {item["resource_type"] for item in batch["tasks"]} == {"lecture", "mindmap", "quiz"}
        assert len({item["task_id"] for item in batch["tasks"]}) == 3
        duplicate = workflows.start_general_resource_batch({**payload, "resourceTypes": ["lecture", "mindmap", "quiz"]}, auth)
        assert {item["task_id"] for item in duplicate["tasks"]} == {item["task_id"] for item in batch["tasks"]}
        assert all(item["reused_existing"] for item in duplicate["tasks"])
    finally:
        workflow_task_manager.start = original_start  # type: ignore[method-assign]
        workflow_task_manager.clear()
    print("general resource generation tests: ok")


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            from app.db.engine import engine
            engine.dispose()
        except Exception:
            pass
        _bootstrap.cleanup()
