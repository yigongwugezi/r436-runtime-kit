import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _profile() -> dict:
    return {
        "major_background": {"value": "软件工程大二学生"},
        "knowledge_base": {"value": "数据结构基础一般"},
        "weak_points": {"value": "栈和队列不熟，树和图比较薄弱"},
        "learning_goal": {"value": "为了考试通过"},
        "cognitive_style": {"value": "喜欢图解和练习题"},
        "learning_rhythm": {"value": "48小时完成"},
    }


def test_data_structure_exam_plan_uses_full_course_outline() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_test",
            "course_id": "data_structures",
            "user_message": "我是软件工程大二学生，想48小时复习数据结构，为了考试通过，喜欢图解和练习题。",
            "profile": _profile(),
            "profile_facts": {
                "background": "软件工程大二学生",
                "target_course": "数据结构",
                "knowledge_base": "数据结构基础一般",
                "weak_points": "栈和队列不熟，树和图比较薄弱",
                "learning_goal": "为了考试通过",
                "time_budget": "48小时",
                "preference": "图解、练习题",
            },
            "diagnosis": {
                "weak_knowledge_points": [
                    {"name": "栈、队列与递归", "priority": "high"},
                ]
            },
        }
    )

    path = result["learning_path"]
    text = " ".join(str(stage) for stage in path)

    assert_true(result["estimatedDays"] == 2, "48 hours should be compressed to 2 days")
    assert_true(len(path) >= 3, "short exam plan should still be split into actionable stages")
    assert_true("数据结构与算法复杂度基础" in text, "plan should include complexity fundamentals")
    assert_true("线性表" in text, "plan should include linear list")
    assert_true("栈、队列" in text, "plan should include stack and queue")
    assert_true("树、二叉树" in text, "plan should include tree chapter")
    assert_true("图结构" in text, "plan should include graph chapter")
    assert_true("查找与排序" in text, "plan should include search and sort")
    assert_true("神经网络" not in text and "机器学习" not in text, "data structure plan must not leak AI course topics")
    assert_true(all(stage.get("reason") for stage in path), "each stage should explain planning reason")


def test_diagnosis_weak_points_drive_plan_metadata() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_diagnosis_test",
            "user_message": "我递归和动态规划都不太会，帮我安排学习路径。",
            "profile": {"learning_goal": {"value": "学习算法基础"}},
            "diagnosis": {
                "weak_knowledge_points": ["递归", "动态规划"],
                "evidence_chain": [
                    {
                        "source": "user_message",
                        "signal": "我递归和动态规划都不太会",
                        "related_knowledge_point": "递归",
                        "weight": 0.7,
                    }
                ],
                "needs_more_evidence": False,
                "recommended_next_actions": ["先补递归基础，再进入动态规划练习"],
            },
        }
    )

    text = str(result)
    assert_true(result["learning_path"], "diagnosis-driven plan should have stages")
    assert_true(result["stages"] == result["learning_path"], "stages should remain compatible with learning_path")
    assert_true("递归" in text and "动态规划" in text, "plan should reflect weak points")
    assert_true(result["diagnosis_used"] is True, "diagnosis should be marked as used")
    assert_true(result["diagnosis_references"], "diagnosis references should be exposed")
    assert_true(result["stage_rationales"], "stage rationales should be exposed")
    assert_true("estimatedDays" in result, "estimatedDays must remain compatible")


def test_insufficient_diagnosis_starts_with_probe_stage() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_insufficient_diagnosis_test",
            "user_message": "我觉得哪里都不太会。",
            "diagnosis": {
                "weak_knowledge_points": [],
                "evidence_chain": [
                    {
                        "source": "fallback_rule",
                        "signal": "我觉得哪里都不太会",
                        "related_knowledge_point": None,
                        "weight": 0.2,
                    }
                ],
                "needs_more_evidence": True,
                "recommended_next_actions": ["完成一次基础测验"],
            },
        }
    )

    first_stage = result["learning_path"][0]
    first_text = str(first_stage)
    assert_true(result["needs_more_diagnosis"] is True, "insufficient evidence should request more diagnosis")
    assert_true("evidence_insufficient" in result["risk_flags"], "insufficient evidence should be flagged")
    assert_true(any(word in first_text for word in ["诊断", "测验", "确认薄弱点"]), "first stage should confirm weak points")
    assert_true("递归" not in first_text and "动态规划" not in first_text, "planner must not invent specific weak points")


