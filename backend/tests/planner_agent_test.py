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
    test_infer_days_profile_message_both_have_time_prefer_profile()
    test_infer_days_clamped_to_60()
    test_infer_days_zero_days_clamped_to_1()
    test_infer_days_hours_vs_days_prefer_hours_first()
    test_infer_days_fallback_is_not_hardcoded_2()
    print("PASS planner_agent_test")
