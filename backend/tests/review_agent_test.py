import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.review_agent import ReviewAgent
from app.services.orchestrator import AgentOrchestrator


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _resource(resource_type: str, resource_id: str, chapter: str = "03 栈、队列与递归") -> dict[str, Any]:
    content_by_type = {
        "lecture": "## 栈与队列讲义\n\n先理解基本操作，再分析边界条件和时间复杂度，最后完成阶段练习。",
        "mindmap": "mindmap\n  root((栈与队列))\n    栈\n      入栈\n      出栈\n    队列",
        "reading": "## 阅读任务\n\n阅读课程对应章节，整理栈和队列的定义、操作、复杂度与常见误区。",
        "practice": "## 实操任务\n\n1. 实现顺序栈。\n2. 运行边界用例。\n3. 记录复杂度和错误原因。",
    }
    return {
        "resource_id": resource_id,
        "type": resource_type,
        "title": f"{resource_type} resource",
        "description": "课程内资源",
        "content_format": "json" if resource_type == "quiz" else "markdown",
        "content": content_by_type.get(resource_type, ""),
        "items": [
            {"question_id": "q1", "stem": "栈的入栈操作复杂度是什么？", "answer": "O(1)"}
        ] if resource_type == "quiz" else None,
        "related_stage_id": "stage_1",
        "related_chapter": chapter,
        "related_knowledge_points": ["栈", "队列"],
        "source": "rule_based_fallback",
        "source_type": "course_knowledge_base",
        "generation_mode": "fallback",
        "quality_status": "fallback",
        "reason": "Matches the current learning stage and course chapter.",
        "evidence": ["Learning stage: stage_1", f"Course chapter: {chapter}"],
        "fallback_reason": "LLM client is not configured; deterministic rule resources were generated.",
    }


def _context() -> dict[str, Any]:
    return {
        "course_id": "data_structures",
        "profile": {
            key: {"value": value}
            for key, value in {
                "major_background": "软件工程",
                "knowledge_base": "基础一般",
                "learning_goal": "通过考试",
                "cognitive_style": "图解和练习",
                "learning_rhythm": "48小时",
            }.items()
        },
        "knowledge_context": {
            "course_id": "data_structures",
            "source": "course_knowledge_base",
            "retrieved_points": [{"chapter_id": "03", "name": "栈、队列与递归"}],
        },
        "learning_path": [
            {
                "stage_id": "stage_1",
                "title": "栈与队列",
                "duration": "第 1-2 天",
                "goal": "掌握基本操作",
                "tasks": ["阅读讲义", "完成练习"],
            }
        ],
        "estimatedDays": 2,
        "resources": [
            _resource("lecture", "res_lecture"),
            _resource("mindmap", "res_mindmap"),
            _resource("quiz", "res_quiz"),
            _resource("reading", "res_reading"),
            _resource("practice", "res_practice"),
        ],
    }


def _review(context: dict[str, Any]) -> dict[str, Any]:
    return ReviewAgent().run(context)["review"]


def _check(review: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(item for item in review["checks"] if item["check_id"] == check_id)


def test_valid_review_passes_and_keeps_legacy_fields() -> None:
    review = _review(_context())

    assert_true(review["quality_status"] == "passed", "valid course-grounded output should pass")
    assert_true(all(item["status"] == "passed" for item in review["checks"]), "all valid checks should pass")
    assert_true(
        all(item["status"] in {"passed", "warning", "blocked"} for item in review["checks"]),
        "checks must use the P0 three-state contract",
    )
    assert_true(all(key in review for key in ("checks", "summary", "anti_hallucination")), "legacy review fields must remain")


def test_foreign_chapter_is_blocked() -> None:
    context = _context()
    context["resources"][0]["related_chapter"] = "神经网络与深度学习"
    review = _review(context)

    assert_true(review["quality_status"] == "blocked", "foreign course chapter should block review")
    assert_true(_check(review, "course_chapter_alignment")["status"] == "blocked", "chapter check should expose blocked")


def test_empty_and_short_content_are_reported() -> None:
    empty_context = _context()
    empty_context["resources"][0]["content"] = ""
    empty_review = _review(empty_context)
    assert_true(_check(empty_review, "resource_content_quality")["status"] == "blocked", "empty content should block")

    short_context = _context()
    short_context["resources"][0]["content"] = short_context["resources"][0]["title"]
    short_review = _review(short_context)
    assert_true(_check(short_review, "resource_content_quality")["status"] == "warning", "title-only content should warn")


def test_resource_type_mismatches_warn() -> None:
    cases = [
        ("mindmap", "这是一段普通说明文字，没有图结构。", None),
        ("quiz", "", []),
        ("practice", "这是一段概念介绍，没有可执行内容。", None),
    ]
    for resource_type, content, items in cases:
        context = _context()
        resource = next(item for item in context["resources"] if item["type"] == resource_type)
        resource["content"] = content
        resource["items"] = items
        review = _review(context)
        assert_true(
            _check(review, "resource_type_match")["status"] == "warning",
            f"{resource_type} content mismatch should warn",
        )


def test_untrusted_resource_sources_warn() -> None:
    for source in ("mock", "unknown", ""):
        context = _context()
        context["resources"][0]["source"] = source
        review = _review(context)
        assert_true(_check(review, "provenance_trust")["status"] == "warning", f"source={source!r} should warn")


def test_invalid_time_budget_is_reported_without_breaking_48_hour_plan() -> None:
    invalid_estimate = _context()
    invalid_estimate["estimatedDays"] = 0
    invalid_review = _review(invalid_estimate)
    assert_true(_check(invalid_review, "path_time_budget")["status"] == "blocked", "non-positive estimate should block")

    inverted = _context()
    inverted["learning_path"][0]["duration"] = "第 3-2 天"
    inverted_review = _review(inverted)
    assert_true(_check(inverted_review, "path_time_budget")["status"] == "warning", "inverted duration should warn")

    valid_review = _review(_context())
    assert_true(_check(valid_review, "path_time_budget")["status"] == "passed", "48 hours mapped to 2 days should pass")


def test_blocked_review_does_not_block_orchestrator() -> None:
    class BlockedReviewProbe:
        agent_id = "review_agent"
        agent_name = "blocked review probe"

        def run(self, context: dict[str, Any]) -> dict[str, Any]:
            return {
                "review": {
                    "quality_status": "blocked",
                    "checks": [],
                    "summary": "blocked for test",
                    "anti_hallucination": {"enabled": True},
                },
                "agent_step": {"status": "completed", "summary": "review completed"},
            }

        def validate_result(self, result: dict[str, Any]) -> None:
            return None

    orchestrator = AgentOrchestrator()
    orchestrator._build_agents = lambda: [BlockedReviewProbe()]
    result = orchestrator.run(
        session_id="blocked_review_contract",
        course_id="data_structures",
        user_message="review contract",
    )

    assert_true(result["review"]["quality_status"] == "blocked", "blocked review should remain visible")
    assert_true(result["overall_status"] == "completed", "review quality must not block orchestrator execution")


if __name__ == "__main__":
    test_valid_review_passes_and_keeps_legacy_fields()
    test_foreign_chapter_is_blocked()
    test_empty_and_short_content_are_reported()
    test_resource_type_mismatches_warn()
    test_untrusted_resource_sources_warn()
    test_invalid_time_budget_is_reported_without_breaking_48_hour_plan()
    test_blocked_review_does_not_block_orchestrator()
    print("PASS review_agent_test")
