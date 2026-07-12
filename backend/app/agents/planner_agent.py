"""
学习路径规划智能体 — LLM 主导，规则仅作为 LLM 不可用时的兜底。
"""

import json
import logging
import re
from math import ceil
from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.services.course_catalog import course_catalog
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
            return self._run_adjustment(context, diagnosis, profile)

        weak_points = self._extract_weak_points(diagnosis)
        planning_points = self._get_planning_points(context, weak_points)
        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)
        diag_meta = self._build_diagnosis_meta(diagnosis, weak_points, total_days, profile, time_text)

        # ── Determine planning mode (focus vs textbook) ──
        plan_mode = context.get("plan_mode", "") or self._detect_plan_mode(
            context, weak_points, diagnosis,
        )

        # ── Determine path structure mode ──
        # textbook: stages→chapters→sections (math, physics, history)
        # daily:    周→日→任务 (languages, exam prep)
        # project:  阶段→实操→项目 (coding, design)
        path_mode = context.get("path_mode", "textbook")

        # ── Mode A: Focused sprint — target specific weak points ──
        if plan_mode == "focus":
            return self._run_focus_mode(context, profile, diagnosis, weak_points, total_days)

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

        # ── Mode B: Generate path with appropriate structure ──
        chapters = None
        try:
            chapters = self._generate_chapters(
                context, profile, planning_points, total_days, diag_meta, path_mode,
            )
        except Exception:
            pass

        # ── Step 2: If no chapters, try DeepTutor for structure ──
        if not chapters:
            chapters = self._try_deeptutor_as_structure(context, total_days)

        # ── Step 3: LLM pipeline as last resort ──
        if not chapters:
            chapters = self._llm_pipeline_fallback(context, profile, planning_points, total_days, diag_meta)

        if not chapters:
            # If textbook is available, use it as the fallback instead of generic rule-based path
            if textbook_chapters:
                chapters = self._build_path_from_textbook(
                    textbook_chapters, profile, total_days, diag_meta,
                )
            if not chapters:
                return self._fallback_path(context, planning_points, total_days, profile, diag_meta)

        # ── Step 4: Personalize with DeepTutor ──
        personalized = self._personalize_with_deeptutor(
            chapters, context, profile, diagnosis, weak_points, total_days,
        )
        chapters = personalized if personalized else chapters

        # ── Resolve textbook section IDs to page ranges ──
        if textbook_chapters and chapters:
            chapters = self._resolve_textbook_pages(chapters, textbook_chapters)

        return self._make_chapter_result(chapters, total_days, diag_meta)


    # ── Mode detection: textbook vs focus sprint ──

    def _detect_plan_mode(self, context: dict, weak_points: list, diagnosis: dict) -> str:
        """Auto-detect whether the user wants textbook learning or a focused sprint.

        Focus mode when:
        - User explicitly asks to strengthen specific weak areas
        - Diagnosis has clear weak points with high priority
        - Message contains focus keywords like 强化/补/不会/薄弱/专攻

        Textbook mode when:
        - User says 学X/入门X/系统学X (learning a whole subject)
        - No specific weak points identified
        - Message contains 入门/系统/从头/全面
        """
        msg = str(context.get("user_message", "") or "")
        facts = context.get("profile_facts", {}) or {}
        user_msg = str(facts.get("_raw_user_message", msg))

        # ── Explicit focus signals ──
        focus_keywords = [
            "强化", "补一补", "补一下", "专攻", "重点学", "突击",
            "不太会", "搞不懂", "不熟练", "总是错", "薄弱",
            "帮我加强", "专门练", "针对", "就学",
        ]
        textbook_keywords = [
            "入门", "从头", "系统学", "全面", "学完", "学一遍",
            "开始学", "想学", "我要学", "学这门",
        ]

        has_focus_signal = any(kw in user_msg for kw in focus_keywords)
        has_textbook_signal = any(kw in user_msg for kw in textbook_keywords)
        has_strong_weak_points = any(
            w.get("priority") == "high" for w in weak_points
        ) if weak_points else False

        # Clear focus intent → focus mode
        if has_focus_signal and not has_textbook_signal:
            return "focus"

        # Clear textbook intent → textbook mode
        if has_textbook_signal and not has_focus_signal:
            return "textbook"

        # Both or neither → use weak points as tiebreaker
        if has_strong_weak_points and weak_points and len(weak_points) >= 2:
            return "focus"

        return "textbook"

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
        """Build a concise textbook structure summary for LLM prompt injection.

        Includes section_id and page ranges for each section so the LLM
        can output explicit textbook_section_ids in its response.
        """
        lines = ["【教材参考】"]
        for ch in textbook_chapters:
            ch_title = ch.get("title", "")
            ch_start = ch.get("start_page", 0)
            ch_end = ch.get("end_page", 0)
            page_info = f"({ch_start}-{ch_end}页)" if ch_start > 0 else ""
            lines.append(f"\n- {ch_title} {page_info}")
            for sec in ch.get("sections", []):
                sec_id = sec.get("section_id", "")
                sec_title = sec.get("title", "")
                sec_start = sec.get("start_page", 0)
                sec_end = sec.get("end_page", 0)
                if sec_title:
                    lines.append(
                        f"    [{sec_id}] {sec_title} (第{sec_start}-{sec_end}页)"
                    )
        lines.append(
            "\n请参考以上教材结构来规划学习路径。你可以：\n"
            "- 只选择与学生目标相关的章节\n"
            "- 调整章节学习顺序\n"
            "- 跳过不相关的内容\n\n"
            "重要：请在输出的每个 section 中指定 textbook_section_ids 字段（字符串数组），\n"
            "填入该学习小节对应的教材小节ID（即上面方括号中的ID，如 sec_01_01）。\n"
            "一个学习小节可以对应一个或多个教材小节。"
        )
        return "\n".join(lines)

    @staticmethod
    def _resolve_textbook_pages(
        llm_chapters: list[dict], textbook_chapters: list[dict]
    ) -> list[dict]:
        """Resolve LLM-assigned textbook_section_ids to actual page ranges.

        The LLM outputs textbook_section_ids on each section (e.g. ["sec_01_01"]).
        We look up those IDs in the textbook data to get start_page/end_page.

        This is deterministic — no title matching needed.
        """
        # Build ID → section data lookup
        tb_section_by_id: dict[str, dict] = {}
        for ch in textbook_chapters:
            for sec in ch.get("sections", []):
                sec_id = sec.get("section_id", "")
                if sec_id:
                    tb_section_by_id[sec_id] = sec

        for stage in llm_chapters:
            for ch in stage.get("chapters", []):
                for sec in ch.get("sections", []):
                    sec_ids = sec.get("textbook_section_ids", [])
                    if not sec_ids:
                        continue
                    # Collect page ranges from ALL assigned textbook sections
                    pages: list[tuple[int, int]] = []
                    primary_id = ""
                    for sid in sec_ids:
                        tb_sec = tb_section_by_id.get(sid)
                        if tb_sec:
                            pages.append((
                                tb_sec.get("start_page", 1),
                                tb_sec.get("end_page", 1),
                            ))
                            if not primary_id:
                                primary_id = sid
                    if pages:
                        sec["textbookPageStart"] = min(p[0] for p in pages)
                        sec["textbookPageEnd"] = max(p[1] for p in pages)
                        sec["textbookSectionId"] = primary_id

        return llm_chapters

    # ── Mode T: Textbook-driven path building ──

    def _build_path_from_textbook(
        self,
        textbook_chapters: list[dict],
        profile: dict,
        total_days: int,
        diag_meta: dict,
    ) -> list[dict] | None:
        """Convert imported textbook chapter structure into learning path stages.

        Each textbook chapter becomes a path stage containing one chapter
        with the textbook's sections as its learning sections.

        Textbook chapter JSON schema (from chapters_json):
          [{chapter_id, title, order, start_page, end_page,
            sections: [{section_id, title, order, start_page, end_page,
                        estimated_minutes, knowledge_points}]}]
        """
        if not textbook_chapters:
            return None

        stages = []
        for ch in textbook_chapters:
            ch_title = ch.get("title", "")
            ch_order = ch.get("order", len(stages))
            ch_id = ch.get("chapter_id", f"tb_ch_{ch_order:02d}")

            sections = []
            for sec in ch.get("sections", []):
                sec_title = sec.get("title", "")
                sec_order = sec.get("order", len(sections))
                sec_id = sec.get("section_id", f"{ch_id}_sec_{sec_order:02d}")

                # Build section ID using the canonical factory
                section_factory_id = make_section_id(
                    make_chapter_id(
                        make_stage_id(make_path_id("textbook"), ch_order),
                        0,
                    ),
                    sec_order,
                )

                kps = []
                for kp_idx, kp_name in enumerate(sec.get("knowledge_points", [])):
                    if isinstance(kp_name, str) and kp_name.strip():
                        kps.append({
                            "id": make_kp_id(section_factory_id, kp_idx),
                            "name": kp_name.strip(),
                            "type": "concept",
                            "mastery": 0,
                            "status": "not_started",
                        })

                sections.append({
                    "id": section_factory_id,
                    "title": sec_title,
                    "goal": sec.get("goal", "") or f"掌握{sec_title}的核心内容",
                    "estimatedMinutes": sec.get("estimated_minutes", 45),
                    "knowledge_points": kps,
                    "lectureIds": [],
                    "contentType": "lecture",
                    "status": "not_started",
                    # Textbook-specific fields
                    "textbookPageStart": sec.get("start_page", 1),
                    "textbookPageEnd": sec.get("end_page", 1),
                    "textbookSectionId": sec_id,
                })

            if not sections:
                # Chapter with no sections: create one default section
                sec_id = make_section_id(
                    make_chapter_id(
                        make_stage_id(make_path_id("textbook"), ch_order), 0,
                    ), 0,
                )
                sections.append({
                    "id": sec_id,
                    "title": ch_title,
                    "goal": f"掌握{ch_title}的核心内容",
                    "estimatedMinutes": 60,
                    "knowledgePoints": [
                        {
                            "id": make_kp_id(sec_id, 0),
                            "name": ch_title,
                            "type": "concept",
                            "mastery": 0,
                            "status": "not_started",
                        }
                    ],
                    "lectureIds": [],
                    "contentType": "lecture",
                    "status": "not_started",
                    "textbookPageStart": ch.get("start_page", 1),
                    "textbookPageEnd": ch.get("end_page", 1),
                    "textbookSectionId": ch_id,
                })

            stage_id = make_stage_id(make_path_id("textbook"), ch_order)
            chapter_id = make_chapter_id(stage_id, 0)

            stages.append({
                "id": stage_id,
                "title": ch_title,
                "order": ch_order,
                "description": f"学习{ch_title}",
                "status": "not_started",
                "nodes": [],
                "chapters": [{
                    "id": chapter_id,
                    "title": ch_title,
                    "order": 0,
                    "status": "not_started",
                    "sections": sections,
                    "mindmapId": None,
                }],
                "objective": f"完成{ch_title}的学习",
                "estimatedDays": max(1, total_days // max(1, len(textbook_chapters))),
            })

        logger.info(
            "Built textbook-driven path: %d stages, %d sections",
            len(stages),
            sum(len(s.get("chapters", [{}])[0].get("sections", [])) for s in stages),
        )
        return stages

    # ── Mode A: Focus sprint ──

    def _run_focus_mode(
        self, context: dict, profile: dict, diagnosis: dict,
        weak_points: list, total_days: int,
    ) -> dict[str, Any]:
        """Generate a focused sprint plan targeting specific weak points.

        Skips chapter structure entirely — produces a flat list of
        sprint stages ordered by priority.
        """
        weak_names = [w.get("name", w.get("topic", "")) for w in weak_points[:8]]
        facts = context.get("profile_facts", {})
        course = facts.get("target_course", "") or str(context.get("course_id", ""))

        # ── Try DeepTutor for personalised sprint plan ──
        try:
            from app.services.deeptutor_client import deeptutor_call

            prompt = (
                f"学生正在学{course or '一门课'}，发现以下薄弱点需要重点突破：\n"
                + "\n".join(f"- {n}" for n in weak_names if n)
                + f"\n\n可用时间：{total_days} 天。"
                + "请设计一个精进突破计划，不要按教材章节顺序，"
                + "而是按薄弱点的优先级和依赖关系排列。"
                + "每个阶段聚焦一个薄弱点，包含：该补什么前置知识、核心练习、检验标准。"
                + "\n\n输出 JSON："
                + '{"sprints":[{"title":"阶段标题","focus":"薄弱点名称",'
                + '"reason":"为什么要先攻克这个","estimated_days":3,'
                + '"tasks":["具体任务1","具体任务2"],'
                + '"success_criteria":"怎样算掌握了"}]}'
            )
            raw = deeptutor_call("chat", prompt)
            import json as _json
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s >= 0 and e > s:
                parsed = _json.loads(raw[s:e])
                sprints = parsed.get("sprints", [])
                if sprints:
                    stages = []
                    for i, sp in enumerate(sprints):
                        days = int(sp.get("estimated_days", max(1, total_days // max(1, len(sprints)))))
                        stages.append({
                            "stage_id": f"sprint_{i}",
                            "title": sp.get("title", f"突破{sp.get('focus','')}"),
                            "order": i,
                            "goal": sp.get("success_criteria", ""),
                            "duration": f"第{i+1}阶段（{days}天）",
                            "estimated_days": days,
                            "tasks": sp.get("tasks", []),
                            "focus": sp.get("focus", ""),
                            "reason": sp.get("reason", ""),
                            "plan_mode": "focus",
                        })
                    return {
                        "learning_path": stages,
                        "stages": stages,
                        "estimatedDays": total_days,
                        "plan_mode": "focus",
                        "plan_summary": f"精进突破计划：{' → '.join(weak_names[:5])}",
                        "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name, "status": "completed"},
                    }
        except Exception as e:
            logger.debug("Focus mode DeepTutor failed: %s", e)

        # ── Fallback: simple priority-ordered sprint ──
        stages = []
        for i, w in enumerate(weak_points[:5]):
            name = w.get("name", w.get("topic", f"薄弱点{i+1}"))
            reason = w.get("reason", "")
            days = max(1, total_days // max(1, len(weak_points[:5])))
            stages.append({
                "stage_id": f"sprint_{i}",
                "title": f"突破：{name}",
                "order": i,
                "goal": f"掌握{name}，能做对相关题型",
                "duration": f"第{i+1}阶段（{days}天）",
                "estimated_days": days,
                "tasks": [f"复习{name}的核心概念", f"做{name}的专项练习", "整理错题"],
                "focus": name,
                "reason": reason,
                "plan_mode": "focus",
            })
        return {
            "learning_path": stages,
            "stages": stages,
            "estimatedDays": total_days,
            "plan_mode": "focus",
            "plan_summary": f"精进突破计划：{' → '.join(weak_names[:5])}",
            "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name, "status": "completed"},
        }

    # ── Step 2: DeepTutor as structure source (when chapter generation fails) ──

    def _try_deeptutor_as_structure(self, context: dict, total_days: int) -> list | None:
        """Use DeepTutor mastery_path to generate the initial stage structure."""
        try:
            from app.services.deeptutor_client import deeptutor_call
            course = str(context.get("course_id", "") or "")
            message = str(context.get("user_message", "") or "")
            prompt = (
                f"为学生规划学习路径。课程：{course}。需求：{message}。"
                f"请按 stages→chapters→sections→knowledge_points 层级输出，"
                f"每个 stage 包含多个 chapter，每个 chapter 包含多个 section。"
            )
            dt_result = deeptutor_call("mastery_path", prompt)
            if dt_result and len(dt_result) > 50:
                stages = self._parse_mastery_path(dt_result)
                if stages:
                    return self._rewrite_chapter_ids(context, stages)
        except Exception as e:
            logger.debug("DeepTutor structure failed: %s", e)
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
            course = str(context.get("course_id", "") or "")
            weak_names = [p.get("name", "") for p in planning_points[:10]]
            kp_total = max(1, len(planning_points))
            stage_count = max(2, min(8, max(2, total_days // 4)))
            prompt = f"""你是课程架构师。为「{course}」设计学习路径。
学生：{total_days}天，薄弱点：{chr(44).join(weak_names) if weak_names else chr(39)+chr(39)}。
要求：大约{stage_count}个阶段，难度递增，优先覆盖薄弱点，每阶段2-4类资源。具体数量按知识点分布灵活调整。
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
每个阶段：细化tasks为2-4个可执行任务，明确resource_types，total_days匹配{total_days}天。
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

    def _generate_chapters(self, context, profile, planning_points, total_days, diag_meta, path_mode="textbook"):
        course = str(context.get('course_id', '') or '')
        weak = [p.get('name','') for p in planning_points[:10]]
        from app.config import settings
        max_tokens = settings.path_max_tokens

        if path_mode == "daily":
            prompt = f"""你是课程设计师。为「{course}」设计一份{total_days}天的每日学习计划。
薄弱知识点：{','.join(weak) if weak else '待诊断'}。

这是语言类/积累型学科，不要按教材章节来。而是按「周→日→任务」组织，每天的学习内容可以并行叠加（如：词汇+听力+阅读可以同一天进行）。
每天的任务需要标注 task_type：
- vocabulary: 单词/词汇记忆
- listening: 听力训练
- reading: 阅读理解
- grammar: 语法专项
- speaking: 口语练习
- writing: 写作训练
- review: 复习/测验

按 weeks→days→tasks 层级输出JSON：
{{"weeks":[{{"week":1,"title":"第1周：xxx","days":[{{"day":1,"tasks":[{{"title":"任务名称","task_type":"vocabulary","estimated_minutes":30,"goal":"学习目标","content":[{{"type":"text","value":"任务描述"}}]}}]}}]}}]}}"""
        else:
            textbook_context = str(context.get("textbook_context", ""))
            textbook_block = f"\n\n{textbook_context}\n" if textbook_context else ""
            prompt = f"""你是课程设计师。为「{course}」设计一份内容全面、粒度合理的教科书级学习路径。
总学时：{total_days}天。薄弱知识点：{','.join(weak) if weak else '待诊断'}。{textbook_block}
小节划分原则：根据内容自然拆分，不要强行合并不相关的概念。比如"数组和广义表"一章可以拆成数组定义、数组实现、矩阵压缩存储、广义表定义、广义表存储、广义表递归算法等——具体情况具体分析。不能太概括，但也不必纠结数量。
知识点type取：concept|procedure|memory。

每个 section 需要标注 content_type 表示该小节的交互形式：
- lecture: 讲义/概念讲解（数学推导、历史事件、物理原理等）
- memory_drill: 记忆训练（单词、化学方程式、历史年代等需要背诵的内容）
- step_through: 分步推导/渐进式教程（数学解题、代码实现、实验步骤等）

按 stages→chapters→sections→knowledge_points 层级输出JSON：
{{"stages":[{{"stage_id":"s0","title":"阶段标题","order":0,"chapters":[{{"chapter_id":"ch0","title":"章节标题","order":0,"sections":[{{"section_id":"sec0","title":"1.1 节标题","goal":"学习目标","content_type":"lecture","estimated_minutes":45,"textbook_section_ids":["sec_01_01"],"knowledge_points":[{{"name":"知识点","type":"concept"}},{{"name":"知识点","type":"procedure"}}]}}]}}]}}]}}
textbook_section_ids 字段为必填——请从教材参考中选取对应小节的ID填入。若该节无对应教材小节，请填 []。"""
        if self.llm_client:
            try:
                raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=max_tokens)
                s, e = raw.find("{"), raw.rfind("}") + 1
                if s >= 0 and e > s:
                    data = json.loads(raw[s:e])
                    if path_mode == "daily":
                        weeks = data.get("weeks", [])
                        return self._convert_daily_to_stages(context, weeks)
                    stages = data.get("stages") or data.get("chapters") or []
                    return self._rewrite_chapter_ids(context, stages)
            except: pass
        return None

    def _convert_daily_to_stages(self, context: dict, weeks: list) -> list:
        """Convert daily-plan weeks→days→tasks into stages→chapters→sections."""
        stages = []
        for w in weeks:
            days = w.get("days", [])
            stage = {
                "stage_id": f"week_{w.get('week', 1)}",
                "title": w.get("title", f"第{w.get('week', 1)}周"),
                "order": w.get("week", 1) - 1,
                "chapters": [],
                "path_mode": "daily",
            }
            for d in days:
                tasks = d.get("tasks", [])
                chapter = {
                    "chapter_id": f"day_{w.get('week',1)}_{d.get('day',1)}",
                    "title": f"Day {d.get('day', 1)}",
                    "order": d.get("day", 1) - 1,
                    "sections": [],
                }
                for t in tasks:
                    task_type = t.get("task_type", "vocabulary")
                    ct_map = {
                        "vocabulary": "memory_drill", "grammar": "lecture",
                        "listening": "lecture", "reading": "lecture",
                        "speaking": "lecture", "writing": "lecture",
                        "review": "lecture",
                    }
                    section = {
                        "section_id": f"task_{w.get('week',1)}_{d.get('day',1)}_{task_type}",
                        "title": t.get("title", ""),
                        "goal": t.get("goal", ""),
                        "estimated_minutes": t.get("estimated_minutes", 30),
                        "content_type": ct_map.get(task_type, "lecture"),
                        "task_type": task_type,
                        "knowledge_points": [],
                    }
                    chapter["sections"].append(section)
                if chapter["sections"]:
                    stage["chapters"].append(chapter)
            if stage["chapters"]:
                stages.append(stage)
        return self._rewrite_chapter_ids(context, stages)
        if self.llm_client:
            try:
                raw = self.llm_client.chat(messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=max_tokens)
                s, e = raw.find("{"), raw.rfind("}") + 1
                if s >= 0 and e > s:
                    data = json.loads(raw[s:e])
                    stages = data.get("stages") or data.get("chapters") or []
                    return self._rewrite_chapter_ids(context, stages)
            except: pass
        return None

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
                    })
                rewritten_stage["chapters"].append(rewritten_ch)
            rewritten.append(rewritten_stage)
        return rewritten

    def _make_chapter_result(self, stages_with_chapters, total_days, diag_meta):
        """Wrap chapter-structured stages into the canonical result format.

        Each stage already contains chapters → sections → knowledge_points
        with canonical IDs from _rewrite_chapter_ids.
        """
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
        return {
            "learning_path": stages_with_chapters,
            "stages": stages_with_chapters,
            "chapters": stages_with_chapters,
            "estimatedDays": total_days,
            "section_count": total_sections,
            "knowledge_point_count": total_kps,
            "plan_summary": f"{len(stages_with_chapters)}阶段{total_chapters}章{total_sections}节{total_kps}知识点",
            "summary": f"{len(stages_with_chapters)}阶段{total_chapters}章{total_sections}节",
            "diagnosis_used": diag_meta.get("diagnosis_used", False),
            "needs_more_diagnosis": diag_meta.get("needs_more_diagnosis", False),
            "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name, "status": "completed"},
        }

    def _fallback_path(self, context, planning_points, total_days, profile, diag_meta):
        rule_path = self._build_rule_path(planning_points, profile, total_days, diag_meta)
        result = self._make_result(rule_path, total_days, diag_meta)
        result["review_tasks"] = self._generate_review_tasks(rule_path)
        result["planner_metadata"] = {"stages": len(rule_path), "reviewed": False, "revisions": 0, "backtracked": False, "revision_notes": "LLM不可用，使用规则生成"}
        return result

    def _run_adjustment(self, context: dict, diagnosis: dict, profile: dict) -> dict:
        """基于诊断结果动态调整已有学习路径。"""
        existing_path = list(context.get("existing_path", []) or [])
        mastery_levels = diagnosis.get("mastery_levels", []) or []
        grading_results = context.get("grading_results", []) or []

        if not existing_path:
            return self._make_result([], 14, {"diagnosis_used": False, "needs_more_diagnosis": True,
                                              "weak_topic_names": [], "evidence_sources": [], "risk_flags": ["no_existing_path"],
                                              "total_days": 14, "time_basis": {"has_time_budget": False}})

        # 统计连续作答表现
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

        adjustments = []
        adjusted_path = []

        for stage in existing_path:
            if not isinstance(stage, dict):
                adjusted_path.append(stage)
                continue

            stage_title = str(stage.get("title", ""))
            stage_tasks = list(stage.get("tasks", []))
            duration_str = str(stage.get("duration", ""))
            days = self._parse_duration_days(duration_str)

            # 匹配掌握度
            mastery = next((m for m in mastery_levels if isinstance(m, dict) and
                           m.get("name", "") in stage_title), None)

            adj = dict(stage)
            if mastery:
                level = mastery.get("level", "初步")
                score = mastery.get("score", 50)

                if level == "精通" and score >= 95:
                    # 加速/跳过：>95% 标记为已精通，减少该知识点出现频率
                    new_days = max(1, days // 3)
                    adj["duration"] = f"第{days}-{new_days}天（加速）"
                    adj["reason"] = f"诊断显示{stage_title}已精通（{score}分），大幅缩短学习时间。"
                    adj["mastered"] = True
                    adjustments.append(f"加速 {stage_title}：{days}天→{new_days}天")
                elif level == "精通" and score >= 90:
                    # 接近精通：适度加速
                    new_days = max(1, days // 2)
                    adj["duration"] = f"第{days}-{new_days}天（加速）"
                    adj["reason"] = f"诊断显示{stage_title}接近精通（{score}分），缩短学习时间。"
                    adjustments.append(f"加速 {stage_title}：{days}天→{new_days}天")
                elif level == "未学" and score < 40:
                    # 强化：增加天数，插入前置知识
                    new_days = min(days + 3, 14)
                    adj["duration"] = f"第{days}-{new_days}天（强化）"
                    adj["tasks"] = stage_tasks + self._trace_prerequisites_bfs(stage_title, context)
                    adj["reason"] = f"诊断显示{stage_title}未掌握（{score}分），增加学习时间和前置知识回顾。"
                    adjustments.append(f"强化 {stage_title}：{days}天→{new_days}天")
            else:
                adj["reason"] = stage.get("reason", "") + "（无诊断数据，保持原计划）"

            adjusted_path.append(adj)

        # 连续错题 → 在前端插入前置知识阶段
        if consecutive_wrong >= 2 and mastery_levels:
            weak_names = [m.get("name", "") for m in mastery_levels[:2] if isinstance(m, dict) and m.get("level") in ("未学", "初步")]
            if weak_names:
                adjusted_path.insert(0, {
                    "stage_id": "stage_remedial",
                    "title": f"前置知识补救：{'、'.join(weak_names)}",
                    "duration": "第1-2天（补救）",
                    "goal": f"连续{consecutive_wrong}题错误，先回顾前置基础。",
                    "tasks": [f"复习 {name} 的核心概念和基础题" for name in weak_names],
                    "daily_tasks": [{"day": 1, "tasks": [f"重新学习 {name} 的基础定义" for name in weak_names]}],
                    "resource_types": ["lecture", "quiz"],
                    "reason": f"连续{consecutive_wrong}题错误触发动态调整——回溯前置知识。",
                    "source": "dynamic_adjustment",
                })
                adjustments.append(f"连续{consecutive_wrong}题错误，插入前置知识补救阶段")

        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)

        # 目标临近 → 考前冲刺模式
        exam_keywords = ["考试", "期末", "考研", "高分"]
        if any(w in str(context.get("user_message", "")) for w in exam_keywords):
            for adj in adjusted_path:
                adj["resource_types"] = list(set(adj.get("resource_types", []) + ["quiz", "practice"]))
                adj["reason"] = str(adj.get("reason", "")) + "（考前冲刺模式——增加练习密度）"
            adjustments.append("检测到考试目标，切换到考前冲刺模式")

        # ── 阶段耗时过长 → 拆分为步骤引导（M5）──
        decomposed_path = []
        for stage in adjusted_path:
            if not isinstance(stage, dict):
                decomposed_path.append(stage)
                continue
            days = self._parse_duration_days(str(stage.get("duration", "")))
            if days >= 10 and len(stage.get("tasks", []) or []) >= 3:
                sub_stages = self._decompose_stage(stage)
                decomposed_path.extend(sub_stages)
                adjustments.append(f"拆解长阶段 {stage.get('title','')}：{days}天→{len(sub_stages)}个子阶段")
            else:
                decomposed_path.append(stage)

        diag_meta = {
            "diagnosis_used": True, "weak_topic_names": [m.get("name", "") for m in mastery_levels[:5] if isinstance(m, dict)],
            "needs_more_diagnosis": len(mastery_levels) < 3,
            "evidence_sources": ["diagnosis_mastery", "grading_results"],
            "risk_flags": ["dynamic_adjustment"] + (["time_budget_tight"] if consecutive_correct >= 3 else []),
            "total_days": total_days,
        }

        result = self._make_result(decomposed_path, total_days, diag_meta)
        result["adjustments"] = adjustments
        result["review_tasks"] = self._generate_review_tasks(decomposed_path)
        result["consecutive_correct"] = consecutive_correct
        result["consecutive_wrong"] = consecutive_wrong
        return result

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
                if 1 <= days <= 60:
                    return self._clamp_days(days)

        # Fallback: LLM or rule-based from time_text
        if self.llm_client:
            llm_days = self._llm_infer_days(time_text, profile)
            if llm_days:
                return self._clamp_days(llm_days)
        return self._clamp_days(self._rule_infer_days(time_text, profile))

    def _clamp_days(self, days: int) -> int:
        return max(1, min(60, int(days)))

    def _llm_infer_days(self, time_text: str, profile: dict) -> int | None:
        profile_text = self._compact_profile_text(profile)
        prompt = f"""从以下信息提取学生的学习时间（天数）：

用户消息和时间信息：{time_text}
学习画像中的时间信息：{profile_text}

常见时间表达参考：
- "两个月" = 60天
- "一个月" = 30天
- "三周" = 21天
- "两周" = 14天
- "半年" = 180天
- "一个半月" = 45天
- "这学期" = 90天（默认一学期约3个月）
- "每天2小时，持续1个月" = 30天（关注总周期而非每日时长）
- 如果没有明确时间 = 14天

只返回一个整数，不要解释。"""
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
            return max(1, min(365, int(m.group(1)) * 30))

        m = re.search(r"(\d+)\s*个?\s*(?:周|星期)", combined)
        if m:
            return max(1, min(365, int(m.group(1)) * 7))

        m = re.search(r"(\d+)\s*(?:天|日)", combined)
        if m:
            return max(1, min(365, int(m.group(1))))

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
                return max(1, min(365, total * 7))
            if unit == "月":
                return max(1, min(365, total * 30))
            return max(1, min(365, total))

        m = re.search(r"([一二两三四五六七八九])\s*个?\s*(天|日|周|星期|月)", combined)
        if m:
            total = cn_map.get(m.group(1), 7)
            unit = m.group(2)
            if unit in ("周", "星期"):
                return max(1, min(365, total * 7))
            if unit == "月":
                return max(1, min(365, total * 30))
            return max(1, min(365, total))

        return 14

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
        lowered = text.lower()
        if any(word in text for word in ["微积分", "高等数学"]) or "calculus" in lowered:
            names = ["函数、极限与连续", "导数与微分", "导数应用", "积分基础", "综合题型与期末复盘"]
        elif "数据结构" in text or "data structure" in lowered:
            names = ["复杂度、数组与链表", "栈、队列与递归", "树、二叉树与遍历", "图、查找与排序", "综合练习与错题复盘"]
        else:
            return []
        return [
            {
                "point_id": f"course_outline_{i}",
                "name": name,
                "title": name,
                "priority": "high" if i <= 2 else "medium",
                "difficulty": "medium",
                "prerequisites": [],
            }
            for i, name in enumerate(names, 1)
        ]

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
        n_stages = min(5, max(3, len(points))) if points else 3
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
        plan_summary = self._summarize(path, diag_meta, total_days)
        return {
            "learning_path": path,
            "stages": path,
            "estimatedDays": total_days,
            "plan_summary": plan_summary,
            "summary": plan_summary,
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
