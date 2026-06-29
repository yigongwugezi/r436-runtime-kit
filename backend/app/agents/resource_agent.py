import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.services.course_catalog import course_catalog
from app.services.llm_client import LLMClientError


RESOURCE_TYPES = ["lecture", "mindmap", "quiz", "reading", "practice", "multimodal"]
SOURCE_LLM = "llm_generated"
SOURCE_FALLBACK = "rule_based_fallback"
SOURCE_TYPE_COURSE_KB = "course_knowledge_base"
SOURCE_TYPE_AGENT = "agent_generated"

QUALITY_STATUSES = {"passed", "warning", "fallback", "insufficient_context"}


class ResourceAgent(BaseAgent):
    agent_id = "resource_agent"
    agent_name = "学习资源生成智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        stages = self._stages(context)
        course = self._course_context(context)
        knowledge_points = self._knowledge_points(context, course, stages)
        profile = context.get("profile", {})

        if not stages or not knowledge_points:
            missing = []
            if not stages:
                missing.append("learning_path stages")
            if not knowledge_points:
                missing.append("course chapters or knowledge points")
            return {
                "resources": [],
                "limitations": [f"Resource generation needs {', '.join(missing)}."],
                "agent_step": self.agent_step(),
            }

        # RAG retrieval (best-effort, graceful fallback)
        rag_evidence = self._rag_retrieve(context, stages, knowledge_points, profile)

        resources = self._generate_with_llm(context, course, stages, knowledge_points, profile, rag_evidence)
        if not resources:
            fallback_reason = (
                "LLM client is not configured; deterministic rule resources were generated."
                if not self.llm_client
                else "LLM output was unavailable or invalid; deterministic rule resources were generated."
            )
            if course.get("_source_type") != SOURCE_TYPE_COURSE_KB:
                fallback_reason += " No verified course knowledge-base match was available."
            if any(stage.get("_inferred") for stage in stages):
                fallback_reason += " Learning stages were inferred from diagnosis because no explicit learning path was available."
            resources = self._build_rule_fallback(
                course,
                stages,
                knowledge_points,
                profile,
                fallback_reason,
                rag_evidence,
            )

        resources = self._scope_resource_ids(resources, str(context.get("session_id") or ""))
        return {"resources": resources, "agent_step": self.agent_step()}

    def _generate_with_llm(
        self,
        context: dict[str, Any],
        course: dict[str, Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        profile: dict[str, Any],
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.llm_client:
            return []

        rag_evidence = rag_evidence or []
        rag_context = ""
        if rag_evidence:
            lines = []
            for ev in rag_evidence[:10]:
                lines.append(
                    f"- [{ev.get('title','')}] {ev.get('snippet','')[:120]} "
                    f"(source={ev.get('source','')}, score={ev.get('score',0):.3f})"
                )
            rag_context = (
                "\n## RAG Knowledge Base Evidence\n"
                + "\n".join(lines)
                + "\n\nUse the above evidence to ground titles, descriptions, reasons, "
                "and source references. Do NOT invent external sources.\n"
            )

        payload = {
            "course_id": course.get("course_id") or context.get("course_id"),
            "course_name": course.get("course_name") or context.get("course_id"),
            "course_chapters": [
                {
                    "chapter_id": item.get("chapter_id"),
                    "title": item.get("title") or item.get("name"),
                    "difficulty": item.get("difficulty", "medium"),
                    "prerequisites": item.get("prerequisites", []),
                    "content_excerpt": str(item.get("content_excerpt") or item.get("content") or "")[:500],
                }
                for item in knowledge_points
            ],
            "learning_path_stages": [
                {
                    "stage_id": stage.get("stage_id"),
                    "title": stage.get("title"),
                    "duration": stage.get("duration"),
                    "goal": stage.get("goal"),
                    "tasks": stage.get("tasks", []),
                    "reason": stage.get("reason", ""),
                }
                for stage in stages
            ],
            "diagnosis_weak_points": context.get("diagnosis", {}).get("weak_knowledge_points", []),
            "profile": self._compact_profile(profile),
            "profile_facts": context.get("profile_facts", {}),
            "rag_evidence": rag_evidence[:10],
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 EduAgent 的资源生成智能体。你必须仅根据提供的课程知识库、学习路径阶段、诊断结果和学习者画像来生成个性化学习资源。"
                    + (rag_context if rag_context else "") +
                    "只输出 JSON，不要用 Markdown 代码块包裹。JSON 格式为 {\"resources\": [...]}。"
                    "至少生成五种资源，覆盖讲义(lecture)、思维导图(mindmap)、练习题(quiz)、拓展阅读(reading)、实操案例(case_study)，可选视频讲稿(video)或PPT大纲(ppt)。"
                    "每个资源必须包含 resource_id、type、title、description、content_format、content 或 items、related_stage_id、related_chapter、related_knowledge_points、quality_status、reason、evidence。"
                    "只使用输入中存在的阶段ID和课程章节，不要编造外部书籍、论文、链接或章节。"
                    "所有 title、description、content 内容必须使用中文撰写。"
                    "如使用 RAG evidence，只能基于输入中的片段生成 reason、evidence 和来源说明，不要伪造 provenance claims。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            raw = self.llm_client.chat(messages, temperature=0.2, max_tokens=2200)
            parsed = self._parse_json(raw)
        except (LLMClientError, json.JSONDecodeError, TypeError, ValueError):
            return []

        resources = parsed.get("resources") if isinstance(parsed, dict) else None
        if not isinstance(resources, list):
            return []
        return self._normalize_llm_resources(resources, stages, knowledge_points, course, rag_evidence)

    def _build_rule_fallback(
        self,
        course: dict[str, Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        profile: dict[str, Any],
        fallback_reason: str,
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate resources per learning path: stage-level + per-task.

        Architecture:
        1. For each stage -> generate stage-level overview resources (mindmap + reading)
           tagged with ``related_stage_id`` only (no ``task_id``).
        2. For each task/node within the stage -> generate task-specific resources
           (lecture + quiz + case_study) tagged with both ``related_stage_id``
           and ``task_id``.

        This enables both stage-level filtering (``?relatedStageId=stage_1``)
        and node-level filtering (``?taskId=stage_1_node_2``).
        """
        bindings = self._stage_bindings(stages, knowledge_points)
        resources: list[dict[str, Any]] = []
        extra_types = ["mindmap", "reading", "practice", "video"]

        for binding in bindings:
            stage_id = str(binding.get("stage_id", ""))
            tasks = binding.get("tasks", [])

            # Stage-level resources (no task_id, show for entire stage)
            resources.append(self._mindmap_for_task(course, binding, binding.get("title", ""), stage_id, ""))
            resources.append(self._reading_for_task(course, binding, binding.get("title", ""), stage_id, ""))

            # Per-task resources (with task_id, show only for that node)
            for ti, task in enumerate(tasks[:6]):
                task_id = f"{stage_id}_node_{ti + 1}"
                # Every task gets lecture + quiz as the base pair
                resources.append(self._lecture_for_task(course, binding, profile, task, task_id))
                resources.append(self._quiz_for_task(course, binding, profile, task, task_id))
                # Plus one additional type cycling through the extras
                extra = extra_types[ti % len(extra_types)]
                if extra == "mindmap":
                    resources.append(self._mindmap_for_task(course, binding, task, stage_id, task_id))
                elif extra == "reading":
                    resources.append(self._reading_for_task(course, binding, task, stage_id, task_id))
                elif extra == "practice":
                    resources.append(self._practice_for_task(course, binding, profile, task, task_id))
                elif extra == "video":
                    resources.append(self._video_script_for_task(course, binding, task, task_id))

        source_type = str(course.get("_source_type") or SOURCE_TYPE_AGENT)
        quality_status = "fallback" if source_type == SOURCE_TYPE_COURSE_KB else "insufficient_context"
        for resource in resources:
            resource.update(
                {
                    "source_type": source_type,
                    "generation_mode": "fallback",
                    "quality_status": quality_status,
                    "fallback_reason": fallback_reason,
                }
            )
            resource["evidence"] = self._resource_evidence(
                resource,
                generation="rule_based_fallback",
                fallback_reason=fallback_reason,
            )
            resource["rag_evidence"] = rag_evidence or []
        return resources

    def _normalize_llm_resources(
        self,
        resources: list[Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        course: dict[str, Any],
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Normalize LLM output and auto-fill ``task_id`` when missing.

        LLM may not output ``task_id``.  When missing, resources are
        distributed among each stage's tasks round-robin so that they
        can be filtered by node in the frontend.
        """
        stage_ids = {str(stage.get("stage_id") or f"stage_{index}") for index, stage in enumerate(stages, start=1)}
        fallback_bindings = self._stage_bindings(stages, knowledge_points)
        normalized: list[dict[str, Any]] = []
        seen_types: set[str] = set()
        seen_stage_ids: set[str] = set()

        for index, item in enumerate(resources[:8], start=1):
            if not isinstance(item, dict):
                continue
            resource_type = self._clean_type(item.get("type"))
            if resource_type not in RESOURCE_TYPES:
                continue
            default_binding = fallback_bindings[min(index - 1, len(fallback_bindings) - 1)]
            stage_id = str(item.get("related_stage_id") or default_binding["stage_id"])
            if stage_id not in stage_ids:
                stage_id = default_binding["stage_id"]
            binding = next(
                (candidate for candidate in fallback_bindings if candidate["stage_id"] == stage_id),
                default_binding,
            )
            knowledge = self._clean_list(item.get("related_knowledge_points")) or binding["knowledge_points"]
            content_format = str(item.get("content_format") or self._format_for_type(resource_type))
            content = str(item.get("content") or "").strip()
            quiz_items = item.get("items") if isinstance(item.get("items"), list) else None
            if not content and not quiz_items:
                continue

            # Auto-fill task_id if LLM didn't provide it
            task_id = str(item.get("task_id") or "")
            if not task_id:
                tasks = binding.get("tasks", [])
                if tasks:
                    task_idx = (index - 1) % len(tasks)
                    task_id = f"{stage_id}_node_{task_idx + 1}"

            resource_id = str(item.get("resource_id") or f"res_{resource_type}_{index:03d}")
            requested_chapter = str(item.get("related_chapter") or "").strip()
            chapter_is_grounded = self._chapter_is_grounded(requested_chapter, knowledge_points)
            related_chapter = requested_chapter if chapter_is_grounded else binding["chapter"]
            stage_is_inferred = any(
                str(stage.get("stage_id") or "") == stage_id and stage.get("_inferred")
                for stage in stages
            )
            used_inferred_binding = (
                not item.get("related_stage_id")
                or not chapter_is_grounded
                or stage_is_inferred
            )
            source_type = str(course.get("_source_type") or SOURCE_TYPE_AGENT)
            requested_quality = str(item.get("quality_status") or "passed")
            quality_status = requested_quality if requested_quality in QUALITY_STATUSES else "warning"
            if source_type != SOURCE_TYPE_COURSE_KB or used_inferred_binding:
                quality_status = "warning"
            generation_mode = "mixed" if used_inferred_binding else "llm"
            normalized_item = {
                    "id": resource_id,
                    "resource_id": resource_id,
                    "type": resource_type,
                    "title": str(item.get("title") or f"{binding['title']} resource").strip(),
                    "description": str(item.get("description") or "").strip(),
                    "content_format": content_format,
                    "content": content,
                    "items": quiz_items,
                    "related_stage_id": stage_id,
                    "related_chapter": related_chapter,
                    "related_knowledge_points": knowledge,
                    "knowledge_points": knowledge,
                    "source": SOURCE_LLM,
                    "source_type": source_type,
                    "generation_mode": generation_mode,
                    "quality_status": quality_status,
                    "task_id": task_id,
                    "reason": str(item.get("reason") or item.get("generation_reason") or binding["reason"]),
                    "generation_reason": str(item.get("generation_reason") or item.get("reason") or binding["reason"]),
                    "difficulty": str(item.get("difficulty") or binding["difficulty"]),
                    "fallback_reason": "",
                }
            normalized_item["evidence"] = self._resource_evidence(
                normalized_item,
                generation="llm_generated with rule binding" if used_inferred_binding else "llm_generated",
            )
            normalized_item["rag_evidence"] = rag_evidence or []
            normalized.append(normalized_item)
            seen_types.add(resource_type)
            seen_stage_ids.add(stage_id)

        has_stage_coverage = stage_ids.issubset(seen_stage_ids)
        return normalized if len(normalized) >= 5 and len(seen_types) >= 5 and has_stage_coverage else []

    def _lecture(self, course: dict[str, Any], binding: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        base = self._profile_value(profile, ["knowledge_base", "coding_ability", "programming_ability"], "基础未明确")
        goal = self._profile_value(profile, ["learning_goal", "interest_direction"], "完成当前阶段学习")
        names = "、".join(binding["knowledge_points"])
        content = (
            f"## {binding['title']} 课程讲义\n\n"
            f"- 课程：{course.get('course_name', course.get('course_id', '课程'))}\n"
            f"- 对应阶段：{binding['stage_id']}\n"
            f"- 关联章节：{binding['chapter']}\n"
            f"- 学生基础：{base}\n"
            f"- 学习目标：{goal}\n\n"
            f"### 核心知识点\n\n{names}\n\n"
            "### 学习顺序\n\n"
            "1. 先复述每个概念解决的问题和适用场景。\n"
            "2. 再结合课程章节中的例题或伪代码手推一遍。\n"
            "3. 最后用练习题检查边界条件、复杂度和常见误区。\n"
        )
        return self._resource(
            "res_lecture_001",
            "lecture",
            f"{binding['title']}讲义",
            "根据学习路径阶段、课程章节和学生画像生成的阶段讲义。",
            "markdown",
            binding,
            content=content,
        )

    def _mindmap(self, course: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
        root = self._safe_mermaid(str(course.get("course_name") or "学习资源"))
        lines = ["mindmap", f"  root(({root}))"]
        for binding in bindings[:6]:
            lines.append(f"    {self._safe_mermaid(binding['title'])}")
            for point in binding["knowledge_points"][:4]:
                lines.append(f"      {self._safe_mermaid(point)}")
        return self._resource(
            "res_mindmap_001",
            "mindmap",
            f"{course.get('course_name', '课程')}知识结构图",
            "把学习路径阶段和课程章节组织成 Mermaid 思维导图。",
            "mermaid",
            bindings[0],
            content="\n".join(lines),
            reason="用于帮助学生先建立章节之间的结构关系，再进入讲义和练习。",
        )

    def _quiz(self, course: dict[str, Any], bindings: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
        goal = self._profile_value(profile, ["learning_goal"], "查漏补缺")
        items = []
        for index, binding in enumerate(bindings[:5], start=1):
            point = binding["knowledge_points"][0]
            items.append(
                {
                    "question_id": f"q_{index:03d}",
                    "question_type": "short_answer" if index % 2 == 0 else "single_choice",
                    "stem": self._quiz_stem(str(course.get("course_id", "")), point),
                    "options": self._quiz_options(str(course.get("course_id", "")), point) if index % 2 else [],
                    "answer": self._quiz_answer(str(course.get("course_id", "")), point),
                    "explanation": f"本题服务于目标：{goal}；重点检查 {point} 是否能用于真实题目或任务。",
                    "difficulty": binding["difficulty"],
                    "knowledge_point": point,
                }
            )
        return self._resource(
            "res_quiz_001",
            "quiz",
            "阶段诊断练习题",
            "覆盖当前学习路径主要阶段的测验题。",
            "json",
            bindings[0],
            items=items,
            reason="用分阶段题目检查学生是否真正掌握课程核心知识点。",
        )

    def _reading(self, course: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
        lines = []
        for index, binding in enumerate(bindings[:6], start=1):
            lines.append(
                f"{index}. 建议阅读课程对应章节：{binding['chapter']}。阅读后整理 "
                f"{'、'.join(binding['knowledge_points'][:3])} 的定义、例题和易错点。"
            )
        content = "## 拓展阅读路径\n\n" + "\n".join(lines) + "\n\n不编造外部书籍、论文或链接；没有明确来源时只引用课程对应章节。"
        return self._resource(
            "res_reading_001",
            "reading",
            "课程章节拓展阅读",
            "基于课程知识库章节生成的阅读顺序。",
            "markdown",
            bindings[min(1, len(bindings) - 1)],
            content=content,
            reason="把课程章节转成可执行的阅读和复盘顺序。",
        )

    def _practice(self, course: dict[str, Any], binding: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        point = binding["knowledge_points"][0]
        content = self._practice_content(str(course.get("course_id", "")), point, profile)
        return self._resource(
            "res_practice_001",
            "practice",
            f"{point}实操案例",
            "结合课程主题生成可手推或可运行的实操任务。",
            "markdown",
            binding,
            content=content,
            reason="用小任务把抽象概念落到代码、伪代码或手算过程。",
            difficulty=binding["difficulty"],
        )

    def _video_script(self, course: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
        point = binding["knowledge_points"][0]
        content = (
            f"## 90 秒视频脚本：{point}\n\n"
            f"1. 画面：显示课程 {course.get('course_name', '')} 与阶段 {binding['stage_id']}。\n"
            f"2. 旁白：先说明 {point} 要解决的核心问题。\n"
            "3. 画面：用一个最小例子展示输入、处理过程和输出。\n"
            "4. 旁白：点出常见误区和本阶段练习任务。\n"
            "5. 画面：收束到讲义、练习题和实操案例。"
        )
        return self._resource(
            "res_multimodal_001",
            "multimodal",
            f"视频脚本：{point}",
            "可交给多模态工具继续制作的视频讲解脚本。",
            "markdown",
            binding,
            content=content,
            reason="满足偏好视频/图解的学生，也为后续多模态生成预留结构。",
        )

    # Per-task resource generators
    # Each generates a single resource for a specific task within a stage.

    def _lecture_for_task(self, course, binding, profile, task, task_id):
        base = self._profile_value(profile, ["knowledge_base"], "基础未明确")
        content = (
            f"## {task} 课程讲义\n\n"
            f"- 课程：{course.get('course_name', '')}\n"
            f"- 对应阶段：{binding['stage_id']}\n"
            f"- 学习任务：{task}\n"
            f"- 学生基础：{base}\n\n"
            f"### 核心内容\n\n{task}的核心知识点和概念讲解。\n\n"
            f"### 学习步骤\n\n"
            f"1. 先理解每个概念解决的问题和适用场景。\n"
            f"2. 再结合课程章节中的示例或伪代码手推一遍。\n"
            f"3. 最后用练习题检查边界条件、复杂度和常见误区。"
        )
        return self._resource(
            f"res_lecture_{task_id}", "lecture",
            f"{task}讲义",
            f"针对学习任务「{task}」的个性化讲义。",
            "markdown", binding,
            content=content,
            reason=f"针对任务「{task}」的阅读和练习材料",
            task_id=task_id,
        )

    def _mindmap_for_task(self, course, binding, task, stage_id, task_id=""):
        label = task or stage_id
        res_id = f"res_mindmap_{task_id}" if task_id else f"res_mindmap_{stage_id}"
        content = f"mindmap\n  root(({self._safe_mermaid(label)}))\n    核心概念\n    关键算法\n    应用场景\n    常见误区"
        return self._resource(
            res_id, "mindmap",
            f"{label}知识图谱",
            f"学习任务「{label}」的知识结构图。",
            "mermaid", binding,
            content=content,
            reason=f"帮助学生建立{label}的结构关系",
            task_id=task_id,
        )

    def _quiz_for_task(self, course, binding, profile, task, task_id):
        goal = self._profile_value(profile, ["learning_goal"], "查漏补缺")
        items = [{
            "question_id": f"q_{task_id}_001",
            "question_type": "short_answer",
            "stem": f"围绕 {task}，说明它在当前学习目标中的作用。",
            "options": [],
            "answer": f"应从 {task} 的任务目标、输入输出、方法流程和评价方式四方面作答。",
            "explanation": f"本题服务于目标：{goal}；重点检查 {task} 是否能用于真实题目或任务。",
            "difficulty": binding["difficulty"],
            "knowledge_point": task,
        }]
        return self._resource(
            f"res_quiz_{task_id}", "quiz",
            f"{task}练习题",
            f"覆盖学习任务「{task}」的测验题。",
            "json", binding,
            items=items,
            reason=f"检验{task}的掌握情况",
            task_id=task_id,
        )

    def _reading_for_task(self, course, binding, task, stage_id, task_id=""):
        label = task or stage_id
        res_id = f"res_reading_{task_id}" if task_id else f"res_reading_{stage_id}"
        content = (
            f"## {label} 拓展阅读\n\n"
            f"### 阅读重点\n\n"
            f"1. {label}的核心概念与定义\n"
            f"2. 经典算法与实现思路\n"
            f"3. 实际应用案例分析\n"
            f"4. 前沿进展与扩展方向\n\n"
            f"### 阅读建议\n\n"
            f"先阅读讲义掌握基础概念，再通过拓展阅读加深理解。"
        )
        return self._resource(
            res_id, "reading",
            f"{label}拓展阅读",
            f"与学习任务「{label}」相关的拓展阅读材料。",
            "markdown", binding,
            content=content,
            reason=f"拓展{label}的深度和广度",
            task_id=task_id,
        )

    def _practice_for_task(self, course, binding, profile, task, task_id):
        base = self._profile_value(profile, ["coding_ability"], "基础未明确")
        content = (
            f"## 实操任务：拆解 {task} 的 AI 流程\n\n"
            f"1. 写出任务输入、模型/算法、输出和评价指标。\n"
            f"2. 用 5 条样本数据模拟一次预测、搜索或推理流程。\n"
            f"3. 说明可能的数据偏差、过拟合或评价误差。\n\n"
            f"学生编程基础：{base}"
        )
        return self._resource(
            f"res_practice_{task_id}", "practice",
            f"{task}实操案例",
            f"结合学习任务「{task}」生成可手推或可运行的实操任务。",
            "markdown", binding,
            content=content,
            reason=f"通过实践加深对{task}的理解",
            task_id=task_id,
        )

    def _video_script_for_task(self, course, binding, task, task_id):
        content = (
            f"## 90 秒视频脚本：{task}\n\n"
            f"1. 画面：显示课程 {course.get('course_name', '')} 与阶段 {binding['stage_id']}。\n"
            f"2. 旁白：先说明 {task} 要解决的核心问题。\n"
            f"3. 画面：用一个最小例子展示输入、处理过程和输出。\n"
            f"4. 旁白：点出常见误区和本阶段练习任务。\n"
            f"5. 画面：收束到讲义、练习题和实操案例。"
        )
        return self._resource(
            f"res_video_{task_id}", "multimodal",
            f"视频脚本：{task}",
            f"针对学习任务「{task}」的视频讲解脚本。",
            "markdown", binding,
            content=content,
            reason=f"满足偏好视频/图解的学生",
            task_id=task_id,
        )

    def _resource(
        self,
        resource_id: str,
        resource_type: str,
        title: str,
        description: str,
        content_format: str,
        binding: dict[str, Any],
        *,
        content: str = "",
        items: list[dict[str, Any]] | None = None,
        reason: str | None = None,
        difficulty: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        resource = {
            "id": resource_id,
            "resource_id": resource_id,
            "type": resource_type,
            "title": title,
            "description": description,
            "content_format": content_format,
            "content": content,
            "items": items,
            "related_stage_id": binding["stage_id"],
            "related_chapter": binding["chapter"],
            "related_knowledge_points": binding["knowledge_points"],
            "knowledge_points": binding["knowledge_points"],
            "source": SOURCE_FALLBACK,
            "source_type": SOURCE_TYPE_AGENT,
            "generation_mode": "fallback",
            "quality_status": "fallback",
            "reason": reason or binding["reason"],
            "generation_reason": reason or binding["reason"],
            "evidence": [],
            "rag_evidence": [],
            "fallback_reason": "",
            "difficulty": difficulty or binding["difficulty"],
            "task_id": task_id or "",
        }
        return resource

    def _course_context(self, context: dict[str, Any]) -> dict[str, Any]:
        course_id = str(context.get("course_id") or context.get("knowledge_context", {}).get("course_id") or "")
        catalog_course = course_catalog.get_course(course_id) if course_id else None
        knowledge = context.get("knowledge_context", {})
        if catalog_course:
            return {**catalog_course, "_source_type": SOURCE_TYPE_COURSE_KB}
        knowledge_source = str(knowledge.get("source") or "")
        return {
            "course_id": knowledge.get("course_id", course_id),
            "course_name": knowledge.get("course_name", course_id or "课程"),
            "chapters": knowledge.get("retrieved_points", []),
            "_source_type": (
                SOURCE_TYPE_COURSE_KB
                if knowledge_source == SOURCE_TYPE_COURSE_KB and knowledge.get("retrieved_points")
                else SOURCE_TYPE_AGENT
            ),
        }

    def _rag_retrieve(
        self,
        context: dict[str, Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        profile: dict[str, Any],
        max_queries: int = 5,
    ) -> list[dict[str, Any]]:
        """Attempt RAG retrieval for resource enrichment. Graceful fallback on any failure.

        Returns a list of evidence dicts with keys: query, title, snippet, source, score.
        Returns an empty list when the RAG index is unavailable, retrieval fails, or
        results are empty -- callers must handle the empty case transparently.
        """
        # Build candidate queries from context
        queries: list[str] = []

        # Diagnosis weak points
        diagnosis = context.get("diagnosis", {})
        for wp in diagnosis.get("weak_knowledge_points", []) or []:
            if isinstance(wp, dict):
                name = str(wp.get("name") or wp.get("title") or "").strip()
                if name and len(name) >= 2:
                    queries.append(name)
            elif isinstance(wp, str) and wp.strip():
                queries.append(wp.strip())

        # Stage titles / goals / knowledge_points
        for stage in stages[:3]:
            title = str(stage.get("title") or "").strip()
            goal = str(stage.get("goal") or "").strip()
            if title and len(title) >= 2:
                queries.append(title)
            if goal and len(goal) >= 2 and goal not in queries:
                queries.append(goal)

        # Knowledge point names
        for kp in knowledge_points[:5]:
            name = str(kp.get("name") or kp.get("title") or "").strip()
            if name and len(name) >= 2 and name not in queries:
                queries.append(name)

        # Profile target course / learning goal
        target = str(
            profile.get("interest_direction", {}).get("value", "")
            or context.get("course_id", "")
        ).strip()
        goal_val = str(
            profile.get("learning_goal", {}).get("value", "")
            or profile.get("learning_goal", "")
        ).strip()
        if target and len(target) >= 2:
            queries.append(target)
        if goal_val and len(goal_val) >= 2 and goal_val not in queries:
            queries.append(goal_val)

        # Deduplicate and cap
        seen: set[str] = set()
        unique_queries: list[str] = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        queries = unique_queries[:max_queries]

        if not queries:
            return []

        # Try loading the RAG query engine
        try:
            from app.rag.query_engine import rag_query_engine
            engine = rag_query_engine
            if not engine.is_ready():
                return []
        except Exception:
            return []

        # Search and collect results
        evidence: list[dict[str, Any]] = []
        for query in queries:
            try:
                resp = engine.search(query, top_k=3)
                for r in resp.results[:3]:
                    evidence.append({
                        "query": query,
                        "title": r.title or "",
                        "snippet": (r.text or "")[:200],
                        "source": r.source_file or "",
                        "score": round(r.score or 0.0, 4),
                    })
            except Exception:
                continue

        return evidence

    def _knowledge_points(
        self,
        context: dict[str, Any],
        course: dict[str, Any],
        stages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        course_id = str(course.get("course_id") or context.get("course_id") or "")
        for index, chapter in enumerate(course.get("chapters", []), start=1):
            chapter_id = str(chapter.get("chapter_id", index)).zfill(2)
            detail = course_catalog.load_chapter(course_id, chapter_id) or chapter
            points.append(
                {
                    "chapter_id": chapter_id,
                    "title": str(chapter.get("title") or chapter.get("name") or f"Chapter {index}"),
                    "name": str(chapter.get("title") or chapter.get("name") or f"Chapter {index}"),
                    "difficulty": chapter.get("difficulty", "medium"),
                    "prerequisites": chapter.get("prerequisites", []),
                    "content_excerpt": str(detail.get("content", ""))[:600],
                    "_origin": str(course.get("_source_type") or SOURCE_TYPE_AGENT),
                }
            )

        retrieved = context.get("knowledge_context", {}).get("retrieved_points", [])
        for item in retrieved:
            if isinstance(item, dict):
                self._append_unique_point(
                    points,
                    item,
                    str(context.get("knowledge_context", {}).get("source") or SOURCE_TYPE_AGENT),
                )

        diagnosis = context.get("diagnosis", {})
        weak_points = list(diagnosis.get("weak_knowledge_points", []) or [])
        weak_points.extend(diagnosis.get("weak_topics", []) or [])
        for item in weak_points:
            if isinstance(item, dict):
                self._append_unique_point(points, item, "diagnosis")

        if points:
            return points
        return [
            {
                "chapter_id": str(index).zfill(2),
                "title": str(stage.get("title") or f"Stage {index}"),
                "name": str(stage.get("title") or f"Stage {index}"),
                "difficulty": "medium",
                "prerequisites": [],
                "_origin": "learning_path_inference",
            }
            for index, stage in enumerate(stages, start=1)
        ]

    def _append_unique_point(
        self,
        points: list[dict[str, Any]],
        item: dict[str, Any],
        origin: str = SOURCE_TYPE_AGENT,
    ) -> None:
        name = str(item.get("title") or item.get("name") or item.get("topic") or "").strip()
        if not name:
            return
        if any(str(point.get("name") or point.get("title")) == name for point in points):
            return
        points.append(
            {
                "chapter_id": str(item.get("chapter_id") or len(points) + 1).zfill(2),
                "title": name,
                "name": name,
                "difficulty": item.get("difficulty", item.get("priority", "medium")),
                "prerequisites": item.get("prerequisites", []),
                "content_excerpt": item.get("content_excerpt", ""),
                "_origin": origin,
            }
        )

    def _stage_bindings(self, stages: list[dict[str, Any]], knowledge_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        stage_count = max(1, len(stages))
        for index, stage in enumerate(stages, start=1):
            matched = self._matching_stage_points(stage, knowledge_points)
            if matched:
                group = matched
                binding_mode = "context_match"
            else:
                start = round((index - 1) * len(knowledge_points) / stage_count)
                end = round(index * len(knowledge_points) / stage_count)
                group = knowledge_points[start:end] or [knowledge_points[min(index - 1, len(knowledge_points) - 1)]]
                binding_mode = "path_order_inference"
            names = [str(item.get("name") or item.get("title")) for item in group if item.get("name") or item.get("title")]
            chapter = "、".join(
                f"{item.get('chapter_id', '')} {item.get('title') or item.get('name')}".strip()
                for item in group[:3]
            )
            result.append(
                {
                    "stage_id": str(stage.get("stage_id") or f"stage_{index}"),
                    "title": str(stage.get("title") or f"阶段 {index}"),
                    "chapter": chapter or names[0],
                    "knowledge_points": names[:5] or [str(stage.get("title") or f"阶段 {index}")],
                    "difficulty": self._difficulty(group),
                    "reason": str(stage.get("reason") or stage.get("goal") or "根据学习路径阶段和课程章节生成。"),
                    "tasks": stage.get("tasks", []),
                    "binding_mode": binding_mode,
                }
            )
        return result

    def _matching_stage_points(
        self,
        stage: dict[str, Any],
        knowledge_points: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        explicit_values = [
            stage.get("chapter_id"),
            stage.get("related_chapter"),
            *self._clean_list(stage.get("knowledge_points")),
            *self._clean_list(stage.get("related_knowledge_points")),
        ]
        stage_text = " ".join(
            str(value)
            for value in [stage.get("title"), stage.get("goal"), *(stage.get("tasks") or []), *explicit_values]
            if value
        )
        normalized_stage = self._normalize_binding_text(stage_text)
        if not normalized_stage:
            return []
        matches = []
        for point in knowledge_points:
            candidates = [point.get("chapter_id"), point.get("title"), point.get("name")]
            if any(
                normalized
                and (normalized in normalized_stage or normalized_stage in normalized)
                for normalized in (self._normalize_binding_text(value) for value in candidates)
            ):
                matches.append(point)
        return matches[:3]

    def _normalize_binding_text(self, value: Any) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())

    def _chapter_is_grounded(
        self,
        related_chapter: str,
        knowledge_points: list[dict[str, Any]],
    ) -> bool:
        normalized = self._normalize_binding_text(related_chapter)
        if not normalized:
            return False
        for point in knowledge_points:
            chapter_id = self._normalize_binding_text(point.get("chapter_id"))
            title = self._normalize_binding_text(point.get("title") or point.get("name"))
            if title and (title in normalized or normalized in title):
                return True
            if chapter_id and re.search(
                rf"(^|\D)0*{re.escape(chapter_id.lstrip('0') or '0')}(\D|$)",
                related_chapter,
            ):
                return True
        return False

    def _stages(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        stages = [stage for stage in context.get("learning_path", []) if isinstance(stage, dict)]
        if stages:
            return stages
        diagnosis = context.get("diagnosis", {})
        points = list(diagnosis.get("weak_knowledge_points", []) or [])
        points.extend(diagnosis.get("weak_topics", []) or [])
        return [
            {
                "stage_id": f"stage_{index}",
                "title": str(point.get("name") or point.get("topic") or f"阶段 {index}"),
                "goal": "补齐诊断出的薄弱知识点。",
                "tasks": [str(point.get("name") or point.get("topic") or f"知识点 {index}")],
                "_inferred": True,
            }
            for index, point in enumerate(points[:3], start=1)
            if isinstance(point, dict)
        ]

    def _scope_resource_ids(self, resources: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        if not session_id:
            return resources
        for item in resources:
            resource_id = str(item.get("resource_id", ""))
            if resource_id and not resource_id.startswith(f"{session_id}_"):
                resource_id = f"{session_id}_{resource_id}"
                item["resource_id"] = resource_id
            item["id"] = resource_id
        return resources

    def _resource_evidence(
        self,
        resource: dict[str, Any],
        *,
        generation: str,
        fallback_reason: str = "",
    ) -> list[str]:
        evidence: list[str] = [
            f"Learning stage: {resource.get('related_stage_id') or 'unresolved'}",
            f"Course chapter: {resource.get('related_chapter') or 'unresolved'}",
            f"Generation: {generation}",
        ]
        points = resource.get("related_knowledge_points") or resource.get("knowledge_points") or []
        if points:
            evidence.append(f"Knowledge points: {', '.join(str(point) for point in points[:5])}")
        reason = str(resource.get("reason") or "").strip()
        if reason:
            evidence.append(f"Recommendation reason: {reason}")
        if fallback_reason:
            evidence.append(f"Fallback: {fallback_reason}")
        return evidence

    def _parse_json(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end >= start:
            stripped = stripped[start : end + 1]
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("Resource LLM output must be a JSON object.")
        return parsed

    def _compact_profile(self, profile: dict[str, Any]) -> dict[str, str]:
        compact = {}
        for key, item in profile.items():
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
                if value:
                    compact[key] = value
            elif item:
                compact[key] = str(item)
        return compact

    def _profile_value(self, profile: dict[str, Any], keys: list[str], default: str) -> str:
        for key in keys:
            item = profile.get(key)
            if isinstance(item, dict) and str(item.get("value", "")).strip():
                return str(item.get("value")).strip()
            if isinstance(item, str) and item.strip():
                return item.strip()
        return default

    def _clean_type(self, value: Any) -> str:
        aliases = {"video_script": "multimodal", "video": "multimodal", "case_study": "practice"}
        raw = str(value or "").strip()
        return aliases.get(raw, raw)

    def _format_for_type(self, resource_type: str) -> str:
        if resource_type == "mindmap":
            return "mermaid"
        if resource_type == "quiz":
            return "json"
        return "markdown"

    def _clean_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:8]

    def _difficulty(self, points: list[dict[str, Any]]) -> str:
        text = " ".join(str(point.get("difficulty", "")) + " " + str(point.get("priority", "")) for point in points)
        if "hard" in text or "high" in text:
            return "hard"
        if "medium" in text:
            return "medium"
        return "easy"

    def _quiz_stem(self, course_id: str, point: str) -> str:
        if course_id == "data_structures":
            return f"围绕 {point}，说明它的基本操作、适用场景，并分析一次典型操作的时间复杂度。"
        if course_id == "ai_intro":
            return f"围绕 {point}，说明它在人工智能系统中的作用，并给出一个典型应用场景。"
        return f"围绕 {point}，说明核心概念、适用场景和一个常见误区。"

    def _quiz_options(self, course_id: str, point: str) -> list[str]:
        if course_id == "data_structures":
            return ["定义与操作", "复杂度分析", "边界条件", "以上都需要"]
        if course_id == "ai_intro":
            return ["问题建模", "训练或搜索过程", "评价指标", "以上都需要"]
        return ["概念理解", "应用场景", "常见误区", "以上都需要"]

    def _quiz_answer(self, course_id: str, point: str) -> str:
        if course_id == "data_structures":
            return f"应从 {point} 的结构特征、操作步骤、边界条件和复杂度四方面作答。"
        if course_id == "ai_intro":
            return f"应从 {point} 的任务目标、输入输出、方法流程和评价方式四方面作答。"
        return f"应结合 {point} 的定义、应用和限制进行回答。"

    def _practice_content(self, course_id: str, point: str, profile: dict[str, Any]) -> str:
        coding = self._profile_value(profile, ["coding_ability", "programming_ability"], "基础水平")
        if course_id == "data_structures":
            return (
                f"## 实操任务：实现并验证 {point}\n\n"
                f"编程能力：{coding}\n\n"
                "### 要求\n\n"
                "1. 写出核心结构或操作的伪代码。\n"
                "2. 准备空输入、单元素、重复元素和普通样例。\n"
                "3. 记录每步操作后的状态，并估算时间复杂度。\n\n"
                "```python\n"
                "def run_case(values):\n"
                "    trace = []\n"
                "    for value in values:\n"
                "        trace.append((value, list(values)))\n"
                "    return trace\n\n"
                "print(run_case([3, 1, 2]))\n"
                "```\n"
            )
        if course_id == "ai_intro":
            return (
                f"## 实操任务：拆解 {point} 的 AI 流程\n\n"
                "1. 写出任务输入、模型/算法、输出和评价指标。\n"
                "2. 用 5 条样例数据模拟一次预测、搜索或推理流程。\n"
                "3. 说明可能的数据偏差、过拟合或评价误差。\n"
            )
        return f"## 实操任务：{point}\n\n用一个最小样例写出输入、处理过程、输出和检查标准。"

    def _safe_mermaid(self, text: str) -> str:
        cleaned = re.sub(r"[\r\n\t]+", " ", text).strip()
        return cleaned.replace("(", "（").replace(")", "）").replace(":", "：")[:60] or "resource"
