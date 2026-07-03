import sys
import asyncio
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import product
from app.services.conversation_state import conversation_store


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def zh(escaped: str) -> str:
    return escaped.encode("ascii").decode("unicode_escape")


def seed_message(session_id: str, message: str) -> None:
    state = conversation_store.get(session_id)
    state.messages.append({"role": "user", "content": message, "timestamp": 0})
    conversation_store.extract_facts(state, message)


def run_reply(session_id: str, message: str, intent: dict | None = None) -> tuple[str, bool]:
    return product._reply_for_intent(
        message,
        intent or {"action": "full_workflow", "intent": "full_workflow"},
        session_id,
    )


def fake_result(session_id: str, course_id: str, days: int, titles: list[str], *, tight: bool = False) -> dict:
    return {
        "session_id": session_id,
        "course_id": course_id,
        "pipeline_executed": True,
        "agents_run": ["profile_agent", "conversation_agent", "planner_agent"],
        "estimatedDays": days,
        "planner_metadata": {
            "priority_basis": ["time_budget"],
            "risk_flags": ["time_budget_tight"] if tight else [],
            "estimated_days": days,
        },
        "learning_path": [
            {
                "stage_id": f"stage_{idx}",
                "title": title,
                "duration": f"第{idx}天",
                "goal": title,
                "tasks": [title],
                "resource_types": ["lecture"],
            }
            for idx, title in enumerate(titles, 1)
        ],
        "resources": [{"title": "配套讲义"}],
    }


class AgentPatch:
    def __init__(self, result_factory):
        self.result_factory = result_factory
        self.calls = 0
        self.original = product.ag_run_agents
        self.original_final_reply = product._generate_final_reply

    def __enter__(self):
        def patched(session_id: str, user_message: str, course_id: str | None = None, progress_callback=None, **_kwargs):
            self.calls += 1
            return self.result_factory(session_id, user_message, course_id)

        def deterministic_final_reply(_message: str, _session_id: str, result: dict) -> str:
            return product._learning_plan_reply(result, {})

        product.ag_run_agents = patched
        product._generate_final_reply = deterministic_final_reply
        return self

    def __exit__(self, exc_type, exc, tb):
        product.ag_run_agents = self.original
        product._generate_final_reply = self.original_final_reply


class AttrPatch:
    def __init__(self, target, **replacements):
        self.target = target
        self.replacements = replacements
        self.originals = {}

    def __enter__(self):
        for name, value in self.replacements.items():
            self.originals[name] = getattr(self.target, name)
            setattr(self.target, name, value)
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self.originals.items():
            setattr(self.target, name, value)


def stream_events(payload: dict) -> list[dict]:
    async def collect():
        response = product.stream_chat(payload)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return chunks

    events = []
    for block in "".join(asyncio.run(collect())).split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


def stream_patch(reply_factory):
    def classify(_message: str, _session_id: str | None = None) -> dict:
        return {"action": "full_workflow", "intent": "full_workflow"}

    def will_run(_intent: dict, _session_id: str) -> bool:
        return True

    return AttrPatch(
        product,
        _classify_intent=classify,
        _will_run_agents=will_run,
        _reply_for_intent=reply_factory,
    )


def assert_no_old_template(reply: str) -> None:
    for text in [
        zh(r"\u753b\u50cf\u5b8c\u6574\u5ea6"),
        zh(r"\u5f53\u524d\u753b\u50cf\u4fe1\u606f\u5c1a\u4e0d\u8db3"),
        zh(r"\u8bf7\u8865\u5145"),
        "unknown",
        "fallback_rule",
        zh(r"\u65e0\u8bca\u65ad\u6570\u636e"),
    ]:
        assert_true(text not in reply, f"old/internal text leaked: {text}\n{reply}")


