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
            stage_id = "stage_1" if index <= 3 else "stage_2"
            chapter = "03 Stack and Queue" if stage_id == "stage_1" else "06 Search and Sort"
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
                    "related_stage_id": stage_id,
                    "related_chapter": chapter,
                    "related_knowledge_points": ["Stack", "Queue"],
                    "quality_status": "passed",
                    "reason": "Matches stage_1 and the learner's weak points.",
                }
            )
        return json.dumps({"resources": resources})


class UngroundedChapterLLM(ResourceLLM):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        payload = json.loads(super().chat(messages, **kwargs))
        payload["resources"][0]["related_chapter"] = "Neural Networks and Deep Learning"
        return json.dumps(payload)


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
    required_fields = {
        "id",
        "title",
        "type",
        "related_stage_id",
        "related_chapter",
        "knowledge_points",
        "source",
        "source_type",
        "generation_mode",
        "quality_status",
        "reason",
        "evidence",
        "fallback_reason",
    }
    assert_true(
        all(required_fields.issubset(item) for item in resources),
        "fallback resources should expose the complete P1 provenance contract",
    )
    assert_true(
        {item["related_stage_id"] for item in resources} == {"stage_1", "stage_2"},
        "fallback resources should cover every learning-path stage",
    )
    assert_true(all(item["source_type"] == "course_knowledge_base" for item in resources), "catalog grounding should be explicit")
    assert_true(all(item["generation_mode"] == "fallback" for item in resources), "rule fallback mode should be explicit")
    assert_true(all(item["quality_status"] == "fallback" for item in resources), "grounded fallback should use fallback quality")
    assert_true(all(item["fallback_reason"] for item in resources), "fallback resources must explain why fallback was used")
    assert_true(all(isinstance(item["evidence"], list) and item["evidence"] for item in resources), "resources should include readable evidence")


def test_llm_success_is_marked_and_normalized() -> None:
    result = ResourceAgent(llm_client=ResourceLLM()).run(_context("data_structures"))
    resources = result["resources"]

    assert_true(len(resources) >= 5, "LLM resources should be accepted when complete")
    assert_true(all(item["source"] == SOURCE_LLM for item in resources), "LLM resources should be marked llm_generated")
    assert_true(all(item.get("quality_status") for item in resources), "LLM resources should include quality status")
    assert_true(all(item.get("related_knowledge_points") for item in resources), "LLM resources should include knowledge binding")
    assert_true(all(item["source_type"] == "course_knowledge_base" for item in resources), "LLM resources should disclose grounding source")
    assert_true(all(item["generation_mode"] == "llm" for item in resources), "complete LLM output should use llm generation mode")
    assert_true(all(item["quality_status"] == "passed" for item in resources), "grounded complete LLM resources should pass")
    assert_true(all(item["fallback_reason"] == "" for item in resources), "successful LLM resources should not claim fallback")


def test_insufficient_course_context_is_not_disguised_as_course_kb() -> None:
    context = _context("course_not_in_catalog")
    result = ResourceAgent().run(context)
    resources = result["resources"]

    assert_true(resources, "learning-path context should still allow transparent fallback resources")
    assert_true(all(item["source"] == SOURCE_FALLBACK for item in resources), "insufficient context should use rule fallback")
    assert_true(all(item["source_type"] == "agent_generated" for item in resources), "inferred chapters must not claim course KB provenance")
    assert_true(all(item["quality_status"] == "insufficient_context" for item in resources), "unverified context should lower quality status")
    assert_true(
        all("No verified course knowledge-base match" in item["fallback_reason"] for item in resources),
        "fallback reason should disclose missing course grounding",
    )


def test_llm_cannot_claim_a_chapter_outside_the_course_catalog() -> None:
    resources = ResourceAgent(llm_client=UngroundedChapterLLM()).run(_context("data_structures"))["resources"]
    first = resources[0]

    assert_true("Neural Networks" not in first["related_chapter"], "ungrounded LLM chapters should not be preserved")
    assert_true(first["generation_mode"] == "mixed", "rule-corrected LLM binding should be marked mixed")
    assert_true(first["quality_status"] == "warning", "rule-corrected LLM binding should require review")
    assert_true(
        any("rule binding" in evidence for evidence in first["evidence"]),
        "evidence should disclose automatic binding correction",
    )


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
    test_insufficient_course_context_is_not_disguised_as_course_kb()
    test_llm_cannot_claim_a_chapter_outside_the_course_catalog()
    test_data_structures_resources_do_not_drift_to_ai_topics()
    test_ai_intro_resources_stay_on_ai_topics()
    print("PASS resource_agent_test")
