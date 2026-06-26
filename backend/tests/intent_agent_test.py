import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.agents.intent_examples_zh import INTENT_EXAMPLES_ZH  # noqa: E402
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


def classify_with_context(message: str, context: dict[str, Any]) -> dict[str, Any]:
    return IntentAgent(llm_client=MockLLMClient()).classify(message, context=context)


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


def test_p2_semantic_example_library_has_enough_coverage() -> None:
    total = sum(len(samples) for samples in INTENT_EXAMPLES_ZH.values())
    assert_true(total >= 80, f"semantic library should have at least 80 samples, got {total}")
    for label, samples in INTENT_EXAMPLES_ZH.items():
        assert_true(len(samples) >= 8, f"{label} should have at least 8 samples")


def test_p2_semantic_example_regression_routes_all_samples() -> None:
    for label, samples in INTENT_EXAMPLES_ZH.items():
        for sample in samples:
            result = classify(sample)
            if label == "general_chat":
                assert_true(result["primary_intent"] == "general_chat", f"general_chat failed: {sample} -> {result}")
                assert_true(result["should_run_agents"] is False, f"general_chat should not run agents: {sample}")
                assert_true(result["needs_clarification"] is False, f"general_chat should not clarify: {sample}")
            elif label == "full_workflow":
                assert_intent(result, "full_workflow")
                assert_true(result["should_run_full_workflow"] is True, f"full_workflow flag failed: {sample}")
                for intent in ("profile_update", "learning_plan", "resource_request"):
                    assert_true(intent in result["secondary_intents"], f"missing {intent}: {sample} -> {result}")
            elif label == "profile_update":
                assert_intent(result, "profile_update")
                assert_true(result["needs_clarification"] is False, f"profile_update should be clear: {sample}")
            elif label == "learning_plan":
                assert_intent(result, "learning_plan")
                assert_true(result["should_run_agents"] is True, f"learning_plan should run agents: {sample}")
            elif label == "resource_request":
                assert_intent(result, "resource_request")
                assert_true(result["should_run_agents"] is True, f"resource_request should run agents: {sample}")
            elif label == "diagnosis":
                assert_intent(result, "diagnosis")
                assert_true(result["should_run_agents"] is True, f"diagnosis should run agents: {sample}")
                assert_true(result["needs_clarification"] is False, f"diagnosis should not clarify: {sample}")
            elif label == "diagnosis_resource_combo":
                assert_intent(result, "diagnosis")
                assert_true("resource_request" in result["secondary_intents"], f"missing resource secondary: {sample} -> {result}")
                assert_true(result["should_run_agents"] is True, f"diagnosis combo should run agents: {sample}")
            elif label == "subject_create_or_learning_plan":
                assert_true(result["primary_intent"] in {"learning_plan", "subject_create"}, f"subject route failed: {sample} -> {result}")
                assert_true(result["intent"] in {"learning_plan", "subject_create"}, f"subject legacy intent failed: {sample} -> {result}")
                assert_true(result["needs_subject"] is True, f"subject route should mark needs_subject: {sample} -> {result}")
                assert_true(result["extracted"]["subject_name"], f"subject_name should be extracted: {sample} -> {result}")
            elif label == "ambiguous":
                assert_true(result["needs_clarification"] is True, f"ambiguous should clarify: {sample} -> {result}")
                assert_true(result["clarification_question"], f"ambiguous should include question: {sample} -> {result}")
                assert_true(result["primary_intent"] != "full_workflow", f"ambiguous must not become full workflow: {sample} -> {result}")
            elif label == "off_topic":
                assert_true(result["primary_intent"] == "unknown", f"off_topic should stay outside agent workflow: {sample} -> {result}")
                assert_true(result["should_run_agents"] is False, f"off_topic should not run agents: {sample} -> {result}")
                assert_true(result["needs_clarification"] is False, f"off_topic should not ask learning clarification: {sample} -> {result}")


def test_subject_extraction_examples_are_stable() -> None:
    cases = {
        "我想学操作系统": "操作系统",
        "我想学 Python": "Python",
        "2 天入门 Python": "Python",
        "学数据结构": "数据结构",
        "一周入门 Java": "Java",
        "我想系统学习高等数学": "高等数学",
    }
    for message, expected_subject in cases.items():
        result = classify(message)
        assert_true(result["extracted"]["subject_name"] == expected_subject, f"{message} extracted {result}")


