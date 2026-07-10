from app.routers.product import _fallback_section_lecture, _is_profile_json, _is_valid_section_lecture


def main() -> None:
    profile = '{"major_background": {}, "knowledge_base": {}, "learning_goal": {}, "cognitive_style": {}}'
    assert _is_profile_json(profile)
    assert not _is_valid_section_lecture(profile, "数组", [{"name": "数组"}])

    lecture = _fallback_section_lecture("数组", "掌握数组操作。", [{"name": "数组"}])
    assert _is_valid_section_lecture(lecture, "数组", [{"name": "数组"}])
    assert "## 学习目标" in lecture and "## 小结" in lecture
    print("section lecture validation: PASS")


if __name__ == "__main__":
    main()
