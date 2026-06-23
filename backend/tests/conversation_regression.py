import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.routers import product  # noqa: E402
from app.services.conversation_state import conversation_store  # noqa: E402


def classify(message: str) -> dict:
    return IntentAgent(mock_data={}, llm_client=None).classify(message)


def reply(session_id: str, message: str) -> str:
    state = conversation_store.append_message(session_id, "user", message)
    intent = classify(message)
    conversation_store.set_intent(session_id, intent)
    content, _ = product._reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", content)
    assert state.session_id == session_id
    return content


def assert_contains(text: str, expected: str) -> None:
    if expected not in text:
        raise AssertionError(f"Expected {expected!r} in:\n{text}")


def assert_not_contains(text: str, unexpected: str) -> None:
    if unexpected in text:
        raise AssertionError(f"Did not expect {unexpected!r} in:\n{text}")


def zh(escaped: str) -> str:
    return escaped.encode("ascii").decode("unicode_escape")


def test_fresh_start_has_no_fake_profile() -> None:
    sid = "regression_fresh_start"
    conversation_store.reset(sid)
    content = reply(sid, "你觉得我该从什么开始")
    assert_contains(content, "还没有你的学习画像")
    assert_not_contains(content, "当前已记录")


def test_profile_update_is_not_casual_chat() -> None:
    sid = "regression_profile_update"
    conversation_store.reset(sid)
    content = reply(sid, "我是软件工程学生")
    assert_contains(content, "身份/专业背景：软件工程学生")
    assert_contains(content, "最想学习哪门课")
    assert_not_contains(content, "我是 r436-runtime-kit")


def test_incremental_slot_filling() -> None:
    sid = "regression_slot_filling"
    conversation_store.reset(sid)
    reply(sid, "我是软件工程学生")
    reply(sid, "我想学数据结构")
    state = conversation_store.get(sid)
    assert state.facts["background"] == "软件工程学生"
    assert state.facts["target_course"] == "数据结构"
    assert not conversation_store.readiness(state)["readyToPlan"]

    content = reply(sid, "我数据结构基础一般，链表和树比较薄弱，想两周内做课程实验，更喜欢图解加代码")
    state = conversation_store.get(sid)
    assert conversation_store.readiness(state)["readyToPlan"]
    assert_contains(content, "已经可以生成第一版学习方案")


def test_plan_request_needs_core_profile() -> None:
    sid = "regression_plan_guard"
    conversation_store.reset(sid)
    content = reply(sid, "开始生成学习方案")
    state = conversation_store.get(sid)
    assert "target_course" not in state.facts
    assert_contains(content, "画像信息还不够")
    assert_not_contains(content, "学习方案已生成")


def test_low_value_background_does_not_fill_core_profile() -> None:
    sid = "regression_low_value_background"
    conversation_store.reset(sid)
    content = reply(sid, "我是男生")
    state = conversation_store.get(sid)
    assert "background" not in state.facts
    assert "男生" in state.supplemental_facts.get("personal_background", [])
    assert not conversation_store.readiness(state)["readyToPlan"]
    assert_contains(content, "补充背景")
    assert_contains(content, "不足以决定学习路径")


def test_major_background_fills_core_profile() -> None:
    sid = "regression_major_background"
    conversation_store.reset(sid)
    reply(sid, "我是软件工程学生")
    state = conversation_store.get(sid)
    assert state.facts["background"] == "软件工程学生"
    assert "personal_background" not in state.supplemental_facts


def test_real_dialogue_extracts_time_and_learning_levels() -> None:
    sid = "regression_real_dialogue"
    conversation_store.reset(sid)
    assert classify("我是软件工程大二学生，不会PYTHON，数据结构还可以，线性代数还可以，不会机器学习")["intent"] == "profile_update"
    reply(sid, "我是软件工程大二学生，不会PYTHON，数据结构还可以，线性代数还可以，不会机器学习")
    state = conversation_store.get(sid)
    assert state.facts["background"] == "软件工程大二学生"
    assert "数据结构：还可以" in state.facts["knowledge_base"]
    assert "线性代数：还可以" in state.facts["knowledge_base"]
    assert "PYTHON：不会/不熟" in state.facts["weak_points"]
    assert "机器学习：不会/不熟" in state.facts["weak_points"]

    content = reply(sid, "我想48小时完成")
    state = conversation_store.get(sid)
    assert state.facts["time_budget"] == "48小时完成"
    assert "target_course" not in state.facts
    assert_contains(content, "时间安排：48小时完成")

    reply(sid, "我想学习数据结构，为了考试通过")
    state = conversation_store.get(sid)
    assert state.facts["target_course"] == "数据结构"
    assert "考试" in state.facts["learning_goal"]
    assert conversation_store.readiness(state)["readyToPlan"]


