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


if __name__ == "__main__":
    test_data_structure_exam_plan_uses_full_course_outline()
    print("PASS planner_agent_test")
