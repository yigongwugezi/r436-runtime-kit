import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ResourceModel
from app.services.section_generated_resources import RESOURCE_DEFINITIONS, SectionGeneratedResourcesService


class ProfileJsonClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        return json.dumps({"major_background": {}, "knowledge_base": {}, "learning_goal": {}, "cognitive_style": {}})


def main() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    client = ProfileJsonClient()
    service = SectionGeneratedResourcesService(llm_client=client)
    profile = {"subject_context": {"prior_experience": ["零基础"], "content_preferences": ["example_first"], "learning_goal": "完整私人目标"}, "knowledge_mastery": [{"label": "数组", "status": "weak"}]}
    for resource_type in RESOURCE_DEFINITIONS:
        data = service.generate(session_id="test", path_id="path_1", stage_id="stage_1", chapter_id="chapter_1", section_id="section_1", section_title="数组与链表", lecture_content="数组和链表的操作成本。", knowledge_points=["数组", "链表"], resource_type=resource_type, profile=profile)
        assert "major_background" not in data["content"] and "数组与链表" in data["content"]
        saved = service.persist(db, "test", data)
        assert saved.related_section_id == "section_1" and saved.related_chapter_id == "chapter_1" and saved.source == "agent_generated"
        assert service.existing(db, "test", "section_1", resource_type).id == data["id"]
        data["content"] += "\n\n重新生成版本。"
        assert "重新生成版本" in service.persist(db, "test", data).content  # same ID overwrites
    lecture = "# 数组与链表\n\n## 学习目标\n- 理解访问成本\n\n## 核心概念\n- 区分结构"
    notes = service._fallback("review_notes", "数组与链表", ["数组", "链表"], lecture)
    assert notes.startswith("# 数组与链表 复习笔记\n\n")
    assert all(f"## {title}" in notes for title in ("关键知识", "复习提醒", "自测问题"))
    assert lecture not in notes and "## 学习目标" not in notes
    assert "\n- 数组\n- 链表\n" in notes
    comparison = service._fallback("concept_comparison", "数组与链表", ["数组"], lecture, {})
    assert "当前概念" not in comparison and "关联概念" not in comparison
    recursion = service._fallback("worked_example", "递归调用栈", ["递归", "调用栈"], lecture, {})
    assert "factorial(3)" in recursion and "栈帧" in recursion and "返回过程" in recursion
    assert all("完整私人目标" not in prompt and "major_background" not in prompt for prompt in client.prompts)
    assert db.query(ResourceModel).count() == len(RESOURCE_DEFINITIONS)
    assert len([row for row in db.query(ResourceModel) if "section_generated" in (row.tags or [])]) == len(RESOURCE_DEFINITIONS)
    print("section generated resources: PASS")


if __name__ == "__main__":
    main()
