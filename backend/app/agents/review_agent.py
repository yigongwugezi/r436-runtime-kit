import re
from typing import Any

from app.agents.base import BaseAgent
from app.services.course_catalog import course_catalog


class ReviewAgent(BaseAgent):
    agent_id = "review_agent"
    agent_name = "质量审核智能体"

    required_resource_types = {"lecture", "mindmap", "quiz", "reading", "practice"}
    blocked_terms = {
        "代写作业",
        "考试作弊",
        "泄题",
        "绕过监考",
        "违法",
        "攻击系统",
        "窃取",
    }
    trusted_resource_sources = {"llm_generated", "rule_based_fallback"}

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        checks = [
            self._check_profile(context),
            self._check_knowledge_grounding(context),
            self._check_learning_path(context),
            self._check_resource_coverage(context),
            self._check_course_chapter_alignment(context),
            self._check_resource_content_quality(context),
            self._check_resource_type_match(context),
            self._check_provenance_trust(context),
            self._check_path_time_budget(context),
            self._check_content_safety(context),
        ]
        quality_status = self._aggregate_status(checks)

        return {
            "review": {
                "quality_status": quality_status,
                "checks": checks,
                "summary": self._summary(checks),
                "anti_hallucination": {
                    "enabled": True,
                    "strategy": "基于课程知识库检查章节归属、资源内容、类型匹配、来源标记和路径时间预算。",
                    "knowledge_source": context.get("knowledge_context", {}).get("source", "unknown"),
                },
            },
            "agent_step": self.agent_step(),
        }

    def _check_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = context.get("profile", {})
        filled = [
            key
            for key, value in profile.items()
            if isinstance(value, dict) and str(value.get("value", "")).strip()
        ]
        if len(filled) >= 5:
            return self._check(
                "profile_completeness",
                "画像完整度检查",
                "passed",
                f"已形成 {len(filled)} 个画像维度，可支撑第一版学习方案。",
            )
        return self._check(
            "profile_completeness",
            "画像完整度检查",
            "warning",
            f"画像维度只有 {len(filled)} 个，建议继续补充学生背景、目标、基础和偏好。",
        )

    def _check_knowledge_grounding(self, context: dict[str, Any]) -> dict[str, Any]:
        knowledge = context.get("knowledge_context", {})
        points = knowledge.get("retrieved_points", [])
        if knowledge.get("source") == "course_knowledge_base" and points:
            return self._check(
                "knowledge_grounding",
                "知识库依据检查",
                "passed",
                f"已从课程知识库检索到 {len(points)} 个相关知识点。",
            )
        return self._check(
            "knowledge_grounding",
            "知识库依据检查",
            "warning",
            "未发现有效课程知识库依据，生成结果需要人工复核。",
        )

    def _check_learning_path(self, context: dict[str, Any]) -> dict[str, Any]:
        path = self._dict_items(context.get("learning_path"))
        incomplete = [
            str(stage.get("stage_id") or stage.get("title") or "unknown")
            for stage in path
            if not stage.get("tasks") or not stage.get("goal")
        ]
        if path and not incomplete:
            return self._check(
                "path_structure",
                "学习路径结构检查",
                "passed",
                f"已生成 {len(path)} 个学习阶段，阶段目标和任务完整。",
            )
        message = "学习路径为空。" if not path else f"阶段目标或任务不完整：{', '.join(incomplete)}。"
        return self._check("path_structure", "学习路径结构检查", "warning", message)

    def _check_resource_coverage(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = self._dict_items(context.get("resources"))
        types = {str(item.get("type") or "").strip() for item in resources}
        missing = sorted(self.required_resource_types - types)
        if not missing:
            return self._check(
                "resource_coverage",
                "资源类型覆盖检查",
                "passed",
                f"已覆盖资源类型：{', '.join(sorted(types))}。",
            )
        return self._check(
            "resource_coverage",
            "资源类型覆盖检查",
            "warning",
            f"缺少资源类型：{', '.join(missing)}。",
        )

    def _check_course_chapter_alignment(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = self._dict_items(context.get("resources"))
        chapters = self._course_chapters(context)
        missing: list[str] = []
        drifted: list[str] = []

        for resource in resources:
            resource_id = self._resource_label(resource)
            related = str(resource.get("related_chapter") or "").strip()
            if not related:
                missing.append(resource_id)
            elif chapters and not self._chapter_matches(related, chapters):
                drifted.append(f"{resource_id}（{related}）")

        if drifted:
            return self._check(
                "course_chapter_alignment",
                "课程章节归属检查",
                "blocked",
                f"资源章节不属于当前课程：{', '.join(drifted)}。",
            )
        if missing:
            return self._check(
                "course_chapter_alignment",
                "课程章节归属检查",
                "warning",
                f"资源缺少 related_chapter：{', '.join(missing)}。",
            )
        if resources and not chapters:
            return self._check(
                "course_chapter_alignment",
                "课程章节归属检查",
                "warning",
                "当前课程缺少可核验的章节目录，暂不能确认资源章节归属。",
            )
        return self._check(
            "course_chapter_alignment",
            "课程章节归属检查",
            "passed",
            f"{len(resources)} 个资源的 related_chapter 均可映射到当前课程章节。",
        )

    def _check_resource_content_quality(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = self._dict_items(context.get("resources"))
        blocked: list[str] = []
        warnings: list[str] = []

        for resource in resources:
            label = self._resource_label(resource)
            resource_type = str(resource.get("type") or "").strip()
            content = str(resource.get("content") or "").strip()
            items = resource.get("items") if isinstance(resource.get("items"), list) else []

            if resource_type == "quiz":
                valid_items = [item for item in items if isinstance(item, dict) and str(item.get("stem") or item.get("question") or "").strip()]
                if not valid_items:
                    blocked.append(f"{label}（quiz 无有效题目）")
                continue
            if not content and not items:
                blocked.append(f"{label}（内容为空）")
                continue

            compact = self._normalize_text(content)
            title = self._normalize_text(resource.get("title"))
            if resource_type == "mindmap":
                if not self._looks_like_mindmap(content):
                    warnings.append(f"{label}（缺少有效 Mermaid/结构）")
            elif resource_type == "practice":
                if not self._looks_like_practice(content):
                    warnings.append(f"{label}（缺少实操步骤或练习说明）")
            elif compact == title or len(compact) < 30:
                warnings.append(f"{label}（正文过短或只有标题）")

        if blocked:
            return self._check(
                "resource_content_quality",
                "资源内容质量检查",
                "blocked",
                f"存在不可用资源：{', '.join(blocked)}。",
            )
        if warnings:
            return self._check(
                "resource_content_quality",
                "资源内容质量检查",
                "warning",
                f"资源内容需要补强：{', '.join(warnings)}。",
            )
        return self._check(
            "resource_content_quality",
            "资源内容质量检查",
            "passed",
            "资源均包含与类型相符的可用正文、结构或题目。",
        )

    def _check_resource_type_match(self, context: dict[str, Any]) -> dict[str, Any]:
        mismatches: list[str] = []
        for resource in self._dict_items(context.get("resources")):
            label = self._resource_label(resource)
            resource_type = str(resource.get("type") or "").strip()
            content = str(resource.get("content") or "").strip()
            items = resource.get("items") if isinstance(resource.get("items"), list) else []

            if resource_type == "mindmap" and not self._looks_like_mindmap(content):
                mismatches.append(f"{label}（mindmap 内容形态不匹配）")
            elif resource_type == "quiz" and not any(
                isinstance(item, dict) and str(item.get("stem") or item.get("question") or "").strip()
                for item in items
            ):
                mismatches.append(f"{label}（quiz 缺少题目 items）")
            elif resource_type == "practice" and not self._looks_like_practice(content):
                mismatches.append(f"{label}（practice 缺少任务或步骤）")
            elif resource_type in {"reading", "lecture"} and items and len(self._normalize_text(content)) < 30:
                mismatches.append(f"{label}（正文资源呈现为题目/练习形态）")

        if mismatches:
            return self._check(
                "resource_type_match",
                "资源类型匹配检查",
                "warning",
                f"资源类型与内容形态可能不匹配：{', '.join(mismatches)}。",
            )
        return self._check(
            "resource_type_match",
            "资源类型匹配检查",
            "passed",
            "资源类型与内容形态匹配。",
        )

    def _check_provenance_trust(self, context: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        knowledge_source = str(context.get("knowledge_context", {}).get("source") or "unknown")
        if knowledge_source != "course_knowledge_base":
            warnings.append(f"knowledge_context.source={knowledge_source}")

        for resource in self._dict_items(context.get("resources")):
            label = self._resource_label(resource)
            source = str(resource.get("source") or "").strip()
            quality = str(resource.get("quality_status") or "").strip()
            if source not in self.trusted_resource_sources:
                warnings.append(f"{label} source={source or 'empty'}")
            if not quality:
                warnings.append(f"{label} 缺少 quality_status")
            elif source == "rule_based_fallback" and quality != "fallback_passed":
                warnings.append(f"{label} fallback 来源与 quality_status={quality} 不自洽")
            elif source == "llm_generated" and quality == "fallback_passed":
                warnings.append(f"{label} LLM 来源却标记为 fallback_passed")

        if warnings:
            return self._check(
                "provenance_trust",
                "来源可信度检查",
                "warning",
                f"来源或质量标记需要复核：{', '.join(warnings)}。",
            )
        return self._check(
            "provenance_trust",
            "来源可信度检查",
            "passed",
            "课程依据和资源来源均已如实标记。",
        )

    def _check_path_time_budget(self, context: dict[str, Any]) -> dict[str, Any]:
        estimated = self._positive_int(context.get("estimatedDays"))
        path = self._dict_items(context.get("learning_path"))
        inverted: list[str] = []
        ranges: list[tuple[int, int]] = []

        for stage in path:
            label = str(stage.get("stage_id") or stage.get("title") or "unknown")
            duration_range = self._duration_range(stage.get("duration"))
            if duration_range is None:
                continue
            start, end = duration_range
            if start > end:
                inverted.append(f"{label}（{stage.get('duration')}）")
            else:
                ranges.append((start, end))

        if context.get("estimatedDays") is not None and estimated is None:
            return self._check(
                "path_time_budget",
                "路径时间预算检查",
                "blocked",
                f"estimatedDays 必须大于 0，当前值为 {context.get('estimatedDays')}。",
            )

        warnings: list[str] = []
        if inverted:
            warnings.append(f"阶段时间区间反向：{', '.join(inverted)}")
        if estimated is None:
            warnings.append("缺少有效 estimatedDays")
        elif estimated > 365:
            warnings.append(f"estimatedDays={estimated} 明显偏大且未提供合理说明")

        if estimated and ranges:
            scheduled_days = {day for start, end in ranges for day in range(start, end + 1)}
            if scheduled_days and max(scheduled_days) > estimated:
                warnings.append(f"阶段安排延伸至第 {max(scheduled_days)} 天，超过 estimatedDays={estimated}")

        if warnings:
            return self._check(
                "path_time_budget",
                "路径时间预算检查",
                "warning",
                "；".join(warnings) + "。",
            )
        return self._check(
            "path_time_budget",
            "路径时间预算检查",
            "passed",
            f"estimatedDays={estimated}，阶段时间范围与总预算一致。",
        )

    def _check_content_safety(self, context: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            [
                str(context.get("diagnosis", {}).get("summary", "")),
                " ".join(str(stage.get("goal", "")) for stage in self._dict_items(context.get("learning_path"))),
                " ".join(
                    f"{item.get('title', '')} {item.get('description', '')} {item.get('content', '')}"
                    for item in self._dict_items(context.get("resources"))
                ),
            ]
        )
        hits = sorted(term for term in self.blocked_terms if term in text)
        if hits:
            return self._check(
                "content_safety",
                "内容安全检查",
                "blocked",
                f"发现不适合教育场景的内容：{', '.join(hits)}。",
            )
        return self._check(
            "content_safety",
            "内容安全检查",
            "passed",
            "未发现明显违规或不适合教育场景的内容。",
        )

    def _course_chapters(self, context: dict[str, Any]) -> list[dict[str, str]]:
        knowledge = context.get("knowledge_context", {})
        course_id = str(context.get("course_id") or knowledge.get("course_id") or "").strip()
        course = course_catalog.get_course(course_id) if course_id else None
        raw_chapters = course.get("chapters", []) if course else knowledge.get("retrieved_points", [])
        chapters = []
        for chapter in self._dict_items(raw_chapters):
            chapter_id = str(chapter.get("chapter_id") or "").strip()
            title = str(chapter.get("title") or chapter.get("name") or "").strip()
            if chapter_id or title:
                chapters.append({"chapter_id": chapter_id, "title": title})
        return chapters

    def _chapter_matches(self, related: str, chapters: list[dict[str, str]]) -> bool:
        parts = [
            part
            for part in re.split(r"[、,，;；/|]+", related)
            if part.strip() and not self._is_placeholder_chapter(part)
        ]
        # ResourceAgent may bind one catalog chapter together with a diagnosed
        # knowledge point. At least one grounded chapter keeps that combination valid.
        return any(self._chapter_part_matches(part, chapters) for part in parts)

    def _is_placeholder_chapter(self, value: str) -> bool:
        normalized = self._normalize_text(value)
        return any(
            marker in normalized
            for marker in ("当前薄弱点需要进一步诊断", "薄弱点待诊断", "待诊断", "unknown")
        )

    def _chapter_part_matches(self, part: str, chapters: list[dict[str, str]]) -> bool:
        normalized = self._normalize_text(part)
        for chapter in chapters:
            chapter_id = self._normalize_text(chapter.get("chapter_id"))
            title = self._normalize_text(chapter.get("title"))
            if title and (title in normalized or normalized in title):
                return True
            if chapter_id and re.search(rf"(^|\D)0*{re.escape(chapter_id.lstrip('0') or '0')}(\D|$)", part):
                return True
        return False

    def _looks_like_mindmap(self, content: str) -> bool:
        lowered = content.lower()
        return any(marker in lowered for marker in ("mindmap", "graph td", "graph lr", "flowchart"))

    def _looks_like_practice(self, content: str) -> bool:
        lowered = content.lower()
        markers = ("实操", "练习", "步骤", "任务", "代码", "伪代码", "实现", "运行", "step", "exercise", "task", "code")
        has_marker = any(marker in lowered for marker in markers)
        has_sequence = bool(re.search(r"(^|\n)\s*(?:\d+[.、)]|[-*])\s*\S+", content))
        return has_marker and (has_sequence or len(self._normalize_text(content)) >= 60)

    def _duration_range(self, value: Any) -> tuple[int, int] | None:
        text = str(value or "").strip()
        if not text:
            return None
        numbers = [int(item) for item in re.findall(r"\d+", text)]
        if len(numbers) >= 2:
            return numbers[0], numbers[1]
        if len(numbers) == 1 and ("第" in text or "day" in text.lower()):
            return numbers[0], numbers[0]
        return None

    def _positive_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _normalize_text(self, value: Any) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())

    def _resource_label(self, resource: dict[str, Any]) -> str:
        return str(resource.get("resource_id") or resource.get("title") or "unknown")

    def _dict_items(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _check(self, check_id: str, name: str, status: str, message: str) -> dict[str, str]:
        return {"check_id": check_id, "name": name, "status": status, "message": message}

    def _aggregate_status(self, checks: list[dict[str, str]]) -> str:
        statuses = {check["status"] for check in checks}
        if "blocked" in statuses:
            return "blocked"
        if "warning" in statuses:
            return "warning"
        return "passed"

    def _summary(self, checks: list[dict[str, str]]) -> str:
        blocked = [check["name"] for check in checks if check["status"] == "blocked"]
        warnings = [check["name"] for check in checks if check["status"] == "warning"]
        if blocked:
            return f"质量审核发现阻断项：{'、'.join(blocked)}；主流程结果已保留，请修正后再使用。"
        if warnings:
            return f"质量审核通过基础可用性检查，但建议复核：{'、'.join(warnings)}。"
        return "生成结果已通过画像、知识依据、章节归属、资源质量、来源和时间预算检查。"
