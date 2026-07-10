import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ResourceModel
from app.services.section_generated_resources import RESOURCE_DEFINITIONS, SectionGeneratedResourcesService


class ProfileJsonClient:
    def chat(self, **kwargs):
        return json.dumps({"major_background": {}, "knowledge_base": {}, "learning_goal": {}, "cognitive_style": {}})


def main() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = SectionGeneratedResourcesService(llm_client=ProfileJsonClient())
    for resource_type in RESOURCE_DEFINITIONS:
        data = service.generate(session_id="test", path_id="path_1", stage_id="stage_1", chapter_id="chapter_1", section_id="section_1", section_title="数组与链表", lecture_content="数组和链表的操作成本。", knowledge_points=["数组", "链表"], resource_type=resource_type)
        assert "major_background" not in data["content"] and "数组与链表" in data["content"]
        saved = service.persist(db, "test", data)
        assert saved.related_section_id == "section_1" and saved.source == "agent_generated"
        assert service.existing(db, "test", "section_1", resource_type).id == data["id"]
        data["content"] += "\n\n重新生成版本。"
        assert "重新生成版本" in service.persist(db, "test", data).content  # same ID overwrites
    assert db.query(ResourceModel).count() == len(RESOURCE_DEFINITIONS)
    assert len([row for row in db.query(ResourceModel) if "section_generated" in (row.tags or [])]) == len(RESOURCE_DEFINITIONS)
    print("section generated resources: PASS")


if __name__ == "__main__":
    main()