def test_fragment_background_is_profile_update() -> None:
    sid = "regression_fragment_background"
    conversation_store.reset(sid)
    intent = classify("大一，软件工程，学生")
    assert intent["intent"] == "profile_update"
    content = reply(sid, "大一，软件工程，学生")
    state = conversation_store.get(sid)
    assert state.facts["background"] == "软件工程大一学生"
    assert_contains(content, "身份/专业背景：软件工程大一学生")
    assert_not_contains(content, "我是 r436-runtime-kit")


def test_force_generate_bypasses_profile_guard() -> None:
    sid = "regression_force_generate"
    conversation_store.reset(sid)
    reply(sid, "为我规划一个两周的机器学习学习路径")
    state = conversation_store.get(sid)
    assert state.facts["target_course"] == "机器学习"
    content = reply(sid, "不用在意准不准，直接生成看看效果")
    assert_contains(content, "学习方案已生成")
    assert_contains(content, "低画像完整度")


def test_casual_chat_uses_existing_context() -> None:
    sid = "regression_contextual_casual"
    conversation_store.reset(sid)
    reply(sid, "我是软件工程学生")
    content = reply(sid, "你好")
    assert_contains(content, "不用重新填表")
    assert_contains(content, "我目前已记录")
    assert_contains(content, "身份/专业背景：软件工程学生")
    assert_not_contains(content, "例如：我是软件工程大三学生")


def test_data_structure_two_day_plan_uses_correct_course_and_duration() -> None:
    sid = "regression_data_structure_two_day_plan"
    conversation_store.reset(sid)

    reply(
        sid,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"
            r"\uff0c\u4e3a\u4e86\u8003\u8bd5\u901a\u8fc7"
        ),
    )

    time_message = zh(r"\u6211\u6709\u4e24\u5929\u65f6\u95f4")
    time_intent = classify(time_message)
    assert time_intent["intent"] == "profile_update"
    reply(sid, time_message)

    content = reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state = conversation_store.get(sid)
    assert state.last_result is not None
    assert state.last_result["course_id"] == "data_structures"

    path = product._to_learning_path(state.last_result)
    assert path["courseName"] == zh(r"\u6570\u636e\u7ed3\u6784")
    assert path["estimatedDays"] == 2
    assert_contains(content, zh(r"\u6570\u636e\u7ed3\u6784"))
    assert_contains(content, "2")


def test_intent_classify_profile_keyword_画像() -> None:
    """Issue #1: 构建学习画像 should be profile_update, not learning_plan."""
    assert classify("帮我构建学习画像")["intent"] == "profile_update"


def test_intent_classify_diagnosis_question() -> None:
    """Issue #4: 我哪里比较薄弱 is a diagnosis query (explicitly listed as diagnosis example in intent_routes)."""
    result = classify("我哪里比较薄弱")
    assert result["intent"] == "diagnosis"


def test_intent_classify_compound_full_workflow() -> None:
    """Issue #3: compound request should be full_workflow."""
    result = classify("帮我构建学习画像、学习路径和学习资源")
    assert result["intent"] == "full_workflow"
    assert result["should_run_agents"] is True


def test_intent_画像_with_self_intro_is_profile_update() -> None:
    """我是计算机新生 + 构建学习画像 → profile_update，不能归到 learning_plan。"""
    assert classify("我是计算机新生，帮我构建学习画像")["intent"] == "profile_update"


