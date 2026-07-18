"""
学习资源生成智能体 — LLM 优先，规则完整保留做兜底。
"""

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.services.course_catalog import course_catalog
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)

RESOURCE_TYPES = ["lecture", "mindmap", "quiz", "reading", "practice", "multimodal"]
SOURCE_LLM = "llm_generated"
SOURCE_FALLBACK = "rule_based_fallback"
SOURCE_TYPE_COURSE_KB = "course_knowledge_base"
SOURCE_TYPE_AGENT = "agent_generated"
QUALITY_STATUSES = {"passed", "warning", "fallback", "insufficient_context"}


@register_agent
class ResourceAgent(BaseAgent):
    agent_id = "resource_agent"
    agent_name = "学习资源生成智能体"

    # 保存分批生成的中间结果，超时时 get_fallback 可返回。
    # 注意：设为 None 避免 Python 类级别可变默认值的陷阱；
    # run() 在每次请求时初始化为新列表。
    _partial_resources: list[dict] | None = None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """主入口 — DeepTutor first, LLM fallback, rule last resort."""
        stages = self._stages(context)
        course = self._course_context(context)
        knowledge_points = self._knowledge_points(context, course, stages)
        profile = context.get("profile", {})

        course_name = (course.get("course_name") or
                       context.get("profile_facts", {}).get("target_course") or
                       context.get("course_id", "目标课程"))

        
        course_name = str(course_name).strip()

        # ── 检测审核反馈，进入修正模式 ──
        # 当 ReviewAgent 标记了问题，ResourceAgent 需针对性修复而非从头生成
        review_feedback = self._build_review_feedback(context)
        if review_feedback:
            context["_review_feedback"] = review_feedback

        # ── 修正模式快速路径：审核反馈指出缺少特定类型 → 只补类型，不重跑 LLM ──
        missing_types = self._missing_types_from_feedback(review_feedback)
        if missing_types:
            existing = context.get("resources", []) or []
            # 用规则生成缺失的类型
            for stage in stages:
                stage_id = str(stage.get("stage_id", ""))
                for mt in missing_types:
                    if mt == "practice":
                        r = self._practice_for_task(course, self._binding_for_stage(stage, knowledge_points), profile, stage.get("title", ""), stage_id)
                        if r:
                            existing.append(r)
                    elif mt == "mindmap":
                        r = self._mindmap_for_stage(course, stage, knowledge_points)
                        if r:
                            existing.append(r)
            if existing:
                logger.info("Retry fast path: generated %d missing-type resources via rules",
                            len([r for r in existing if r.get("type", "") in missing_types]))
                return {"resources": existing, "agent_step": self.agent_step()}

        # ── DeepTutor: lecture + mindmap + reading ──
        dt_resources = []
        try:
            from app.services.deeptutor_client import deeptutor_call, generate_mindmap, generate_research
            import uuid as _uuid

            # Lecture via DeepTutor
            lecture_prompt = f"为「{course_name}」生成一份图文并茂的完整讲义。Markdown格式，含课程概述、学习目标、核心知识体系、Mermaid图表、课后思考题。1500字以上。"
            lecture = deeptutor_call("chat", lecture_prompt)
            if lecture and len(lecture) > 300:
                has_mermaid = "mermaid" in lecture.lower()
                dt_resources.append({"resource_id": _uuid.uuid4().hex[:12], "type": "lecture",
                    "title": f"{course_name} - 完整讲义", "content": lecture,
                    "related_stage_id": stages[0].get("stage_id", "") if stages else "",
                    "source": "deeptutor", "format": "markdown", "difficulty": "medium", "quality_status": "passed"})

            mm = generate_mindmap(course_name)
            if mm and len(mm) > 50:
                mm_clean = '\n'.join(l.strip() for l in mm.strip().split('\n'))
                dt_resources.append({"resource_id": _uuid.uuid4().hex[:12], "type": "mindmap",
                    "title": f"{course_name} - 思维导图", "content": mm_clean, "content_format": "mermaid",
                    "related_stage_id": stages[0].get("stage_id", "") if stages else "",
                    "source": "deeptutor", "format": "mermaid", "difficulty": "medium", "quality_status": "passed"})

            rm = generate_research(course_name)
            if rm and len(rm) > 50:
                dt_resources.append({"resource_id": _uuid.uuid4().hex[:12], "type": "reading",
                    "title": f"{course_name} - 拓展阅读", "content": rm,
                    "related_stage_id": stages[0].get("stage_id", "") if stages else "",
                    "source": "deeptutor", "format": "markdown", "difficulty": "medium", "quality_status": "passed"})
        except Exception as e:
            logger.debug("DeepTutor resource skip: %s", e)

        # DeepTutor 结果作为增强补充，不替代 LLM 完整生成
        # 继续走 LLM 路径以生成完整的 5-6 类资源

        # No stages/knowledge_points → try LLM minimal lecture
        if not stages or not knowledge_points:
            try:
                if self.llm_client:
                    lecture = self._generate_single_lecture(course_name, context)
                    if lecture:
                        resources = [lecture]
                        if dt_resources:
                            resources = dt_resources + resources
                        return {"resources": resources, "agent_step": self.agent_step()}
            except Exception:
                pass
            if dt_resources:
                return {"resources": dt_resources, "agent_step": self.agent_step()}
            return {"resources": [], "agent_step": self.agent_step()}

        # RAG 检索
        rag_evidence = self._rag_retrieve(context, stages, knowledge_points, profile)

        # ── 分批生成：每个阶段独立调用，不受 token 限制 ──
        self._partial_resources = []
        all_resources = []
        batch_size = 2  # 每批 1-2 个阶段
        llm_available = bool(self.llm_client)

        for batch_start in range(0, len(stages), batch_size):
            batch_stages = stages[batch_start:batch_start + batch_size]
            batch_kps = [kp for kp in knowledge_points
                         if any(kp.get("chapter_id") == s.get("stage_id") or
                                str(kp.get("name", "")) in str(s.get("title", ""))
                                for s in batch_stages)] or knowledge_points[
                                    batch_start:batch_start + batch_size * 2]

            if llm_available:
                try:
                    batch_resources = self._generate_with_llm(
                        context, course, batch_stages, batch_kps, profile, rag_evidence,
                        batch_label=f"{batch_start // batch_size + 1}/{(len(stages) + batch_size - 1) // batch_size}"
                    )
                    if batch_resources:
                        all_resources.extend(batch_resources)
                        self._partial_resources = list(all_resources)
                        continue
                except Exception as e:
                    logger.warning("Batch %d failed: %s", batch_start, e)

            # 规则兜底（按 task 数量生成，不固定每阶段 2 个）
            for stage in batch_stages:
                try:
                    resources = self._build_rule_fallback_for_stage(course, stage, batch_kps, profile)
                    all_resources.extend(resources)
                except Exception:
                    pass

        # 确保所有资源 ID 全局唯一（UUID 根除冲突）
        import uuid as _uuid
        for _i, _r in enumerate(all_resources):
            if isinstance(_r, dict):
                _r["resource_id"] = _uuid.uuid4().hex[:12]
        all_resources = self._scope_resource_ids(all_resources, str(context.get("session_id") or ""))
        # ── 合并 DeepTutor 结果作为增强补充 ──
        if dt_resources:
            all_resources = dt_resources + all_resources

        # ── 修正模式：保留原有通过审核的资源，用新资源覆盖有问题的 ──
        # 以 (type, related_stage_id) 为 key，有新的就用新的，没新的就保留旧的
        if context.get("_review_feedback"):
            existing = context.get("resources") or []
            if existing:
                new_by_key = {
                    (r.get("type", ""), r.get("related_stage_id", "")): r
                    for r in all_resources if isinstance(r, dict)
                }
                seen_keys: set[tuple[str, str]] = set()
                merged: list[dict] = []
                for r in existing:
                    if not isinstance(r, dict):
                        continue
                    key = (r.get("type", ""), r.get("related_stage_id", ""))
                    if key in new_by_key:
                        merged.append(new_by_key[key])
                        seen_keys.add(key)
                    else:
                        merged.append(r)
                for key, r in new_by_key.items():
                    if key not in seen_keys:
                        merged.append(r)
                all_resources = merged

        # ── 多模态资源后处理 ──
        # 1. 保证所有 multimodal 资源都有结构化描述（文字脚本/大纲），不依赖API
        # 2. API 有效时尝试生成实际内容，失败也不影响已有脚本
        for i, r in enumerate(all_resources):
            if not isinstance(r, dict):
                continue
            rtype = str(r.get("type", "")).strip()
            if rtype not in ("multimodal", "video"):
                continue

            # 确保有 content 字段（文字脚本/大纲）
            if not r.get("content"):
                r["content"] = r.get("description", "") or f"## {r.get('title','')}\n\n多模态学习资源脚本。"
            r["format"] = r.get("format", "markdown")
            r["multimodal_status"] = "script_only"

            # 尝试通过 MultimodalAgent 生成实际内容（图片/视频）
            try:
                from app.agents.multimodal_agent import MultimodalAgent, default_registry
                # 检查是否有可用的多模态工具（需要 API 密钥）
                task_type = "video_generation" if rtype == "video" else "image_generation"
                _, tool = default_registry.select_tool(task_type)
                if tool:
                    logger.info("MultimodalAgent tool available for %s, attempting generation", r.get("resource_id", ""))
                    mm_ctx = {
                        "user_message": str(r.get("content", ""))[:500],
                        "task_type": task_type,
                        "title": r.get("title", ""),
                    }
                    mm_result = MultimodalAgent(default_registry).run(mm_ctx)
                    if mm_result.get("status") == "completed":
                        content_url = mm_result.get("content_url") or mm_result.get("result", {}).get("url")
                        if content_url:
                            r["content_url"] = content_url
                            r["format"] = "video" if rtype == "video" else "image"
                            r["multimodal_status"] = "generated"
                            logger.info("MultimodalAgent generated content for %s: %s", r.get("resource_id", ""), content_url)
                        else:
                            r["multimodal_status"] = "generation_no_url"
                            logger.warning("MultimodalAgent completed but no URL for %s", r.get("resource_id", ""))
                    else:
                        r["multimodal_status"] = "generation_failed"
                        logger.warning("MultimodalAgent failed for %s: %s", r.get("resource_id", ""), mm_result.get("status", "unknown"))
                else:
                    logger.info("No multimodal tool available for %s, keeping script-only version", r.get("resource_id", ""))
            except Exception as mm_err:
                logger.warning("MultimodalAgent post-process error for %s: %s", r.get("resource_id", ""), mm_err)

        logger.info("ResourceAgent returning %d resources", len(all_resources))
        return {"resources": all_resources, "agent_step": self.agent_step()}

    def _generate_single_lecture(self, course_name: str, context: dict) -> dict | None:
        """Generate a single lecture resource via LLM — no templates."""
        try:
            import uuid
            feedback = context.get("_review_feedback", "")
            feedback_block = f"\n\n## 上一轮审核反馈\n{feedback}\n请针对性修正上述问题，不要从头重复生成全部内容。" if feedback else ""
            prompt = (
                f"为'{course_name}'生成一份专业课程讲解文档。包含：\n"
                "1. 课程概述与学习目标\n2. 核心知识体系（3-5个模块）\n"
                "3. 每个模块的关键概念和典型应用\n4. 推荐学习顺序\n"
                "输出Markdown格式，至少500字。"
                f"{feedback_block}"
            )
            content = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5, max_tokens=2000,
            )
            if content and len(content) > 100:
                return {
                    "resource_id": uuid.uuid4().hex[:12], "type": "lecture",
                    "title": f"{course_name} - 课程讲义", "content": content,
                    "related_stage_id": "", "source": "llm_generated",
                    "format": "markdown", "difficulty": "medium", "quality_status": "passed",
                }
        except Exception:
            pass
        return None

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        # 返回超时前已完成批次的资源，不全丢
        partial = self._partial_resources or []
        self._partial_resources = None
        if partial:
            logger.info("get_fallback: returning %d partial resources from timed-out batches", len(partial))
        return {
            "resources": partial,
            "limitations": (["资源生成超时，返回已完成的批次。"] if not partial
                           else [f"资源生成超时，已返回 {len(partial)} 份已完成资源。"]),
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "timeout" if partial else "failed",
                "summary": f"ResourceAgent timed out, returning {len(partial)} partial resources.",
                "error_reason": "Resource agent timed out",
                "source": "partial_timeout" if partial else "rule_based_fallback",
                "quality_status": "warning" if partial else "fallback",
                "started_at": None,
                "finished_at": None,
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # LLM 路径
    # ═══════════════════════════════════════════════════════════════

    def _generate_with_llm(
        self,
        context: dict[str, Any],
        course: dict[str, Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        profile: dict[str, Any],
        rag_evidence: list[dict[str, Any]] | None = None,
        batch_label: str = "",
    ) -> list[dict[str, Any]]:
        """LLM 生成资源"""
        if not self.llm_client:
            return []

        rag_evidence = rag_evidence or []
        rag_context = ""
        if rag_evidence:
            lines = []
            for ev in rag_evidence[:10]:
                lines.append(
                    f"- [{ev.get('title', '')}] {ev.get('snippet', '')[:120]} "
                    f"(source={ev.get('source', '')}, score={ev.get('score', 0):.3f})"
                )
            rag_context = (
                "\n## RAG Knowledge Base Evidence\n" + "\n".join(lines) +
                "\n\nUse the above evidence to ground titles, descriptions, reasons, "
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
                    "adjustment_summary": self._section_adjustment_map(stage),
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
                    "你是 EduAgent 的资源生成智能体。根据学习路径阶段、诊断结果和学习者画像生成学习资源。\n\n"
                    "## 核心规则：任务驱动，深度讲解，多多益善\n"
                    "学习路径中每个阶段都有 tasks 列表——每一项 task 都需要配套的学习资源。\n"
                    "逐个检查每个阶段的 tasks 数组，为每一项任务生成至少 2 份讲义/阅读材料。\n"
                    "大型知识点自动拆分为上下篇或多篇，不要怕内容多。\n"
                    "每份讲义必须包含例题——概念讲解后紧跟例题演示，解析步骤要详细。\n"
                    "练习题由练习中心处理，你专注做学习材料（讲义、导图、阅读、代码案例等）。\n"
                    "不要偷工减料，不要跳过任何任务。宁多勿少，宁深勿浅。\n\n"
                    "## 资源类型（按课程模式选择）\n"
                    + self._mode_resource_guide() + "\n\n"
                    "## 内容深度\n"
                    "简单概念 → 精炼讲义附1-2道基础例题\n"
                    "核心难点 → 拆分为上下篇 + 每篇3-5道例题 + 阶梯难度\n"
                    "大知识点 → 自动拆分多个资源（上/中/下或更多），每篇聚焦一个子主题\n"
                    "综合复习 → 跨知识点综合讲义 + 易错点总结\n"
                    "每份讲义结构：概念讲解→公式推导→例题→解题技巧→易错提示\n\n"
                    "## 代码实操案例（按需生成，不强制）\n"
                    "当课程涉及编程、算法、数据处理时，必须生成 code_practice 类型资源。\n"
                    "格式要求：\n"
                    "- ### 需求说明：明确任务目标和输入输出\n"
                    "- ### 参考代码：完整可运行的代码（含注释），用 ``` 代码块包裹\n"
                    "- ### 测试用例：至少 2 组输入/输出示例\n"
                    "- ### 运行指导：如何运行、预期结果、常见错误\n"
                    "content_format 设为 \\\"markdown\\\"，type 设为 \\\"practice\\\"。\n\n"
                    "## 输出格式（极其重要！严格按此格式）\n"
                    "每个资源用 ---RESOURCE_META--- 和 ---RESOURCE_CONTENT--- 分隔：\n\n"
                    "---RESOURCE_META---\n"
                    '{{"resource_id":"res_01","type":"lecture","title":"极限定义精讲","description":"短描述","content_format":"markdown","related_stage_id":"stage_1","related_knowledge_points":["极限","连续"],"reason":"说明为什么生成此资源"}}\n'
                    "---RESOURCE_CONTENT---\n"
                    "## 讲义正文（markdown格式，自由书写，无需转义）\n"
                    "知识点讲解、例题、解题步骤……\n\n"
                    "---RESOURCE_META---\n"
                    '{{"resource_id":"res_02","type":"quiz",...}}\n'
                    "---RESOURCE_CONTENT---\n"
                    "题目内容（如果是quiz，把题目+选项+答案+解析写在这里）\n\n"
                    "规则：\n"
                    "- META行必须是单行JSON，包含除正文外的所有元数据\n"
                    "- CONTENT行之后到下一个---分隔符之前的所有内容都是正文，自由书写markdown，无需任何JSON转义\n"
                    "- 分隔符必须独占一行\n"
                    "- 每个资源的META JSON中不包含content字段——正文在CONTENT块里\n\n"
                    "## 公式格式（极其重要！不遵守则公式无法显示）\n所有数学表达式必须用 `$` 包裹。短公式行内：`$f(x)=x^2$`，大公式独立行：`$$\\int_a^b f(x)dx$$`。不包 `$` 的公式会变成乱码纯文本。涉及数学内容必须严格包裹。\n\n"
                    "## 正文排版要求（极其重要！决定学生是否愿意读下去）\n"
                    "- 必须用 ## 标题分段，每段内容不超过4行，宁可多分段也不要一大坨文字\n"
                    "- 每个小节下至少有一个三级标题 ### 展开细节\n"
                    "- 关键概念/定义/公式必须用 **加粗** 突出\n"
                    "- 对比性内容（优缺点、类型对比）必须用markdown表格\n"
                    "- 步骤性内容必须用有序列表\n"
                    "- 重点提醒/易错点/考点必须用 > **重点：** 引用块高亮\n"
                    "- 例题必须有题目、解答、总结三步，用 ### 分隔\n"
                    "- 不要连续超过3段纯文字，穿插列表/表格/代码块打破视觉单调\n"
                    + (f"\n## 审核反馈（请据此修正）\n{context['_review_feedback']}\n" if context.get("_review_feedback") else "")
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            raw = self.llm_client.chat(messages, temperature=0.2, max_tokens=8000)
            logger.info(f"ResourceAgent LLM raw response (first 500 chars): {raw[:500]}")
            resources = self._parse_delimited(raw)
            # 分隔符解析失败时回退到旧 JSON 格式
            if not resources:
                logger.info("Delimited format returned 0 resources, trying legacy JSON format")
                old_parsed = self._parse_json(raw)
                legacy = old_parsed.get("resources") if isinstance(old_parsed, dict) else None
                if isinstance(legacy, list):
                    resources = legacy
        except Exception as e:
            logger.warning(f"ResourceAgent LLM call failed: {e}")
            logger.exception("Full traceback:")
            return []

        if not resources:
            return []
        return self._normalize_llm_resources(resources, stages, knowledge_points, course, rag_evidence)

    def _mode_resource_guide(self) -> str:
        """Return mode-specific resource type instructions for the LLM prompt."""
        
        if pm == "daily":
            return (
                "这是语言类/每日学习模式。不要生成讲义！生成以下类型的资源：\n"
                "- memory_drill: 单词闪卡/词汇表（**word** — 释义 格式）\n"
                "- listening: 听力训练材料（对话文本+理解题）\n"
                "- reading: 阅读理解文章+问答\n"
                "- grammar: 语法讲解+例句+练习\n"
                "- speaking: 口语对话模板+场景练习\n"
                "- writing: 写作模板+范文\n"
                "- review: 复习测验/错题回顾\n"
                "练习题和测验题由练习中心单独生成，你专注学习材料即可。"
            )
        if pm == "project":
            return (
                "这是编程/项目驱动模式。生成以下类型的资源：\n"
                "- lecture: 概念讲解（简明扼要）\n"
                "- practice: 代码实操案例（需求说明+参考代码+测试用例+运行指导）\n"
                "- mindmap: 技术栈关系图\n"
                "- reading: 最佳实践/设计模式文章\n"
                "练习题和测验题由练习中心单独生成，你专注学习材料即可。"
            )
        return (
            "练习题和测验题由练习中心单独生成，你专注学习材料即可。\n"
            "根据课程特点自由决定类型：lecture(讲义), mindmap(思维导图), reading(阅读材料), practice(实操案例)等。\n"
            "不同学科用不同组合，不套固定模板。"
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        from app.utils.llm_json import parse_safe
        return parse_safe(text)

    # _parse_json 已替换为 _parse_delimited —— 分隔符格式从根本上避免了 JSON 中的内容转义问题

    @staticmethod
    def _parse_delimited(text: str) -> list[dict]:
        """解析分隔符格式的输出。元数据和内容分离，不再依赖 JSON 容纳长文本。

        格式：
        ---RESOURCE_META---
        {json}
        ---RESOURCE_CONTENT---
        正文内容（自由文本，无需转义）
        ---RESOURCE_META---
        ...
        """
        resources = []
        # 按 META 分隔符切分
        meta_blocks = re.split(r'\n?---RESOURCE_META---\n?', text)
        for block in meta_blocks:
            block = block.strip()
            if not block:
                continue
            # 分离 META JSON 和 CONTENT
            parts = re.split(r'\n?---RESOURCE_CONTENT---\n?', block, maxsplit=1)
            if len(parts) < 2:
                continue

            meta_text = parts[0].strip()
            content_text = parts[1].strip()

            # 提取 JSON（取第一行或第一个 { ... }）
            if meta_text.startswith('{'):
                json_str = meta_text
            else:
                # 可能是代码块包裹
                json_str = re.sub(r'^```(?:json)?\s*', '', meta_text)
                json_str = re.sub(r'\s*```$', '', json_str)

            # 尝试解析 JSON
            try:
                meta = json.loads(json_str)
            except json.JSONDecodeError:
                # 尝试用 sanitize 修复
                from app.utils.llm_json import sanitize_json
                try:
                    meta = json.loads(sanitize_json(json_str))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse resource meta: %s...", json_str[:100])
                    continue

            if not isinstance(meta, dict) or not meta.get("title"):
                continue

            # 根据类型设置内容
            if meta.get("type") == "quiz":
                # Quiz: 尝试解析 content 中的 items（题目数组）
                quiz_items = None
                try:
                    stripped = content_text.strip()
                    if stripped.startswith('{') or stripped.startswith('['):
                        from app.utils.llm_json import sanitize_json
                        parsed = json.loads(sanitize_json(stripped))
                        if isinstance(parsed, list):
                            quiz_items = parsed
                        elif isinstance(parsed, dict) and "items" in parsed:
                            quiz_items = parsed["items"]
                except Exception:
                    pass
                if quiz_items:
                    meta["items"] = quiz_items
                    meta["content"] = ""
                    meta["content_format"] = "json"
                else:
                    meta["content"] = content_text
                    meta["content_format"] = meta.get("content_format", "markdown")
            elif meta.get("type") == "mindmap":
                meta["content"] = content_text
                meta["content_format"] = "mermaid"
            else:
                meta["content"] = content_text
                meta["content_format"] = meta.get("content_format", "markdown")

            # 补全默认字段
            meta.setdefault("description", meta.get("title", ""))
            meta.setdefault("quality_status", "passed")
            meta.setdefault("source", "llm_generated")
            resources.append(meta)

        logger.info(f"Parsed {len(resources)} resources from delimited format")
        return resources

    def _normalize_llm_resources(
        self,
        resources: list[Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        course: dict[str, Any],
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """标准化 LLM 生成的资源"""
        stage_ids = {str(stage.get("stage_id") or f"stage_{index}") for index, stage in enumerate(stages, start=1)}
        fallback_bindings = self._stage_bindings(stages, knowledge_points)
        normalized = []
        seen_types = set()
        seen_stage_ids = set()

        for index, item in enumerate(resources, start=1):
            if not isinstance(item, dict):
                continue
            resource_type = self._clean_type(item.get("type"))
            if not resource_type:
                resource_type = "lecture"
            default_binding = fallback_bindings[min(index - 1, len(fallback_bindings) - 1)]
            stage_id = str(item.get("related_stage_id") or default_binding["stage_id"])
            if stage_id not in stage_ids:
                stage_id = default_binding["stage_id"]
            binding = next(
                (c for c in fallback_bindings if c["stage_id"] == stage_id),
                default_binding,
            )
            knowledge = self._clean_list(item.get("related_knowledge_points")) or binding["knowledge_points"]
            content_format = str(item.get("content_format") or self._format_for_type(resource_type))
            content = str(item.get("content") or "").strip()
            quiz_items = item.get("items") if isinstance(item.get("items"), list) else None
            # 如果 items 是字符串，把它当 content 用
            if not quiz_items and isinstance(item.get("items"), str) and not content:
                content = str(item.get("items")).strip()
            if not content and not quiz_items:
                content = item.get("title", "学习资源")

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
        return normalized if len(normalized) >= 1 else []

    # ═══════════════════════════════════════════════════════════════
    # 规则兜底（完整保留原 ResourceAgent 全部逻辑）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _section_adjustment_map(stage: dict) -> dict:
        """Scan a stage's sections for _adjustment markers and return a summary.

        Returns:
            dict with keys: strengthened (list), accelerated (list),
                            remedial (list), mixed (list), normal (list)
        """
        result = {"strengthened": [], "accelerated": [], "remedial": [], "mixed": [], "normal": []}
        for ch in stage.get("chapters", []):
            for sec in ch.get("sections", []):
                adj = sec.get("_adjustment", "")
                title = sec.get("title", "")
                if adj in result:
                    result[adj].append(title)
                else:
                    result["normal"].append(title)
        return result

    def _build_rule_fallback_for_stage(
        self, course: dict, stage: dict, knowledge_points: list, profile: dict
    ) -> list[dict]:
        """为单个阶段生成规则兜底资源。使用 _adjustment 标记个性化资源。

        根据 section 级别的 _adjustment 调整资源类型：
        - strengthened: 多生成 practice 辅助强化
        - accelerated: 只生成 quiz（跳过 lecture/reading）
        - remedial: 多生成 lecture + practice 打基础
        - normal/mixed: lecture + reading（默认）
        """
        resources = []
        stage_id = str(stage.get("stage_id", ""))
        stage_title = str(stage.get("title", ""))
        tasks = stage.get("tasks", []) or [stage_title]
        binding = {
            "stage_id": stage_id, "title": stage_title,
            "knowledge_points": [kp.get("name", "") for kp in knowledge_points[:5]],
            "chapter": stage_title,
            "difficulty": stage.get("difficulty", "medium"),
        }

        # Check adjustment markers
        adj = self._section_adjustment_map(stage)
        has_strengthened = len(adj["strengthened"]) > 0
        has_accelerated = len(adj["accelerated"]) > 0
        has_remedial = len(adj["remedial"]) > 0

        for i, task in enumerate(tasks, 1):
            task_id = f"{stage_id}_node_{i}"
            if has_remedial:
                resources.append(self._lecture_for_task(course, binding, profile, task, task_id))
                resources.append(self._practice_for_task(course, binding, profile, task, task_id))
            elif has_accelerated and not has_strengthened:
                resources.append(self._quiz_for_task(course, binding, profile, task, task_id))
            else:
                resources.append(self._lecture_for_task(course, binding, profile, task, task_id))
                resources.append(self._reading_for_task(course, binding, task, stage_id, task_id))
                if has_strengthened:
                    resources.append(self._practice_for_task(course, binding, profile, task, task_id))
        return resources

    def _build_rule_fallback(
        self,
        course: dict[str, Any],
        stages: list[dict[str, Any]],
        knowledge_points: list[dict[str, Any]],
        profile: dict[str, Any],
        fallback_reason: str,
        rag_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        bindings = self._stage_bindings(stages, knowledge_points)
        resources = []
        extra_types = ["mindmap", "reading", "practice", "video"]

        for binding in bindings:
            stage_id = str(binding.get("stage_id", ""))
            tasks = binding.get("tasks", [])

            resources.append(self._mindmap_for_task(course, binding, binding.get("title", ""), stage_id, ""))
            resources.append(self._reading_for_task(course, binding, binding.get("title", ""), stage_id, ""))

            for ti, task in enumerate(tasks[:6]):
                task_id = f"{stage_id}_node_{ti + 1}"
                resources.append(self._lecture_for_task(course, binding, profile, task, task_id))
                resources.append(self._quiz_for_task(course, binding, profile, task, task_id))
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
            resource.update({
                "source_type": source_type,
                "generation_mode": "fallback",
                "quality_status": quality_status,
                "fallback_reason": fallback_reason,
            })
            resource["evidence"] = self._resource_evidence(
                resource,
                generation="rule_based_fallback",
                fallback_reason=fallback_reason,
            )
            resource["rag_evidence"] = rag_evidence or []
        return resources

    # ── 以下完整保留原 ResourceAgent 所有辅助方法 ──

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
        if type(self.llm_client).__name__ == "MockLLMClient":
            return []

        queries = []
        diagnosis = context.get("diagnosis", {})
        for wp in diagnosis.get("weak_knowledge_points", []) or []:
            if isinstance(wp, dict):
                name = str(wp.get("name") or wp.get("title") or "").strip()
                if name and len(name) >= 2:
                    queries.append(name)
            elif isinstance(wp, str) and wp.strip():
                queries.append(wp.strip())

        for stage in stages[:3]:
            title = str(stage.get("title") or "").strip()
            goal = str(stage.get("goal") or "").strip()
            if title and len(title) >= 2:
                queries.append(title)
            if goal and len(goal) >= 2 and goal not in queries:
                queries.append(goal)

        for kp in knowledge_points[:5]:
            name = str(kp.get("name") or kp.get("title") or "").strip()
            if name and len(name) >= 2 and name not in queries:
                queries.append(name)

        target = str(profile.get("interest_direction", {}).get("value", "") or context.get("course_id", "")).strip()
        goal_val = str(profile.get("learning_goal", {}).get("value", "") or profile.get("learning_goal", "")).strip()
        if target and len(target) >= 2:
            queries.append(target)
        if goal_val and len(goal_val) >= 2 and goal_val not in queries:
            queries.append(goal_val)

        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        queries = unique_queries[:max_queries]

        if not queries:
            return []

        try:
            from app.rag.query_engine import rag_query_engine
            engine = rag_query_engine
            if not engine.is_ready():
                return []
        except Exception:
            return []

        evidence = []
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

    def _build_review_feedback(self, context: dict[str, Any]) -> str:
        """将 ReviewAgent 的审核结果转成 LLM 可理解的修正指令。

        当审核发现问题时返回反馈字符串，ResourceAgent 据此针对性修复。
        """
        review = context.get("review", {})
        if not review:
            return ""
        status = review.get("quality_status", "passed")
        if status == "passed":
            return ""
        checks = review.get("checks", [])
        parts: list[str] = []
        for c in checks:
            if c.get("status") in ("warning", "blocked"):
                parts.append(f"- 【{c.get('name','')}】{c.get('message','')}")
        if not parts:
            return ""
        return (
            "## 上一轮质量审核未通过，以下是需要修正的问题（请逐条修复）\n"
            + "\n".join(parts)
            + "\n\n请根据以上反馈重新生成有问题的资源，不要从头重复生成全部内容。"
        )


    @staticmethod
    def _missing_types_from_feedback(feedback: str) -> set[str]:
        """从审核反馈中提取缺失的资源类型。"""
        if not feedback:
            return set()
        types = set()
        for t in ("mindmap", "practice", "lecture", "reading", "quiz"):
            if f"缺少{t}" in feedback or f"缺少资源类型：{t}" in feedback:
                types.add(t)
        return types

    def _binding_for_stage(self, stage: dict, knowledge_points: list) -> dict:
        return {
            "stage_id": str(stage.get("stage_id", "")),
            "reason": f'为阶段「{stage.get("title","")}」补齐缺失资源',
            "difficulty": "medium",
        }

    def _mindmap_for_stage(self, course: dict, stage: dict, knowledge_points: list) -> dict | None:
        title = str(stage.get("title", ""))
        course_name = str(course.get("course_name", ""))
        if not title and not course_name:
            return None
        from app.services.deeptutor_client import generate_mindmap
        try:
            mm = generate_mindmap(title or course_name)
            if mm and len(mm) > 50:
                import uuid, json
                # Wrap raw mermaid content as graph_data for unified rendering
                graph_data = {
                    "nodes": [
                        {"id": "root", "label": title or course_name, "type": "concept", "difficulty": "medium", "importance": 4},
                    ],
                    "edges": [],
                }
                # Try to parse structured nodes from mermaid lines
                for line in mm.strip().split("\n"):
                    stripped = line.strip()
                    if stripped and not stripped.startswith("mindmap") and not stripped.startswith("root") and not stripped.startswith("```"):
                        node_id = stripped.replace(" ", "_").replace("(", "").replace(")", "")[:24]
                        graph_data["nodes"].append({"id": node_id, "label": stripped, "type": "concept", "difficulty": "medium", "importance": 2})
                        graph_data["edges"].append({"source": "root", "target": node_id, "relation": "contains"})
                return {
                    "resource_id": uuid.uuid4().hex[:12],
                    "type": "mindmap",
                    "title": f"{title} - 思维导图",
                    "content": json.dumps(graph_data, ensure_ascii=False),
                    "content_format": "graph_data",
                    "related_stage_id": str(stage.get("stage_id", "")),
                    "source": "deeptutor",
                    "format": "diagram",
                    "difficulty": "medium",
                    "quality_status": "passed",
                }
        except Exception:
            pass
        return None
    def _knowledge_points(
        self,
        context: dict[str, Any],
        course: dict[str, Any],
        stages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        points = []
        course_id = str(course.get("course_id") or context.get("course_id") or "")
        for index, chapter in enumerate(course.get("chapters", []), start=1):
            chapter_id = str(chapter.get("chapter_id", index)).zfill(2)
            detail = course_catalog.load_chapter(course_id, chapter_id) or chapter
            points.append({
                "chapter_id": chapter_id,
                "title": str(chapter.get("title") or chapter.get("name") or f"Chapter {index}"),
                "name": str(chapter.get("title") or chapter.get("name") or f"Chapter {index}"),
                "difficulty": chapter.get("difficulty", "medium"),
                "prerequisites": chapter.get("prerequisites", []),
                "content_excerpt": str(detail.get("content", ""))[:600],
                "_origin": str(course.get("_source_type") or SOURCE_TYPE_AGENT),
            })

        retrieved = context.get("knowledge_context", {}).get("retrieved_points", [])
        for item in retrieved:
            if isinstance(item, dict):
                self._append_unique_point(points, item, str(context.get("knowledge_context", {}).get("source") or SOURCE_TYPE_AGENT))

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

    def _append_unique_point(self, points, item, origin=SOURCE_TYPE_AGENT):
        name = str(item.get("title") or item.get("name") or item.get("topic") or "").strip()
        if not name:
            return
        if any(str(p.get("name") or p.get("title")) == name for p in points):
            return
        points.append({
            "chapter_id": str(item.get("chapter_id") or len(points) + 1).zfill(2),
            "title": name,
            "name": name,
            "difficulty": item.get("difficulty", item.get("priority", "medium")),
            "prerequisites": item.get("prerequisites", []),
            "content_excerpt": item.get("content_excerpt", ""),
            "_origin": origin,
        })

    def _stage_bindings(self, stages, knowledge_points):
        result = []
        stage_count = max(1, len(stages))
        for index, stage in enumerate(stages, start=1):
            matched = self._matching_stage_points(stage, knowledge_points)
            if matched:
                group = matched
                binding_mode = "context_match"
            else:
                if not knowledge_points:
                    group = []
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
            result.append({
                "stage_id": str(stage.get("stage_id") or f"stage_{index}"),
                "title": str(stage.get("title") or f"阶段 {index}"),
                "chapter": chapter or (names[0] if names else str(stage.get("title") or f"阶段 {index}")),
                "knowledge_points": names[:5] or [str(stage.get("title") or f"阶段 {index}")],
                "difficulty": self._difficulty(group),
                "reason": str(stage.get("reason") or stage.get("goal") or "根据学习路径阶段和课程章节生成。"),
                "tasks": stage.get("tasks", []),
                "binding_mode": binding_mode,
            })
        return result

    def _matching_stage_points(self, stage, knowledge_points):
        explicit_values = [
            stage.get("chapter_id"),
            stage.get("related_chapter"),
            *self._clean_list(stage.get("knowledge_points")),
            *self._clean_list(stage.get("related_knowledge_points")),
        ]
        stage_text = " ".join(
            str(v) for v in [stage.get("title"), stage.get("goal"), *(stage.get("tasks") or []), *explicit_values] if v
        )
        normalized_stage = self._normalize_binding_text(stage_text)
        if not normalized_stage:
            return []
        matches = []
        for point in knowledge_points:
            candidates = [point.get("chapter_id"), point.get("title"), point.get("name")]
            if any(
                normalized and (normalized in normalized_stage or normalized_stage in normalized)
                for normalized in (self._normalize_binding_text(v) for v in candidates)
            ):
                matches.append(point)
        return matches[:3]

    def _normalize_binding_text(self, value):
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())

    def _chapter_is_grounded(self, related_chapter, knowledge_points):
        normalized = self._normalize_binding_text(related_chapter)
        if not normalized:
            return False
        for point in knowledge_points:
            chapter_id = self._normalize_binding_text(point.get("chapter_id"))
            title = self._normalize_binding_text(point.get("title") or point.get("name"))
            if title and (title in normalized or normalized in title):
                return True
            if chapter_id and re.search(
                rf"(^|\D)0*{re.escape(chapter_id.lstrip('0') or '0')}(\D|$)", related_chapter
            ):
                return True
        return False

    def _stages(self, context):
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

    def _scope_resource_ids(self, resources, session_id):
        if not session_id:
            return resources
        for item in resources:
            resource_id = str(item.get("resource_id", ""))
            if resource_id and not resource_id.startswith(f"{session_id}_"):
                resource_id = f"{session_id}_{resource_id}"
                item["resource_id"] = resource_id
            item["id"] = resource_id
        return resources

    def _resource_evidence(self, resource, *, generation, fallback_reason=""):
        evidence = [
            f"Learning stage: {resource.get('related_stage_id') or 'unresolved'}",
            f"Course chapter: {resource.get('related_chapter') or 'unresolved'}",
            f"Generation: {generation}",
        ]
        points = resource.get("related_knowledge_points") or resource.get("knowledge_points") or []
        if points:
            evidence.append(f"Knowledge points: {', '.join(str(p) for p in points[:5])}")
        reason = str(resource.get("reason") or "").strip()
        if reason:
            evidence.append(f"Recommendation reason: {reason}")
        if fallback_reason:
            evidence.append(f"Fallback: {fallback_reason}")
        return evidence

    def _compact_profile(self, profile):
        compact = {}
        for key, item in profile.items():
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
                if value:
                    compact[key] = value
            elif item:
                compact[key] = str(item)
        return compact

    def _profile_value(self, profile, keys, default):
        for key in keys:
            item = profile.get(key)
            if isinstance(item, dict) and str(item.get("value", "")).strip():
                return str(item.get("value")).strip()
            if isinstance(item, str) and item.strip():
                return item.strip()
        return default

    def _clean_type(self, value):
        aliases = {"video_script": "multimodal", "video": "multimodal", "case_study": "practice"}
        raw = str(value or "").strip()
        return aliases.get(raw, raw)

    def _format_for_type(self, resource_type):
        if resource_type == "mindmap":
            return "mermaid"
        if resource_type == "quiz":
            return "json"
        return "markdown"

    def _clean_list(self, value):
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:8]

    def _difficulty(self, points):
        text = " ".join(str(p.get("difficulty", "")) + " " + str(p.get("priority", "")) for p in points)
        if "hard" in text or "high" in text:
            return "hard"
        if "medium" in text:
            return "medium"
        return "easy"

    def _lecture_for_task(self, course, binding, profile, task, task_id):
        base = self._profile_value(profile, ["knowledge_base", "coding_ability", "programming_ability"], "基础未明确")
        stage_title = binding.get("title", "")
        knowledge = "、".join(binding.get("knowledge_points", [])[:5]) or task
        chapter = binding.get("chapter", "")
        content = (
            f"## {task}\n\n"
            f"所属阶段：{stage_title}\n"
            f"关联知识点：{knowledge}\n"
            f"参考章节：{chapter}\n\n"
            f"### 学习目标\n"
            f"通过本讲义掌握 {task} 涉及的核心概念、原理和方法。\n\n"
            f"### 概念要点\n"
            f"以下为 {knowledge} 的关键概念框架，建议结合实际教材深入学习：\n\n"
            f"1. **定义与背景** —— 理解 {task} 涉及的基础术语和应用场景\n"
            f"2. **核心原理** —— 掌握主要方法与推导逻辑\n"
            f"3. **典型应用** —— 通过例题理解如何运用这些知识解决实际问题\n"
            f"4. **常见误区** —— 注意易错点和边界条件\n\n"
            f"### 推荐学习路径\n"
            f"1. 先阅读教材对应章节，建立整体概念框架\n"
            f"2. 结合讲义中的例题手动推导一遍\n"
            f"3. 完成配套练习题，对照解析查漏补缺\n"
            f"4. 对错题进行归类整理，标记薄弱环节\n\n"
            f"> ⚠ 此为规则兜底生成的讲义框架。启用 LLM 后将自动替换为含详细例题和个性化讲解的完整讲义。"
        )
        # 标题用阶段标题+任务关键词，而不是直接用 task 原文
        short_title = task[:25] + ("…" if len(task) > 25 else "")
        return self._resource(
            f"res_lecture_{task_id}", "lecture",
            f"{stage_title} — {short_title}讲义",
            f"{stage_title}阶段学习任务「{task}」的讲义。",
            "markdown", binding,
            content=content,
            reason=f"为阶段「{stage_title}」的任务「{task}」提供结构化讲义。",
            task_id=task_id,
        )

    def _mindmap_for_task(self, course, binding, task, stage_id, task_id=""):
        label = task or stage_id
        res_id = f"res_mindmap_{task_id}" if task_id else f"res_mindmap_{stage_id}"
        safe_label = str(label).replace("(", "").replace(")", "").replace("[", "").replace("]", "")
        # Generate graph_data instead of Mermaid mindmap
        graph_data = {
            "nodes": [
                {"id": "root", "label": safe_label, "type": "concept", "difficulty": "medium", "importance": 4},
                {"id": "concept", "label": "核心概念", "type": "concept", "difficulty": "medium", "importance": 3},
                {"id": "algorithm", "label": "关键算法", "type": "procedure", "difficulty": "medium", "importance": 3},
                {"id": "scenario", "label": "应用场景", "type": "concept", "difficulty": "easy", "importance": 2},
                {"id": "mistake", "label": "常见误区", "type": "memory", "difficulty": "medium", "importance": 2},
            ],
            "edges": [
                {"source": "root", "target": "concept", "relation": "contains"},
                {"source": "root", "target": "algorithm", "relation": "contains"},
                {"source": "root", "target": "scenario", "relation": "contains"},
                {"source": "root", "target": "mistake", "relation": "contains"},
            ],
        }
        import json
        content = json.dumps(graph_data, ensure_ascii=False)
        return self._resource(
            res_id, "mindmap",
            f"{label}知识图谱", f"学习任务「{label}」的知识结构图。",
            "graph_data", binding,
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
            f"{task}练习题", f"覆盖学习任务「{task}」的测验题。",
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
            f"{label}拓展阅读", f"与学习任务「{label}」相关的拓展阅读材料。",
            "markdown", binding,
            content=content,
            reason=f"拓展{label}的深度和广度",
            task_id=task_id,
        )

    def _practice_for_task(self, course, binding, profile, task, task_id):
        base = self._profile_value(profile, ["coding_ability"], "基础未明确")
        course_name = course.get("course_name", "")
        content = (
            f"## 实操任务：{task}\n\n"
            f"### 需求说明\n"
            f"掌握 {task} 的核心概念和实现方法，能够独立完成从分析到编码的完整流程。"
            f"适用于 {course_name} 课程学习者，{base}。\n\n"
            f"### 参考代码\n"
            f"```python\n"
            f"# 任务：{task}\n"
            f"def solution(input_data):\n"
            f"    # 实现核心逻辑\n"
            f"    result = process(input_data)\n"
            f"    return result\n\n"
            f"# 测试\n"
            f"if __name__ == '__main__':\n"
            f"    print(solution('test'))\n"
            f"```\n\n"
            f"### 测试用例\n"
            f"- 输入：典型数据 → 预期输出：正常结果\n"
            f"- 输入：边界数据 → 预期输出：边界处理结果\n"
            f"- 输入：异常数据 → 预期输出：错误处理\n\n"
            f"### 运行指导\n"
            f"1. 将代码保存为 `.py` 文件\n"
            f"2. 在终端运行：`python 文件名.py`\n"
            f"3. 观察输出是否与预期一致\n"
            f"4. 尝试修改输入数据观察不同结果"
        )
        return self._resource(
            f"res_practice_{task_id}", "practice",
            f"{task}实操案例", f"结合学习任务「{task}」生成可手推或可运行的实操任务。",
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
            f"视频脚本：{task}", f"针对学习任务「{task}」的视频讲解脚本。",
            "markdown", binding,
            content=content,
            reason=f"满足偏好视频/图解的学生",
            task_id=task_id,
        )

    def _resource(self, resource_id, resource_type, title, description, content_format, binding, *,
                  content="", items=None, reason=None, difficulty=None, task_id=None):
        return {
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

    def _quiz_stem(self, course_id, point):
        if course_id == "data_structures":
            return f"围绕 {point}，说明它的基本操作、适用场景，并分析一次典型操作的时间复杂度。"
        if course_id == "ai_intro":
            return f"围绕 {point}，说明它在人工智能系统中的作用，并给出一个典型应用场景。"
        return f"围绕 {point}，说明核心概念、适用场景和一个常见误区。"

    def _quiz_options(self, course_id, point):
        if course_id == "data_structures":
            return ["定义与操作", "复杂度分析", "边界条件", "以上都需要"]
        if course_id == "ai_intro":
            return ["问题建模", "训练或搜索过程", "评价指标", "以上都需要"]
        return ["概念理解", "应用场景", "常见误区", "以上都需要"]

    def _quiz_answer(self, course_id, point):
        if course_id == "data_structures":
            return f"应从 {point} 的结构特征、操作步骤、边界条件和复杂度四方面作答。"
        if course_id == "ai_intro":
            return f"应从 {point} 的任务目标、输入输出、方法流程和评价方式四方面作答。"
        return f"应结合 {point} 的定义、应用和限制进行回答。"

    def _practice_content(self, course_id, point, profile):
        coding = self._profile_value(profile, ["coding_ability", "programming_ability"], "基础水平")
        if course_id == "data_structures":
            return (
                f"### 需求说明\n"
                f"实现并验证 {point}，理解核心操作和时间复杂度。编程能力：{coding}\n\n"
                f"### 参考代码\n"
                f"```python\n"
                f"def solution(data):\n"
                f"    result = []\n"
                f"    for item in data:\n"
                f"        result.append(process(item))\n"
                f"    return result\n\n"
                f"print(solution([3, 1, 2]))\n"
                f"```\n\n"
                f"### 测试用例\n"
                f"- 空输入：[] → 预期输出：[]\n"
                f"- 单元素：[1] → 预期输出：[1]\n"
                f"- 重复元素：[3,1,2,1] → 不丢元素\n\n"
                f"### 运行指导\n"
                f"1. 复制代码到本地运行\n"
                f"2. 修改输入测试不同场景\n"
                f"3. 对比输出与预期"
            )
        if course_id == "ai_intro":
            return (
                f"## 实操任务：拆解 {point} 的 AI 流程\n\n"
                "1. 写出任务输入、模型/算法、输出和评价指标。\n"
                "2. 用 5 条样例数据模拟一次预测、搜索或推理流程。\n"
                "3. 说明可能的数据偏差、过拟合或评价误差。\n"
            )
        return f"## 实操任务：{point}\n\n用一个最小样例写出输入、处理过程、输出和检查标准。"

    # ── 通用推荐模式（§10.1, 补充3）──

