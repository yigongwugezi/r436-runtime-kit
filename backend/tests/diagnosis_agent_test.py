import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.diagnosis_agent import DiagnosisAgent  # noqa: E402


ALLOWED_EVIDENCE_SOURCES = {
    "user_message",
    "profile",
    "learning_path",
    "quiz_result",
    "course_catalog",
    "fallback_rule",
    "rule_based",
}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def diagnose(context: dict[str, Any]) -> dict[str, Any]:
    return DiagnosisAgent().run(context)["diagnosis"]


def names(diagnosis: dict[str, Any]) -> list[str]:
    return [str(item.get("name") or item.get("topic")) for item in diagnosis["weak_knowledge_points"]]


def assert_contract(diagnosis: dict[str, Any]) -> None:
    assert_true("weak_knowledge_points" in diagnosis, "weak_knowledge_points must remain compatible")
    assert_true("confidence" in diagnosis, "confidence must remain compatible")
    assert_true(isinstance(diagnosis.get("evidence_chain"), list), "evidence_chain must be a list")
    assert_true(isinstance(diagnosis.get("recommended_next_actions"), list), "recommended_next_actions must be a list")
    assert_true(
        all(item.get("source") in ALLOWED_EVIDENCE_SOURCES for item in diagnosis["evidence_chain"]),
        f"unexpected evidence source: {diagnosis['evidence_chain']}",
    )


def test_explicit_user_message_weak_points_have_evidence_chain() -> None:
    diagnosis = diagnose({"user_message": "我递归和动态规划都不会"})

    assert_contract(diagnosis)
    weak_names = names(diagnosis)
    assert_true("递归" in weak_names, f"missing 递归: {diagnosis}")
    assert_true("动态规划" in weak_names, f"missing 动态规划: {diagnosis}")
    assert_true(diagnosis["evidence_chain"], "explicit weak points should have evidence")
    assert_true(
        any(item["source"] == "user_message" for item in diagnosis["evidence_chain"]),
        f"user_message evidence missing: {diagnosis}",
    )
    assert_true(diagnosis["needs_more_evidence"] is True, "self-report still needs behavioral evidence")


def test_vague_input_does_not_invent_specific_topics() -> None:
    diagnosis = diagnose({"user_message": "我学得很乱"})

    assert_contract(diagnosis)
    assert_true(diagnosis["weak_knowledge_points"] == [], f"vague input should not invent topics: {diagnosis}")
    assert_true(diagnosis["needs_more_evidence"] is True, "vague input should need more evidence")
    assert_true(diagnosis["recommended_next_actions"], "vague input should recommend next actions")
    assert_true(
        diagnosis["evidence_chain"][0]["source"] == "fallback_rule",
        f"vague input should be fallback evidence: {diagnosis}",
    )


def test_profile_context_contributes_evidence_chain() -> None:
    diagnosis = diagnose(
        {
            "profile": {
                "current_level": {"value": "基础薄弱"},
                "weak_topic": {"value": "函数"},
                "time_budget": {"value": "每天 30 分钟"},
            },
            "profile_facts": {"weak_points": "函数"},
        }
    )

    assert_contract(diagnosis)
    assert_true("函数" in names(diagnosis), f"profile weak topic missing: {diagnosis}")
    assert_true(
        any(item["source"] == "profile" for item in diagnosis["evidence_chain"]),
        f"profile evidence missing: {diagnosis}",
    )


def test_message_patterns_and_contract_are_stable() -> None:
    for message, expected in [
        ("我循环和函数总是搞混", {"循环", "函数"}),
        ("我数学基础差", {"数学"}),
    ]:
        diagnosis = diagnose({"user_message": message})
        assert_contract(diagnosis)
        actual = set(names(diagnosis))
        assert_true(expected <= actual, f"{message} expected {expected}, got {diagnosis}")


if __name__ == "__main__":
    test_explicit_user_message_weak_points_have_evidence_chain()
    test_vague_input_does_not_invent_specific_topics()
    test_profile_context_contributes_evidence_chain()
    test_message_patterns_and_contract_are_stable()
    print("PASS diagnosis_agent_test")