def test_intent_生成学习路径_is_learning_plan() -> None:
    """帮我生成学习路径 → learning_plan。"""
    result = classify("帮我生成学习路径")
    assert result["intent"] == "learning_plan"
    assert result["should_run_agents"] is True


def test_intent_根据路径推荐资源_is_resource_request() -> None:
    """根据我的学习路径推荐资源 → resource_request。"""
    result = classify("根据我的学习路径推荐资源")
    assert result["intent"] == "resource_request"
    assert result["should_run_agents"] is True


def test_intent_找学习资源_is_resource_request() -> None:
    """帮我找学习资源 → resource_request。"""
    result = classify("帮我找学习资源")
    assert result["intent"] == "resource_request"
    assert result["should_run_agents"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Time budget parsing regression tests
# ═══════════════════════════════════════════════════════════════════════════


def test_three_day_plan_estimated_days_is_3() -> None:
    sid = "regression_three_day_plan"
    conversation_store.reset(sid)

    reply(
        sid,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"
            r"\uff0c\u4e3a\u4e86\u8003\u8bd5\u901a\u8fc7"
        ),
    )

    time_message = zh(r"\u6211\u67093\u5929\u65f6\u95f4")
    time_intent = classify(time_message)
    assert time_intent["intent"] == "profile_update"
    reply(sid, time_message)

    content = reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state = conversation_store.get(sid)
    assert state.last_result is not None
    path = product._to_learning_path(state.last_result)
    assert path["estimatedDays"] == 3, f"Expected 3 days, got {path['estimatedDays']}"
    assert_contains(content, zh(r"\u5b66\u4e60\u65b9\u6848\u5df2\u751f\u6210"))


def test_one_week_plan_estimated_days_is_7() -> None:
    sid = "regression_one_week_plan"
    conversation_store.reset(sid)

    reply(
        sid,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u4eba\u5de5\u667a\u80fd\u5bfc\u8bba"
            r"\uff0c\u4e3a\u4e86\u5165\u95e8"
        ),
    )

    time_message = zh(r"\u6211\u6709\u4e00\u5468\u65f6\u95f4")
    time_intent = classify(time_message)
    assert time_intent["intent"] == "profile_update"
    reply(sid, time_message)

    content = reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state = conversation_store.get(sid)
    assert state.last_result is not None
    path = product._to_learning_path(state.last_result)
    assert path["estimatedDays"] == 7, f"Expected 7 days, got {path['estimatedDays']}"
    assert_contains(content, zh(r"\u5b66\u4e60\u65b9\u6848\u5df2\u751f\u6210"))


def test_ten_day_plan_estimated_days_is_10() -> None:
    sid = "regression_ten_day_plan"
    conversation_store.reset(sid)

    reply(
        sid,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"
            r"\uff0c\u4e3a\u4e86\u8003\u8bd5\u901a\u8fc7"
        ),
    )

    time_message = zh(r"\u6211\u670910\u5929\u65f6\u95f4")
    time_intent = classify(time_message)
    assert time_intent["intent"] == "profile_update"
    reply(sid, time_message)

    content = reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state = conversation_store.get(sid)
    assert state.last_result is not None
    path = product._to_learning_path(state.last_result)
    assert path["estimatedDays"] == 10, f"Expected 10 days, got {path['estimatedDays']}"
    assert_contains(content, zh(r"\u5b66\u4e60\u65b9\u6848\u5df2\u751f\u6210"))


