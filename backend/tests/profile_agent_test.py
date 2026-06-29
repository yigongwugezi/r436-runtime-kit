import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.profile_agent import ProfileAgent


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


EXPECTED_KEYS = [
    "major_background",
    "knowledge_base",
    "learning_goal",
    "cognitive_style",
    "error_patterns",
    "coding_ability",
    "learning_progress",
    "interest_direction",
    "learning_rhythm",
]


class FakeLLMClient:
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        del messages, kwargs
        payload = {
            key: {
                "key": key,
                "label": key,
                "value": f"{key} value",
                "score": 72,
                "confidence": 0.8,
                "explanation": f"{key} explanation",
                "evidence": f"{key} evidence",
                "source": "user_input",
            }
            for key in EXPECTED_KEYS
        }
        return json.dumps(payload, ensure_ascii=False)


def _assert_dimension_shape(profile: dict[str, dict]) -> None:
    assert_true(list(profile.keys()) == EXPECTED_KEYS, "profile should expose exactly 9 stable keys")
    for key in EXPECTED_KEYS:
        item = profile[key]
        assert_true(all(field in item for field in ("value", "score", "confidence", "explanation", "evidence", "source")), f"{key} should include all required fields")
        assert_true(item["source"] != "unknown", f"{key} should not use unknown source")


def test_profile_agent_rule_fallback_outputs_9_dimensions() -> None:
    agent = ProfileAgent(llm_client=None)
    result = agent.run(
        {
            "user_message": "我是软件工程大三学生，Python 基础一般，想用 9 天入门人工智能导论，重点学习机器学习和神经网络，希望多给图解和代码案例。",
            "profile_facts": {
                "background": "软件工程大三学生",
                "knowledge_base": "Python 基础一般",
                "learning_goal": "9 天入门人工智能导论",
                "preference": "图解、代码案例",
                "target_course": "人工智能导论",
                "time_budget": "9 天",
            },
        }
    )
    profile = result["profile"]
    _assert_dimension_shape(profile)
    assert_true("weak_points" not in profile and "programming_ability" not in profile and "interests" not in profile, "legacy 8-dim keys should not be final output")


def test_profile_agent_llm_success_is_tagged_as_generated() -> None:
    agent = ProfileAgent(llm_client=FakeLLMClient())
    result = agent.run(
        {
            "user_message": "我是计算机大二学生，想在 48 小时复习数据结构。",
            "profile_facts": {"background": "计算机大二学生"},
        }
    )
    profile = result["profile"]
    _assert_dimension_shape(profile)
    assert_true(profile["major_background"]["source"] == "user_input", "direct facts can remain user_input")
    assert_true(profile["knowledge_base"]["source"] == "llm_generated", "LLM-produced dimensions should be tagged as llm_generated")


def _rule_profile(message: str, facts: dict | None = None, diagnosis: dict | None = None) -> dict:
    agent = ProfileAgent(llm_client=None)
    return agent.run(
        {
            "user_message": message,
            "profile_facts": facts or {},
            "diagnosis": diagnosis or {},
        }
    )["profile"]


def test_profile_agent_learning_target_extraction() -> None:
    cases = [
        ("我要学习微积分", {"target_course": "习微积分"}, "微积分", "习微积分"),
        ("我想学微积分", {}, "微积分", "学微积分"),
        ("我要学高等数学", {}, "高等数学", "学高等数学"),
        ("我想学习机器学习", {}, "机器学习", "习机器学习"),
        ("我准备学习数据结构", {}, "数据结构", ""),
        ("我想补一下线性代数", {}, "线性代数", "一下线性代数"),
    ]
    for message, facts, expected, forbidden in cases:
        profile = _rule_profile(message, facts)
        target = profile["interest_direction"]["value"]
        assert_true(target == expected, f"{message} target should be {expected}, got {target}")
        if forbidden:
            assert_true(forbidden not in target, f"{message} target should not contain {forbidden}")


def test_profile_agent_does_not_default_time_budget() -> None:
    profile = _rule_profile("我要学习微积分")
    rhythm = profile["learning_rhythm"]
    assert_true(rhythm["value"] != "1个月", f"time_budget should not default to 1个月: {rhythm}")
    assert_true(rhythm["evidence"] == "", f"missing time_budget should not have evidence: {rhythm}")


def test_profile_agent_extracts_explicit_time_budget() -> None:
    profile = _rule_profile("我想一个月学完微积分")
    assert_true(profile["interest_direction"]["value"] == "微积分", f"target should be 微积分: {profile['interest_direction']}")
    assert_true(profile["learning_rhythm"]["value"] in {"一个月", "1个月"}, f"explicit time_budget should be kept: {profile['learning_rhythm']}")


def test_profile_agent_filters_weak_point_placeholders() -> None:
    profile = _rule_profile(
        "我要学习微积分",
        {"weak_points": "无诊断数据"},
        {"weak_knowledge_points": [{"name": "无诊断数据"}]},
    )
    weak = profile["error_patterns"]
    assert_true("无诊断数据" not in weak["value"], f"placeholder should not become weak point: {weak}")
    assert_true(weak["evidence"] == "", f"placeholder should not leave weak-point evidence: {weak}")


if __name__ == "__main__":
    test_profile_agent_rule_fallback_outputs_9_dimensions()
    test_profile_agent_llm_success_is_tagged_as_generated()
    test_profile_agent_learning_target_extraction()
    test_profile_agent_does_not_default_time_budget()
    test_profile_agent_extracts_explicit_time_budget()
    test_profile_agent_filters_weak_point_placeholders()
    print("PASS profile_agent_test")
