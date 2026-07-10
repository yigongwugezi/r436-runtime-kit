from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ResourceModel
from app.services.chapter_mindmap_resources import ChapterMindmapResourceService


class EmptyTool:
    def run(self, context):
        return {"status": "needs_input", "result": {}}


def main() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = ChapterMindmapResourceService(tool=EmptyTool())
    resource = service.generate(path_id="path_1", stage_id="stage_1", chapter_id="chapter_1", chapter_title="线性表", sections=[{"title": "数组", "knowledge_points": ["随机访问", "插入"]}, {"title": "链表", "knowledge_points": ["指针", "删除"]}])
    assert resource["type"] == "mindmap" and "mindmap" in resource["content"]
    saved = service.persist(db, "test", resource)
    assert saved.related_chapter_id == "chapter_1" and saved.mermaid_def
    resource["content"] += "\n    新节点"
    resource["mermaid_def"] = resource["content"]
    service.persist(db, "test", resource)
    assert db.query(ResourceModel).count() == 1 and "新节点" in service.existing(db, "test", "chapter_1").content
    print("chapter mindmap resources: PASS")


if __name__ == "__main__":
    main()
