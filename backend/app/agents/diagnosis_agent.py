import re
from typing import Any

from app.agents.base import BaseAgent


class DiagnosisAgent(BaseAgent):
    agent_id = "diagnosis_agent"
    agent_name = "学习诊断智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile_map(context.get("profile"))
        profile_facts = context.get("profile_facts") if isinstance(context.get("profile_facts"), dict) else {}
        stages = self._stages(context.get("learning_path"))
        resources = list(context.get("resources") or [])
        points = list(context.get("knowledge_context", {}).get("retrieved_points", []))
        analytics = context.get("analytics") if isinstance(context.get("analytics"), dict) else {}

        candidates = self._event_candidates(analytics)
        candidates.extend(self._profile_candidates(profile, profile_facts))
        candidates = self._deduplicate(candidates)

        if not candidates and stages:
            candidates.extend(self._path_candidates(stages))
        if len(candidates) < 2 and points:
            candidates.extend(self._knowledge_candidates(points))

        weak_topics = [
            self._enrich_topic(candidate, stages, resources)
            for candidate in self._deduplicate(candidates)[:4]
        ]
        limitations = self._limitations(profile, stages, resources, analytics, weak_topics)
        next_actions = self._next_actions(weak_topics)
        confidence = self._overall_confidence(weak_topics)
        reason = self._overall_reason(weak_topics)

        weak_knowledge_points = [
            {
                "point_id": item.get("point_id") or f"diagnosis_{index}",
                "chapter_id": item.get("chapter_id"),
                "name": item["topic"],
                "reason": item["reason"],
                "priority": item["priority"],
                "difficulty": item.get("difficulty", "medium"),
                "prerequisites": item.get("prerequisites", []),
            }
            for index, item in enumerate(weak_topics, start=1)
        ]

        diagnosis = {
            "summary": self._summary(weak_topics),
            "weak_topics": weak_topics,
            # Keep the existing field for PlannerAgent, ResourceAgent and persisted snapshots.
            "weak_knowledge_points": weak_knowledge_points,
            "reason": reason,
            "source": "rule_based_diagnosis",
            "confidence": confidence,
            "next_actions": next_actions,
            "limitations": limitations,
            "evidence": self._collect_evidence(weak_topics),
            "recommended_stage_id": weak_topics[0].get("recommended_stage_id") if weak_topics else None,
            "recommended_resource_ids": self._recommended_resource_ids(weak_topics),
            "priority": weak_topics[0].get("priority", "low") if weak_topics else "low",
            "recommended_strategy": "；".join(next_actions),
        }
        return {
            "diagnosis": diagnosis,
            "agent_step": self.agent_step(),
        }

    def _profile_map(self, raw_profile: Any) -> dict[str, Any]:
        if isinstance(raw_profile, dict):
            return raw_profile
        if isinstance(raw_profile, list):
            return {
                str(item.get("key")): item
                for item in raw_profile
                if isinstance(item, dict) and item.get("key")
            }
        return {}

    def _profile_value(self, profile: dict[str, Any], *keys: str) -> str:
        for key in keys:
            item = profile.get(key)
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
            else:
                value = str(item or "").strip()
            if value:
                return value
        return ""

    def _stages(self, raw_path: Any) -> list[dict[str, Any]]:
        if isinstance(raw_path, dict):
            raw_path = raw_path.get("stages", [])
        return [item for item in (raw_path or []) if isinstance(item, dict)]

    def _event_candidates(self, analytics: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = []
        for item in analytics.get("weakTopics") or []:
            if not isinstance(item, dict) or not item.get("topic"):
                continue
            risk = self._clamp(item.get("risk"), default=0.5)
            candidates.append(
                {
                    "topic": str(item["topic"]),
                    "reason": (
                        f"学习行为记录显示该知识点答错 {item.get('wrongCount', 0)} 次，"
                        f"共记录 {item.get('totalCount', 0)} 次作答。"
                    ),
                    "source": "learning_events",
                    "confidence": round(0.65 + 0.25 * risk, 2),
                    "priority": "high" if risk >= 0.5 else "medium",
                    "evidence": [
                        f"行为数据：错误 {item.get('wrongCount', 0)}/{item.get('totalCount', 0)}"
                    ],
                }
            )
        return candidates

    def _profile_candidates(
        self,
        profile: dict[str, Any],
        profile_facts: dict[str, Any],
    ) -> list[dict[str, Any]]:
        weak_text = self._profile_value(profile, "error_patterns", "weak_points")
        weak_text = weak_text or str(profile_facts.get("weak_points", "")).strip()
        candidates = []
        for topic in self._split_topics(weak_text):
            candidates.append(
                {
                    "topic": topic,
                    "reason": "学习画像或用户输入明确提到该知识点掌握较弱，需要优先验证和补齐。",
                    "source": "profile",
                    "confidence": 0.68,
                    "priority": "high",
                    "evidence": [f"画像薄弱点：{weak_text}"],
                }
            )
        return candidates

    def _path_candidates(self, stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for stage in stages:
            progress = stage.get("progress", stage.get("overallProgress", 0))
            try:
                is_incomplete = float(progress or 0) < 100
            except (TypeError, ValueError):
                is_incomplete = True
            title = str(stage.get("title") or stage.get("goal") or "").strip()
            if title and is_incomplete:
                return [
                    {
                        "topic": title,
                        "reason": "当前学习路径尚未完成该阶段，暂将其作为需要验证的学习重点。",
                        "source": "learning_path_inference",
                        "confidence": 0.42,
                        "priority": "medium",
                        "evidence": [f"未完成路径阶段：{title}"],
                        "recommended_stage_id": stage.get("stage_id") or stage.get("id"),
                    }
                ]
        return []

    def _knowledge_candidates(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for index, point in enumerate(points[:3], start=1):
            topic = str(point.get("name") or f"重点知识点 {index}").strip()
            candidates.append(
                {
                    "topic": topic,
                    "reason": "缺少作答证据，暂按课程知识依赖顺序列为待验证重点，而不是确定薄弱结论。",
                    "source": "course_knowledge_inference",
                    "confidence": 0.35,
                    "priority": "medium" if index <= 2 else "low",
                    "evidence": [f"课程知识点：{topic}"],
                    "point_id": point.get("point_id"),
                    "chapter_id": point.get("chapter_id"),
                    "difficulty": point.get("difficulty", "medium"),
                    "prerequisites": point.get("prerequisites", []),
                }
            )
        return candidates

    def _split_topics(self, value: str) -> list[str]:
        if not value or "哪里比较薄弱" in value or "哪里薄弱" in value:
            return []
        parts = re.split(r"[、，,；;/]|以及|和|与", value)
        suffixes = ("比较薄弱", "掌握不牢", "不熟", "不会", "不懂", "薄弱", "较弱", "容易出错")
        topics = []
        for part in parts:
            topic = part.strip(" 。！？!?：:")
            for suffix in suffixes:
                if topic.endswith(suffix):
                    topic = topic[: -len(suffix)].strip()
                    break
            if topic and topic not in {"我", "哪里", "比较", "基础一般", "一般"}:
                topics.append(topic)
        return list(dict.fromkeys(topics))

    def _deduplicate(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        seen = set()
        for item in candidates:
            topic = str(item.get("topic", "")).strip()
            key = topic.lower()
            if topic and key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _enrich_topic(
        self,
        candidate: dict[str, Any],
        stages: list[dict[str, Any]],
        resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        item = dict(candidate)
        topic = str(item["topic"])
        stage = self._matching_stage(topic, stages)
        stage_id = item.get("recommended_stage_id") or (
            stage.get("stage_id") or stage.get("id") if stage else None
        )
        resource_ids = self._matching_resource_ids(topic, stage_id, resources)
        item["recommended_stage_id"] = stage_id
        item["recommended_resource_ids"] = resource_ids
        item["next_actions"] = self._topic_actions(topic, stage_id, resource_ids)
        item.setdefault("evidence", [])
        return item

    def _matching_stage(self, topic: str, stages: list[dict[str, Any]]) -> dict[str, Any] | None:
        for stage in stages:
            text = " ".join(
                str(value)
                for value in [
                    stage.get("title", ""),
                    stage.get("goal", ""),
                    " ".join(str(task) for task in stage.get("tasks", [])),
                ]
            )
            if topic in text or any(token and token in text for token in self._topic_tokens(topic)):
                return stage
        return None

    def _matching_resource_ids(
        self,
        topic: str,
        stage_id: str | None,
        resources: list[dict[str, Any]],
    ) -> list[str]:
        matches = []
        for resource in resources:
            knowledge_points = resource.get("related_knowledge_points") or resource.get("knowledge_points") or []
            text = " ".join(
                [
                    str(resource.get("title", "")),
                    str(resource.get("description", "")),
                    str(resource.get("related_chapter", "")),
                    " ".join(str(point) for point in knowledge_points),
                ]
            )
            same_stage = bool(stage_id and resource.get("related_stage_id") == stage_id)
            same_topic = topic in text or any(token and token in text for token in self._topic_tokens(topic))
            resource_id = resource.get("resource_id") or resource.get("id")
            if resource_id and (same_stage or same_topic):
                matches.append(str(resource_id))
        return list(dict.fromkeys(matches))[:3]

    def _topic_tokens(self, topic: str) -> list[str]:
        return [token for token in re.split(r"[、，,；;\s/]|和|与", topic) if len(token) >= 2]

    def _topic_actions(self, topic: str, stage_id: str | None, resource_ids: list[str]) -> list[str]:
        actions = [f"先复习“{topic}”的核心概念和前置知识"]
        if resource_ids:
            actions.append("完成推荐资源中的讲解与练习，并记录错因")
        else:
            actions.append("完成一组与该知识点直接相关的练习或实操")
        if stage_id:
            actions.append(f"回到学习路径阶段 {stage_id} 复核完成情况")
        return actions

    def _limitations(
        self,
        profile: dict[str, Any],
        stages: list[dict[str, Any]],
        resources: list[dict[str, Any]],
        analytics: dict[str, Any],
        weak_topics: list[dict[str, Any]],
    ) -> list[str]:
        limitations = []
        if not profile:
            limitations.append("缺少结构化学习画像，无法充分判断基础、目标和学习偏好。")
        if not stages:
            limitations.append("缺少学习路径，无法将薄弱点精确绑定到学习阶段。")
        if not resources:
            limitations.append("缺少已生成资源，暂时无法给出可靠的资源级推荐。")
        if not analytics.get("eventCount"):
            limitations.append("暂无测验、实操、反馈或节点进度等行为数据，本次仅为初步诊断。")
        if not weak_topics:
            limitations.append("当前证据不足，尚不能确认具体薄弱知识点。")
        return limitations

    def _next_actions(self, weak_topics: list[dict[str, Any]]) -> list[str]:
        if not weak_topics:
            return [
                "补充目标课程、已有基础和自述薄弱点",
                "先生成学习路径和配套资源",
                "完成一次测验或实操后重新发起诊断",
            ]
        actions = []
        for item in weak_topics[:2]:
            actions.extend(item.get("next_actions", []))
        return list(dict.fromkeys(actions))[:5]

    def _overall_confidence(self, weak_topics: list[dict[str, Any]]) -> float:
        if not weak_topics:
            return 0.15
        values = [self._clamp(item.get("confidence"), default=0.3) for item in weak_topics]
        return round(sum(values) / len(values), 2)

    def _overall_reason(self, weak_topics: list[dict[str, Any]]) -> str:
        if not weak_topics:
            return "当前缺少可验证的画像薄弱点和学习行为证据，无法形成确定诊断。"
        sources = {str(item.get("source")) for item in weak_topics}
        if "learning_events" in sources:
            return "诊断综合了当前学习行为、学习画像、路径阶段和可用资源。"
        return "诊断基于当前学习画像、学习路径和资源关联推断，仍需行为数据进一步验证。"

    def _summary(self, weak_topics: list[dict[str, Any]]) -> str:
        if not weak_topics:
            return "现有数据不足以确认具体薄弱点，建议先补充学习信息并完成一次可记录的练习。"
        names = "、".join(str(item["topic"]) for item in weak_topics[:3])
        return f"当前优先关注：{names}。请按建议行动验证并逐步收窄诊断范围。"

    def _collect_evidence(self, weak_topics: list[dict[str, Any]]) -> list[str]:
        evidence = []
        for item in weak_topics:
            evidence.extend(str(value) for value in item.get("evidence", []) if value)
        return list(dict.fromkeys(evidence))

    def _recommended_resource_ids(self, weak_topics: list[dict[str, Any]]) -> list[str]:
        resource_ids = []
        for item in weak_topics:
            resource_ids.extend(str(value) for value in item.get("recommended_resource_ids", []) if value)
        return list(dict.fromkeys(resource_ids))[:5]

    def _clamp(self, value: Any, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default
