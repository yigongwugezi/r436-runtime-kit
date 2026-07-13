from app.agents.profile_agent import ProfileAgent
from app.routers.product import update_profile
from app.services.conversation_state import ConversationState, ConversationStore
from app.services.profile_extractor import extract_profile_facts
from app.services.profile_v2 import assess_interest, build_profile_v2, update_context, update_self_report
from fastapi import HTTPException


def by_key(items):
    return {item["key"]: item for item in items}


def main() -> None:
    math_facts = extract_profile_facts("我是大学生，想在两周内复习高等数学，每天一小时。极限基础一般，比较怕证明题，喜欢先看例题。")
    math = build_profile_v2(facts=math_facts.facts, course={"course_name": "高等数学"})
    assert math["subject_context"]["subject_category"] == "mathematics"
    assert "coding_ability" not in by_key(math["subject_dimensions"])
    assert all(item["score"] is None for item in math["subject_dimensions"])

    cs_facts = extract_profile_facts("我学过C语言，但数据结构基础不太好，希望一周内复习完，每天能学一小时。")
    cs = build_profile_v2(facts=cs_facts.facts, course={"course_name": "数据结构"})
    assert cs["subject_context"]["subject_category"] == "computing"
    assert {"complexity_analysis", "code_implementation", "debugging"}.issubset(by_key(cs["subject_dimensions"]))
    assert all(item["score"] is None for item in cs["subject_dimensions"])

    language = build_profile_v2(facts={"target_course": "英语", "learning_goal": "考试", "time_budget": "每天30分钟"}, course={"course_name": "英语"})
    assert language["subject_context"]["subject_category"] == "language"
    assert set(by_key(language["subject_dimensions"])) == {"vocabulary", "grammar", "reading", "writing"}

    legacy = build_profile_v2(dimensions=[{"key": "coding_ability", "value": "待补充", "score": 50, "source": "rule_based_fallback", "evidence": ""}], course={"course_name": "高等数学"})
    assert all(item["score"] is None for item in legacy["subject_dimensions"])

    updated = update_context(cs, {"learning_goal": "期末复习", "daily_minutes": 90, "unknown": "ignored"})
    assert updated["subject_context"]["learning_goal"] == "期末复习"
    assert "unknown" not in updated["subject_context"]
    updated = update_self_report(updated, {"interest": 75})
    interest = by_key(updated["general_states"])["interest"]
    assert interest["self_report"] == 75 and interest["system_estimate"] is None
    assessed = assess_interest(updated, [5, 4, 4])
    assert by_key(assessed["general_states"])["interest"]["system_estimate"] == 87

    try:
        update_profile({"sessionId": "profile_v2_guard", "dimensions": [{"key": "coding_ability", "value": "100"}]})
        raise AssertionError("legacy profile patch accepted a direct ability update")
    except HTTPException as exc:
        assert exc.status_code == 400

    agent = ProfileAgent(mock_data={}, llm_client=None)
    result = agent.run({"user_message": "我想学英语", "profile_facts": {"target_course": "英语"}, "course": {"course_name": "英语"}})
    assert result["profile_v2"]["profile_version"] == 2

    explicit = extract_profile_facts("\u6211\u662f\u5927\u5b66\u751f\uff0c\u60f3\u5728\u4e24\u5468\u5185\u590d\u4e60\u9ad8\u7b49\u6570\u5b66\uff0c\u6bcf\u5929\u53ef\u4ee5\u5b66\u4e60\u4e00\u5c0f\u65f6\u3002\u6211\u7684\u6781\u9650\u57fa\u7840\u4e00\u822c\uff0c\u6bd4\u8f83\u6015\u8bc1\u660e\u9898\uff0c\u559c\u6b22\u5148\u770b\u4f8b\u9898\u518d\u505a\u7ec3\u4e60\u3002").facts
    explicit_profile = build_profile_v2(facts=explicit, course={"course_name": "\u9ad8\u7b49\u6570\u5b66"})
    assert explicit_profile["subject_context"]["daily_minutes"] == 60
    assert set(explicit_profile["subject_context"]["content_preferences"]) == {"example_first", "practice_after_explanation"}
    assert all(item["score"] is None for item in explicit_profile["subject_dimensions"])
    assert explicit_profile["profile_completeness"] < 0.83

    weekly_facts = extract_profile_facts("\u4e00\u5468\u5185\u590d\u4e60\u6570\u636e\u7ed3\u6784\uff0c\u6bcf\u5929\u53ef\u4ee5\u5b66\u4e60\u4e00\u5c0f\u65f6\u3002C\u8bed\u8a00\u57fa\u7840\u8fd8\u53ef\u4ee5\uff0c\u94fe\u8868\u548c\u6811\u6bd4\u8f83\u8584\u5f31\uff0c\u559c\u6b22\u5148\u770b\u4f8b\u9898\uff0c\u518d\u5b8c\u6210\u7ec3\u4e60\u3002").facts
    weekly = build_profile_v2(facts=weekly_facts, course={"course_name": "\u6570\u636e\u7ed3\u6784"})
    weekly_context = weekly["subject_context"]
    assert weekly_context["deadline"] == "\u4e00\u5468" and weekly_context["daily_minutes"] == 60
    assert weekly_context["content_preferences"] == ["example_first", "practice_after_explanation"]
    assert by_key(weekly["general_states"])["interest"]["self_report"] is None
    assert weekly["profile_completeness"] == 0.5

    existing = {"profile_version": 2, "subject_context": {"daily_minutes": 50, "deadline": "\u5f85\u8865\u5145", "background": {"value": ""}}, "profile_completeness": 0.86}
    merged = build_profile_v2(facts=weekly_facts, course={"course_name": "\u6570\u636e\u7ed3\u6784"}, existing=existing)
    assert merged["subject_context"]["daily_minutes"] == 60 and merged["subject_context"]["deadline"] == "\u4e00\u5468"
    assert merged["profile_completeness"] == 0.5

    corrupted = build_profile_v2(
        facts={"target_course": "\u6570\u636e\u7ed3\u6784", "learning_goal": "\u590d\u4e60", "daily_minutes": "60", "deadline": "\u4e00\u5468", "background": "\u5927\u4e8c\u5b66\u751f", "knowledge_base": "\u6bcf\u5929\uff1a\u8fd8\u53ef\u4ee5\uff1b\u8bed\u8a00\u57fa\u7840\uff1a\u8fd8\u53ef\u4ee5", "content_preferences": "example_first,practice_after_explanation"},
        course={"course_name": "\u6570\u636e\u7ed3\u6784"},
    )
    assert corrupted["subject_context"]["prior_experience"] == []
    assert corrupted["profile_completeness"] == 0.83

    extracted_state = ConversationState(session_id="profile_v2_extraction")
    ConversationStore().extract_facts(extracted_state, "\u6211\u7684 C \u8bed\u8a00\u57fa\u7840\u8fd8\u53ef\u4ee5\uff0c\u4f46\u94fe\u8868\u548c\u6811\u6bd4\u8f83\u8584\u5f31\u3002")
    assert extracted_state.facts["knowledge_base"] == "C\u8bed\u8a00\u57fa\u7840\uff1a\u8fd8\u53ef\u4ee5"

    readiness = ConversationStore().readiness(ConversationState(
        session_id="profile_v2_readiness",
        facts={"target_course": "\u6570\u636e\u7ed3\u6784", "daily_minutes": "60", "deadline": "\u4e00\u5468"},
    ))
    assert readiness["filledCount"] == 1
    print("profile v2: PASS")


if __name__ == "__main__":
    main()
