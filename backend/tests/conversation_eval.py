import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.routers import product  # noqa: E402
from app.services import agent_service  # noqa: E402
from app.services.conversation_state import conversation_store  # noqa: E402
from app.services.llm_client import MockLLMClient  # noqa: E402
from app.services.orchestrator import AgentOrchestrator  # noqa: E402


class DeterministicTestOrchestrator(AgentOrchestrator):
    """Keep conversation evaluation independent from external LLM behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.llm_client = MockLLMClient()


CASES_PATH = Path(__file__).with_name("conversation_cases.json")
REQUIRED_INTENT_CASES = {
    "帮我构建学习画像": "profile_update",
    "我是计算机新生，帮我构建学习画像": "profile_update",
    "帮我生成学习路径": "learning_plan",
    "根据我的学习路径推荐资源": "resource_request",
    "帮我找学习资源": "resource_request",
    "帮我构建学习画像、学习路径和学习资源": "full_workflow",
    "我哪里比较薄弱": "diagnosis",
}


def classify(message: str) -> dict[str, Any]:
    return IntentAgent(mock_data={}, llm_client=None).classify(message)


def reply(session_id: str, message: str) -> tuple[dict[str, Any], str]:
    conversation_store.append_message(session_id, "user", message)
    intent = classify(message)
    conversation_store.set_intent(session_id, intent)
    with patch.object(agent_service, "AgentOrchestrator", DeterministicTestOrchestrator):
        content, _ = product._reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", content)
    return intent, content


def assert_contains(text: str, expected: str, case_name: str) -> None:
    if expected not in text:
        raise AssertionError(f"[{case_name}] expected {expected!r} in reply:\n{text}")


def assert_not_contains(text: str, unexpected: str, case_name: str) -> None:
    if unexpected in text:
        raise AssertionError(f"[{case_name}] did not expect {unexpected!r} in reply:\n{text}")


def assert_case(case: dict[str, Any]) -> None:
    case_name = case["name"]
    session_id = f"eval_{case_name}"
    conversation_store.reset(session_id)

    for index, turn in enumerate(case.get("turns", []), start=1):
        intent, content = reply(session_id, turn["message"])
        expected_intent = turn.get("intent")
        if expected_intent and intent["intent"] != expected_intent:
            raise AssertionError(
                f"[{case_name} turn {index}] expected intent {expected_intent!r}, got {intent!r}"
            )
        for expected in turn.get("reply_contains", []):
            assert_contains(content, expected, f"{case_name} turn {index}")
        for unexpected in turn.get("reply_not_contains", []):
            assert_not_contains(content, unexpected, f"{case_name} turn {index}")

    state = conversation_store.get(session_id)

    for key, expected in case.get("expect_facts", {}).items():
        actual = state.facts.get(key)
        if actual != expected:
            raise AssertionError(f"[{case_name}] expected facts[{key!r}]={expected!r}, got {actual!r}")

    for key, values in case.get("expect_fact_contains", {}).items():
        actual = state.facts.get(key, "")
        for value in values:
            if value not in actual:
                raise AssertionError(f"[{case_name}] expected {value!r} in facts[{key!r}]={actual!r}")

    for key in case.get("expect_missing_facts", []):
        if key in state.facts:
            raise AssertionError(f"[{case_name}] expected facts[{key!r}] to be missing, got {state.facts[key]!r}")

    for key, values in case.get("expect_supplemental_contains", {}).items():
        actual_values = state.supplemental_facts.get(key, [])
        for value in values:
            if value not in actual_values:
                raise AssertionError(
                    f"[{case_name}] expected supplemental[{key!r}] to contain {value!r}, got {actual_values!r}"
                )

    if "expect_ready_to_plan" in case:
        actual_ready = conversation_store.readiness(state)["readyToPlan"]
        if actual_ready is not case["expect_ready_to_plan"]:
            raise AssertionError(
                f"[{case_name}] expected readyToPlan={case['expect_ready_to_plan']}, got {actual_ready}"
            )


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    for case in cases:
        assert_case(case)
        print(f"PASS {case['name']}")

    seen_intents: dict[str, str] = {}
    for case in cases:
        for turn in case.get("turns", []):
            message = turn.get("message")
            intent = turn.get("intent")
            if isinstance(message, str) and isinstance(intent, str):
                seen_intents.setdefault(message, intent)

    for message, expected_intent in REQUIRED_INTENT_CASES.items():
        actual_intent = seen_intents.get(message)
        if actual_intent != expected_intent:
            raise AssertionError(
                f"required intent case {message!r} expected {expected_intent!r}, got {actual_intent!r}"
            )

    print(f"PASS {len(cases)} conversation evaluation cases")


if __name__ == "__main__":
    main()
