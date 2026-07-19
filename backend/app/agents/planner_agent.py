"""
学习路径规划智能体 — LLM 主导，规则仅作为 LLM 不可用时的兜底。
"""

import json
import logging
import re
import time
from math import ceil
from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.services.course_catalog import course_catalog
from app.services.day_planner import build_day_plan
from app.services.llm_client import LLMClientError
from app.utils.id_factory import (
    make_chapter_id,
    make_kp_id,
    make_path_id,
    make_section_id,
    make_stage_id,
)

logger = logging.getLogger(__name__)


@register_agent
class PlannerAgent(BaseAgent):
    agent_id = "planner_agent"
    agent_name = "学习路径规划智能体"

    # ── 公共接口 ──

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        # ── Compute shared context needed by all planning paths ──
        diagnosis = context.get("diagnosis") if isinstance(context.get("diagnosis"), dict) else {}
        profile = context.get("profile", {})
        mode = str(context.get("mode", "plan"))
        existing = context.get("existing_path")

        if mode == "adjust":
            # 检测是否需要实质性重构（薄弱点超过阈值）
            if self._adjustment_needs_restructure(context, diagnosis):
                logger.info(
                    "adjustment_needs_restructure=True → re-entering planner "
                    "with diagnosis weak_points injected"
                )
                ctx = dict(context)
                ctx["mode"] = "plan"
                ctx["_from_adjustment"] = True
                # 已有路径作为 LLM 参考上下文（不做严格约束，仅提示）
                if existing:
                    ctx["_existing_context"] = (
                        f"学生已有学习路径，请参考已有阶段，重点针对诊断发现的薄弱点重新规划："
                        f"{diagnosis.get('diagnosis_summary', '')}"
                    )
                return self.run(ctx)
            # 轻量微调（时长、type）
            return self._run_adjustment(context, diagnosis, profile)

        weak_points = self._extract_weak_points(diagnosis)
        planning_points = self._get_planning_points(context, weak_points)
        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)
        diag_meta = self._build_diagnosis_meta(diagnosis, weak_points, total_days, profile, time_text)
        diag_meta["daily_minutes"] = self._infer_daily_minutes(context, profile)

        # ── Filter profile_facts to current course only (prevent cross-subject contamination) ──
        course_id = str(context.get("course_id", "") or "")
        course_name = str(context.get("course_name", "") or "")
        if course_id:
            facts = context.get("profile_facts", {}) or {}
            target = str(facts.get("target_course", "") or "")
            # If facts reference a different course, clear unrelated fields
            # For user-defined courses (custom_xxx), course_id is a hash that
            # can't be compared with course name — use course_name when available,
            # or skip the check entirely.
            should_clear = False
            if target and course_name:
                # Compare course names (not hash IDs)
                if target.strip() != course_name.strip() and target[:4] != course_name[:4]:
                    should_clear = True
            elif target and not course_id.startswith("custom_"):
                # Pre-defined course: compare course_id with target_course name
                if target.lower() != course_id.lower() and target[:4] != course_id[:4]:
                    should_clear = True
            # custom_ courses are what the user typed — no cross-subject risk
            if should_clear:
                logger.info("Cross-subject fact detected: facts reference '%s' but course is '%s' — clearing", target, course_id)
                context["profile_facts"] = {}
            # Also clean facts extracted from unrelated conversation topics
            # by keeping only fields that are generic enough
        
        # ── Load textbook chapters for LLM context (if available) ──
        textbook_chapters = context.get("textbook_chapters")
        if not textbook_chapters:
            session_id = context.get("session_id", "")
            if session_id:
                textbook_chapters = self._load_textbook_chapters(session_id)

        # Build textbook context prompt for LLM
        if textbook_chapters and isinstance(textbook_chapters, list) and len(textbook_chapters) > 0:
            textbook_context = self._build_textbook_context_prompt(textbook_chapters)
            context["textbook_context"] = textbook_context
        else:
            textbook_chapters = None

        # ── Primary: DeepTutor mastery_path ──
        chapters = None
        try:
            chapters = self._try_deeptutor_as_structure(context, total_days)
        except Exception:
            pass

        # ── Fallback 1: LLM + web search ──
        if not chapters:
            try:
                chapters = self._generate_chapters(
                    context, profile, planning_points, total_days, diag_meta,
                )
            except Exception:
                pass

        # ── Fallback 2: 4-stage LLM pipeline ──
        if not chapters:
            chapters = self._llm_pipeline_fallback(
                context, profile, planning_points, total_days, diag_meta,
            )

        # ── Last resort: rule-based template ──
        if not chapters:
            return self._fallback_path(context, planning_points, total_days, profile, diag_meta)

        # ── Resolve textbook section IDs to page ranges ──
        if textbook_chapters and chapters:
            chapters = self._resolve_textbook_pages(chapters, textbook_chapters)

        # ── Personalize: adjust pacing/emphasis based on student profile ──
        personalized = self._personalize_with_deeptutor(
            chapters, context, profile, diagnosis, weak_points, total_days,
        )
        chapters = personalized if personalized else chapters

        chapters = self._validate_prerequisites(chapters, context)
        chapters = self._normalize_stage_days(chapters, total_days)
        self._materialize_daily_tasks(chapters, diag_meta["daily_minutes"], context)

        # ── 构建 _agent_context 供下游 agent 协同 ──
        ctx = {
            "action": "initial_plan",
            "target_stages": [
                s.get("stage_id", "")
                for s in (chapters or []) if isinstance(s, dict)
            ],
            "reason": "基于画像和诊断的全量路径规划",
            "needs_resources": ["lecture", "quiz", "mindmap", "reading", "practice"],
            "focus_topics": diag_meta.get("weak_topic_names", []),
            "urgency": "medium",
        }

        result = self._make_chapter_result(chapters, total_days, diag_meta)
        result["_agent_context"] = ctx
        return result


    # ── Load textbook chapters from DB if available ──

    @staticmethod
    def _load_textbook_chapters(session_id: str) -> list[dict] | None:
        """Load textbook chapters from DB for the session's subject.

        Returns the chapters_json list or None if no textbook is linked.
        """
        try:
            from app.db.engine import SessionLocal
            from app.db.models import PersonalSubjectModel, SessionModel, TextbookModel

            db = SessionLocal()
            try:
                session = db.get(SessionModel, session_id)
                if session is None or not session.subject_id:
                    return None

                subject = db.get(PersonalSubjectModel, session.subject_id)
                if subject is None or not subject.textbook_id:
                    return None

                textbook = db.get(TextbookModel, subject.textbook_id)
                if textbook is None or not textbook.chapters_json:
                    return None

                if textbook.status != "ready":
                    logger.info(
                        "Textbook %s status is %s — not ready for path planning",
                        textbook.id, textbook.status,
                    )
                    return None

                logger.info(
                    "Loaded textbook %s for subject %s: %d chapters",
                    textbook.id, subject.id, len(textbook.chapters_json),
                )
                return list(textbook.chapters_json)
            finally:
                db.close()
        except Exception:
            logger.exception("Failed to load textbook chapters for session %s", session_id)
            return None

    # ── Textbook context helpers ──

    @staticmethod
    def _build_textbook_context_prompt(textbook_chapters: list[dict]) -> str:
        """Build a textbook structure summary for LLM prompt injection.

        Shows only chapter/section titles and section IDs — the planner is
        NOT allowed to know page numbers, only section assignments.
        """
        lines = [
            "【教材参考 — 你必须按照以下结构规划学习路径】",
            "",
            "你正在为一位使用指定教材的学生规划学习路径。以下是该教材的完整章节目录。",
            "你的任务是：",
            "1. 整体上严格遵循教材的章节顺序，不得跳过核心教学内容",
            "2. 可以将多个简短的教材小节合并为一个学习小节（在 source_section_ids 中列出所有合并的ID）",
            "3. 可以根据学生基础调整节奏（章间插入复习日、调整小节顺序等），但不能遗漏教材的核心知识点",
            "4. 每个学习小节的输出中必须包含 source_section_ids 字段（字符串数组），填入对应的教材小节ID。",
            "5. 如果某个学习小节没有对应的教材小节（如复习日），source_section_ids 填 []。",
            "",
        ]
        for ch in textbook_chapters:
            ch_title = ch.get("title", "")
            sec_count = len(ch.get("sections", []) or [])
            lines.append(f"## {ch_title}（{sec_count}个小节）")
            for sec in ch.get("sections", []):
                sec_id = sec.get("section_id", "")
                sec_title = sec.get("title", "")
                if sec_title:
                    lines.append(f"  - [{sec_id}] {sec_title}")
            lines.append("")
        lines.append(
            "以上方括号中的ID（如 sec_01_01）就是你要填入 source_section_ids 的值。"
            "注意：你只负责分配章节 ID，不应输出、不应知晓任何页码信息。"
        )
        return "\n".join(lines)

    @staticmethod
    def _resolve_textbook_pages(
        llm_chapters: list[dict], textbook_chapters: list[dict]
    ) -> list[dict]:
        """Strip residual textbook page-number fields from LLM output.

        All page-number fields (textbookPageStart/End/SectionId) are
        unconditionally removed from every task/section — the planner
        agent is NOT permitted to write page numbers.  Pages are resolved
        at display time from the textbook TOC via
        _enrich_textbook_pages_for_response.
        """
        # Build ID → section data lookup
        tb_section_by_id: dict[str, dict] = {}
        for ch in textbook_chapters:
            for sec in ch.get("sections", []):
                sec_id = sec.get("section_id", "")
                if sec_id:
                    tb_section_by_id[sec_id] = sec

        # v1.2: 此函数仅负责清理可能残留的 LLM 编造页码字段。
        # 不设置、不验证 source_section_ids——展示层从教材 TOC 按 section_id
        # 动态解析页码；无效 ID 在展示时自然无页码，不影响任务显示。
        _tb_clean = ("textbookPageStart", "textbookPageEnd", "textbookSectionId")

        for stage in llm_chapters:
            # ── New format: stages→tasks (direct) ──
            for task in stage.get("tasks", []):
                for _k in _tb_clean:
                    task.pop(_k, None)

            # ── New format: stages→days→tasks (after _rewrite_stage_ids) ──
            for day in stage.get("days", []):
                for task in day.get("tasks", []):
                    for _k in _tb_clean:
                        task.pop(_k, None)

            # ── Old format: stages→chapters→sections ──
            for ch in stage.get("chapters", []):
                for sec in ch.get("sections", []):
                    for _k in _tb_clean:
                        sec.pop(_k, None)

        return llm_chapters

    # ── Mode T: Textbook-driven path building ──

    def _build_path_from_textbook(
        self,
        textbook_chapters: list[dict],
        profile: dict,
        total_days: int,
        diag_meta: dict,
    ) -> list[dict] | None:
        if not textbook_chapters:
            return None

        # ── 多样任务类型轮转 ──
        _task_variants = [
            {"ct": "read_doc",   "rtypes": ["lecture","reading"],    "label": "阅读理解", "est": 30},
            {"ct": "watch_video","rtypes": ["video"],                 "label": "视频学习", "est": 25},
            {"ct": "quiz_prac",  "rtypes": ["quiz","homework"],       "label": "练习测验", "est": 35},
            {"ct": "mind_map",   "rtypes": ["mindmap"],               "label": "思维导图", "est": 20},
            {"ct": "hands_on",   "rtypes": ["lab","code","project"],  "label": "实操练习", "est": 40},
            {"ct": "review",     "rtypes": ["quiz","reading"],        "label": "阶段复习", "est": 25},
        ]

        # ── 先平铺所有 section ──
        all_sections = []
        chapter_bounds = []  # (ch_title, sec_start_idx, sec_end_idx)
        for ch in textbook_chapters:
            ch_title = ch.get("title", "")
            ch_order = ch.get("order", len(chapter_bounds))
            start_idx = len(all_sections)
            for sec in ch.get("sections", []):
                sec_title = sec.get("title", "")
                sec_order = sec.get("order", len(all_sections) - start_idx)
                sec_id_orig = sec.get("section_id", f"tb_s_{len(all_sections):03d}")

                kps = []
                for kp_idx, kp_name in enumerate(sec.get("knowledge_points", [])):
                    if isinstance(kp_name, str) and kp_name.strip():
                        kps.append({"id": f"{sec_id_orig}_kp_{kp_idx:02d}", "name": kp_name.strip(), "type": "concept", "mastery": 0, "status": "not_started"})

                variant = _task_variants[len(all_sections) % len(_task_variants)]
                all_sections.append({
                    "id": sec_id_orig,
                    "title": f"{sec_title} · {variant['label']}",
                    "goal": sec.get("goal", "") or f"掌握{sec_title}的核心内容",
                    "estimatedMinutes": sec.get("estimated_minutes", variant["est"]),
                    "knowledge_points": kps,
                    "lectureIds": [],
                    "contentType": variant["ct"],
                    "status": "not_started",
                    "task_type": variant["ct"],
                    "required_resource_types": variant["rtypes"],
                    "textbookPageStart": sec.get("start_page", 1),
                    "textbookPageEnd": sec.get("end_page", 1),
                    "textbookSectionId": sec_id_orig,
                })
            chapter_bounds.append((ch_title, start_idx, len(all_sections)))

        # ── 按章拆成多个阶段：每 2~3 个小节一个阶段 ──
        stages = []
        stage_global_order = 0
        for ch_title, sec_a, sec_b in chapter_bounds:
            ch_secs = all_sections[sec_a:sec_b]
            if not ch_secs:
                continue
            # chunk: 至少2个, 最多4个 section 一个阶段
            chunk_sz = max(2, min(4, len(ch_secs)))
            for g in range(0, len(ch_secs), chunk_sz):
                chunk = ch_secs[g:g + chunk_sz]
                s_id = make_stage_id(make_path_id("textbook"), stage_global_order)
                c_id = make_chapter_id(s_id, 0)
                suffix = "·上" if g == 0 else ("·中" if g + chunk_sz < len(ch_secs) else "·下")
                stages.append({
                    "id": s_id,
                    "title": f"{ch_title}{suffix if len(ch_secs) > chunk_sz else ''}",
                    "order": stage_global_order,
                    "description": f"学习{ch_title}第{g//chunk_sz + 1}部分",
                    "status": "not_started",
                    "nodes": [],
                    "chapters": [{"id": c_id, "title": ch_title, "order": 0, "sections": chunk, "status": "not_started", "mindmapId": None}],
                    "objective": f"完成{ch_title}第{g//chunk_sz + 1}部分的学习",
                    "estimatedDays": max(1, min(5, total_days // max(1, len(ch_secs) * len(textbook_chapters) // max(2, chunk_sz)))),
                })
                stage_global_order += 1

        logger.info("Built textbook-driven path: %d stages, %d sections (diversified)", len(stages), len(all_sections))
        return stages if stages else None

    # ── Mode A: Focus sprint ──

    def _run_focus_mode(
        self, context: dict, profile: dict, diagnosis: dict,
        weak_points: list, total_days: int,
    ) -> dict[str, Any]:
        return None

    # ── Step 2: DeepTutor as structure source (when chapter generation fails) ──

    def _try_deeptutor_as_structure(self, context: dict, total_days: int) -> list | None:
        """Primary planner: DeepTutor mastery_path, flat stages->tasks."""
        try:
            from app.services.deeptutor_client import deeptutor_call
            course = str(context.get("course_name", "") or context.get("course_id", "") or "")
            message = str(context.get("user_message", "") or "")
            facts = context.get("profile_facts", {}) or {}
            analysis = self._analyze_profile(facts, course)
            p_parts = []
            p_parts.append("学习起点：" + analysis["starting_level"] + "，每天可用约" + str(analysis["daily_minutes_est"]) + "分钟")
            p_parts.append("学习深度：" + analysis["depth"])
            p_parts.append("内容风格偏好：" + analysis["content_style"])
            if analysis["focus_areas"]:
                p_parts.append("重点关注领域：" + "，".join(analysis["focus_areas"]))
            if analysis["domain_context"]:
                p_parts.append("专业背景：" + analysis["domain_context"])
            p_text = chr(10).join(p_parts) if p_parts else ""
            parts = ["为学生规划学习路径。课程：" + course + "。需求：" + message + "。"]
            if total_days:
                parts.append("总学时：" + str(total_days) + "天。")
            # ── v1.2: 教材上下文注入（与 _generate_chapters 一致）──
            textbook_ctx = str(context.get("textbook_context", "") or "")
            if textbook_ctx:
                parts.append(chr(10) * 2 + "【教材参考】" + chr(10) + textbook_ctx)
                parts.append("")
                parts.append("教材参考如上。*** 重要 ***：每个 read_doc 类型任务**必须**包含 source_section_ids 字段，填入对应的教材小节 section_id（取自教材参考）。允许多个小节合并到一个任务中。其他类型（quiz_prac、review 等）不需要此字段。")
            # ────────────────────────────────────────────────────────
            parts.append("请按 stages->tasks 层级输出，每个 stage 直接包含 tasks。")
            parts.append("任务类型必须多样化，从以下选取（每阶段至少3种）：read_doc(阅读讲义)|watch_video(视频)|quiz_prac(练习)|mind_map(导图)|hands_on(实操)|review(复习)")
            parts.append("阶段数量根据知识点自然聚类决定，不设上限。")
            if p_text:
                parts.append(chr(10) * 2 + "【学生画像】" + chr(10) + p_text)
            prompt = chr(10).join(parts)
            dt_result = deeptutor_call("mastery_path", prompt)
            if dt_result and len(dt_result) > 50:
                stages = self._parse_mastery_path(dt_result)
                if stages:
                    return self._rewrite_stage_ids(context, stages)
        except Exception as e:
            logger.debug("DeepTutor mastery_path failed: %s", e)
        return None

    # ── Step 3: LLM pipeline fallback ──

    def _llm_pipeline_fallback(self, context, profile, planning_points, total_days, diag_meta):
        """Original 4-stage LLM pipeline: architect → creator → reviewer → refiner."""
        if diag_meta.get("needs_more_diagnosis") and not planning_points:
            diagnosis = context.get("diagnosis", {})
            planning_points = [self._make_probe_point(diagnosis)]

        architect_plan = self._stage_architect(context, profile, planning_points, total_days, diag_meta)
        if not architect_plan:
            return None

        detailed_stages = self._stage_creator(context, profile, architect_plan, total_days)
        if not detailed_stages:
            return None

        for round_num in range(2):
            review = self._stage_reviewer(detailed_stages, profile, total_days)
            if not review.get("needs_revision"):
                break
            detailed_stages = self._stage_refine(detailed_stages, review, profile, total_days)
            if round_num == 1 and review.get("needs_revision"):
                logger.info("Backtracking to architect after failed reviews")
                arch2 = self._stage_architect(context, profile, planning_points, total_days, diag_meta)
                if arch2:
                    detailed_stages = self._stage_creator(context, profile, arch2, total_days) or detailed_stages

        return detailed_stages

    # ── Step 4: Personalize chapter structure with DeepTutor ──

    def _personalize_with_deeptutor(
        self, chapters: list, context: dict, profile: dict,
        diagnosis: dict, weak_points: list, total_days: int,
    ) -> list | None:
        """Use DeepTutor to adjust chapter pacing/emphasis based on student profile.

        Sends the chapter skeleton + student context to DeepTutor and asks it
        to suggest personalised adjustments: which topics to spend more time on,
        where to insert review days, and difficulty adaptations.
        """
        try:
            from app.services.deeptutor_client import deeptutor_call
        except Exception:
            return None

        # ── Build a compact summary of the chapter structure ──
        chapter_summary_parts = []
        for stage in chapters:
            st_title = stage.get("title", "")
            for ch in stage.get("chapters", []):
                ch_title = ch.get("title", "")
                sec_titles = [s.get("title", "") for s in ch.get("sections", [])[:5]]
                chapter_summary_parts.append(
                    f"  {st_title} > {ch_title}: {'; '.join(sec_titles)}"
                )
        chapter_text = "\n".join(chapter_summary_parts[:30])

        # ── Build student context ──
        facts = context.get("profile_facts", {})
        target = facts.get("target_course", "") or str(context.get("course_id", ""))
        knowledge = facts.get("knowledge_base", "")
        goal = facts.get("learning_goal", "")
        time_info = facts.get("time_budget", "")
        weak_names = [w.get("name", w.get("topic", "")) for w in weak_points[:5]]
        weak_str = "、".join(weak_names) if weak_names else "待诊断"

        prompt = (
            f"你是学习路径个性化专家。学生正在学「{target}」，共 {total_days} 天。\n"
            f"学生基础：{knowledge or '未知'}。目标：{goal or '未知'}。\n"
            f"时间安排：{time_info or '未知'}。薄弱点：{weak_str}。\n\n"
            f"以下是当前的章节结构（骨架）：\n{chapter_text}\n\n"
            f"请基于学生情况给出个性化调整建议，返回 JSON：\n"
            f'{{"adjustments": [\n'
            f'  {{"chapter_title": "章节名", "action": "spend_more_time|spend_less_time|insert_review|skip", '
            f'"reason": "调整原因", "suggested_minutes": 45}}\n'
            f'], "overall_pacing": "aggressive|moderate|gentle", '
            f'"focus_areas": ["重点1", "重点2"]}}\n\n'
            f"只输出 JSON，不要 Markdown 包裹。"
        )

        try:
            raw = deeptutor_call("chat", prompt)
            import json as _json
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s >= 0 and e > s:
                parsed = _json.loads(raw[s:e])
                adjustments = parsed.get("adjustments", [])
                if not adjustments:
                    return None

                # ── Apply adjustments to chapters ──
                adj_map: dict[str, dict] = {
                    a.get("chapter_title", ""): a for a in adjustments
                }
                for stage in chapters:
                    for ch in stage.get("chapters", []):
                        ch_title = ch.get("title", "")
                        adj = adj_map.get(ch_title)
                        if not adj:
                            continue
                        action = adj.get("action", "")
                        if action == "spend_more_time":
                            for sec in ch.get("sections", []):
                                sec["estimated_minutes"] = adj.get(
                                    "suggested_minutes",
                                    sec.get("estimated_minutes", 45),
                                )
                            ch["_dt_action"] = "spend_more_time"
                            ch["_dt_reason"] = adj.get("reason", "")
                        elif action == "insert_review":
                            ch["_dt_review_day"] = True
                            ch["_dt_reason"] = adj.get("reason", "")
                        elif action == "skip":
                            ch["_dt_skip"] = True
                            ch["_dt_reason"] = adj.get("reason", "")

                logger.info(
                    "DeepTutor personalised %d chapters (total adjustments: %d)",
                    sum(1 for s in chapters for c in s.get("chapters", []) if c.get("_dt_action")),
                    len(adjustments),
                )
                return chapters
        except Exception as e:
            logger.debug("DeepTutor personalisation failed: %s", e)

        return None


    # ── 动态调整（M5）──



    # ── Stage 1: Architect ──
    def _stage_architect(self, context, profile, planning_points, total_days, diag_meta):
        if not self.llm_client:
            return None
        try:
            course = str(context.get("course_name", "") or context.get("course_id", "") or "")
            weak_names = [p.get("name", "") for p in planning_points[:10]]
            kp_total = max(1, len(planning_points))
            prompt = f"""你是课程架构师。为「{course}」设计学习路径。
学生：{total_days}天，知识点{kp_total}个，薄弱点：{chr(44).join(weak_names) if weak_names else chr(39)+chr(39)}。
要求：根据知识点自然聚类和难度递进划分阶段数量，不设固定上限。优先覆盖薄弱点，为每个阶段提供所需类型的资源。
输出JSON：{{"stages":[{{"stage_id":"s1","title":"","duration":"","goal":"","tasks":[],"resource_types":[],"estimated_days":N}}],"rationale":""}}"""
            raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=2000)
            s, e = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[s:e]) if s >= 0 and e > s else None
        except Exception as e:
            logger.warning("Architect: %s", e)
            return None

    # ── Stage 2: Creator ──
    def _stage_creator(self, context, profile, architect_plan, total_days):
        if not self.llm_client:
            return None
        try:
            stages_json = json.dumps(architect_plan.get("stages", []), ensure_ascii=False)
            prompt = f"""细化学习阶段：{stages_json}
每个阶段：根据知识点数量灵活细化tasks，任务类型必须多样化（至少包含read_doc/quiz_prac/hands_on/watch_video/mind_map中3种），明确resource_types，total_days匹配{total_days}天。
输出JSON：{{"stages":[...]}}"""
            raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=2500)
            s, e = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[s:e]).get("stages", []) if s >= 0 and e > s else None
        except Exception as e:
            logger.warning("Creator: %s", e)
            return None

    # ── Stage 3: Reviewer ──
    def _stage_reviewer(self, stages, profile, total_days):
        if not self.llm_client:
            return {"needs_revision": False}
        try:
            stages_json = json.dumps(stages, ensure_ascii=False)
            prompt = f"""审查学习路径：{stages_json}
检查：难度递增？时间合理({total_days}天)？任务可执行？逻辑衔接？
输出JSON：{{"passed":true/false,"issues":[],"suggestions":[],"notes":""}}"""
            raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.2, max_tokens=1000)
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s >= 0 and e > s:
                r = json.loads(raw[s:e])
                return {"needs_revision": not r.get("passed", True), "issues": r.get("issues",[]), "suggestions": r.get("suggestions",[]), "notes": r.get("notes","")}
        except Exception as e:
            logger.warning("Reviewer: %s", e)
        return {"needs_revision": False}

    # ── Stage 4: Refine ──
    def _stage_refine(self, stages, review, profile, total_days):
        if not self.llm_client:
            return stages
        try:
            stages_json = json.dumps(stages, ensure_ascii=False)
            issues_text = chr(59).join(review.get("issues", []))
            suggestions_text = chr(59).join(review.get("suggestions", []))
            prompt = f"""修改学习路径：{stages_json}
问题：{issues_text}
建议：{suggestions_text}
输出JSON：{{"stages":[...]}}"""
            raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=2500)
            s, e = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[s:e]).get("stages", stages) if s >= 0 and e > s else stages
        except Exception as e:
            logger.warning("Refine: %s", e)
            return stages

    def _parse_mastery_path(self, raw: str) -> list[dict]:
        """Parse DeepTutor mastery_path output into stage list."""
        import json
        try:
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s >= 0 and e > s:
                parsed = json.loads(raw[s:e])
                return parsed.get("stages", parsed.get("learning_path", []))
        except Exception:
            pass
        return []
    def _generate_chapters(self, context, profile, planning_points, total_days, diag_meta):
        """Fallback planner: web search + LLM. Flat stages->tasks."""
        course = str(context.get("course_name", "") or context.get("course_id", "") or "")
        weak = [p.get("name", "") for p in planning_points[:10]]
        from app.config import settings
        max_tokens = settings.path_max_tokens
        kp_total = max(1, len(planning_points))
        # Profile
        facts = context.get("profile_facts", {}) or {}
        analysis = self._analyze_profile(facts, course)
        pl = []
        pl.append("学习起点：" + analysis["starting_level"] + "，每天约" + str(analysis["daily_minutes_est"]) + "分钟")
        pl.append("学习深度：" + analysis["depth"])
        pl.append("内容风格偏好：" + analysis["content_style"])
        if analysis["focus_areas"]:
            pl.append("重点关注：" + "，".join(analysis["focus_areas"]))
        pb = (chr(10)*2 + "【学生画像】" + chr(10) + chr(10).join(pl) + chr(10)) if pl else ""
        wb = (chr(10) + "薄弱知识点（需重点关注）：" + ", ".join(weak) + chr(10)) if weak else ""
        tb = str(context.get("textbook_context", ""))
        tbb = (chr(10)*2 + tb + chr(10)) if tb else ""
        # Web search
        sb = ""
        try:
            from app.services.search_client import get_search_client
            client = get_search_client("duckduckgo")
            resp = client.search(course + " 课程大纲 核心知识点 学习路径", max_results=5)
            if resp and resp.results:
                items = []
                for r in resp.results[:5]:
                    t = (r.title or "").strip()
                    s = (r.snippet or "").strip()
                    if t or s: items.append("- " + (t + ": " + s if t and s else (t or s)))
                if items:
                    sb = chr(10)*2 + "【网络搜索结果】" + chr(10) + chr(10).join(items) + chr(10)
        except Exception as exc:
            logger.debug("Web search failed: %s", exc)
        # Prompt
        parts = [
            "你是课程设计师和学习路径规划专家。请为「%s」设计一份完整、科学的个性化学习路径。" % course,
            "",
            "【设计要求】",
            "- 总学时：%d天，共%d个知识点" % (total_days, kp_total),
            "- 请根据知识点自然分组设计阶段数量，不设阶段数上限",
            "- 按 stages->tasks 层级：每个 stage 直接包含 tasks",
            "- 任务类型必须多样化，根据课程内容特点从以下选取（每个阶段至少3种）：",
            "  read_doc(讲义阅读) | watch_video(视频学习) | quiz_prac(练习测验) | mind_map(思维导图) | hands_on(实操练习) | review(阶段复习)",
            "- 每条 task 必填：title（任务名）、type（从上述选）、estimated_minutes（分钟）、goal（目标）、resource_types（如[\"lecture\",\"quiz\"]）",
            "- 每天的任务数根据知识点密度和学生可用时间灵活决定",
        ]
        # ── Textbook context instruction ──
        if tbb:
            parts.extend([
                "",
                "【教材参考 — 重要】",
                "上面提供了这本教材的完整章节目录。你必须遵循以下规则：",
                "- read_doc 类型的任务应当对应教材中的小节。在 source_section_ids 字段中填入教材小节ID（方括号中的值，如 sec_01_01）。",
                "- 可以将多个短小的教材小节合并为一个 read_doc 任务（source_section_ids 填入多个ID）。",
                "- 不是所有任务都需要教材小节——quiz_prac、review 等类型的任务可以不填 source_section_ids。",
                "- source_section_ids 为可选字段，无对应教材小节时可省略或填 []。",
            ])
        parts.append("Use 4 to 6 stages, ordered by prerequisites rather than textbook chapter count.")
        for b in [tbb, pb, wb, sb]:
            if b: parts.append(b.strip())
        parts.extend(["", "【输出格式】",
            "严格按照以下 JSON 格式输出，不要包含 Markdown 包裹或额外说明：",
            "{", '  "stages": [', "    {",
            '      "title": "阶段标题（如：逻辑代数基础·上）",',
            '      "theme": "阶段主题说明",',
            '      "estimated_days": 3,', '      "tasks": [', '        {',
            '          "title": "阅读讲义",', '          "type": "read_doc",',
            '          "estimated_minutes": 30,', '          "goal": "理解核心概念",',
            '          "required": true,', '          "resource_types": ["lecture","reading"],',
            '          "source_section_ids": ["sec_01_01"]',
            '        },', '        {',
            '          "title": "巩固练习",', '          "type": "quiz_prac",',
            '          "estimated_minutes": 35,', '          "goal": "通过做题检验理解",',
            '          "required": true,', '          "resource_types": ["quiz","homework"]',
            '        }', '      ]', '    }', '  ]', '}'])
        prompt = chr(10).join(parts)
        if self.llm_client:
            try:
                raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=max_tokens)
                bs, be = raw.find("{"), raw.rfind("}") + 1
                if bs >= 0 and be > bs:
                    data = json.loads(raw[bs:be])
                    stages = data.get("stages", [])
                    if not stages: return None
                    return self._rewrite_stage_ids(context, stages)
            except Exception:
                pass
        return None
    def _ensure_task_diversity(self, tasks: list, stage_title: str, stage_id: str) -> list:
        """确保每个阶段至少3种任务类型。"""
        if len(tasks) >= 12:
            return tasks
        _all = [
            ("read_doc","阅读：{t}核心内容",["lecture","reading"],30),
            ("watch_video","视频：{t}教学视频",["video"],25),
            ("quiz_prac","练习：{t}巩固测验",["quiz","homework"],35),
            ("mind_map","导图：{t}思维整理",["mindmap"],20),
            ("hands_on","实操：{t}动手练习",["lab","code"],40),
            ("review","复习：{t}阶段回顾",["quiz","reading"],25),
        ]
        existing = {str(t.get("type","")).strip() for t in tasks if t.get("type")}
        if len(existing) >= 3:
            return tasks
        out = list(tasks)
        st = stage_title or "当前阶段"
        for tt, tmpl, rts, est in _all:
            if tt not in existing and len(out) < 12:
                out.append({"task_id":f"{stage_id}_auto_{tt}","title":tmpl.replace("{t}",st),"type":tt,"estimated_minutes":est,"goal":f"通过{tt}方式巩固{st}的学习","required":False,"resource_types":rts,"status":"pending","source":"diversity_ensured"})
                existing.add(tt)
            if len(existing) >= 3:
                break
        return out
    def _rewrite_stage_ids(self, context: dict, stages: list) -> list:
        """Rewrite IDs for stages->days->tasks format."""
        session_id = str(context.get("session_id", "") or "")
        path_id = ("path_" + session_id) if session_id else "path_local"
        rewritten = []
        for si, stage in enumerate(stages):
            stage_id = f"{path_id}_s{si}"
            raw_days = stage.get("days", [])
            if not raw_days and stage.get("tasks"):
                raw_days = [{"day": 1, "tasks": stage["tasks"]}]
            if not raw_days:
                raw_days = [{"day": 1, "tasks": [{"title": stage.get("title", ""), "type": "read_doc"}]}]
            day_list = []
            for di, d in enumerate(raw_days):
                day_num = d.get("day", di + 1)
                task_list = []
                for ti, t in enumerate(d.get("tasks", [])):
                    if isinstance(t, str):
                        t = {"title": t, "type": "read_doc", "estimated_minutes": 45, "goal": t[:200]}
                    task_id = t.get("task_id") or t.get("id") or f"{stage_id}_d{day_num}_t{ti}"
                    task_list.append({
                        "task_id": task_id,
                        "title": str(t.get("title", t.get("name", f"任务{ti+1}"))),
                        "type": str(t.get("type", "read_doc")),
                        "estimated_minutes": int(t.get("estimated_minutes", t.get("minutes", 45))),
                        "goal": str(t.get("goal", t.get("description", ""))),
                        "required": bool(t.get("required", True)),
                        "resource_types": t.get("resource_types", ["lecture"]),
                        "status": t.get("status", "pending"),
                        "source": t.get("source", "generated"),
                        "_adjustment": t.get("_adjustment", ""),
                        "_adjustment_reason": t.get("_adjustment_reason", ""),
                        # ── Textbook fields: only preserve section IDs — page
                        #    numbers are resolved later by _resolve_textbook_pages
                        #    (the sole authority), never trust LLM output.
                        "source_section_ids": t.get("source_section_ids") or t.get("textbook_section_ids", []),
                    })
                day_list.append({"day": day_num, "tasks": task_list})
            # 确保多样性
            task_list = self._ensure_task_diversity(task_list, str(stage.get("title","")), stage_id)
            day_list = [{"day": day_list[0]["day"] if day_list else 1, "tasks": task_list}]
            rewritten.append({
                "stage_id": stage_id,
                "title": str(stage.get("title", "")),
                "order": si,
                "theme": str(stage.get("theme", stage.get("objective", ""))),
                "days": day_list,
            })
        return rewritten

    def _rewrite_chapter_ids(self, context, chapters: list) -> list:
        """Rewrite LLM-generated IDs with canonical, stable IDs."""
        session_id = str(context.get("session_id", "") or "")
        course_id = str(context.get("course_id", "") or "")
        path_id = make_path_id(session_id)

        rewritten = []
        for stage_index, stage in enumerate(chapters):
            # If the LLM returned chapters directly (not wrapped in stages),
            # treat them as one stage
            stage_id = make_stage_id(path_id, stage_index)
            rewritten_stage = {
                "stage_id": stage_id,
                "title": stage.get("title", f"阶段 {stage_index + 1}"),
                "order": stage_index,
                "chapters": [],
                "focus": stage.get("focus", ""),
                "reason": stage.get("reason", ""),
                "estimated_days": stage.get("estimated_days", stage.get("estimatedDays", 0)),
            }
            raw_chapters = stage.get("chapters") or [stage]  # support nested or flat
            for ch_index, ch in enumerate(raw_chapters):
                chapter_id = make_chapter_id(stage_id, ch_index)
                rewritten_ch = {
                    "chapter_id": chapter_id,
                    "title": ch.get("title", f"第{ch_index + 1}章"),
                    "order": ch_index,
                    "sections": [],
                }
                for sec_index, sec in enumerate(ch.get("sections", [])):
                    section_id = make_section_id(chapter_id, sec_index)
                    kps = []
                    for kp_index, kp in enumerate(sec.get("knowledge_points", [])):
                        kps.append({
                            "kp_id": make_kp_id(section_id, kp_index),
                            "name": kp.get("name", ""),
                            "type": kp.get("type", "concept"),
                        })
                    rewritten_ch["sections"].append({
                        "section_id": section_id,
                        "title": sec.get("title", f"{sec_index + 1}.{sec_index + 1}"),
                        "goal": sec.get("goal", ""),
                        "estimated_minutes": sec.get("estimated_minutes", 45),
                        "content_type": sec.get("content_type", "lecture"),
                        "knowledge_points": kps,
                        "textbook_section_ids": sec.get("textbook_section_ids", []),
                        # ── Preserve fields from upstream (daily/focus/textbook modes) ──
                        "task_type": sec.get("task_type", ""),
                        "textbookPageStart": sec.get("textbookPageStart", sec.get("start_page", 1)),
                        "textbookPageEnd": sec.get("textbookPageEnd", sec.get("end_page", 1)),
                        "textbookSectionId": sec.get("textbookSectionId", sec.get("section_id", "")),
                    })
                rewritten_stage["chapters"].append(rewritten_ch)
            rewritten.append(rewritten_stage)
        return rewritten

    def _make_chapter_result(self, stages_with_chapters, total_days, diag_meta):
        """Wrap chapter-structured stages into the canonical result format.

        Each stage already contains chapters → sections → knowledge_points
        with canonical IDs from _rewrite_chapter_ids.
        """
        # Normalize stage estimated_days to sum to total_days
        stages_with_chapters = self._normalize_stage_days(stages_with_chapters, total_days)

        # v1.2: 兼容扁平 stages→days→tasks 格式（新）与层级 stages→chapters→sections（旧）
        _has_flat = any(s.get("days") for s in stages_with_chapters) if stages_with_chapters else False
        if _has_flat:
            total_chapters = sum(
                sum(1 for d in s.get("days", []) for _t in d.get("tasks", []))
                for s in stages_with_chapters
            )
            total_sections = total_chapters  # 扁平格式中 task 即"节"
            total_kps = sum(
                len(s.get("knowledge_points", s.get("knowledgePoints", [])))
                for s in stages_with_chapters
            )
            estimated_minutes_total = sum(
                t.get("estimated_minutes", 45)
                for s in stages_with_chapters
                for d in s.get("days", [])
                for t in d.get("tasks", [])
            )
        else:
            total_chapters = sum(len(s.get("chapters", [])) for s in stages_with_chapters)
            total_sections = sum(
                len(c.get("sections", []))
                for s in stages_with_chapters
                for c in s.get("chapters", [])
            )
            total_kps = sum(
                len(sec.get("knowledge_points", []))
                for s in stages_with_chapters
                for c in s.get("chapters", [])
                for sec in c.get("sections", [])
            )
            estimated_minutes_total = sum(
                sec.get("estimated_minutes", 45)
                for s in stages_with_chapters
                for c in s.get("chapters", [])
                for sec in c.get("sections", [])
            )
        # ── 生成按天组织的学习计划 ──
        day_plan = self._build_day_plan(stages_with_chapters, diag_meta)
        return {
            "learning_path": stages_with_chapters,
            "stages": stages_with_chapters,
            "chapters": stages_with_chapters,
            "day_plan": day_plan,
            "estimatedDays": total_days,
            "dailyMinutes": diag_meta.get("daily_minutes", 60),
            "estimated_minutes_total": estimated_minutes_total,
            "version": int(time.time() * 1000),
            "section_count": total_sections,
            "knowledge_point_count": total_kps,
            "plan_summary": f"{len(stages_with_chapters)}阶段{total_chapters}章{total_sections}节{total_kps}知识点",
            "summary": f"{len(stages_with_chapters)}阶段{total_chapters}章{total_sections}节",
            "day_plan": day_plan,
            "diagnosis_used": diag_meta.get("diagnosis_used", False),
            "needs_more_diagnosis": diag_meta.get("needs_more_diagnosis", False),
            "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name, "status": "completed"},
        }

    @staticmethod
    def _build_day_plan(stages: list[dict], diag_meta: dict) -> dict:
        """从 stages 生成按天组织的学习计划。"""
        try:
            weekend_off = bool(diag_meta.get("time_basis", {}).get("schedule_limited", False)) if diag_meta else False
            return build_day_plan(stages, daily_minutes=diag_meta.get("daily_minutes", 60), weekend_off=weekend_off)
        except Exception:
            logger.exception("build_day_plan failed")
            return {}

    def _fallback_path(self, context, planning_points, total_days, profile, diag_meta):
        rule_path = self._build_rule_path(planning_points, profile, total_days, diag_meta)
        diag_meta["daily_minutes"] = self._infer_daily_minutes(context, profile)
        rule_path = self._normalize_stage_days(rule_path, total_days)
        self._materialize_daily_tasks(rule_path, diag_meta["daily_minutes"], context)
        result = self._make_result(rule_path, total_days, diag_meta)
        result["dailyMinutes"] = diag_meta["daily_minutes"]
        result["day_plan"] = self._build_day_plan(rule_path, diag_meta)
        result["review_tasks"] = self._generate_review_tasks(rule_path)
        result["planner_metadata"] = {"stages": len(rule_path), "reviewed": False, "revisions": 0, "backtracked": False, "revision_notes": "LLM不可用，使用规则生成"}
        return result

    def _run_adjustment(self, context: dict, diagnosis: dict, profile: dict) -> dict:
        """基于诊断结果动态调整已有学习路径 —— section/KP 级别。

        不再只改 stage duration 字符串，而是深入到 section 和 knowledge_point 粒度：
        - 某知识点评分≥95（精通） → 对应 section 标记 mastered，缩短学时
        - 某知识点评分≤40（未掌握） → 对应 section 标记 needs_review，延长学时+插入前置回顾
        - 掌握度变化 → 反映到 section 的 estimated_minutes 和 content_type
        """
        existing_path = list(context.get("existing_path", []) or [])
        mastery_levels = diagnosis.get("mastery_levels", []) or []
        grading_results = context.get("grading_results", []) or []

        # ── 读取 diagnosis 全量字段，不止 mastery_levels ──
        evidence_chain = diagnosis.get("evidence_chain", []) or []
        risk_flags = diagnosis.get("risk_flags", []) or []
        strengths = diagnosis.get("strengths", []) or []
        weak_topics = diagnosis.get("weak_topics", []) or diagnosis.get("weak_knowledge_points", []) or []
        needs_more_evidence = bool(diagnosis.get("needs_more_evidence", False))

        # 构建更丰富的弱点信息（含证据类型和优先级）
        weak_detail: dict[str, dict] = {}
        for wt in weak_topics:
            if isinstance(wt, dict):
                name = str(wt.get("name", "") or wt.get("topic", ""))
                if name:
                    weak_detail[name] = {
                        "reason": str(wt.get("reason", "")),
                        "evidence": str(wt.get("evidence", "")),
                        "priority": str(wt.get("priority", "medium")),
                        "confidence": float(wt.get("confidence", 0.5)),
                    }
        adjustments: list[str] = []

        if not existing_path:
            return self._make_result([], 14, {"diagnosis_used": False, "needs_more_diagnosis": True,
                                              "weak_topic_names": [], "evidence_sources": [], "risk_flags": ["no_existing_path"],
                                              "total_days": 14, "time_basis": {"has_time_budget": False}})

        # ── Build mastery lookup: kp_name → {score, level} ──
        mastery_map: dict[str, dict] = {}
        for m in mastery_levels:
            if isinstance(m, dict):
                name = str(m.get("name", "")).strip()
                if name:
                    mastery_map[name] = {"score": float(m.get("score", 50)), "level": str(m.get("level", ""))}

        # ── 统计连续作答表现 ──
        consecutive_correct = 0
        consecutive_wrong = 0
        for g in reversed(grading_results[-10:]):
            if not isinstance(g, dict):
                continue
            score = g.get("total_score", 50)
            if score is not None and score >= 80:
                consecutive_correct += 1
                consecutive_wrong = 0
            elif score is not None and score < 40:
                consecutive_wrong += 1
                consecutive_correct = 0

        def _adjust_section(sec: dict, stage_title: str) -> dict:
            """调整单个 section：匹配 mastery_map，返回带调整标记的 section。"""
            sec = dict(sec)
            kps = sec.get("knowledge_points", [])
            if not kps or not isinstance(kps, list):
                kps = [{"name": sec.get("title", ""), "type": "concept"}]

            kp_statuses: list[str] = []  # "mastered" | "weak" | "unknown"
            total_kp_score = 0
            matched_kp_count = 0

            for kp in kps:
                kp_name = str(kp.get("name", "")).strip()
                km = mastery_map.get(kp_name)
                if km:
                    matched_kp_count += 1
                    score = km["score"]
                    total_kp_score += score
                    if score >= 85:
                        kp_statuses.append("mastered")
                    elif score <= 40:
                        kp_statuses.append("weak")
                    else:
                        kp_statuses.append("progress")
                else:
                    kp_statuses.append("unknown")

            if matched_kp_count == 0:
                # 无诊断数据：保持原样
                return sec

            avg_score = total_kp_score / matched_kp_count if matched_kp_count > 0 else 50
            base_minutes = sec.get("estimated_minutes", 45)

            # ── 根据 KP 掌握情况决策 ──
            all_mastered = all(s == "mastered" for s in kp_statuses)
            any_weak = any(s == "weak" for s in kp_statuses)
            has_progress = any(s == "progress" for s in kp_statuses)

            if all_mastered:
                # 全部精通 → 极速回顾
                sec["estimated_minutes"] = max(10, base_minutes // 3)
                sec["_adjustment"] = "accelerated"
                sec["_adjustment_reason"] = f"知识点均已达精通（avg={avg_score:.0f}分），仅需快速回顾"
                sec["content_type"] = "review"
            elif any_weak and not has_progress:
                # 全部或多数薄弱 → 大幅强化
                sec["estimated_minutes"] = min(120, base_minutes * 2)
                sec["_adjustment"] = "strengthened"
                sec["_adjustment_reason"] = f"知识点掌握度较低（avg={avg_score:.0f}分），需强化学习"
                # 改为分步推导+练习模式
                if sec.get("content_type") in ("lecture", "memory_drill"):
                    sec["content_type"] = "step_through"
            elif any_weak and has_progress:
                # 既有薄弱又有进展 → 标注薄弱KP，增加练习
                sec["estimated_minutes"] = int(base_minutes * 1.3)
                sec["_adjustment"] = "mixed"
                weak_kps = [kp["name"] for kp in kps if mastery_map.get(str(kp.get("name", "")), {}).get("score", 50) <= 40]
                sec["_adjustment_reason"] = f"部分知识点需重点突破：{'、'.join(weak_kps)}"
                sec["_weak_kps"] = weak_kps
            else:
                # 正常进展
                sec["estimated_minutes"] = max(20, int(base_minutes * (1 - (avg_score - 50) / 200)))
                sec["_adjustment"] = "normal"

            return sec

        # ── 对每个 stage 的每个 section 应用调整 ──
        adjusted_path = []
        for stage in existing_path:
            if not isinstance(stage, dict):
                adjusted_path.append(stage)
                continue

            stage = dict(stage)
            chapters = stage.get("chapters", [])
            stage_title = str(stage.get("title", ""))

            if chapters and isinstance(chapters, list):
                # ── 新版：chapters → sections 结构 ──
                new_chapters = []
                for ch in chapters:
                    ch = dict(ch)
                    sections = ch.get("sections", [])
                    new_sections = [_adjust_section(s, stage_title) for s in sections]
                    ch["sections"] = new_sections

                    # 汇总 chapter 层级的调整标记
                    sec_adjustments = [s.get("_adjustment", "") for s in new_sections]
                    if "strengthened" in sec_adjustments:
                        ch["_adjustment"] = "strengthened"
                    elif "mixed" in sec_adjustments:
                        ch["_adjustment"] = "mixed"
                    elif all(a == "accelerated" for a in sec_adjustments if a):
                        ch["_adjustment"] = "accelerated"

                    new_chapters.append(ch)

                stage["chapters"] = new_chapters

                # ── 从 section 级重新估算 stage 天数 ──
                total_sec_minutes = sum(
                    s.get("estimated_minutes", 45)
                    for ch in new_chapters
                    for s in ch.get("sections", [])
                )
                # 假设每天有效学习 90 分钟
                new_days = max(1, round(total_sec_minutes / 90))
                old_days = self._parse_duration_days(str(stage.get("duration", "")))
                if new_days != old_days:
                    stage["estimated_days"] = new_days
                    stage["_days_adjustment"] = f"{old_days}→{new_days}天"
                    adjustments.append(f"调整 {stage_title}：{old_days}天→{new_days}天（基于section级掌握度）")

                # 如果有 accelerated + strengthened 混合，记录
                sec_adj_types = set(s.get("_adjustment", "") for ch in new_chapters for s in ch.get("sections", []))
                # 将 section 级 _adjustment 汇总到 stage，前端靠这个渲染徽章
                if "strengthened" in sec_adj_types:
                    stage["_adjustment"] = "strengthened"
                elif "mixed" in sec_adj_types:
                    stage["_adjustment"] = "mixed"
                elif sec_adj_types == {"accelerated"}:
                    stage["_adjustment"] = "accelerated"
                if "strengthened" in sec_adj_types:
                    adj_kps = []
                    for ch in new_chapters:
                        for s in ch.get("sections", []):
                            if s.get("_adjustment") == "strengthened":
                                adj_kps.append(s.get("title", ""))
                    if adj_kps:
                        adjustments.append(f"强化小节：{'、'.join(adj_kps[:3])}")
                if "accelerated" in sec_adj_types:
                    fast_kps = []
                    for ch in new_chapters:
                        for s in ch.get("sections", []):
                            if s.get("_adjustment") == "accelerated":
                                fast_kps.append(s.get("title", ""))
                    if fast_kps:
                        adjustments.append(f"加速小节（已掌握）：{'、'.join(fast_kps[:3])}")

            else:
                # ── 旧版：flat tasks 结构（保持原逻辑降级） ──
                stage_tasks = list(stage.get("tasks", []))
                duration_str = str(stage.get("duration", ""))
                days = self._parse_duration_days(duration_str)
                mastery = next((m for m in mastery_levels if isinstance(m, dict) and m.get("name", "") in stage_title), None)
                adj = dict(stage)
                if mastery:
                    score = mastery.get("score", 50)
                    level = mastery.get("level", "")
                    if level == "精通" and score >= 85:
                        new_days = max(1, days // 3)
                        adj["duration"] = f"第{days}-{new_days}天（加速）"
                        adj["_adjustment"] = "accelerated"
                        adjustments.append(f"加速 {stage_title}：{days}天→{new_days}天")
                    elif level == "未学" and score < 40:
                        new_days = min(days + 3, 14)
                        adj["duration"] = f"第{days}-{new_days}天（强化）"
                        adj["tasks"] = stage_tasks + self._trace_prerequisites_bfs(stage_title, context)
                        adj["_adjustment"] = "strengthened"
                        adjustments.append(f"强化 {stage_title}：{days}天→{new_days}天")
                adj.setdefault("reason", stage.get("reason", ""))
                adjusted_path.append(adj)
                continue

            adjusted_path.append(stage)

        # ── 连续错题 → 插入前置知识补救阶段（section 级别） ──
        if consecutive_wrong >= 2 and mastery_levels:
            weak_kps = [m for m in mastery_levels if isinstance(m, dict) and m.get("score", 50) <= 40]
            weak_names = [m.get("name", "") for m in weak_kps[:3]]
            if weak_names:
                # 构建补救章节，包含对薄弱 KPs 的回顾 section
                remedial_chapters = [{
                    "chapter_id": "ch_remedial",
                    "title": "前置知识补救",
                    "order": 0,
                    "sections": [
                        {
                            "section_id": f"sec_remedial_{i}",
                            "title": f"回顾：{name}",
                            "goal": f"快速回顾 {name} 的核心概念和基础题型，为后续学习扫清障碍",
                            "estimated_minutes": 30,
                            "content_type": "step_through",
                            "knowledge_points": [{"name": name, "type": "concept"}],
                            "_adjustment": "remedial",
                        }
                        for i, name in enumerate(weak_names)
                    ],
                }]
                adjusted_path.insert(0, {
                    "stage_id": "stage_remedial",
                    "title": f"前置知识补救：{'、'.join(weak_names)}",
                    "order": 0,
                    "goal": f"连续{consecutive_wrong}题错误，先回顾前置基础再继续后续学习。",
                    "estimated_days": max(1, len(weak_names)),
                    "chapters": remedial_chapters,
                    "_adjustment": "remedial",
                    "source": "dynamic_adjustment",
                })
                adjustments.append(f"连续{consecutive_wrong}题错误→插入前置知识补救阶段（{'、'.join(weak_names)}）")

        # ── 考前冲刺模式 ──
        exam_keywords = ["考试", "期末", "考研", "高分"]
        user_msg = str(context.get("user_message", ""))
        if any(w in user_msg for w in exam_keywords):
            for stage in adjusted_path:
                for ch in stage.get("chapters", []):
                    for sec in ch.get("sections", []):
                        if sec.get("content_type") in ("lecture", "review"):
                            sec["content_type"] = "step_through"
                            sec["estimated_minutes"] = max(
                                20, int(sec.get("estimated_minutes", 45) * 0.8)
                            )
            adjustments.append("检测到考试目标→切换到考前冲刺模式（step_through+减少讲义时间）")

        # ── DeepTutor 间隔复习：到期知识点自动插入复习任务 ──
        due_reviews = diagnosis.get("_due_reviews", []) or []
        if due_reviews:
            review_stage = {
                "stage_id": "stage_review_dt",
                "title": "间隔复习（系统自动）",
                "order": 0,
                "goal": "根据艾宾浩斯遗忘曲线，以下知识点已到复习时间",
                "estimated_days": 1,
                "chapters": [{
                    "chapter_id": "ch_review_dt",
                    "title": "到期复习",
                    "order": 0,
                    "sections": [
                        {
                            "section_id": f"sec_review_{i}",
                            "title": f"复习：{r.get('knowledge_point_name', r.get('knowledge_point_id', ''))}",
                            "goal": f"快速回顾已学内容，巩固长期记忆（第{r.get('interval_index', 0)+1}轮复习）",
                            "estimated_minutes": 15,
                            "content_type": "review",
                            "knowledge_points": [{"name": r.get("knowledge_point_name", ""), "type": "concept"}],
                            "_adjustment": "review_due",
                        }
                        for i, r in enumerate(due_reviews[:5])
                    ],
                }],
                "_adjustment": "review_due",
                "source": "dt_scheduler",
                "_needs_questions": True,  # 触发 question_agent 出复习题
            }
            adjusted_path.insert(0, review_stage)
            adjustments.append(f"DeepTutor间隔复习：{len(due_reviews[:5])}个知识点到期，已插入复习阶段")

        # ── 节奏感知(按天移动平均, 优先用completionTrend) ──
        analytics = context.get("analytics", {}) or {}
        pacing_ratio = 1.0
        completion_trend = analytics.get("completionTrend", []) or []
        if completion_trend and len(completion_trend) >= 3:
            recent = [d.get("count", 0) for d in completion_trend[-5:] if isinstance(d, dict)]
            if recent:
                daily_avg = sum(recent) / len(recent)
                planned_daily = self._analyze_profile(context.get("profile_facts",{}),"").get("daily_minutes_est",60)
                pacing_ratio = (daily_avg * 15) / max(1, planned_daily)
        else:
            actual_minutes = int(analytics.get("totalStudyMinutes", 0))
            if actual_minutes > 0 and total_days > 0:
                actual_daily_min = max(10, actual_minutes // max(1, total_days))
                planned_daily = self._analyze_profile(context.get("profile_facts",{}),"").get("daily_minutes_est",60)
                pacing_ratio = actual_daily_min / max(1, planned_daily)
        # pacing_ratio > 1.2 = 学得快，压缩； < 0.8 = 学得慢，放宽
            if pacing_ratio > 1.2:
                factor = max(0.5, 1.0 / pacing_ratio)
                for stage in adjusted_path:
                    if isinstance(stage, dict):
                        old_days = stage.get("estimated_days", 1)
                        stage["estimated_days"] = max(1, int(old_days * factor))
                        stage["_pacing_adjusted"] = True
                adjustments.append(
                    f"学习节奏快{int(pacing_ratio*100)}%，剩余阶段压缩至{int(factor*100)}%天数"
                )
            elif pacing_ratio < 0.8:
                factor = min(2.0, 1.0 / pacing_ratio)
                for stage in adjusted_path:
                    if isinstance(stage, dict):
                        old_days = stage.get("estimated_days", 1)
                        stage["estimated_days"] = max(1, int(old_days * factor))
                        stage["_pacing_adjusted"] = True
                adjustments.append(
                    f"学习节奏慢{int(pacing_ratio*100)}%，剩余阶段放宽至{int(factor*100)}%天数"
                )

        # ── 判断是否需要静默应用（仅节奏调整，无结构性变化）──
        has_structural_change = any(
            s.get("_adjustment", "") in ("remedial", "strengthened", "accelerated")
            for s in adjusted_path if isinstance(s, dict)
        )
        apply_silently = not has_structural_change and any(
            s.get("_pacing_adjusted") for s in adjusted_path if isinstance(s, dict)
        )

        # ── 统计并生成结果 ──
        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)

        diag_meta = {
            "diagnosis_used": True,
            "weak_topic_names": [m.get("name", "") for m in mastery_levels[:5] if isinstance(m, dict)],
            "needs_more_diagnosis": len(mastery_levels) < 3,
            "evidence_sources": ["diagnosis_mastery", "grading_results"],
            "risk_flags": ["dynamic_adjustment"] + (["time_budget_tight"] if consecutive_correct >= 3 else []),
            "total_days": total_days,
        }

        result = self._make_result(adjusted_path, total_days, diag_meta)
        result["adjustments"] = adjustments
        result["review_tasks"] = self._generate_review_tasks(adjusted_path)
        result["consecutive_correct"] = consecutive_correct
        result["consecutive_wrong"] = consecutive_wrong
        result["apply_silently"] = apply_silently  # 仅节奏变化时静默应用，不弹窗

        # ── 构建 _agent_context 供下游 agent 协同 ──
        adj_types = set(
            s.get("_adjustment", "")
            for s in adjusted_path if isinstance(s, dict)
        )
        target_stages = [
            s.get("stage_id", "")
            for s in adjusted_path if isinstance(s, dict) and s.get("_adjustment") in ("remedial", "strengthened", "accelerated")
        ]
        result["_agent_context"] = {
            "action": "adjusted_path",
            "target_stages": target_stages,
            "reason": "; ".join(adjustments[:3]) if adjustments else "基于诊断数据调整节奏",
            "needs_resources": ["lecture", "quiz", "practice"],
            "focus_topics": [wt.get("name","") or wt.get("topic","") for wt in weak_topics[:8] if isinstance(wt, dict) and (wt.get("name") or wt.get("topic"))],
            "urgency": "high" if consecutive_wrong >= 2 else "medium",
            "adjustment_types": list(adj_types),
            "mastery_snapshot": {
                n: {"score": float(m.get("score",50)), "level": str(m.get("level",""))}
                for m in mastery_levels if isinstance(m,dict) and m.get("name")
                for n in [str(m["name"])]
            },
        }
        return result


    # ── Prerequisite validation ──

    def _validate_prerequisites(self, chapters: list, context: dict) -> list:
        """Reorder sections so prerequisites come before dependents."""
        adj = {}
        course = context.get("course", {}) if isinstance(context.get("course"), dict) else {}
        for ch in course.get("chapters", []):
            if isinstance(ch, dict):
                title = str(ch.get("title", ""))
                prereqs = [str(p) for p in (ch.get("prerequisites", []) or []) if p]
                if title and prereqs:
                    adj[title] = prereqs
        for stage in chapters:
            for chapter in stage.get("chapters", []):
                sections = chapter.get("sections", [])
                titles = [s.get("title", "") for s in sections if s.get("title")]
                if not adj or not titles:
                    continue
                for i in range(len(titles)):
                    for j in range(i + 1, len(titles)):
                        deps_of_i = adj.get(titles[i], [])
                        if titles[j] in deps_of_i:
                            sections[i], sections[j] = sections[j], sections[i]
                            titles[i], titles[j] = titles[j], titles[i]
                            break
                    else:
                        continue
                    break
        return chapters

    @staticmethod
    def _normalize_stage_days(stages: list[dict], total_days: int) -> list[dict]:
        """Ensure stage estimated_days sum to approximately total_days."""
        if not stages:
            return stages
        raw_days = [s.get("estimated_days", s.get("estimatedDays", 0)) or (re.findall(r"\d+", str(s.get("duration", ""))) or [0])[0] for s in stages]
        raw_days = [int(days) for days in raw_days]
        raw_sum = sum(raw_days)
        if raw_sum <= 0 or raw_sum == total_days:
            return stages
        ratio = total_days / raw_sum
        cumulative = 0
        for i, s in enumerate(stages):
            if i == len(stages) - 1:
                d = total_days - cumulative
            else:
                d = max(1, round(raw_days[i] * ratio))
            cumulative += d
            s["estimated_days"] = d
            s["estimatedDays"] = d
        return stages

    @staticmethod
    def _adjustment_needs_restructure(context: dict, diagnosis: dict) -> bool:
        """Return True if adjustment requires full re-planning instead of lightweight tweaks.

        Re-plan when:
        - No existing path → must plan from scratch
        - Any mastery score ≤ 40 (base weak) → needs content restructuring
        """
        existing_path = context.get("existing_path", []) or []
        if not existing_path:
            return True

        mastery_levels = diagnosis.get("mastery_levels", []) or []
        for m in mastery_levels:
            if isinstance(m, dict):
                score = m.get("score", 50)
                if score <= 40:
                    return True
        return False

    def _parse_duration_days(self, duration: str) -> int:
        """解析 duration 字符串中的天数。"""
        nums = re.findall(r"\d+", duration)
        if len(nums) >= 2:
            return max(1, int(nums[1]) - int(nums[0]) + 1)
        if len(nums) == 1:
            return int(nums[0])
        return 3

    # ── 艾宾浩斯复习调度（M5）──

    def _generate_review_tasks(self, path: list[dict]) -> list[dict]:
        """基于艾宾浩斯遗忘曲线生成复习任务。
        新学知识点 → 第1天 → 第2天 → 第4天 → 第7天 → 第15天 → 第30天
        """
        intervals = [1, 2, 4, 7, 15, 30]
        review_tasks = []

        for stage in path:
            if not isinstance(stage, dict):
                continue
            title = str(stage.get("title", ""))
            stage_id = str(stage.get("stage_id", ""))
            tasks = stage.get("tasks", []) or [title]

            for interval in intervals:
                review_tasks.append({
                    "stage_id": stage_id,
                    "knowledge_point": title,
                    "interval_days": interval,
                    "review_content": f"快速回顾 {title} 的核心要点和错题",
                    "estimated_minutes": max(10, 5 * interval),  # 间隔越久复习越久
                })

        return review_tasks

    @staticmethod
    def get_review_for_today(review_tasks: list[dict], day_index: int) -> list[dict]:
        """获取当天应完成的复习任务。"""
        return [t for t in review_tasks if isinstance(t, dict) and t.get("interval_days") == day_index]

    # ── 前置依赖 BFS 追溯（M5）──

    def _trace_prerequisites_bfs(self, stage_title: str, context: dict) -> list[str]:
        """BFS 反向追溯前置依赖链，返回需回顾的前置知识任务列表。

        从给定知识点出发，沿 prerequisites 边逐层回溯，收集所有前置节点名。
        """
        visited: set[str] = set()
        queue: list[str] = [stage_title]
        prereq_names: list[str] = []

        # 构建知识点邻接表（名称 → 前置依赖列表）
        adj: dict[str, list[str]] = {}
        course = context.get("course", {}) if isinstance(context.get("course"), dict) else {}
        for ch in course.get("chapters", []):
            if isinstance(ch, dict) and ch.get("title"):
                adj[str(ch["title"])] = [str(p) for p in (ch.get("prerequisites", []) or []) if p]
        # 也从学习路径阶段提取
        for stage in (context.get("existing_path") or context.get("learning_path") or []):
            if isinstance(stage, dict) and stage.get("title"):
                title = str(stage["title"])
                if title not in adj:
                    adj[title] = [str(p) for p in (stage.get("prerequisites", []) or []) if p]

        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            # 获取该节点的前置依赖
            prereqs = adj.get(node, [])
            for p in prereqs:
                if p not in visited:
                    prereq_names.append(p)
                    queue.append(p)

        # 最多追溯5个前置知识，去重保序
        seen: set[str] = set()
        result: list[str] = []
        for name in prereq_names:
            if name not in seen:
                seen.add(name)
                result.append(f"回顾 {name} 的核心概念")
            if len(result) >= 5:
                break
        return result if result else [f"回顾 {stage_title} 的基础知识"]

    @staticmethod
    def _analyze_profile(facts: dict, course_id: str = "") -> dict:
        """Convert raw profile facts into structured planning parameters.
        
        Filters out facts that belong to a different course to prevent
        cross-subject data contamination.
        """
        # If facts contain a target_course that doesn't match current course_id,
        # clear the subject-specific fields to prevent contamination
        if course_id and facts.get("target_course"):
            tc = str(facts["target_course"]).lower()
            ci = course_id.lower()
            # Different topics → contamination likely
            if ci[:8] not in tc and tc[:8] not in ci and tc not in ci and ci not in tc:
                # Only clear subject-specific fields, keep generic ones
                clean = {
                    "time_budget": facts.get("time_budget", ""),
                    "preference": facts.get("preference", ""),
                }
                # Only keep knowledge_base if it's generic, not subject-specific
                kb = str(facts.get("knowledge_base", "") or "")
                if not any(topic in kb.lower() for topic in ["cnn", "深度学习", "神经网络", "python", "java", "微积分", "线性代数"]):
                    clean["knowledge_base"] = kb
                # Add back original fields that aren't contaminated
                for k in ["background", "target_course"]:
                    if k in facts:
                        clean[k] = facts[k]
                facts = clean
        result = {
            "starting_level": "intermediate",
            "daily_minutes_est": 60,
            "depth": "standard",
            "focus_areas": [],
            "content_style": "text",
            "domain_context": "",
        }
        kb = str(facts.get("knowledge_base", "") or "")
        if any(w in kb for w in ["初学", "零基础", "入门", "没学过", "beginner", "basic"]):
            result["starting_level"] = "beginner"
        elif any(w in kb for w in ["进阶", "提升", "加深", "advanced", "deep"]):
            result["starting_level"] = "advanced"
        
        tb = str(facts.get("time_budget", "") or "")
        import re
        nums = re.findall(r'(\d+)\s*小时', tb)
        if nums:
            result["daily_minutes_est"] = max(15, min(240, int(nums[0]) * 60))
        nums = re.findall(r'(\d+)\s*分钟', tb)
        if nums:
            result["daily_minutes_est"] = max(15, min(240, int(nums[0])))
        
        goal = str(facts.get("learning_goal", "") or "")
        if any(w in goal for w in ["考试", "考研", "复习", "应试"]):
            result["depth"] = "exam"
        elif any(w in goal for w in ["入门", "了解", "概览"]):
            result["depth"] = "overview"
        elif any(w in goal for w in ["精通", "掌握", "深入"]):
            result["depth"] = "mastery"
        
        pref = str(facts.get("preference", "") or "")
        if any(w in pref for w in ["视频", "图解", "图片", "动画"]):
            result["content_style"] = "visual"
        elif any(w in pref for w in ["动手", "代码", "实操", "项目"]):
            result["content_style"] = "hands-on"
        
        wp = str(facts.get("weak_points", "") or "")
        if wp:
            result["focus_areas"] = [w.strip() for w in re.split(r"[,，、\s]+", wp) if w.strip()][:5]
        
        bg = str(facts.get("background", "") or "")
        if bg:
            result["domain_context"] = bg
        
        return result


    # ── 知识点收益权重计算（M5）──

    @staticmethod
    def _calc_benefit_weight(point: dict, mastery_levels: list[dict], deps_count: int) -> float:
        """计算知识点的学习收益权重。

        公式：benefit = (100 - mastery) / 100 * 0.7 + min(deps_count, 5) / 5 * 0.3
        - 前项：掌握度越低权重越高（补短板）
        - 后项：依赖数越多权重越高（解锁更多后续知识点）
        """
        name = str(point.get("name", ""))
        mastery = 50  # 默认未知
        for m in mastery_levels:
            if isinstance(m, dict) and m.get("name", "") == name:
                mastery = m.get("score", 50)
                break
        gap_weight = (100 - mastery) / 100.0
        dep_weight = min(deps_count, 5) / 5.0
        return round(gap_weight * 0.7 + dep_weight * 0.3, 3)

    # ── 超时拆解（M5）──

    @staticmethod
    def _decompose_stage(stage: dict) -> list[dict]:
        """将耗时过长的阶段拆分为逐步引导的子阶段。

        一个解答题 → 3个填空题引导 → 最后再回到解答。
        """
        title = str(stage.get("title", ""))
        tasks = stage.get("tasks", []) or []
        if len(tasks) <= 1:
            return [stage]
        # 拆成3个子阶段：概念回顾 → 引导练习 → 综合应用
        n = len(tasks)
        chunk1 = tasks[:max(1, n // 3)]
        chunk2 = tasks[max(1, n // 3):max(1, 2 * n // 3)]
        chunk3 = tasks[max(1, 2 * n // 3):]
        return [
            {**stage, "stage_id": f"{stage.get('stage_id','')}_step1",
             "title": f"{title}（① 概念回顾）", "tasks": chunk1,
             "duration": "第1-2天", "resource_types": ["lecture", "reading"]},
            {**stage, "stage_id": f"{stage.get('stage_id','')}_step2",
             "title": f"{title}（② 引导练习）", "tasks": chunk2,
             "duration": "第3-4天", "resource_types": ["quiz", "fill"]},
            {**stage, "stage_id": f"{stage.get('stage_id','')}_step3",
             "title": f"{title}（③ 综合应用）", "tasks": chunk3,
             "duration": "第5-6天", "resource_types": ["shortanswer", "practice"]},
        ]

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        time_text = self._collect_time_text(ctx)
        total_days = self._infer_days(time_text, ctx.get("profile", {}))
        return {
            "learning_path": [],
            "stages": [],
            "estimatedDays": total_days,
            "plan_summary": "规划智能体暂时不可用，请稍后重试。",
            "diagnosis_used": False,
            "diagnosis_references": [],
            "stage_rationales": [],
            "needs_more_diagnosis": True,
            "priority_basis": ["fallback"],
            "recommended_resource_strategy": "智能体恢复后，建议先从基础诊断确认薄弱点。",
            "risk_flags": ["planner_unavailable"],
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "PlannerAgent fell back to defaults.",
                "error_reason": "Planner agent failed, returning empty path",
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "started_at": None,
                "finished_at": None,
            },
        }

    # ── 时间推断 ──

    def _collect_time_text(self, context: dict) -> str:
        parts = [
            str(context.get("user_message", "")),
            str(context.get("time_budget", "")),
        ]
        profile_facts = context.get("profile_facts", {})
        if isinstance(profile_facts, dict):
            parts.append(str(profile_facts.get("time_budget", "")))
        return " ".join(parts)

    def _infer_days(self, time_text: str, profile: dict) -> int:
        explicit_days = self._rule_infer_days(time_text, {})
        if self._has_explicit_duration(time_text):
            return self._clamp_days(explicit_days)
        # Single source of truth: if ProfileAgent already normalized time_budget or
        # learning_rhythm to a numeric score, extract days from it directly.
        for dim_key in ("learning_rhythm", "time_budget"):
            dim = profile.get(dim_key)
            if isinstance(dim, dict) and isinstance(dim.get("score"), (int, float)):
                if dim["score"] >= 80:   return 60   # ample time
                if dim["score"] >= 60:   return 30
                if dim["score"] >= 40:   return 14
                if dim["score"] >= 20:   return 7
            val = (dim.get("value", "") if isinstance(dim, dict) else "")
            if val and isinstance(val, str):
                days = self._rule_infer_days(val, profile)
                if 1 <= days <= 365:
                    return self._clamp_days(days)

        # Fallback: LLM or rule-based from time_text
        if self.llm_client:
            llm_days = self._llm_infer_days(time_text, profile)
            if llm_days:
                return self._clamp_days(llm_days)
        return self._clamp_days(self._rule_infer_days(time_text, profile))

    def _clamp_days(self, days: int) -> int:
        return max(1, min(365, int(days)))

    @staticmethod
    def _has_explicit_duration(text: str) -> bool:
        return bool(re.search(r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:个?月|周|星期|天|日)", text or ""))

    @staticmethod
    def _infer_daily_minutes(context: dict, profile: dict) -> int:
        facts = context.get("profile_facts") if isinstance(context.get("profile_facts"), dict) else {}
        value = facts.get("daily_minutes") or context.get("daily_minutes")
        try:
            if value is not None:
                return max(15, min(240, int(value)))
        except (TypeError, ValueError):
            pass
        text = " ".join(str(item or "") for item in (context.get("user_message"), context.get("time_budget"), facts.get("time_budget")))
        hours = re.search(r"每天\s*(\d+)\s*(?:个?小时|h)", text, re.I)
        minutes = re.search(r"每天\s*(\d+)\s*分钟", text)
        if hours:
            return max(15, min(240, int(hours.group(1)) * 60))
        if minutes:
            return max(15, min(240, int(minutes.group(1))))
        return 60

    @staticmethod
    def _materialize_daily_tasks(stages: list[dict], daily_minutes: int, context: dict) -> None:
        task_types = (("read_doc", "阅读讲义"), ("practice", "专项练习"), ("write_code", "代码实践"), ("do_quiz", "小测"), ("method", "图解梳理"), ("review", "复盘"))
        day = 1
        exam_goal = "考研" in str((context.get("profile_facts") or {}).get("learning_goal", ""))
        for stage_index, stage in enumerate(stages):
            sections = [sec for chapter in stage.get("chapters", []) for sec in chapter.get("sections", [])]
            if not sections:
                sections = [{"title": task.get("title", "") if isinstance(task, dict) else str(task), "goal": stage.get("goal", "")}
                            for task in stage.get("tasks", [])]
            if not sections:
                continue
            tasks = []
            duration = int(stage.get("estimatedDays", stage.get("estimated_days", 1)) or 1)
            for offset in range(duration):
                section = sections[offset % len(sections)]
                primary, label = task_types[(day - 1) % len(task_types)]
                if offset == duration - 1:
                    primary, label = ("mock", "综合训练") if exam_goal else ("do_quiz", "阶段小测")
                first_minutes = 40 if primary in {"practice", "write_code", "mock"} else 30
                # v1.2: 保留原任务中的教材字段（source_section_ids / textbookPageStart / etc.）
                _tb_fields = {}
                _src = section if isinstance(section, dict) else {}
                # v1.2: 仅保留 source_section_ids——页码由展示层按 TOC 动态解析
                if _src.get("source_section_ids"):
                    _tb_fields["source_section_ids"] = _src["source_section_ids"]
                _a = {"task_id": f"{stage.get('stage_id', stage_index)}_d{day}_a", "day": day, "title": f"{section.get('title', '')}：{label}", "type": primary, "goal": section.get("goal", "") or section.get("title", ""), "estimated_minutes": first_minutes, "status": "not_started", **_tb_fields}
                _b = {"task_id": f"{stage.get('stage_id', stage_index)}_d{day}_b", "day": day, "title": f"{section.get('title', '')}：巩固与回顾", "type": "review" if primary != "review" else "practice", "goal": "巩固当天知识点并记录疑问", "estimated_minutes": daily_minutes - first_minutes, "status": "not_started"}
                if primary in ("read_doc",) and _tb_fields:
                    _b.update(_tb_fields)  # 巩固任务也关联同一教材章节
                tasks.extend((_a, _b))
                day += 1
            stage["tasks"] = tasks

    def _llm_infer_days(self, time_text: str, profile: dict) -> int | None:
        profile_text = self._compact_profile_text(profile)
        prompt = f"""从以下信息提取学生的有效学习天数：

用户消息和时间信息：{time_text}
学习画像中的时间信息：{profile_text}

关键规则：
- 如果学生说"周末休息"/"周末不学"，只算工作日(5/7)，例如"一个月，周末休息" ≈ 20天
- "一个月" = 30天，"两个月" = 60天，"两周" = 14天
- "每天X小时"是每日强度，不影响总天数
- 如果没有明确时间 = 14天

只返回一个整数（有效学习天数），不要解释。"""
        try:
            raw = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是精确的时间提取器。只返回整数天数。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=10,
            )
            raw = str(raw).strip()
            if not re.fullmatch(r"\d+", raw):
                return None
            return max(1, min(365, int(raw)))
        except Exception:
            return None

    def _rule_infer_days(self, text: str, profile: dict) -> int:
        profile_texts = [text]
        for key in ("time_budget", "learning_rhythm", "learning_goal", "learning_progress"):
            item = profile.get(key, {})
            val = item.get("value", "") if isinstance(item, dict) else item
            if isinstance(val, str) and val.strip():
                profile_texts.append(str(val))

        combined = " ".join(profile_texts)
        combined = self._normalize_cn_numbers(combined)

        m = re.search(r"(\d+)\s*个?\s*月", combined)
        if m:
            return self._adjust_for_weekends(max(1, min(365, int(m.group(1)) * 30)), combined)

        m = re.search(r"(\d+)\s*个?\s*(?:周|星期)", combined)
        if m:
            return self._adjust_for_weekends(max(1, min(365, int(m.group(1)) * 7)), combined)

        m = re.search(r"(\d+)\s*(?:天|日)", combined)
        if m:
            return self._adjust_for_weekends(max(1, min(365, int(m.group(1)))), combined)

        m = re.search(r"(\d+)\s*个?\s*(?:小时|h)", combined)
        if m and "每天" not in combined:
            return max(1, ceil(int(m.group(1)) / 24))

        cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                   "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

        m = re.search(r"([一二两三四五六七八九])?十([一二三四五六七八九])?\s*个?\s*(天|日|周|星期|月)", combined)
        if m:
            tens = cn_map.get(m.group(1), 1) * 10 if m.group(1) else 10
            ones = cn_map.get(m.group(2), 0)
            total = tens + ones
            unit = m.group(3)
            if unit in ("周", "星期"):
                return self._adjust_for_weekends(max(1, min(365, total * 7)), combined)
            if unit == "月":
                return self._adjust_for_weekends(max(1, min(365, total * 30)), combined)
            return self._adjust_for_weekends(max(1, min(365, total)), combined)

        m = re.search(r"([一二两三四五六七八九])\s*个?\s*(天|日|周|星期|月)", combined)
        if m:
            total = cn_map.get(m.group(1), 7)
            unit = m.group(2)
            if unit in ("周", "星期"):
                return self._adjust_for_weekends(max(1, min(365, total * 7)), combined)
            if unit == "月":
                return self._adjust_for_weekends(max(1, min(365, total * 30)), combined)
            return self._adjust_for_weekends(max(1, min(365, total)), combined)

        # ── No explicit time unit found ──
        return self._adjust_for_weekends(14, combined)

    def _adjust_for_weekends(self, raw_days: int, time_text: str) -> int:
        """If user says weekends off, reduce to effective weekdays (~5/7)."""
        weekend_off = re.search(r"周末(?:休息|不学|不?学习|放假)", time_text)
        if weekend_off:
            effective = max(1, round(raw_days * 5 / 7))
            logger.info("Weekends off: %d raw -> %d effective days", raw_days, effective)
            return effective
        return raw_days

    def _normalize_cn_numbers(self, text: str) -> str:
        cn_digits = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
                      "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        cn_all = "一二两三四五六七八九"
        units = r"(?:天|日|周|星期|个小时|小时|个月|月|分钟)"

        text = re.sub(rf"([{cn_all}十])\s*个\s*({units})", r"\1\2", text)

        for tc, tv in cn_digits.items():
            for oc, ov in cn_digits.items():
                text = re.sub(rf"{tc}十{oc}\s*({units})", rf"{tv}{ov}\1", text)

        for tc, tv in cn_digits.items():
            text = re.sub(rf"{tc}十\s*({units})", rf"{tv}0\1", text)

        for oc, ov in cn_digits.items():
            text = re.sub(rf"(?<![{cn_all}])十{oc}\s*({units})", rf"1{ov}\1", text)

        text = re.sub(rf"(?<![{cn_all}])十\s*({units})", r"10\1", text)

        for cn, digit in cn_digits.items():
            text = re.sub(rf"{cn}\s*({units})", rf"{digit}\1", text)

        text = re.sub(rf"半\s*({units})", r"0\1", text)

        return text

    # ── 弱知识点提取 ──

    def _extract_weak_points(self, diagnosis: dict) -> list[dict]:
        result = []
        raw = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
        for i, item in enumerate(raw, 1):
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("topic") or "").strip()
                point = dict(item)
            else:
                name = str(item).strip()
                point = {}
            if not name or self._is_placeholder(name) or self._is_goal_like_title(name):
                continue
            point["name"] = name
            point.setdefault("title", name)
            point.setdefault("point_id", f"dx_{i}")
            point.setdefault("priority", "high")
            point.setdefault("difficulty", "medium")
            point.setdefault("prerequisites", [])
            result.append(point)
        return result

    def _is_placeholder(self, name: str) -> bool:
        return name.strip().lower() in {
            "无诊断数据", "暂无诊断数据", "unknown", "none", "未知", "无",
            "待诊断", "未诊断", "n/a", "null", "",
        }

    # ── 规划知识点 ──

    def _get_planning_points(self, context: dict, weak_points: list[dict]) -> list[dict]:
        course_id = str(context.get("course_id") or "")
        course = course_catalog.get_course(course_id) or {}
        course_name = self._course_name_from_context(context)
        chapters = [
            {
                "point_id": f"{course_id}_{ch.get('chapter_id', i)}",
                "chapter_id": str(ch.get("chapter_id", i)).zfill(2),
                "name": str(ch.get("title", f"第{i}章")),
                "title": str(ch.get("title", f"第{i}章")),
                "priority": "high" if i <= 3 else "medium",
                "difficulty": ch.get("difficulty", "medium"),
                "prerequisites": ch.get("prerequisites", []),
            }
            for i, ch in enumerate(course.get("chapters", []), 1)
        ]

        text = " ".join([
            str(context.get("user_message", "")),
            " ".join(str(v) for v in context.get("profile_facts", {}).values()),
        ])
        if chapters and self._is_whole_course(text):
            return chapters

        course_points = self._fallback_course_points(course_name or text)
        if course_points:
            return self._prioritize_points(course_points, weak_points)

        return weak_points or chapters

    def _is_whole_course(self, text: str) -> bool:
        return any(w in text for w in ["考试", "复习", "完整", "系统", "整门", "全", "通过"])

    def _course_name_from_context(self, context: dict) -> str:
        profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}
        if profile_facts.get("target_course"):
            return str(profile_facts.get("target_course"))
        course = context.get("course") if isinstance(context.get("course"), dict) else {}
        if course.get("course_name"):
            return str(course.get("course_name"))
        profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
        for key in ("interest_direction", "learning_goal"):
            item = profile.get(key, {})
            value = item.get("value", "") if isinstance(item, dict) else item
            if value:
                return str(value)
        return ""
    def _fallback_course_points(self, text: str) -> list[dict]:
        """Fallback using web search then generic phases."""
        try:
            from app.services.search_client import get_search_client
            client = get_search_client("duckduckgo")
            resp = client.search(text + " 课程大纲 核心知识点", max_results=3)
            if resp and resp.results:
                titles = [r.title.strip() for r in resp.results if r.title and len(r.title) > 4]
                if len(titles) >= 3:
                        return [{"point_id": f"course_outline_{i}", "name": name, "title": name,
                             "priority": "high" if i <= 2 else "medium", "difficulty": "medium", "prerequisites": []}
                            for i, name in enumerate(titles[:5], 1)]
        except Exception:
            pass
        names = ["基础概念与入门", "核心知识一", "核心知识二",
             "综合应用与实践", "复习与提升"]
        return [{"point_id": f"course_outline_{i}", "name": name, "title": name,
             "priority": "high" if i <= 2 else "medium", "difficulty": "medium", "prerequisites": []}
            for i, name in enumerate(names, 1)]

    def _prioritize_points(self, course_points: list[dict], weak_points: list[dict],
                           mastery_levels: list[dict] | None = None) -> list[dict]:
        """用收益权重公式排序知识点：补短板(70%) + 解锁依赖(30%)。"""
        weak_names = [str(point.get("name", "")) for point in weak_points if point.get("name")]
        mastery = mastery_levels or []
        if not weak_names and not mastery:
            return course_points
        # 计算每个点的收益权重
        for point in course_points:
            name = str(point.get("name", ""))
            deps = len(point.get("prerequisites", []) or [])
            weight = self._calc_benefit_weight(point, mastery, deps)
            point["benefit_weight"] = weight
            if any(weak and weak in name for weak in weak_names):
                point["priority"] = "high"
                point["benefit_weight"] = min(1.0, weight + 0.2)  # 薄弱点加成
        # 按 benefit_weight 降序排列
        course_points.sort(key=lambda p: -(p.get("benefit_weight", 0)))
        return course_points

    # ── 诊断元信息 ──

    def _build_diagnosis_meta(self, diagnosis: dict, weak_points: list[dict],
                               total_days: int, profile: dict, time_text: str = "") -> dict:
        weak_names = [p.get("name", "") for p in weak_points if p.get("name")]
        needs_more = diagnosis.get("needs_more_evidence", False) or (
            bool(diagnosis) and not weak_points
        )
        flags = list(diagnosis.get("risk_flags", []))
        if needs_more and "evidence_insufficient" not in flags:
            flags.append("evidence_insufficient")
        time_basis = self._time_basis(time_text, profile, total_days)
        if time_basis["tight"] and "time_budget_tight" not in flags:
            flags.append("time_budget_tight")
        evidence_sources = [
            self._clean_evidence_source(e.get("source", "unknown"))
            for e in (diagnosis.get("evidence_chain") or [])[:5]
            if isinstance(e, dict) and not self._is_placeholder(str(e.get("source", "")))
        ]
        if time_basis["has_time_budget"] and "time_budget" not in evidence_sources:
            evidence_sources.append("time_budget")

        return {
            "diagnosis_used": bool(diagnosis),
            "weak_topic_names": weak_names,
            "needs_more_diagnosis": needs_more,
            "evidence_sources": evidence_sources,
            "risk_flags": flags,
            "total_days": total_days,
            "time_basis": time_basis,
        }

    def _time_basis(self, time_text: str, profile: dict, total_days: int) -> dict:
        combined = " ".join([time_text, self._compact_profile_text(profile)])
        has_time = bool(re.search(r"\d+\s*(?:天|日|周|星期|月|个月|小时|分钟)|[一二两三四五六七八九十半]+(?:天|周|星期|个月|小时)|每天|周末", combined))
        daily_limited = bool(re.search(r"每天\s*(?:\d+|[一二两三四五六七八九十半]+)\s*(?:个)?小时", combined))
        schedule_limited = "周末休息" in combined
        return {
            "has_time_budget": has_time,
            "daily_limited": daily_limited,
            "schedule_limited": schedule_limited,
            "tight": total_days <= 7 or (daily_limited and total_days == 14),
        }

    def _clean_evidence_source(self, source: str) -> str:
        return {"fallback_rule": "规则兜底", "unknown": ""}.get(source, source)

    def _make_probe_point(self, diagnosis: dict) -> dict:
        actions = diagnosis.get("recommended_next_actions") or []
        return {
            "point_id": "diagnosis_probe",
            "name": "基础诊断与薄弱点确认",
            "title": "基础诊断与薄弱点确认",
            "priority": "high",
            "difficulty": "medium",
            "prerequisites": [],
            "reason": "当前诊断证据不足，先通过测验确认具体薄弱点再制定精准计划。",
            "recommended_next_actions": actions,
        }

    # ── LLM 生成 ──

        def llm_fix(broken: str) -> str:
            return self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是 JSON 修复器。修复以下损坏的 JSON，只输出修复后的 JSON，不要解释。"},
                    {"role": "user", "content": broken},
                ],
                temperature=0,
                max_tokens=2000,
            )

        return parse_safe(text, llm_fix_fn=llm_fix if self.llm_client else None)

    # _repair_truncated_json 已迁移到 app.utils.llm_json.repair_truncated

    def _build_rule_path(self, points, profile, total_days, diag_meta) -> list[dict]:
        n_stages = max(4, min(len(points), total_days // 2)) if points else max(4, total_days // 2)
        groups = self._group_points(points, n_stages) if points else []
        path = []

        if not groups:
            # 尝试从 profile 推断课程名以生成内容化阶段（§8.1）
            course_text = str(profile.get("interest_direction", {}).get("value", "") if isinstance(profile, dict) else "")
            fallback_points = self._fallback_course_points(course_text) if course_text else []
            if fallback_points:
                groups = self._group_points(fallback_points, min(5, len(fallback_points)))
            else:
                # 无法推断课程 → 返回标记 needs_more_info 的空路径（§8.2）
                return [{
                    "stage_id": "stage_info_needed",
                    "title": "需要更多信息",
                    "duration": "待确认",
                    "goal": "请先明确学习对象（课程名或知识点），才能生成内容化的学习阶段。",
                    "tasks": ["告诉我你想学习的具体课程或知识点"],
                    "daily_tasks": [{"day": 1, "tasks": ["明确学习对象"]}],
                    "resource_types": ["lecture"],
                    "reason": "无法从当前信息推断课程结构，需要用户明确学习对象。",
                    "source": "rule_fallback",
                }]

        for i, group in enumerate(groups, 1):
            lead = group[0]
            names = [p.get("name", "重点知识点") for p in group]

            if lead.get("point_id") == "diagnosis_probe":
                path.append({
                    "stage_id": f"stage_{i}",
                    "title": str(lead["name"]),
                    "duration": self._calc_duration(i, n_stages, total_days),
                    "goal": "先完成基础测验，确认真实薄弱点后再进入针对性学习。",
                    "tasks": ["完成基础测验", "回顾错题", "确认优先薄弱点"],
                    "daily_tasks": self._derive_daily_tasks_from_fallback(
                        ["完成基础测验", "回顾错题", "确认优先薄弱点"],
                        self._calc_duration(i, n_stages, total_days), i, n_stages, total_days,
                    ),
                    "resource_types": ["quiz", "practice"],
                    "reason": str(lead.get("reason", "证据不足，需先诊断。")),
                    "source": "rule_fallback",
                })
                continue

            path.append({
                "stage_id": f"stage_{i}",
                "title": self._make_title(i, names),
                "duration": self._calc_duration(i, n_stages, total_days),
                "goal": self._make_goal(lead, profile, names),
                "tasks": self._make_tasks(lead, profile, i, names),
                "daily_tasks": self._derive_daily_tasks_from_fallback(
                    self._make_tasks(lead, profile, i, names),
                    self._calc_duration(i, n_stages, total_days), i, n_stages, total_days,
                ),
                "resource_types": self._make_resource_types(profile, i),
                "reason": self._make_reason(group, profile, total_days, diag_meta),
                "source": "rule_fallback",
            })

        return path

    def _derive_daily_tasks_from_fallback(self, tasks, duration, stage_index, n_stages, total_days):
        days = max(1, self._parse_duration_days(str(duration)))
        clean_tasks = [str(task).strip() for task in (tasks or []) if str(task).strip()]
        if not clean_tasks:
            clean_tasks = [f"完成第{stage_index}阶段学习任务"]

        daily = []
        for day in range(1, days + 1):
            first = clean_tasks[(day - 1) % len(clean_tasks)]
            second = clean_tasks[day % len(clean_tasks)] if len(clean_tasks) > 1 else None
            day_tasks = [first]
            if second and second != first:
                day_tasks.append(second)
            daily.append({"day": day, "tasks": day_tasks})
        return daily

    def _group_points(self, points, n_stages):
        groups = []
        for i in range(n_stages):
            start = round(i * len(points) / n_stages)
            end = round((i + 1) * len(points) / n_stages)
            chunk = points[start:end]
            if not chunk:
                chunk = [points[min(i, len(points) - 1)]]
            groups.append(chunk)
        return groups

    def _make_title(self, i, names):
        names = [name for name in names if not self._is_goal_like_title(str(name))]
        name_str = "、".join(names[:2])
        if not name_str or name_str == "重点知识点":
            return f"第{i}阶段"
        return name_str

    def _calc_duration(self, i, n_stages, total_days):
        dps = max(1, ceil(total_days / n_stages))
        start = min(total_days, (i - 1) * dps + 1)
        end = min(total_days, max(start, i * dps))
        return f"第{start}-{end}天" if start != end else f"第{start}天"

    def _make_goal(self, point, profile, names):
        name_str = "、".join(names or [point.get("name", "该知识点")])
        goal = f"理解并掌握 {name_str} 的核心概念、典型题型和常见误区。"
        prereqs = "、".join(str(x) for x in point.get("prerequisites", []) if x)
        if prereqs:
            goal += f" 同时补齐前置知识：{prereqs}。"
        return goal

    def _make_tasks(self, point, profile, i, names):
        name_str = "、".join(names or [point.get("name", "知识点")])
        tasks = [f"学习《{name_str}》核心内容", f"完成 {name_str} 的配套练习"]
        pref = str(profile.get("cognitive_style", {}).get("value", ""))
        if any(w in pref for w in ["代码", "实操"]):
            tasks.append(f"编写或运行 {name_str} 相关代码案例")
        elif any(w in pref for w in ["图解", "思维导图"]):
            tasks.append(f"绘制 {name_str} 知识结构图")
        else:
            tasks.append(f"整理 {name_str} 的易错点清单")
        if i > 1:
            tasks.append("复盘上一阶段错题")
        return tasks

    def _make_reason(self, group, profile, total_days, diag_meta=None):
        names = "、".join(p.get("name", "") for p in group if p.get("name"))
        goal = str(profile.get("learning_goal", {}).get("value", ""))
        time_basis = (diag_meta or {}).get("time_basis", {})
        notes = []
        if time_basis.get("daily_limited"):
            notes.append("每天学习时间有限")
        if time_basis.get("schedule_limited"):
            notes.append("周末休息")
        suffix = f"（{ '，'.join(notes) }）" if notes else ""
        if total_days <= 3:
            return f"学习周期仅{total_days}天，优先安排{names}等核心内容。{suffix}"
        if any(word in goal for word in ["考试", "期末", "高分"]):
            return f"目标偏考试/高分，{names}是需要优先稳住的课程内容。{suffix}"
        return f"根据课程先修关系，当前阶段适合集中处理{names}。{suffix}"

    def _is_goal_like_title(self, title: str) -> bool:
        text = title.strip()
        if not text:
            return True
        if any(course_word in text for course_word in ["极限", "导数", "微分", "积分", "函数", "连续", "综合", "题型", "复盘", "复杂度", "数组", "链表", "栈", "队列", "递归", "树", "图", "查找", "排序", "练习"]):
            return False
        return any(word in text for word in ["目标", "高分", "入门", "掌握", "复习", "考试", "期末"])

    def _make_resource_types(self, profile, i):
        types = ["lecture", "quiz"]
        pref = str(profile.get("cognitive_style", {}).get("value", ""))
        if any(w in pref for w in ["图解", "思维导图"]):
            types.append("mindmap")
        if any(w in pref for w in ["代码", "实操"]):
            types.append("practice")
        if i == 1:
            types.append("reading")
        return list(dict.fromkeys(types))

    # ── 工具 ──

    def _compact_profile(self, profile: dict) -> dict:
        result = {}
        for k, v in profile.items():
            if isinstance(v, dict):
                val = str(v.get("value", "")).strip()
                if val and val != "未提及":
                    result[k] = val
        return result

    def _compact_profile_text(self, profile: dict) -> str:
        return " ".join(self._compact_profile(profile).values())

    def _make_result(self, path, total_days, diag_meta):
        path = self._normalize_stage_days(path, total_days)
        plan_summary = self._summarize(path, diag_meta, total_days)
        estimated_minutes_total = sum(
            sec.get("estimated_minutes", 45)
            for s in path if isinstance(s, dict)
            for ch in (s.get("chapters") or []) if isinstance(ch, dict)
            for sec in (ch.get("sections") or []) if isinstance(sec, dict)
        )
        return {
            "learning_path": path,
            "stages": path,
            "estimatedDays": total_days,
            "estimated_minutes_total": estimated_minutes_total,
            "version": int(time.time() * 1000),
            "diagnosis_used": diag_meta["diagnosis_used"],
            "diagnosis_references": diag_meta.get("weak_topic_names", []),
            "stage_rationales": [
                {"stage_id": s.get("stage_id"), "rationale": s.get("reason", "")}
                for s in path if isinstance(s, dict)
            ],
            "needs_more_diagnosis": diag_meta["needs_more_diagnosis"],
            "priority_basis": diag_meta.get("evidence_sources", []),
            "recommended_resource_strategy": (
                "先做诊断确认薄弱点，再针对性学习。"
                if diag_meta["needs_more_diagnosis"]
                else "根据薄弱点优先补充基础，再做专项练习。"
            ),
            "risk_flags": diag_meta.get("risk_flags", []),
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed",
                "summary": f"生成了{len(path)}个学习阶段",
                "started_at": None,
                "finished_at": None,
            },
        }

    def _summarize(self, path, diag_meta, total_days):
        if diag_meta["needs_more_diagnosis"]:
            return f"诊断证据不足，先确认薄弱点，再按{total_days}天规划。"
        titles = [s.get("title", "") for s in path[:2] if isinstance(s, dict)]
        return f"根据诊断结果，{'、'.join(titles) or '核心薄弱点'}，总周期{total_days}天。"
