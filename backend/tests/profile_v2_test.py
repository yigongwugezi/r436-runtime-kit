from app.agents.profile_agent import ProfileAgent
from app.routers.product import update_profile
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
    print("profile v2: PASS")


if __name__ == "__main__":
    main()
