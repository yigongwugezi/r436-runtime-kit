from types import SimpleNamespace

from app.routers import chat_router, product


class MemoryStore:
    def __init__(self):
        self.messages = []
        self.result = {}

    def append_message(self, session_id, role, content):
        self.messages.append((session_id, role, content))

    def get(self, session_id):
        return SimpleNamespace(last_result=self.result)

    def set_result(self, session_id, result):
        self.result = result


def main() -> None:
    expected = {
        "生成总结卡片": ["summary_card"],
        "生成概念对比": ["concept_comparison"],
        "生成例题详解": ["worked_example"],
        "生成易错点清单": ["mistake_checklist"],
        "生成复习笔记": ["review_notes"],
        "生成知识结构图": ["knowledge_map"],
        "生成执行过程图": ["execution_trace"],
        "生成本节资源": list(chat_router._SECTION_RESOURCE_REQUESTS),
    }
    for message, resource_types in expected.items():
        assert chat_router._section_resource_types(message) == resource_types

    original_store = chat_router.conversation_store
    original_generate = product.generate_section_resource
    chat_router.conversation_store = MemoryStore()
    try:
        reply, result = chat_router._try_section_resource_chat("生成总结卡片", "test", {})
        assert reply == chat_router._SECTION_RESOURCE_GUIDANCE
        assert result["action"] == "section_generated_resource"
        assert result["section_resource_request"]["status"] == "needs_section_context"

        def fake_generate(section_id, payload):
            return {"data": {"resource": {"id": f"section_{section_id}_{payload['resourceType']}", "title": "总结卡片"}}}

        product.generate_section_resource = fake_generate
        reply, result = chat_router._try_section_resource_chat(
            "生成总结卡片",
            "test",
            {"sectionId": "section_1", "sectionTitle": "数组与链表"},
        )
        assert "总结卡片" in reply
        assert result["section_resource_request"]["status"] == "completed"
        assert len(result["section_resource_request"]["resources"]) == 1
    finally:
        chat_router.conversation_store = original_store
        product.generate_section_resource = original_generate

    print("chat section resource routing: PASS")


if __name__ == "__main__":
    main()
