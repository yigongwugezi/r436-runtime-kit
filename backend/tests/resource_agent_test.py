import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.resource_agent import ResourceAgent, SOURCE_FALLBACK, SOURCE_LLM
from app.services.llm_client import BaseLLMClient


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class ResourceLLM(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        resources = []
        for index, resource_type in enumerate(["lecture", "mindmap", "quiz", "reading", "practice"], start=1):
            resources.append(
                {
                    "resource_id": f"llm_res_{index:03d}",
                    "type": resource_type,
                    "title": f"LLM resource {index}",
                    "description": "Generated from staged course context.",
                    "content_format": "json" if resource_type == "quiz" else ("mermaid" if resource_type == "mindmap" else "markdown"),
                    "content": "mindmap\n  root((Data Structures))\n    Stack" if resource_type == "mindmap" else "Course grounded content.",
                    "items": [
                        {
                            "question_id": "q_001",
                            "stem": "Explain stack push/pop and complexity.",
                            "answer": "O(1) for normal push/pop.",
                        }
                    ]
                    if resource_type == "quiz"
                    else None,
                    "related_stage_id": "stage_1",
                    "related_chapter": "03 Stack and Queue",
                    "related_knowledge_points": ["Stack", "Queue"],
                    "quality_status": "passed",
                    "reason": "Matches stage_1 and the learner's weak points.",
                }
            )
        return json.dumps({"resources": resources})


def _context(course_id: str) -> dict[str, Any]:
    return {
        "session_id": f"resource_agent_{course_id}",
        "course_id": course_id,
        "user_message": "I need a short review plan.",
        "profile": {
            "knowledge_base": {"value": "basic programming"},
            "learning_goal": {"value": "exam review"},
            "cognitive_style": {"value": "diagram and practice"},
            "coding_ability": {"value": "beginner"},
            "learning_rhythm": {"value": "48 hours"},
        },
        "diagnosis": {
            "weak_knowledge_points": [
                {"name": "Stack and queue", "priority": "high", "chapter_id": "03"},
                {"name": "Sorting", "priority": "medium", "chapter_id": "06"},
            ]
        },
        "learning_path": [
            {
                "stage_id": "stage_1",
                "title": "Foundation",
                "duration": "Day 1",
                "goal": "Build concept map.",
                "tasks": ["Read chapter notes", "Do quick quiz"],
                "reason": "High priority basics.",
            },
            {
                "stage_id": "stage_2",
                "title": "Practice",
                "duration": "Day 2",
                "goal": "Practice typical problems.",
                "tasks": ["Run practice case"],
                "reason": "Exam review needs exercises.",
            },
        ],
    }


def _resource_text(resources: list[dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(resource, ensure_ascii=False)
        for resource in resources
    )


def test_rule_fallback_is_marked_and_stage_bound() -> None:
    result = ResourceAgent().run(_context("data_structures"))
    resources = result["resources"]

    assert_true(len(resources) >= 5, "fallback should generate at least five resources")
    assert_true(all(item["source"] == SOURCE_FALLBACK for item in resources), "fallback resources must not be llm_generated")
    assert_true(all(item.get("related_stage_id") for item in resources), "resources should bind to learning stages")
    assert_true(all(item.get("related_knowledge_points") for item in resources), "resources should bind to knowledge points")
    assert_true(all(item.get("reason") for item in resources), "resources should explain generation reason")


def test_llm_success_is_marked_and_normalized() -> None:
    result = ResourceAgent(llm_client=ResourceLLM()).run(_context("data_structures"))
    resources = result["resources"]

    assert_true(len(resources) >= 5, "LLM resources should be accepted when complete")
    assert_true(all(item["source"] == SOURCE_LLM for item in resources), "LLM resources should be marked llm_generated")
    assert_true(all(item.get("quality_status") for item in resources), "LLM resources should include quality status")
    assert_true(all(item.get("related_knowledge_points") for item in resources), "LLM resources should include knowledge binding")


def test_data_structures_resources_do_not_drift_to_ai_topics() -> None:
    resources = ResourceAgent().run(_context("data_structures"))["resources"]
    text = _resource_text(resources)

    forbidden = ["神经网络", "自然语言处理", "机器学习", "NLP", "强化学习"]
    assert_true(not any(term in text for term in forbidden), "data structures resources should not drift into AI topics")
    expected = ["复杂度", "线性表", "链表", "栈", "队列", "树", "排序", "查找", "图"]
    assert_true(any(term in text for term in expected), "data structures resources should use course chapters")


def test_ai_intro_resources_stay_on_ai_topics() -> None:
    resources = ResourceAgent().run(_context("ai_intro"))["resources"]
    text = _resource_text(resources)

    expected = ["机器学习", "神经网络", "自然语言处理", "搜索", "知识表示", "智能体", "人工智能"]
    assert_true(any(term in text for term in expected), "AI intro resources should use AI course topics")


if __name__ == "__main__":
    test_rule_fallback_is_marked_and_stage_bound()
    test_llm_success_is_marked_and_normalized()
    test_data_structures_resources_do_not_drift_to_ai_topics()
    test_ai_intro_resources_stay_on_ai_topics()
    print("PASS resource_agent_test")
