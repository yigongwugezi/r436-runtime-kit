"""Mock smoke for image-chat web acceptance. No real provider calls."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.multimodal_agent import MultimodalAgent  # noqa: E402
from app.routers import product  # noqa: E402
from app.services import multimodal_provider as provider_mod  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class SparseLLM:
    def is_available(self) -> bool:
        return True

    def chat(self, messages: list[dict[str, str]], **_kwargs) -> str:
        prompt = messages[-1]["content"]
        if "复习卡片" in prompt:
            return '{"cards":[{"front":"函数定义域","back":"先看分母和根号","knowledge_point":"函数定义域"}]}'
        if "Markmap" in prompt:
            return "# 图片知识结构\n- 函数"
        return "识别到多道高数题。我先详细讲第1题和第2题：第1题看函数定义域，第2题看奇偶性。可以继续说继续讲第3题。"


class FakeVisionTool:
    provider = "qwen_vl"

    def run(self, _context: dict) -> dict:
        return {
            "status": "success",
            "provider": self.provider,
            "warnings": [],
            "trace": {"model": "fake-vl"},
            "result": {
                "image_type": "question_image",
                "subject": "高等数学",
                "summary": "高数函数与极限题图",
                "detected_text": "函数定义域 奇偶函数 反函数 复合函数 分段函数 数列极限 无穷小比较 等价无穷小 渐近线",
                "possible_knowledge_points": ["函数定义域", "奇偶函数", "反函数", "复合函数", "分段函数", "数列极限"],
                "extracted_questions": [
                    {"index": 1, "content": "求函数定义域", "knowledge_points": ["函数定义域"], "answer": "See extracted_questions for per-question answers"},
                    {"index": 2, "content": "判断函数奇偶性", "knowledge_points": ["奇偶函数"], "answer": "比较 f(-x) 与 f(x)"},
                    {"index": 3, "content": "求反函数", "knowledge_points": ["反函数"]},
                    {"index": 4, "content": "复合函数求值", "knowledge_points": ["复合函数"]},
                    {"index": 5, "content": "分段函数连续性", "knowledge_points": ["分段函数"]},
                    {"index": 6, "content": "数列极限", "knowledge_points": ["数列极限"]},
                ],
                "needs_manual_review": True,
                "review_reasons": ["第3题反函数条件可能不完整"],
                "uncertain_question_indices": [3],
                "uncertain_fields": ["question_text"],
                "review_level": "medium",
                "can_continue": True,
            },
        }


def markdown_nodes(markdown: str) -> int:
    return len([line for line in markdown.splitlines() if line.lstrip().startswith("-")])


def markdown_node_labels(markdown: str) -> list[str]:
    return [line.lstrip(" -").strip() for line in markdown.splitlines() if line.lstrip().startswith("-")]


def main() -> None:
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert_true("127.0.0.1:8001" not in vite, "Vite /api proxy must not point to 8001")

    old_upload_root = provider_mod.UPLOAD_ROOT
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        try:
            provider_mod.UPLOAD_ROOT = Path(tmp)
            upload = provider_mod.save_multimodal_upload(b"\x89PNG\r\n\x1a\n", filename="smoke.png", content_type="image/png", session_id="smoke")
        finally:
            provider_mod.UPLOAD_ROOT = old_upload_root
    assert_true(upload["url"].startswith("/api/multimodal/file/"), "upload URL should use /api proxy")
    assert_true("8001" not in upload["url"], "upload URL must not hardcode 8001")

    agent = MultimodalAgent(llm_client=SparseLLM())
    agent.registry.register_tool("QwenVisionProvider", FakeVisionTool())

    explain = agent.run({"user_message": "请详细讲解这张图片里的题目，并指出每道题考查的知识点", "attachments": [upload]})
    assert_true(explain["result"].get("display_text"), "explain_image_question must expose display_text")
    assert_true("{" not in explain["result"]["display_text"][:20], "display_text should not be raw JSON")
    assert_true("See extracted_questions" not in explain["result"]["display_text"], "internal placeholders must not leak")

    questions = product._questions_from_vision({"extracted_questions": [{"index": 1, "content": "字段别名题干"}, {"index": 2}]})
    assert_true(questions[0]["question_text"] == "字段别名题干", "question aliases should render")
    assert_true(questions[1]["question_text"], "empty question index should get a useful placeholder")

    mindmap = agent.run({"user_message": "根据这张图生成思维导图", "attachments": [upload]})
    assert_true(markdown_nodes(mindmap["result"]["markdown"]) >= 6, "mindmap should not collapse to 2-3 nodes")
    assert_true(max(len(label) for label in markdown_node_labels(mindmap["result"]["markdown"])) <= 40, "mindmap node labels should stay short")

    cards = agent.run({"user_message": "根据这张图生成复习卡片", "attachments": [upload]})
    assert_true(len(cards["result"]["cards"]) >= 6, "flashcards should include at least six cards")

    bundle = provider_mod._normalize_task_result(
        "image_to_resource_bundle",
        {"understanding": {"summary": "函数题资源包"}, "knowledge_candidates": [{"knowledge_point": "函数定义域"}], "confidence": 0.9},
        "",
    )
    assert_true(bundle.get("display_text"), "resource bundle should explain its purpose")

    cleaned = provider_mod._drop_empty_sections({"a": "", "b": [], "c": {}, "d": "..", "e": {"ok": "value"}})
    assert_true(cleaned == {"e": {"ok": "value"}}, "resource bundle empty sections should be dropped")

    review = explain["result"]
    assert_true(review["review_reasons"] and review["uncertain_question_indices"], "manual review must be actionable")
    print("PASS smoke_multimodal_image_acceptance")


if __name__ == "__main__":
    main()
