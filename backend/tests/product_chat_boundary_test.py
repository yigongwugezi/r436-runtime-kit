import sys
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

    def __enter__(self):
        def patched(session_id: str, user_message: str, course_id: str | None = None, progress_callback=None):
            self.calls += 1
            return self.result_factory(session_id, user_message, course_id)

        product.ag_run_agents = patched
        return self

    def __exit__(self, exc_type, exc, tb):
        product.ag_run_agents = self.original


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


if __name__ == "__main__":
    test_target_only_explicit_generation_runs_pipeline()
    test_calculus_reply_uses_real_stages_and_time()
    test_bare_confirmation_asks_clarification()
    test_generate_without_subject_asks_subject_only()
    test_tight_two_day_reply_mentions_focus()
    print("PASS product_chat_boundary_test")
