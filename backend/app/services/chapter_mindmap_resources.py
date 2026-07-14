"""Persistent local Mermaid mind maps for learning-path chapters."""

from __future__ import annotations

from hashlib import sha1
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ResourceModel
from app.db.repository import upsert_resource
from app.services.multimodal_provider import MindMapTool
from app.services.resource_quality import ResourceQualityReviewer
from app.services.structured_multimodal_resources import sanitize_mermaid


class ChapterMindmapResourceService:
    def __init__(self, tool: Any | None = None) -> None:
        self._tool = tool or MindMapTool()

    @staticmethod
    def resource_id(chapter_id: str, session_id: str = "") -> str:
        base = f"chapter_{chapter_id}_mindmap"
        return f"{base}_{sha1(session_id.encode()).hexdigest()[:10]}" if session_id else base

    def existing(self, db: Session, session_id: str, chapter_id: str) -> ResourceModel | None:
        return db.query(ResourceModel).filter(
            ResourceModel.session_id == session_id,
            ResourceModel.id.in_((self.resource_id(chapter_id, session_id), self.resource_id(chapter_id))),
        ).order_by(ResourceModel.updated_at.desc()).first()

    def generate(
        self,
        *,
        path_id: str,
        stage_id: str,
        chapter_id: str,
        chapter_title: str,
        sections: list[dict[str, Any]],
        session_id: str = "",
        lecture_content: str = "",
    ) -> dict[str, Any]:
        children = [
            {"title": str(section.get("title") or ""), "children": self._points(section.get("knowledge_points") or section.get("knowledgePoints") or [])}
            for section in sections if str(section.get("title") or "").strip()
        ]
        # Include lecture/textbook content as context for richer mindmaps
        context = {"topic": chapter_title, "learning_path": {"stages": [{"title": chapter_title, "tasks": children}]}}
        if lecture_content:
            context["lecture_content"] = lecture_content[:2000]
        result = self._tool.run(context)
        mermaid = str((result.get("result") or {}).get("mermaid") or "").strip() if isinstance(result, dict) else ""
        used_fallback = not bool(mermaid)
        mermaid = sanitize_mermaid(mermaid)
        if not self._valid_mermaid(mermaid):
            mermaid = self._fallback_mermaid(chapter_title, children)
            used_fallback = True
        mermaid = sanitize_mermaid(mermaid)
        if not self._valid_mermaid(mermaid):
            raise ValueError("mindmap generation failed")
        resource = {
            "id": self.resource_id(chapter_id, session_id),
            "type": "mindmap",
            "title": f"{chapter_title} · 章节思维导图",
            "description": "基于当前章节小节和知识点生成的 Mermaid 思维导图",
            "content": mermaid,
            "mermaid_def": mermaid,
            "knowledge_points": [point for child in children for point in child["children"]],
            "tags": ["chapter_mindmap", path_id],
            "difficulty": "medium",
            "estimated_minutes": 10,
            "format": "mermaid",
            "source": "agent_generated",
            "related_stage_id": stage_id,
            "related_chapter_id": chapter_id,
            "related_section_id": "",
            "task_id": "chapter_mindmap",
            "personalization": {"learner_level": "general"},
            "generation_source": "local_fallback" if used_fallback else str(result.get("provider") or "multimodal_tool"),
            "generation_mode": "fallback" if used_fallback else "provider",
            "used_fallback": used_fallback,
            "used_llm": not used_fallback,
        }
        return ResourceQualityReviewer().review(
            resource,
            section_title=chapter_title,
            knowledge_points=resource["knowledge_points"],
        )

    @staticmethod
    def persist(db: Session, session_id: str, resource: dict[str, Any]) -> ResourceModel:
        return upsert_resource(db, session_id, resource)

    @staticmethod
    def serialize(resource: ResourceModel) -> dict[str, Any]:
        return {
            "id": resource.id,
            "title": resource.title,
            "mermaidDef": resource.mermaid_def or resource.content or "",
            "chapterId": resource.related_chapter_id or "",
            "stageId": resource.related_stage_id or "",
            "source": resource.source,
            "createdAt": int(resource.created_at.timestamp() * 1000) if resource.created_at else 0,
        }

    @staticmethod
    def _points(items: list[Any]) -> list[str]:
        return [str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip() for item in items if (item.get("name", "") if isinstance(item, dict) else item)][:6]

    @staticmethod
    def _valid_mermaid(value: str) -> bool:
        v = value.strip()
        return len(v) > 50 and (
            (v.startswith("mindmap") and "root((" in v) or
            v.startswith("graph") or
            v.startswith("flowchart")
        )

    @staticmethod
    def _fallback_mermaid(title: str, children: list[dict[str, Any]]) -> str:
        def clean(value: str) -> str:
            return " ".join(str(value).replace("(", "（").replace(")", "）").split())[:48] or "知识点"
        lines = ["mindmap", f"  root(({clean(title)}))"]
        for child in children[:8]:
            lines.append(f"    {clean(child['title'])}")
            for point in child["children"][:5]:
                lines.append(f"      {clean(point)}")
        return "\n".join(lines)