def test_target_only_explicit_generation_runs_pipeline() -> None:
    sid = "product_boundary_target_only"
    conversation_store.reset(sid)
    seed_message(sid, zh(r"\u6211\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"))

    with AgentPatch(lambda session_id, _msg, course_id: fake_result(
        session_id,
        course_id or "data_structures",
        14,
        [
            zh(r"\u590d\u6742\u5ea6"),
            zh(r"\u94fe\u8868"),
            zh(r"\u6808\u4e0e\u961f\u5217"),
            zh(r"\u6811\u4e0e\u56fe"),
            zh(r"\u67e5\u627e\u4e0e\u6392\u5e8f"),
        ],
    )) as patch:
        reply, ran = run_reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))

    assert_true(ran is True, "explicit generation with target should run pipeline")
    assert_true(patch.calls == 1, "pipeline should be called once")
    assert_true(zh(r"\u5b66\u4e60\u65b9\u6848") in reply, "reply should mention learning plan")
    assert_true(zh(r"\u590d\u6742\u5ea6") in reply and zh(r"\u6392\u5e8f") in reply, "reply should cite real stages")
    assert_no_old_template(reply)


def test_calculus_reply_uses_real_stages_and_time() -> None:
    sid = "product_boundary_calculus"
    conversation_store.reset(sid)
    for message in [
        zh(r"\u6211\u60f3\u4e00\u4e2a\u6708\u5b66\u5fae\u79ef\u5206"),
        zh(r"\u9ad8\u4e2d\u5bfc\u6570\u5b66\u8fc7\uff0c\u6781\u9650\u6ca1\u5b66"),
        zh(r"\u6bcf\u5929\u4e09\u5c0f\u65f6\uff0c\u5468\u672b\u4f11\u606f"),
        zh(r"\u76ee\u6807\u671f\u672b\u9ad8\u5206"),
    ]:
        seed_message(sid, message)

    with AgentPatch(lambda session_id, _msg, course_id: fake_result(
        session_id,
        course_id or "custom_calculus",
        30,
        [
            zh(r"\u51fd\u6570\u3001\u6781\u9650\u4e0e\u8fde\u7eed"),
            zh(r"\u5bfc\u6570\u4e0e\u5fae\u5206"),
            zh(r"\u79ef\u5206\u57fa\u7840"),
            zh(r"\u7efc\u5408\u9898\u578b\u4e0e\u671f\u672b\u590d\u76d8"),
        ],
    )):
        reply, ran = run_reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))

    assert_true(ran is True, "complete calculus profile should run pipeline")
    for expected in [
        zh(r"\u6781\u9650"),
        zh(r"\u5bfc\u6570"),
        zh(r"\u79ef\u5206"),
        zh(r"\u7efc\u5408"),
        "30",
        zh(r"\u6bcf\u5929\u4e09\u5c0f\u65f6"),
        zh(r"\u5468\u672b\u4f11\u606f"),
    ]:
        assert_true(expected in reply, f"expected {expected} in reply:\n{reply}")
    assert_no_old_template(reply)


def test_bare_confirmation_asks_clarification() -> None:
    sid = "product_boundary_bare_confirmation"
    conversation_store.reset(sid)
    reply, ran = run_reply(
        sid,
        zh(r"\u53ef\u4ee5"),
        {
            "action": "none",
            "intent": "casual_chat",
            "needs_clarification": True,
            "reason": "confirmation_without_generation_context",
        },
    )
    assert_true(ran is False, "bare confirmation should not run pipeline")
    assert_true(zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848") in reply, "should ask whether to generate")
    assert_true(zh(r"\u7ee7\u7eed\u8865\u5145\u4fe1\u606f") in reply, "should offer continue supplementing")
    assert_true(zh(r"\u4f8b\u5982\uff1a\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b") not in reply, "should not fall back to generic greeting")


def test_generate_without_subject_asks_subject_only() -> None:
    sid = "product_boundary_no_subject"
    conversation_store.reset(sid)
    with AgentPatch(lambda session_id, _msg, course_id: fake_result(session_id, course_id or "x", 14, ["x"])) as patch:
        reply, ran = run_reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))

    assert_true(ran is False, "missing subject should not run pipeline")
    assert_true(patch.calls == 0, "pipeline should not run without learning subject")
    assert_true(zh(r"\u60f3\u5b66\u4e60\u54ea\u95e8\u8bfe\u6216\u54ea\u4e2a\u65b9\u5411") in reply, "should ask for subject")
    assert_no_old_template(reply)


