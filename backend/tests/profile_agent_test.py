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
    "self_efficacy",
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
    assert_true(list(profile.keys()) == EXPECTED_KEYS, "profile should expose exactly 10 stable keys")
    for key in EXPECTED_KEYS:
        item = profile[key]
        assert_true(all(field in item for field in ("value", "score", "confidence", "explanation", "evidence", "source")), f"{key} should include all required fields")
        assert_true(item["source"] != "unknown", f"{key} should not use unknown source")


def test_profile_agent_rule_fallback_outputs_10_dimensions() -> None:
    agent = ProfileAgent(llm_client=None)
    result = agent.run(
        {
            "user_message": "我是软件工程大三学生，Python 基础一般，想用 10 天入门人工智能导论，重点学习机器学习和神经网络，希望多给图解和代码案例。",
            "profile_facts": {
                "background": "软件工程大三学生",
                "knowledge_base": "Python 基础一般",
                "learning_goal": "10 天入门人工智能导论",
                "preference": "图解、代码案例",
                "target_course": "人工智能导论",
                "time_budget": "10 天",
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


if __name__ == "__main__":
    test_profile_agent_rule_fallback_outputs_10_dimensions()
    test_profile_agent_llm_success_is_tagged_as_generated()
    print("PASS profile_agent_test")
