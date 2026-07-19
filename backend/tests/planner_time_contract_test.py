"""Focused regression check for explicit learner time constraints."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent


def main() -> None:
    facts = {
        "target_course": "数据结构",
        "background": "软件工程大二",
        "knowledge_base": "学过基础 C 语言，未接触数据结构",
        "learning_goal": "考研",
        "time_budget": "三个月，每天一小时",
        "daily_minutes": "60",
    }
    result = PlannerAgent(llm_client=None).run({
        "profile_facts": facts,
        "user_message": "课程：数据结构；周期：三个月；每天一小时",
    })
    stages = result["learning_path"]
    tasks = [task for stage in stages for task in stage.get("tasks", [])]

    assert result["estimatedDays"] == 90
    assert result["dailyMinutes"] == 60
    assert sum(stage.get("estimatedDays", stage.get("estimated_days", 0)) for stage in stages) == 90
    assert len(stages) >= 4 and len(tasks) == 180
    assert len({task["type"] for task in tasks}) >= 4
    assert any(task["type"] != "read_doc" for task in tasks)


if __name__ == "__main__":
    main()