def test_tight_two_day_reply_mentions_focus() -> None:
    sid = "product_boundary_tight_time"
    conversation_store.reset(sid)
    seed_message(sid, zh(r"\u6211\u60f3\u4e24\u5929\u590d\u4e60\u6570\u636e\u7ed3\u6784"))

    with AgentPatch(lambda session_id, _msg, course_id: fake_result(
        session_id,
        course_id or "data_structures",
        2,
        [
            zh(r"\u6570\u636e\u7ed3\u6784\u4e0e\u7b97\u6cd5\u590d\u6742\u5ea6\u57fa\u7840"),
            zh(r"\u94fe\u8868"),
            zh(r"\u6811\u4e0e\u56fe"),
            zh(r"\u67e5\u627e\u4e0e\u6392\u5e8f"),
        ],
        tight=True,
    )):
        reply, ran = run_reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))

    assert_true(ran is True, "tight data-structure request should run pipeline")
    assert_true("2" in reply, "reply should show two-day plan")
    assert_true(zh(r"\u91cd\u70b9\u7a81\u7834") in reply, "tight time should mention focused breakthrough")
    assert_no_old_template(reply)


def test_chat_stream_sends_keepalive_final_and_done_metadata() -> None:
    sid = "product_stream_final"
    conversation_store.reset(sid)

    def reply_factory(_message, _intent, session_id, progress_callback=None):
        if progress_callback:
            progress_callback("generating", zh(r"\u6b63\u5728\u751f\u6210\u8d44\u6e90"), 80)
        time.sleep(11)
        conversation_store.get(session_id).last_result = fake_result(
            session_id,
            "data_structures",
            14,
            [zh(r"\u590d\u6742\u5ea6"), zh(r"\u94fe\u8868"), zh(r"\u67e5\u627e\u4e0e\u6392\u5e8f")],
        )
        return zh(r"\u5df2\u751f\u6210\uff1a\u590d\u6742\u5ea6\u3001\u94fe\u8868\u3001\u6392\u5e8f"), True

    with stream_patch(reply_factory):
        events = stream_events({"sessionId": sid, "message": zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848")})

    assert_true(any(event.get("keepalive") for event in events), "stream should keep the SSE connection alive while resources run")
    assert_true(any(zh(r"\u590d\u6742\u5ea6") in event.get("content", "") for event in events), "stream should emit final user-visible content")
    done = events[-1]
    assert_true(done.get("done") is True, "stream should end with done")
    assert_true(done.get("event") == "done", "done event should be explicit")
    assert_true(done.get("pipeline_executed") is True, "done should expose pipeline status")
    assert_true(done.get("learning_path_created") is True, "done should expose learning path creation")
    assert_true(done.get("stage_count") == 3, "done should expose stage count")


def test_chat_stream_error_still_sends_done() -> None:
    sid = "product_stream_error"
    conversation_store.reset(sid)

    def reply_factory(*_args, **_kwargs):
        raise RuntimeError("boom")

    with stream_patch(reply_factory):
        events = stream_events({"sessionId": sid, "message": zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848")})

    assert_true(any(event.get("error") for event in events), "stream should emit an error event")
    assert_true(events[-1].get("done") is True, "stream should end even when pipeline fails")


def test_multimodal_mindmap_chat_response() -> None:
    sid = "product_multimodal_mindmap"
    conversation_store.reset(sid)
    conversation_store.get(sid).facts["target_course"] = zh(r"\u6570\u636e\u7ed3\u6784")
    conversation_store.get(sid).last_result = fake_result(
        sid,
        "data_structures",
        14,
        [zh(r"\u590d\u6742\u5ea6"), zh(r"\u94fe\u8868")],
    )

    with AttrPatch(
        product,
        _classify_intent=lambda _message, _session_id=None: {"action": "none", "intent": "multimodal"},
    ):
        response = product.send_chat({"sessionId": sid, "message": zh(r"\u751f\u6210\u601d\u7ef4\u5bfc\u56fe")})

    data = response["data"]
    assert_true("multimodal_result" in data, "chat response should include multimodal_result")
    assert_true(data["multimodal_result"]["agent"] == "MultimodalAgent", "MultimodalAgent should run")
    assert_true(data["multimodal_result"]["status"] == "success", "mindmap should be generated from cached path")
    assert_true(data["workflow_trace"]["steps"][0]["agent"] == "MultimodalAgent", "workflow trace should record multimodal step")
    assert_true(zh(r"\u601d\u7ef4\u5bfc\u56fe") in data["reply"]["content"], "reply should mention mindmap")


def test_chat_image_url_routes_to_multimodal_agent_with_trace() -> None:
    sid = "product_multimodal_image_url"
    conversation_store.reset(sid)
    contexts = []

    class FakeMultimodalAgent:
        def run(self, context: dict) -> dict:
            contexts.append(context)
            return {
                "agent": "MultimodalAgent",
                "status": "success",
                "task_type": "image_understanding",
                "tool": "QwenVisionProvider",
                "provider": "qwen_vl",
                "result": {
                    "image_type": "question_image",
                    "subject": "math",
                    "detected_text": "lim x",
                    "question_text": "lim x",
                    "possible_knowledge_points": ["limit"],
                    "summary": "limit question",
                    "confidence": 0.9,
                    "needs_manual_review": False,
                },
                "warnings": [],
                "trace": {"tool_trace": {"model": "fake-vl"}},
                "workflow_trace": {
                    "workflow_name": "multimodal_generation",
                    "workflow_status": "success",
                    "pipeline_executed": True,
                    "steps": [
                        {"step": "multimodal_classify", "agent": "MultimodalAgent", "status": "success"},
                        {"step": "vision_understanding", "agent": "QwenVisionProvider", "status": "success"},
                    ],
                },
            }

    with AttrPatch(
        product,
        MultimodalAgent=FakeMultimodalAgent,
        _classify_intent=lambda _message, _session_id=None: {"action": "none", "intent": "multimodal"},
    ):
        response = product.send_chat({
            "sessionId": sid,
            "message": zh(r"\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247"),
            "image_url": "https://example.com/question.png",
        })

    data = response["data"]
    assert_true(contexts and contexts[0]["image_url"] == "https://example.com/question.png", "image_url should be passed to MultimodalAgent")
    assert_true(data["multimodal_result"]["task_type"] == "image_understanding", "chat response should expose multimodal_result")
    assert_true(data["workflow_trace"]["steps"][1]["agent"] == "QwenVisionProvider", "workflow trace should include vision provider")
    assert_true(data["workflow_trace"]["pipeline_executed"] is True, "multimodal workflow should be marked executed")


if __name__ == "__main__":
    test_target_only_explicit_generation_runs_pipeline()
    test_calculus_reply_uses_real_stages_and_time()
    test_bare_confirmation_asks_clarification()
    test_generate_without_subject_asks_subject_only()
    test_tight_two_day_reply_mentions_focus()
    test_chat_stream_sends_keepalive_final_and_done_metadata()
    test_chat_stream_error_still_sends_done()
    test_multimodal_mindmap_chat_response()
    test_chat_image_url_routes_to_multimodal_agent_with_trace()
    print("PASS product_chat_boundary_test")
