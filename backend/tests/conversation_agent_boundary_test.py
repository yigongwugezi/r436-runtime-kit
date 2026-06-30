import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.conversation_agent import ConversationAgent


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_fallback(message: str, history: list[dict[str, str]] | None = None) -> dict:
    return ConversationAgent(mock_data={}, llm_client=None).run(
        {
            "user_message": message,
            "conversation_history": history or [],
            "profile_facts": {"_raw_user_message": message},
        }
    )


def assert_generates(message: str, history: list[dict[str, str]] | None = None) -> None:
    result = run_fallback(message, history)
    assert_true(result["action"] != "none", f"{message} should trigger generation")
    assert_true(result["should_run_agents"], f"{message} should run agents")
    assert_true(result.get("pipeline_required"), f"{message} should require pipeline")
    assert_true(result.get("reply") in ("", None), "fallback must not produce user-visible reply")


def test_explicit_generation_requests() -> None:
    for message in [
        "开始生成学习方案",
        "帮我生成学习方案",
        "帮我制定学习计划",
        "给我制定学习路径",
        "按这些信息生成",
        "就按这个生成",
        "给我生成学习路径",
        "生成吧",
        "开始吧",
    ]:
        assert_generates(message)


def test_learning_intent_does_not_generate() -> None:
    for message in [
        "我想学习数据结构",
        "我想一个月学微积分",
        "我是大三，我学过 C 语言",
        "我想期末拿高分",
    ]:
        result = run_fallback(message)
        assert_true(result["action"] == "none", f"{message} should not generate")
        assert_true(not result["should_run_agents"], f"{message} should not run agents")


def test_contextual_confirmation_generates() -> None:
    history = [{"role": "assistant", "content": "信息已经可以生成初版，要开始吗？"}]
    for message in ["可以", "好", "就这样", "按这个来"]:
        assert_generates(message, history)


def test_confirmation_without_context_does_not_generate() -> None:
    for message in ["可以", "好", "行"]:
        result = run_fallback(message)
        assert_true(result["action"] == "none", f"{message} without context should not generate")
        assert_true(result.get("needs_clarification"), f"{message} should need clarification")
        assert_true(result.get("reply") in ("", None), "fallback must not produce user-visible reply")


def test_fallback_reply_is_not_user_visible() -> None:
    result = run_fallback("我想学习数据结构")
    blocked_phrases = ["画像完整度", "当前画像信息尚不足", "请补充以下信息", "我已为你生成", "你的学习方案如下"]
    reply = result.get("reply") or ""
    assert_true(reply == "", "fallback reply should be empty")
    assert_true(not any(phrase in reply for phrase in blocked_phrases), "fallback leaked old user-visible text")


if __name__ == "__main__":
    test_explicit_generation_requests()
    test_learning_intent_does_not_generate()
    test_contextual_confirmation_generates()
    test_confirmation_without_context_does_not_generate()
    test_fallback_reply_is_not_user_visible()
    print("PASS conversation_agent_boundary_test")