def test_tight_time_budget_changes_priority_basis() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_tight_time_test",
            "user_message": "两天复习数据结构",
            "profile": {
                "learning_goal": {"value": "复习数据结构"},
                "learning_rhythm": {"value": "两天"},
            },
            "diagnosis": {
                "weak_knowledge_points": [{"name": "递归", "priority": "high"}],
                "evidence_chain": [{"source": "user_message", "related_knowledge_point": "递归"}],
                "needs_more_evidence": False,
            },
        }
    )

    rationale_text = str(result["stage_rationales"])
    assert_true(result["estimatedDays"] == 2, "two-day budget should stay compressed")
    assert_true("time_budget" in result["priority_basis"], "tight time should affect priority basis")
    assert_true("time_budget_tight" in result["risk_flags"], "tight time should be flagged")
    assert_true("压缩" in rationale_text or "优先" in rationale_text, "rationale should explain compression/priority")


def test_daily_hour_budget_marks_plan_as_time_limited() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_daily_hour_budget_test",
            "user_message": "我是计算机新生，想学习算法基础。",
            "profile": {
                "major_background": {"value": "计算机新生"},
                "learning_rhythm": {"value": "每天两小时"},
                "learning_goal": {"value": "学习算法基础"},
            },
            "diagnosis": {
                "weak_knowledge_points": ["递归"],
                "evidence_chain": [{"source": "user_message", "related_knowledge_point": "递归"}],
                "needs_more_evidence": False,
            },
        }
    )

    assert_true("time_budget" in result["priority_basis"], "daily-hour budget should affect priority")
    assert_true("time_budget_tight" in result["risk_flags"], "daily-hour budget should be flagged")
    assert_true("每天学习时间有限" in str(result["stage_rationales"]), "rationale should mention limited daily time")


def _visible_text(result: dict) -> str:
    return str(
        {
            "plan_summary": result.get("plan_summary"),
            "summary": result.get("summary"),
            "learning_path": result.get("learning_path"),
            "stage_rationales": result.get("stage_rationales"),
            "recommended_resource_strategy": result.get("recommended_resource_strategy"),
            "diagnosis_references": result.get("diagnosis_references"),
        }
    )


def test_one_month_time_budget_is_not_default_14_days() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_one_month_budget_test",
            "user_message": "帮我安排学习微积分。",
            "profile": {
                "time_budget": {"value": "1个月"},
                "learning_goal": {"value": "学习微积分"},
            },
            "diagnosis": {"weak_knowledge_points": ["无诊断数据"]},
        }
    )

    visible = _visible_text(result)
    assert_true(result["estimatedDays"] == 30, "1个月 should be planned as about 30 days")
    assert_true("14 天" not in visible and "14天" not in visible, "one-month plan must not show 14 days")
    assert_true("无诊断数据" not in visible, "placeholder weak point must not be user-visible")


def test_chinese_one_month_time_budget_is_30_days() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_chinese_one_month_budget_test",
            "user_message": "帮我安排学习微积分。",
            "profile": {
                "time_budget": {"value": "一个月"},
                "learning_goal": {"value": "学习微积分"},
            },
            "diagnosis": {"weak_knowledge_points": []},
        }
    )

    assert_true(result["estimatedDays"] == 30, "一个月 should be planned as about 30 days")


def test_placeholder_weak_point_is_filtered_from_learning_content() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_placeholder_weak_point_test",
            "user_message": "帮我安排学习路径。",
            "diagnosis": {
                "weak_knowledge_points": ["无诊断数据"],
                "needs_more_evidence": True,
            },
        }
    )

    visible = _visible_text(result)
    first_title = result["learning_path"][0]["title"]
    assert_true("无诊断数据" not in visible, "placeholder must not appear in stage content")
    assert_true(result["needs_more_diagnosis"] is True, "placeholder-only diagnosis should need more diagnosis")
    assert_true("evidence_insufficient" in result["risk_flags"], "placeholder-only diagnosis should flag insufficient evidence")
    assert_true(any(word in first_title for word in ["诊断", "测验", "评估", "确认薄弱点"]), "first stage should be user-friendly diagnosis")


def test_visible_text_translates_internal_english_fallbacks() -> None:
    result = PlannerAgent().run(
        {
            "session_id": "planner_visible_text_chinese_test",
            "user_message": "我不确定哪里薄弱。",
            "diagnosis": {
                "weak_knowledge_points": [],
                "needs_more_evidence": True,
                "evidence_chain": [
                    {
                        "source": "fallback_rule",
                        "signal": "Complete one quiz_result or practice_result so the next diagnosis has behavioral evidence.",
                    },
                    {
                        "source": "fallback_rule",
                        "signal": "Submit feedback after using the recommended resource.",
                    },
                ],
            },
        }
    )

    visible = _visible_text(result)
    for forbidden in ["Complete one quiz_result", "practice_result", "Submit feedback", "recommended resource", "fallback_rule"]:
        assert_true(forbidden not in visible, f"visible planner text must not expose internal English fallback: {forbidden}")
    assert_true(any(word in visible for word in ["测验", "练习", "反馈", "薄弱点确认"]), "visible text should use Chinese learning language")


