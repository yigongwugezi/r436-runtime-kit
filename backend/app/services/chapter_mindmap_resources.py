"""Persistent local Mermaid mind maps for learning-path chapters."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ResourceModel
from app.db.repository import upsert_resource
from app.services.multimodal_provider import MindMapTool


class ChapterMindmapResourceService:
    def __init__(self, tool: Any | None = None) -> None:
        self._tool = tool or MindMapTool()

    @staticmethod
    def resource_id(chapter_id: str) -> str:
        return f"chapter_{chapter_id}_mindmap"

    def existing(self, db: Session, session_id: str, chapter_id: str) -> ResourceModel | None:
        return db.get(ResourceModel, self.resource_id(chapter_id))

    def generate(
        self,
        *,
        path_id: str,
        stage_id: str,
        chapter_id: str,
        chapter_title: str,
        sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        children = [
            {"title": str(section.get("title") or ""), "children": self._points(section.get("knowledge_points") or section.get("knowledgePoints") or [])}
            for section in sections if str(section.get("title") or "").strip()
        ]
        result = self._tool.run({"topic": chapter_title, "learning_path": {"stages": [{"title": chapter_title, "children": [child["title"] for child in children]}]}})
        mermaid = str((result.get("result") or {}).get("mermaid") or "").strip() if isinstance(result, dict) else ""
        if not self._valid_mermaid(mermaid):
            mermaid = self._fallback_mermaid(chapter_title, children)
        if not self._valid_mermaid(mermaid):
            raise ValueError("mindmap generation failed")
        return {
            "id": self.resource_id(chapter_id),
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
        }

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
        return value.startswith("mindmap") and "root((" in value and len(value) > 30

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
