"""Generate small, persistent learning aids for one lecture section."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ResourceModel
from app.db.repository import upsert_resource
from app.services.llm_client import get_llm_client


RESOURCE_DEFINITIONS = {
    "summary_card": ("总结卡片", "reading"),
    "concept_comparison": ("概念对比", "reading"),
    "worked_example": ("例题详解", "practice"),
    "mistake_checklist": ("易错清单", "reading"),
    "review_notes": ("复习笔记", "reading"),
}
PROFILE_KEYS = {"major_background", "knowledge_base", "learning_goal", "cognitive_style", "error_patterns", "coding_ability"}


class SectionGeneratedResourcesService:
    """Create one deterministic resource per section/type and persist it on demand."""

    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm_client = llm_client or get_llm_client()

    @staticmethod
    def resource_id(section_id: str, resource_type: str) -> str:
        return f"section_{section_id}_{resource_type}"

    def existing(self, db: Session, session_id: str, section_id: str, resource_type: str) -> ResourceModel | None:
        return db.get(ResourceModel, self.resource_id(section_id, resource_type))

    def generate(
        self,
        *,
        session_id: str,
        path_id: str,
        stage_id: str,
        chapter_id: str,
        section_id: str,
        section_title: str,
        lecture_content: str,
        knowledge_points: list[Any],
        resource_type: str,
    ) -> dict[str, Any]:
        if resource_type not in RESOURCE_DEFINITIONS:
            raise ValueError("unsupported resourceType")
        label, storage_type = RESOURCE_DEFINITIONS[resource_type]
        points = self._points(knowledge_points)
        prompt = (
            f"为小节「{section_title}」生成{label}。知识点：{'、'.join(points) or section_title}。"
            f"讲义摘要：{lecture_content[:900]}。只输出 Markdown，不要输出学生画像或 JSON。"
        )
        try:
            content = self._llm_client.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=1200)
        except Exception:
            content = ""
        if self._invalid(content, section_title):
            content = self._fallback(resource_type, section_title, points, lecture_content)

        return {
            "id": self.resource_id(section_id, resource_type),
            "type": storage_type,
            "title": f"{section_title} · {label}",
            "description": f"为当前小节生成的{label}",
            "content": content,
            "knowledge_points": points,
            "tags": ["section_generated", resource_type, path_id],
            "difficulty": "medium",
            "estimated_minutes": 10,
            "format": "text",
            "source": "agent_generated",
            "related_stage_id": stage_id,
            "related_chapter_id": chapter_id,
            "related_section_id": section_id,
            "task_id": resource_type,
            "generated_type": resource_type,
            "generation_status": "completed",
        }

    def persist(self, db: Session, session_id: str, resource: dict[str, Any]) -> ResourceModel:
        return upsert_resource(db, session_id, resource)

    @staticmethod
    def serialize(resource: ResourceModel) -> dict[str, Any]:
        tags = resource.tags or []
        generated_type = next((tag for tag in tags if tag in RESOURCE_DEFINITIONS), resource.task_id or "")
        return {
            "id": resource.id,
            "title": resource.title,
            "content": resource.content or "",
            "type": resource.type,
            "resourceType": generated_type,
            "source": resource.source,
            "sectionId": resource.related_section_id or "",
            "chapterId": resource.related_chapter_id or "",
            "stageId": resource.related_stage_id or "",
            "createdAt": int(resource.created_at.timestamp() * 1000) if resource.created_at else 0,
        }

    @staticmethod
    def _points(items: list[Any]) -> list[str]:
        return [str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip() for item in items if (item.get("name", "") if isinstance(item, dict) else item)][:6]

    @staticmethod
    def _invalid(content: Any, section_title: str) -> bool:
        text = str(content or "").strip()
        if len(text) < 80 or section_title not in text:
            return True
        try:
            value = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return any(key in text for key in PROFILE_KEYS)
        return isinstance(value, dict) and len(PROFILE_KEYS.intersection(value)) >= 3

    @staticmethod
    def _fallback(resource_type: str, title: str, points: list[str], lecture: str) -> str:
        topic = "、".join(points) or title
        if resource_type == "summary_card":
            return f"## {title} 总结卡片\n\n- 核心主题：{topic}\n- 学习重点：先理解定义，再比较操作成本。\n- 自检：能否用一个例子说明每个概念的作用？"
        if resource_type == "concept_comparison":
            return f"## {title} 概念对比\n\n| 维度 | 概念 A | 概念 B |\n|---|---|---|\n| 关注点 | {topic} 的定义 | 典型操作与适用场景 |\n| 复习方法 | 说清为什么需要 | 用例子比较差异 |"
        if resource_type == "worked_example":
            return f"## {title} 例题详解\n\n**题目**：选择一个与 {topic} 有关的操作，说明操作步骤和成本。\n\n**解题步骤**：先明确输入，再逐步写出操作过程，最后解释为什么得到该结论。\n\n> 不只写答案，要写判断依据。"
        if resource_type == "mistake_checklist":
            return f"## {title} 易错点检查清单\n\n- [ ] 没有混淆 {topic} 的定义与操作。\n- [ ] 能说明结论对应的条件。\n- [ ] 能用一个例子检验理解。"
        excerpt = " ".join(str(lecture or "").split())[:180]
        return f"## {title} 复习笔记\n\n### 关键知识\n{topic}\n\n### 复习提醒\n{excerpt or '先回顾核心定义，再完成一道应用练习。'}"