def test_no_time_plan_uses_reasonable_default() -> None:
    """When user provides no time info, estimatedDays should be a reasonable
    default (14), NOT hardcoded to 2 or any other small number."""
    sid = "regression_no_time_plan"
    conversation_store.reset(sid)

    reply(
        sid,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"
            r"\uff0c\u4e3a\u4e86\u8003\u8bd5\u901a\u8fc7"
        ),
    )

    # No time message — just generate the plan directly
    content = reply(sid, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state = conversation_store.get(sid)
    assert state.last_result is not None
    path = product._to_learning_path(state.last_result)

    # Must not be hardcoded to 2
    assert path["estimatedDays"] != 2, (
        f"estimatedDays MUST NOT be hardcoded to 2. Got {path['estimatedDays']}"
    )
    # The default should be >= 7
    assert path["estimatedDays"] >= 7, (
        f"Default estimatedDays should be >= 7 (reasonable study plan)."
        f" Got {path['estimatedDays']}"
    )
    assert_contains(content, zh(r"\u5b66\u4e60\u65b9\u6848\u5df2\u751f\u6210"))


def test_multi_course_time_budget_stable() -> None:
    """Regression: different courses must each parse their own time budgets
    correctly.  A data-structures plan with '两天' must not interfere with
    an AI plan with '一周'."""
    # ── Course A: data_structures, 2 days ──
    sid_a = "regression_multi_course_a"
    conversation_store.reset(sid_a)
    reply(
        sid_a,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u6570\u636e\u7ed3\u6784"
            r"\uff0c\u4e3a\u4e86\u8003\u8bd5\u901a\u8fc7"
        ),
    )
    reply(sid_a, zh(r"\u6211\u6709\u4e24\u5929\u65f6\u95f4"))
    reply(sid_a, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state_a = conversation_store.get(sid_a)
    path_a = product._to_learning_path(state_a.last_result)
    assert path_a["estimatedDays"] == 2, (
        f"Course A (data_structures) should be 2 days, got {path_a['estimatedDays']}"
    )

    # ── Course B: ai_intro, one week ──
    sid_b = "regression_multi_course_b"
    conversation_store.reset(sid_b)
    reply(
        sid_b,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u4eba\u5de5\u667a\u80fd\u5bfc\u8bba"
            r"\uff0c\u4e3a\u4e86\u5165\u95e8"
        ),
    )
    reply(sid_b, zh(r"\u6211\u6709\u4e00\u5468\u65f6\u95f4"))
    reply(sid_b, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state_b = conversation_store.get(sid_b)
    path_b = product._to_learning_path(state_b.last_result)
    assert path_b["estimatedDays"] == 7, (
        f"Course B (ai_intro) should be 7 days, got {path_b['estimatedDays']}"
    )

    # ── Course C: ai_intro, 10 days ──
    sid_c = "regression_multi_course_c"
    conversation_store.reset(sid_c)
    reply(
        sid_c,
        zh(
            r"\u6211\u662f\u8f6f\u4ef6\u5de5\u7a0b\u5927\u4e8c\u5b66\u751f"
            r"\uff0c\u60f3\u5b66\u4e60\u4eba\u5de5\u667a\u80fd\u5bfc\u8bba"
            r"\uff0c\u4e3a\u4e86\u5165\u95e8"
        ),
    )
    reply(sid_c, zh(r"\u6211\u670910\u5929\u65f6\u95f4"))
    reply(sid_c, zh(r"\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848"))
    state_c = conversation_store.get(sid_c)
    path_c = product._to_learning_path(state_c.last_result)
    assert path_c["estimatedDays"] == 10, (
        f"Course C (ai_intro) should be 10 days, got {path_c['estimatedDays']}"
    )


if __name__ == "__main__":
    tests = [
        test_fresh_start_has_no_fake_profile,
        test_profile_update_is_not_casual_chat,
        test_incremental_slot_filling,
        test_plan_request_needs_core_profile,
        test_low_value_background_does_not_fill_core_profile,
        test_major_background_fills_core_profile,
        test_real_dialogue_extracts_time_and_learning_levels,
        test_fragment_background_is_profile_update,
        test_force_generate_bypasses_profile_guard,
        test_casual_chat_uses_existing_context,
        test_data_structure_two_day_plan_uses_correct_course_and_duration,
        test_intent_classify_profile_keyword_画像,
        test_intent_classify_diagnosis_question,
        test_intent_classify_compound_full_workflow,
        test_intent_画像_with_self_intro_is_profile_update,
        test_intent_生成学习路径_is_learning_plan,
        test_intent_根据路径推荐资源_is_resource_request,
        test_intent_找学习资源_is_resource_request,
        test_three_day_plan_estimated_days_is_3,
        test_one_week_plan_estimated_days_is_7,
        test_ten_day_plan_estimated_days_is_10,
        test_no_time_plan_uses_reasonable_default,
        test_multi_course_time_budget_stable,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