# ═══════════════════════════════════════════════════════════════════════════
# _infer_days() time-budget regression tests
# ═══════════════════════════════════════════════════════════════════════════

_AGENT = PlannerAgent()


def _infer(message: str, profile: dict | None = None) -> int:
    """Shortcut to call _infer_days with a message-only context."""
    p = profile or {}
    return _AGENT._infer_days(message, p)


def test_infer_days_48_hours_to_2_days() -> None:
    assert _infer("我想48小时完成") == 2


def test_infer_days_two_days_cn() -> None:
    assert _infer("我有两天时间") == 2


def test_infer_days_2_days_arabic() -> None:
    assert _infer("给我2天") == 2


def test_infer_days_10_days() -> None:
    assert _infer("需要10天完成") == 10


def test_infer_days_one_week() -> None:
    assert _infer("我有一周时间") == 7


def test_infer_days_3_days() -> None:
    assert _infer("三天完成") == 3


def test_infer_days_no_time_defaults_to_14() -> None:
    assert _infer("我想学习数据结构") == 14


def test_infer_days_from_profile_learning_rhythm() -> None:
    assert _infer("请生成学习路径", {"learning_rhythm": {"value": "5天"}}) == 5


def test_infer_days_from_profile_learning_goal() -> None:
    assert _infer("开始规划", {"learning_goal": {"value": "我想用三天复习"}}) == 3


def test_infer_days_12_days_cn_compound() -> None:
    assert _infer("十二天左右") == 12


def test_infer_days_20_days_cn_compound() -> None:
    assert _infer("需要二十天") == 20


def test_infer_days_15_days_cn_compound() -> None:
    assert _infer("十五天") == 15


def test_infer_days_two_weeks_cn() -> None:
    assert _infer("两周时间") == 14


def test_infer_days_1_week_explicit() -> None:
    assert _infer("一个星期") == 7


def test_infer_days_one_month_arabic() -> None:
    assert _infer("1个月") == 30


def test_infer_days_one_month_cn() -> None:
    assert _infer("一个月") == 30


def test_infer_days_profile_message_both_have_time_prefer_profile() -> None:
    """When both profile and message have time info, message context is included
    but the profile dimension (learning_rhythm) is also scanned — the first
    match in the combined text wins."""
    assert _infer(
        "请生成学习路径",
        {
            "learning_rhythm": {"value": "10天"},
            "learning_goal": {"value": "考试通过"},
        },
    ) == 10


def test_infer_days_clamped_to_60() -> None:
    assert _infer("给我100天") == 60


def test_infer_days_zero_days_clamped_to_1() -> None:
    assert _infer("0天完成") == 1


def test_infer_days_hours_vs_days_prefer_hours_first() -> None:
    """When both hours and days are present, hour match runs first."""
    assert _infer("48小时内完成，大约2天") == 2


def test_infer_days_fallback_is_not_hardcoded_2() -> None:
    """Regression: the fallback must NOT be hardcoded to any specific number
    like 2.  It must be 14 — a reasonable general-purpose default."""
    assert _infer("") == 14
    assert _infer("学习一下") == 14


if __name__ == "__main__":
    test_data_structure_exam_plan_uses_full_course_outline()
    test_diagnosis_weak_points_drive_plan_metadata()
    test_insufficient_diagnosis_starts_with_probe_stage()
    test_tight_time_budget_changes_priority_basis()
    test_daily_hour_budget_marks_plan_as_time_limited()
    test_one_month_time_budget_is_not_default_14_days()
    test_chinese_one_month_time_budget_is_30_days()
    test_placeholder_weak_point_is_filtered_from_learning_content()
    test_visible_text_translates_internal_english_fallbacks()
    test_infer_days_48_hours_to_2_days()
    test_infer_days_two_days_cn()
    test_infer_days_2_days_arabic()
    test_infer_days_10_days()
    test_infer_days_one_week()
    test_infer_days_3_days()
    test_infer_days_no_time_defaults_to_14()
    test_infer_days_from_profile_learning_rhythm()
    test_infer_days_from_profile_learning_goal()
    test_infer_days_12_days_cn_compound()
    test_infer_days_20_days_cn_compound()
    test_infer_days_15_days_cn_compound()
    test_infer_days_two_weeks_cn()
    test_infer_days_1_week_explicit()
    test_infer_days_one_month_arabic()
    test_infer_days_one_month_cn()
    test_infer_days_profile_message_both_have_time_prefer_profile()
    test_infer_days_clamped_to_60()
    test_infer_days_zero_days_clamped_to_1()
    test_infer_days_hours_vs_days_prefer_hours_first()
    test_infer_days_fallback_is_not_hardcoded_2()
    print("PASS planner_agent_test")
