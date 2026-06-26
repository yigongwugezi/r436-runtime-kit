import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.services.llm_client import BaseLLMClient, LLMClientError, MockLLMClient  # noqa: E402


class IntentJSONLLM(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        return json.dumps(
            {
                "primary_intent": "diagnosis",
                "secondary_intents": ["learning_plan"],
                "confidence": 0.81,
                "reason": "The learner asks what to repair next, which implies diagnosis.",
                "should_run_full_workflow": False,
                "needs_subject": False,
                "needs_clarification": False,
                "clarification_question": None,
                "extracted": {
                    "subject_name": None,
                    "time_budget": None,
                    "learning_goal": None,
                    "current_level": None,
                    "weak_topic": None,
                    "requested_outputs": ["diagnosis"],
                },
            },
            ensure_ascii=False,
        )


class FailingLLM(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        raise LLMClientError("intent classifier unavailable")


def classify(message: str) -> dict[str, Any]:
    return IntentAgent(llm_client=MockLLMClient()).classify(message)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_intent(result: dict[str, Any], intent: str, primary: str | None = None) -> None:
    assert_true(result["intent"] == intent, f"expected intent {intent}, got {result}")
    assert_true(result["primary_intent"] == (primary or intent), f"unexpected primary_intent: {result}")


def test_explicit_diagnosis_is_stable() -> None:
    result = classify("我哪里比较薄弱？")
    assert_intent(result, "diagnosis")
    assert_true(result["secondary_intents"] == [], "explicit diagnosis should not invent secondary intents")
    assert_true(result["confidence"] >= 0.75, "diagnosis confidence should be high enough")
    assert_true(result["needs_clarification"] is False, "explicit diagnosis should not ask for clarification")
    assert_true(result["should_run_agents"] is True, "diagnosis should trigger agent-backed diagnosis")
    assert_true("diagnosis" in result["extracted"]["requested_outputs"], "diagnosis output should be extracted")


def test_diagnosis_plus_resources_is_multi_intent() -> None:
    result = classify("我哪里比较薄弱？接下来该学什么资源？")
    assert_intent(result, "diagnosis")
    assert_true("resource_request" in result["secondary_intents"], "resource request should be secondary")
    assert_true(result["confidence"] >= 0.75, "diagnosis + resource confidence should be stable")
    assert_true(result["needs_clarification"] is False, "diagnosis + resource should be clear")
    assert_true(result["should_run_agents"] is True, "diagnosis + resource should trigger agents")
    assert_true(result["reason"], "reason should not be empty")


def test_implicit_diagnosis_routes_to_diagnosis() -> None:
    result = classify("我感觉最近学得很乱，不知道该补哪里")
    assert_intent(result, "diagnosis")
    assert_true(
        "learning_plan" in result["secondary_intents"] or "resource_request" in result["secondary_intents"],
        "implicit diagnosis should include a repair/planning secondary intent",
    )
    assert_true(result["confidence"] >= 0.65, "implicit diagnosis confidence should be reasonable")
    assert_true(result["needs_clarification"] is False, "implicit diagnosis should be actionable")
    assert_true("implicit" in result["reason"].lower() or "implies" in result["reason"].lower(), "reason should explain implicit diagnosis")


def test_full_workflow_has_secondary_intents_and_extracted_fields() -> None:
    result = classify(
        "我是计算机新生，Python 基础比较弱，我想用 2 天入门 Python，请帮我构建学习画像、学习路径和学习资源。"
    )
    assert_intent(result, "full_workflow")
    assert_true(result["confidence"] >= 0.75, "full workflow confidence should be stable")
    assert_true(result["should_run_full_workflow"] is True, "full workflow flag should be true")
    assert_true(result["should_run_agents"] is True, "full workflow should run agents")
    for intent in ("profile_update", "learning_plan", "resource_request"):
        assert_true(intent in result["secondary_intents"], f"missing secondary intent: {intent}")
    assert_true("Python" in result["extracted"]["subject_name"], "subject should include Python")
    assert_true("2" in result["extracted"]["time_budget"] and "天" in result["extracted"]["time_budget"], "time budget should include 2 天")
    assert_true(result["extracted"]["current_level"], "current level should reflect freshman/weak foundation")


def test_new_subject_expression_extracts_subject() -> None:
    result = classify("我想学操作系统")
    assert_true(result["primary_intent"] in {"learning_plan", "subject_create"}, f"unexpected primary: {result}")
    assert_true(result["intent"] in {"learning_plan", "subject_create"}, f"unexpected intent: {result}")
    assert_true(result["needs_subject"] is True, "subject handoff should be explicit")
    assert_true(result["extracted"]["subject_name"] == "操作系统", "subject_name should be extracted")
    assert_true(result["confidence"] >= 0.65, "new subject confidence should be reasonable")
    assert_true(result["needs_clarification"] is False, "new subject expression should not be unknown")


def test_resource_request_is_stable() -> None:
    result = classify("给我一些适合我现在阶段的练习和资料")
    assert_intent(result, "resource_request")
    assert_true(result["confidence"] >= 0.7, "resource confidence should be stable")
    assert_true(result["needs_clarification"] is False, "resource request should be clear")
    assert_true(result["should_run_agents"] is True, "resource request should run agents")
    assert_true("resources" in result["extracted"]["requested_outputs"], "requested resources should be extracted")


def test_vague_request_asks_for_clarification() -> None:
    result = classify("帮我安排一下")
    assert_true(result["needs_clarification"] is True, "vague request should ask for clarification")
    assert_true(result["clarification_question"], "clarification question should be present")
    assert_true(result["primary_intent"] in {"unknown", "learning_plan"}, "vague request should not become full_workflow")
    assert_true(result["primary_intent"] != "full_workflow", "vague request must not trigger full workflow")
    assert_true(result["confidence"] < 0.75, "vague request confidence should not be overconfident")


def test_general_chat_does_not_ask_for_clarification() -> None:
    result = classify("你好")
    assert_true(result["primary_intent"] == "general_chat", "greeting should be general_chat")
    assert_true(result["should_run_agents"] is False, "greeting should not run agents")
    assert_true(result["needs_clarification"] is False, "greeting should not ask for learning clarification")
    assert_true(result["should_run_full_workflow"] is False, "greeting should not trigger full workflow")


def test_real_llm_json_classification_is_supported() -> None:
    result = IntentAgent(llm_client=IntentJSONLLM()).classify("我感觉最近学得很乱，不知道该补哪里。")
    assert_intent(result, "diagnosis")
    assert_true(result["source"] == "llm_generated", "real LLM JSON classification should be marked")
    assert_true("learning_plan" in result["secondary_intents"], "follow-up planning should be a secondary intent")
    assert_true(result["confidence"] >= 0.7, "LLM confidence should be retained")


def test_llm_failure_falls_back_to_rules() -> None:
    result = IntentAgent(llm_client=FailingLLM()).classify("帮我生成学习路径")
    assert_intent(result, "learning_plan")
    assert_true(result["source"] in {"rule_based", "rule_based_fallback"}, "fallback source should be explicit")
    assert_true(result["reason"], "fallback reason should be retained")


if __name__ == "__main__":
    test_explicit_diagnosis_is_stable()
    test_diagnosis_plus_resources_is_multi_intent()
    test_implicit_diagnosis_routes_to_diagnosis()
    test_full_workflow_has_secondary_intents_and_extracted_fields()
    test_new_subject_expression_extracts_subject()
    test_resource_request_is_stable()
    test_vague_request_asks_for_clarification()
    test_general_chat_does_not_ask_for_clarification()
    test_real_llm_json_classification_is_supported()
    test_llm_failure_falls_back_to_rules()
    print("PASS intent_agent_test")
