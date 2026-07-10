from app.routers.product import _fallback_tutor_reply, _is_invalid_tutor_reply, _public_tutor_video


def main() -> None:
    profile = '{"major_background": {}, "knowledge_base": {}, "learning_goal": {}, "cognitive_style": {}}'
    assert _is_invalid_tutor_reply(profile)

    concept = _fallback_tutor_reply("concept_explanation", "数组", "掌握数组操作。", [{"name": "数组"}], "数组支持顺序访问。", "解释数组")
    diagram = _fallback_tutor_reply("diagram", "数组", "掌握数组操作。", [{"name": "数组"}], "", "画结构图")
    assert "数组" in concept and "major_background" not in concept
    assert "```mermaid" in diagram

    unavailable = _public_tutor_video({"status": "provider_not_configured", "provider": "spark_video"})
    scripted = _public_tutor_video({"status": "script_ready_provider_not_configured", "script": "视频脚本", "provider": "spark_video"})
    failed = _public_tutor_video({"status": "failed"})
    assert unavailable["status"] == "provider_not_configured" and not unavailable["script"]
    assert scripted["status"] == "provider_not_configured" and scripted["script"] == "视频脚本"
    assert failed["status"] == "generation_failed"
    print("section tutor validation: PASS")


if __name__ == "__main__":
    main()
