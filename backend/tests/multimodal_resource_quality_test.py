"""Direct P4 checks for local visuals, quality metadata, and session isolation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ResourceModel
from app.services.resource_quality import ResourceQualityReviewer
from app.services.section_generated_resources import SectionGeneratedResourcesService
from app.services.structured_multimodal_resources import STRUCTURED_RESOURCE_DEFINITIONS, sanitize_mermaid


class NeverCalledClient:
    def chat(self, **_: object) -> str:
        raise AssertionError("P4 local structured resources must not call the shared LLM")


def generate(service: SectionGeneratedResourcesService, resource_type: str, session_id: str = "session_a", feedback: str = "") -> dict:
    return service.generate(
        session_id=session_id,
        path_id="path_1",
        stage_id="stage_1",
        chapter_id="chapter_1",
        section_id="recursion_section",
        section_title="递归调用栈",
        lecture_content="递归通过调用栈保存局部变量和返回地址。",
        knowledge_points=["递归", "调用栈", "栈帧", "返回顺序"],
        resource_type=resource_type,
        profile={"subject_context": {"prior_experience": ["零基础"], "content_preferences": ["example_first"]}},
        feedback=feedback,
    )


def main() -> None:
    safe = sanitize_mermaid("说明文字\n```mermaid\nflowchart TD\n  A[\"递归\"] --> B[\"基例\"]\n```")
    assert safe.startswith("flowchart TD")
    assert sanitize_mermaid("\n\nflowchart TD\n  A[\"递归\"] --> B[\"基例\"]").startswith("flowchart TD")
    assert not sanitize_mermaid("flowchart TD\n A[\"安全\"]\n click A \"javascript:alert(1)\"")
    assert not sanitize_mermaid("pie\n title unknown")
    assert not sanitize_mermaid("flowchart TD\n A[\"一\"] --> B[\"二\"]\n A[\"三\"]")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = SectionGeneratedResourcesService(llm_client=NeverCalledClient())

    generated = {}
    for resource_type in STRUCTURED_RESOURCE_DEFINITIONS:
        resource = generate(service, resource_type)
        generated[resource_type] = resource
        assert resource["task_id"] == resource_type
        assert "major_background" not in resource["content"]
        assert resource["resource_metadata"]["quality_status"] in {"passed", "repaired"}
        checks = resource["resource_metadata"]["checks"]
        assert all(checks.values())
        assert {"topic_keyword_coverage", "duplicate_node_detection", "generic_content_detection", "semantic_distinctness", "educational_value"} <= set(checks)
        assert [step["agent"] for step in resource["workflow_trace"]] == [
            "ProfileAgent", "ResourceAgent", "MultimodalAgent", "ResourceQualityReviewer", "ResourceModel",
        ]
        assert all({"agent_name", "capability", "status", "started_at", "finished_at", "provider", "used_fallback", "summary"} <= set(step) for step in resource["workflow_trace"])
        saved = service.persist(db, "session_a", resource)
        assert saved.session_id == "session_a" and saved.resource_metadata["quality_score"] >= 0.9

    recursion = generated["execution_trace"]
    assert recursion["mermaid_def"].startswith("sequenceDiagram")
    assert all(fragment in recursion["content"] for fragment in ("factorial(4)", "栈深度", "返回过程", "O(n)", "基例"))
    trace = generated["code_trace"]
    assert trace["mermaid_def"].startswith("sequenceDiagram") and trace["code_blocks"]
    assert trace["content"].count("def factorial") == 0
    assert "n <= 1" in trace["code_blocks"][0]["code"] and "n < 0" in trace["code_blocks"][0]["code"]
    assert "factorial(0)=1" in trace["content"] and "返回后继续执行" in trace["content"]
    knowledge_map = generated["knowledge_map"]
    assert knowledge_map["title"] == "递归调用栈知识结构图"
    assert all(term in knowledge_map["mermaid_def"] for term in ("递归函数", "终止条件", "调用栈", "栈帧", "局部变量", "返回位置", "逐层返回", "阶乘", "斐波那契"))
    comparison = generated["concept_diagram"]
    assert comparison["title"] == "递归与迭代概念对比"
    assert "| 对比维度 | 递归 | 迭代 |" in comparison["content"] and comparison["content"].count("|") >= 24
    flow = generated["process_flow"]
    assert flow["title"] == "递归调用栈学习流程图"
    assert all(term in flow["content"] for term in ("终止条件", "栈帧", "逐层计算返回值"))
    assert "顺序访问" not in recursion["content"] and "数组存储" not in recursion["content"]

    other_session = generate(service, "knowledge_map", "session_b")
    service.persist(db, "session_b", other_session)
    assert other_session["id"] != generated["knowledge_map"]["id"]
    assert service.existing(db, "session_a", "recursion_section", "knowledge_map").session_id == "session_a"
    assert service.existing(db, "session_b", "recursion_section", "knowledge_map").session_id == "session_b"
    assert db.query(ResourceModel).count() == len(STRUCTURED_RESOURCE_DEFINITIONS) + 1

    adjusted = generate(service, "code_trace", feedback="too_hard")
    assert adjusted["resource_metadata"]["quality_status"] in {"passed", "repaired"}
    assert "从 factorial(3) 开始" in adjusted["content"]
    assert "factorial(3)" in adjusted["mermaid_def"]

    invalid = ResourceQualityReviewer().review(
        {"content": "无关内容", "format": "diagram", "mermaid_def": "flowchart TD\n A[\"安全\"]\n click A \"x\""},
        section_title="递归调用栈",
        knowledge_points=["递归"],
    )
    assert invalid["resource_metadata"]["quality_status"] == "failed"
    assert not invalid["resource_metadata"]["checks"]["safety"]
    generic = ResourceQualityReviewer().review(
        {"task_id": "knowledge_map", "type": "mindmap", "format": "diagram", "content": "普通模板", "mermaid_def": "mindmap\n  root((递归调用栈))\n    核心定义\n    核心定义", "personalization": {"learner_level": "beginner"}},
        section_title="递归调用栈", knowledge_points=["递归", "调用栈"],
    )
    assert generic["resource_metadata"]["quality_status"] == "failed"
    print("multimodal resource quality: PASS")


if __name__ == "__main__":
    main()