def test_p3_context_aware_routing_cases() -> None:
    plan_context = {
        "last_intent": "learning_plan",
        "has_learning_path": True,
        "recent_stage_id": "stage_1",
        "recent_messages": [{"role": "assistant", "content": "已生成学习路径"}],
    }
    resource_context = {
        "last_intent": "resource_request",
        "has_resources": True,
        "recent_resource_ids": ["res_intro"],
    }
    diagnosis_context = {
        "last_intent": "diagnosis",
        "has_diagnosis": True,
        "recent_weak_topics": ["递归"],
    }
    full_context = {
        "last_intent": "learning_plan",
        "has_learning_path": True,
        "has_resources": True,
        "has_diagnosis": True,
        "recent_stage_id": "stage_2",
        "recent_resource_ids": ["res_tree"],
        "recent_weak_topics": ["二叉树"],
    }

    cases = [
        ("继续", plan_context, "learning_plan", False, {}, []),
        ("继续", {}, "unknown", True, {}, []),
        ("下一步", diagnosis_context, "diagnosis", False, {}, ["learning_plan"]),
        ("下一步", plan_context, "learning_plan", False, {}, ["resource_request"]),
        ("下一步", {}, "unknown", True, {}, []),
        ("换简单点", plan_context, "learning_plan", False, {"difficulty_preference": "easier"}, []),
        ("换简单点", resource_context, "resource_request", False, {"difficulty_preference": "easier"}, []),
        ("换简单点", {}, "unknown", True, {}, []),
        ("太难了", full_context, "diagnosis", False, {"feedback": "too_difficult"}, ["resource_request"]),
        ("太难了", {}, "diagnosis", False, {"feedback": "too_difficult"}, []),
        ("我还是不懂", diagnosis_context, "diagnosis", False, {"feedback": "still_confused"}, ["resource_request"]),
        ("我还是不懂", {}, "diagnosis", False, {"feedback": "still_confused"}, []),
        ("给我那个资源", resource_context, "resource_request", False, {"resource_reference": "recent"}, []),
        ("给我那个资源", {}, "unknown", True, {}, []),
        ("按刚才那个薄弱点安排", diagnosis_context, "learning_plan", False, {"plan_revision": "from_recent_weak_topic"}, ["resource_request"]),
        ("按刚才那个薄弱点安排", {}, "unknown", True, {}, []),
        ("重新生成", plan_context, "learning_plan", False, {"plan_revision": "regenerate"}, []),
        ("重新生成", resource_context, "resource_request", False, {"plan_revision": "regenerate"}, []),
        ("重新诊断", diagnosis_context, "diagnosis", False, {"plan_revision": "regenerate"}, []),
        ("重新生成", {}, "unknown", True, {}, []),
        ("换一个", resource_context, "resource_request", False, {"plan_revision": "alternative"}, []),
        ("换一个", plan_context, "learning_plan", False, {"plan_revision": "alternative"}, []),
        ("换一个", diagnosis_context, "diagnosis", False, {"plan_revision": "alternative"}, []),
        ("换一个", {}, "unknown", True, {}, []),
        ("不要太多", plan_context, "learning_plan", False, {"constraint": "fewer_items"}, []),
        ("不要太多", resource_context, "resource_request", False, {"constraint": "fewer_items"}, []),
        ("不要太多", {}, "unknown", True, {}, []),
        ("太简单了", resource_context, "resource_request", False, {"difficulty_preference": "harder"}, []),
        ("这个讲得不好", resource_context, "diagnosis", False, {"feedback": "poor_explanation"}, ["resource_request"]),
        ("好的", full_context, "casual_chat", False, {}, []),
        ("明白了", full_context, "casual_chat", False, {}, []),
        ("在吗", full_context, "casual_chat", False, {}, []),
    ]

    assert_true(len(cases) >= 30, "P3 context-aware regression should cover at least 30 cases")
    for message, context, expected_intent, should_clarify, expected_extracted, expected_secondary in cases:
        result = classify_with_context(message, context)
        assert_true(result["intent"] == expected_intent, f"{message} expected {expected_intent}, got {result}")
        assert_true(result["needs_clarification"] is should_clarify, f"{message} clarification mismatch: {result}")
        if context and expected_intent != "casual_chat":
            assert_true(result["source"] == "context_aware", f"{message} should use context-aware source: {result}")
        for key, value in expected_extracted.items():
            assert_true(result["extracted"].get(key) == value, f"{message} expected extracted {key}={value}: {result}")
        for secondary in expected_secondary:
            assert_true(secondary in result["secondary_intents"], f"{message} missing secondary {secondary}: {result}")
        if should_clarify:
            assert_true(result["clarification_question"], f"{message} should include clarification question")
            assert_true(result["confidence"] < 0.75, f"{message} clarification confidence should stay low: {result}")
        if result["source"] == "context_aware":
            assert_true(result["confidence"] <= 0.95, f"{message} context confidence should not exceed 0.95")


def test_p3_run_accepts_context_without_breaking_agent_contract() -> None:
    output = IntentAgent(llm_client=MockLLMClient()).run(
        {
            "user_message": "继续",
            "last_intent": "learning_plan",
            "has_learning_path": True,
            "recent_stage_id": "stage_1",
        }
    )
    intent = output["intent"]
    assert_intent(intent, "learning_plan")
    assert_true(intent["source"] == "context_aware", f"run() should pass context into classify: {intent}")


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
    test_p2_semantic_example_library_has_enough_coverage()
    test_p2_semantic_example_regression_routes_all_samples()
    test_subject_extraction_examples_are_stable()
    test_p3_context_aware_routing_cases()
    test_p3_run_accepts_context_without_breaking_agent_contract()
    print("PASS intent_agent_test")
