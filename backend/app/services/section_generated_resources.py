"""Generate small, persistent learning aids for one lecture section."""

from __future__ import annotations

import json
from hashlib import sha1
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ResourceModel
from app.db.repository import upsert_resource
from app.services.llm_client import get_llm_client
from app.services.resource_quality import ResourceQualityReviewer
from app.services.structured_multimodal_resources import (
    STRUCTURED_RESOURCE_DEFINITIONS,
    build_structured_resource,
    normalized_resource_title,
)


RESOURCE_DEFINITIONS = {
    "summary_card": ("总结卡片", "reading"),
    "concept_comparison": ("概念对比", "reading"),
    "worked_example": ("例题详解", "practice"),
    "mistake_checklist": ("易错清单", "reading"),
    "review_notes": ("复习笔记", "reading"),
    **STRUCTURED_RESOURCE_DEFINITIONS,
}
PROFILE_KEYS = {"major_background", "knowledge_base", "learning_goal", "cognitive_style", "error_patterns", "coding_ability"}


class SectionGeneratedResourcesService:
    """Create one deterministic resource per section/type and persist it on demand."""

    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm_client = llm_client or get_llm_client()

    @staticmethod
    def resource_id(section_id: str, resource_type: str, session_id: str = "") -> str:
        """Use a session suffix for new records without losing legacy readability."""
        base = f"section_{section_id}_{resource_type}"
        return f"{base}_{sha1(session_id.encode()).hexdigest()[:10]}" if session_id else base

    def existing(self, db: Session, session_id: str, section_id: str, resource_type: str) -> ResourceModel | None:
        scoped_id = self.resource_id(section_id, resource_type, session_id)
        legacy_id = self.resource_id(section_id, resource_type)
        return db.query(ResourceModel).filter(
            ResourceModel.session_id == session_id,
            ResourceModel.id.in_((scoped_id, legacy_id)),
        ).order_by(ResourceModel.updated_at.desc()).first()

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
        profile: dict[str, Any] | None = None,
        feedback: str = "",
    ) -> dict[str, Any]:
        if resource_type not in RESOURCE_DEFINITIONS:
            raise ValueError("unsupported resourceType")
        label, storage_type = RESOURCE_DEFINITIONS[resource_type]
        points = self._points(knowledge_points)
        personalization = self._personalization(profile, section_title, points)
        if resource_type in STRUCTURED_RESOURCE_DEFINITIONS:
            from app.agents.multimodal_agent import MultimodalAgent

            multimodal_context = {
                "task_type": "structured_learning_resource",
                "resource_type": resource_type,
                "section_title": section_title,
                "knowledge_points": points,
                "profile": {
                    "subject_context": {"content_preferences": personalization["preferences"]},
                    "knowledge_mastery": [{"label": point, "status": "weak"} for point in personalization["relevant_weak_points"]],
                },
                "feedback": feedback,
                "lecture_content": lecture_content[:2000] if lecture_content else "",
            }
            result = MultimodalAgent().run(multimodal_context)
            generated = result.get("result") if isinstance(result.get("result"), dict) else {}
            if result.get("status") != "completed" or not generated:
                generated = build_structured_resource(multimodal_context)
                generated["used_fallback"] = True
            resource = {
                **generated,
                "id": self.resource_id(section_id, resource_type, session_id),
                "knowledge_points": points,
                "tags": ["section_generated", resource_type, path_id, "p4_multimodal"],
                "difficulty": "easy" if personalization["level"] == "beginner" else "medium",
                "estimated_minutes": 12,
                "source": "agent_generated",
                "source_type": "rule_based_fallback",
                "related_stage_id": stage_id,
                "related_chapter_id": chapter_id,
                "related_section_id": section_id,
                "task_id": resource_type,
                "generated_type": resource_type,
                "generation_status": "completed",
                "quality_status": "pending",
                "workflow_trace": self._workflow_trace(resource_type, profile, feedback),
            }
            reviewed = ResourceQualityReviewer().review(resource, section_title=section_title, knowledge_points=points)
            metadata = reviewed.get("resource_metadata") if isinstance(reviewed.get("resource_metadata"), dict) else {}
            if metadata.get("quality_status") == "failed":
                # The structured agent is local by design.  One deterministic rebuild is
                # safer than retrying a provider or persisting an unrenderable resource.
                fallback = build_structured_resource(multimodal_context)
                reviewed.update(fallback)
                reviewed.update({
                    "id": self.resource_id(section_id, resource_type, session_id),
                    "knowledge_points": points,
                    "tags": resource["tags"],
                    "difficulty": resource["difficulty"],
                    "estimated_minutes": resource["estimated_minutes"],
                    "source": "agent_generated",
                    "source_type": "rule_based_fallback",
                    "related_stage_id": stage_id,
                    "related_chapter_id": chapter_id,
                    "related_section_id": section_id,
                    "task_id": resource_type,
                    "generated_type": resource_type,
                    "generation_status": "completed",
                    "generation_source": "local_fallback",
                    "generation_mode": "fallback",
                    "used_fallback": True,
                })
                reviewed = ResourceQualityReviewer().review(reviewed, section_title=section_title, knowledge_points=points)
                metadata = reviewed.get("resource_metadata") if isinstance(reviewed.get("resource_metadata"), dict) else {}
                if metadata.get("quality_status") in {"passed", "repaired"}:
                    metadata = {**metadata, "quality_status": "fallback", "fallback_reason": "质量审查未通过，已使用本地模板重建"}
            reviewed["quality_status"] = metadata.get("quality_status", "failed")
            reviewed["resource_metadata"] = {
                **metadata,
                "workflow_trace": self._workflow_trace(resource_type, profile, feedback, reviewed["quality_status"]),
            }
            return reviewed
        prompt = (
            f"为小节「{section_title}」生成{label}。知识点：{'、'.join(points) or section_title}。"
            f"讲义摘要：{lecture_content[:900]}。学习适配：基础={personalization['level']}；偏好={'、'.join(personalization['preferences']) or '无'}；"
            f"当前相关薄弱点={'、'.join(personalization['relevant_weak_points']) or '无'}。只输出 Markdown，不要输出学生画像或 JSON。"
        )
        try:
            content = self._llm_client.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=1200)
        except Exception:
            content = ""
        if self._invalid(content, section_title, resource_type):
            content = self._fallback(resource_type, section_title, points, lecture_content, personalization)

        return {
            "id": self.resource_id(section_id, resource_type, session_id),
            "type": storage_type,
            "title": normalized_resource_title(section_title, resource_type, points) if resource_type in STRUCTURED_RESOURCE_DEFINITIONS else f"{section_title} · {label}",
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
        meta = resource.resource_metadata if isinstance(resource.resource_metadata, dict) else {}
        item: dict[str, Any] = {
            "id": resource.id,
            "title": resource.title,
            "content": resource.content or "",
            "type": resource.type,
            "resourceType": generated_type,
            "source": resource.source,
            "sectionId": resource.related_section_id or "",
            "chapterId": resource.related_chapter_id or "",
            "stageId": resource.related_stage_id or "",
            "mermaidDef": resource.mermaid_def or "",
            "format": resource.format or "text",
            "quality": meta.get("quality_status", ""),
            "qualityScore": meta.get("quality_score"),
            "workflowTrace": meta.get("workflow_trace", []),
            "personalization": meta.get("personalization", {}),
            "createdAt": int(resource.created_at.timestamp() * 1000) if resource.created_at else 0,
        }
        return item

    @staticmethod
    def _workflow_trace(
        resource_type: str,
        profile: dict[str, Any] | None,
        feedback: str,
        quality_status: str = "passed",
    ) -> list[dict[str, Any]]:
        from datetime import datetime, timezone

        has_profile = bool(profile)
        timestamp = datetime.now(timezone.utc).isoformat()
        def step(agent: str, capability: str, provider: str, used_fallback: bool, summary: str) -> dict[str, Any]:
            return {
                "agent": agent,  # Kept for the existing lightweight frontend renderer.
                "agent_name": agent,
                "capability": capability,
                "status": "completed",
                "started_at": timestamp,
                "finished_at": timestamp,
                "provider": provider,
                "used_fallback": used_fallback,
                "summary": summary,
            }
        return [
            step("ProfileAgent", "读取最小画像上下文", "profile_store", not has_profile, "读取当前小节所需的最小画像信息" if has_profile else "当前无可用画像，使用通用学习适配"),
            step("ResourceAgent", "构建资源生成任务", "resource_task_builder", False, f"创建 {RESOURCE_DEFINITIONS[resource_type][0]} 生成任务"),
            step("MultimodalAgent", "生成结构化可视化", "local_template", True, "使用本地结构化模板生成可渲染内容"),
            step("ResourceQualityReviewer", "审查主题、结构与渲染安全", "resource_quality_reviewer", quality_status == "fallback", "完成主题、结构、渲染与安全检查"),
            step("ResourceModel", "持久化当前会话资源", "database", False, "按当前会话和小节范围持久化资源"),
        ]

    @staticmethod
    def _points(items: list[Any]) -> list[str]:
        return [str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip() for item in items if (item.get("name", "") if isinstance(item, dict) else item)][:6]

    @staticmethod
    def _personalization(profile: dict[str, Any] | None, title: str, points: list[str]) -> dict[str, Any]:
        profile = profile or {}
        context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
        records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
        enabled = lambda key: not isinstance(records.get(key), dict) or not records[key].get("is_disabled_for_personalization")
        prior = " ".join(str(item) for item in context.get("prior_experience") or []) if enabled("prior_experience") else ""
        preferences = [str(item) for item in context.get("content_preferences") or []] if enabled("content_preferences") else []
        section_text = f"{title} {' '.join(points)}".lower()
        mastery = profile.get("knowledge_mastery") if isinstance(profile.get("knowledge_mastery"), list) else []
        weak = [str(item.get("label") or item.get("knowledge_id") or "").strip() for item in mastery if isinstance(item, dict) and item.get("status") == "weak"]
        return {
            "level": "beginner" if any(token in prior for token in ("零基础", "没学过", "基础薄弱", "初学")) else "general",
            "preferences": preferences[:3],
            "relevant_weak_points": [item for item in weak if item and item.lower() in section_text][:4],
        }

    @staticmethod
    def _invalid(content: Any, section_title: str, resource_type: str = "") -> bool:
        text = str(content or "").strip()
        if len(text) < 80 or section_title not in text:
            return True
        if resource_type == "review_notes" and not all(label in text for label in ("关键知识", "复习提醒", "自测问题")):
            return True
        try:
            value = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return any(key in text for key in PROFILE_KEYS)
        return isinstance(value, dict) and len(PROFILE_KEYS.intersection(value)) >= 3

    @staticmethod
    def _fallback(resource_type: str, title: str, points: list[str], lecture: str, personalization: dict[str, Any] | None = None) -> str:
        topic = "、".join(points) or title
        preferences = (personalization or {}).get("preferences") or []
        study_tip = "先看一个具体例子，再完成一题练习。" if "example_first" in preferences else "先说清定义和适用条件，再用例子验证。"
        if resource_type == "summary_card":
            return f"## {title} 总结卡片\n\n- 核心主题：{topic}\n- 学习重点：{study_tip}\n- 自检：能否用一个例子说明每个概念的作用？"
        if resource_type == "concept_comparison":
            first = points[0] if points else title
            second = points[1] if len(points) > 1 else f"{first} 的操作过程"
            return f"## {title} 概念对比\n\n| 维度 | {first} | {second} |\n|---|---|---|\n| 关注点 | 定义、结构特征与常见操作 | 定义、结构特征与常见操作 |\n| 复习方法 | 用一个具体输入说明操作结果 | 对照相同输入说明差异 |"
        if resource_type == "worked_example":
            if "递归" in f"{title}{topic}":
                return f"## {title} 例题详解\n\n**题目**：计算 `factorial(3)`，其中 `factorial(n) = n * factorial(n - 1)`，`factorial(0) = 1`。\n\n**调用过程**：1. 调用 `factorial(3)`，栈帧保存 `n=3`。2. 调用 `factorial(2)`，栈帧保存 `n=2`。3. 调用 `factorial(1)`，栈帧保存 `n=1`。4. 调用 `factorial(0)`，返回 `1`。\n\n**返回过程**：`factorial(1)` 返回 `1`，`factorial(2)` 返回 `2`，`factorial(3)` 返回 `6`。每一层返回后对应栈帧才退出。"
            first = points[0] if points else title
            return f"## {title} 例题详解\n\n**题目**：在输入 `[2, 4, 6, 8]` 的 {first} 中查找 `6`。\n\n**解题步骤**：1. 从第一个元素 `2` 开始比较。2. 再比较 `4`。3. 比较到 `6` 时找到目标，记录当前位置。\n\n**判断依据**：每一次比较都对应真实输入中的一个元素，能够据此说明访问次数和结果。"
        if resource_type == "mistake_checklist":
            return f"## {title} 易错点检查清单\n\n- [ ] 没有混淆 {topic} 的定义与操作。\n- [ ] 每一步都说明了输入变化或访问位置。\n- [ ] 能用一个例子检验理解。"
        point_lines = "\n".join(f"- {point}" for point in points) or f"- {title}"
        return (
            f"# {title} 复习笔记\n\n"
            f"## 关键知识\n{point_lines}\n\n"
            "## 复习提醒\n"
            "- 先用自己的话说明核心定义和适用条件。\n"
            "- 再完成一道相关练习，检查是否能把概念用于具体问题。\n\n"
            "## 自测问题\n"
            f"1. {title} 中最需要区分的概念是什么？\n"
            "2. 你能用一个例子说明它的适用场景吗？"
        )
