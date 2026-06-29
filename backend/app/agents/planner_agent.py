"""
学习路径规划智能体 — LLM 主导，规则仅作为 LLM 不可用时的兜底。
"""

import json
import logging
import re
from math import ceil
from typing import Any

from app.agents.base import BaseAgent
from app.services.course_catalog import course_catalog
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    agent_id = "planner_agent"
    agent_name = "学习路径规划智能体"

    # ── 公共接口 ──

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        diagnosis = context.get("diagnosis") if isinstance(context.get("diagnosis"), dict) else {}
        profile = context.get("profile", {})
        weak_points = self._extract_weak_points(diagnosis)
        planning_points = self._get_planning_points(context, weak_points)

        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)

        diag_meta = self._build_diagnosis_meta(diagnosis, weak_points, total_days, profile)

        if diag_meta["needs_more_diagnosis"] and not weak_points:
            planning_points = [self._make_probe_point(diagnosis)]

        if not planning_points:
            pass

        llm_path = self._try_generate_with_llm(context, profile, planning_points, total_days, diag_meta)
        if llm_path:
            return self._make_result(llm_path, total_days, diag_meta)

        logger.info("LLM unavailable or failed, using rule-based path")
        rule_path = self._build_rule_path(planning_points, profile, total_days, diag_meta)
        return self._make_result(rule_path, total_days, diag_meta)

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
        if self.llm_client:
            llm_days = self._llm_infer_days(time_text, profile)
            if llm_days:
                return llm_days
        return self._rule_infer_days(time_text, profile)

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
            days = int(re.search(r'\d+', raw).group())
            return max(1, min(365, days))
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
            if not name or self._is_placeholder(name):
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

        return weak_points or chapters

    def _is_whole_course(self, text: str) -> bool:
        return any(w in text for w in ["考试", "复习", "完整", "系统", "整门", "全", "通过"])

    # ── 诊断元信息 ──

    def _build_diagnosis_meta(self, diagnosis: dict, weak_points: list[dict],
                               total_days: int, profile: dict) -> dict:
        weak_names = [p.get("name", "") for p in weak_points if p.get("name")]
        needs_more = diagnosis.get("needs_more_evidence", False) or (
            bool(diagnosis) and not weak_points
        )
        flags = list(diagnosis.get("risk_flags", []))
        if needs_more and "evidence_insufficient" not in flags:
            flags.append("evidence_insufficient")

        return {
            "diagnosis_used": bool(diagnosis),
            "weak_topic_names": weak_names,
            "needs_more_diagnosis": needs_more,
            "evidence_sources": [
                e.get("source", "unknown") for e in (diagnosis.get("evidence_chain") or [])[:5]
                if isinstance(e, dict)
            ],
            "risk_flags": flags,
            "total_days": total_days,
        }

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

    def _try_generate_with_llm(self, context, profile, planning_points,
                                 total_days, diag_meta) -> list[dict] | None:
        if not self.llm_client:
            return None

        course_id = str(context.get("course_id") or "")
        course = course_catalog.get_course(course_id) or {}
        profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}

        user_message = profile_facts.get("_raw_user_message", str(context.get("user_message", "")))
        conversation_context = profile_facts.get("_conversation_context", "")

        course_name = (
            course.get("course_name")
            or context.get("knowledge_context", {}).get("course_name")
            or profile_facts.get("target_course")
            or ""
        )

        payload = {
            "course_name": course_name,
            "estimated_days": total_days,
            "student_profile": self._compact_profile(profile),
            "diagnosis_meta": diag_meta,
            "planning_points": [
                {
                    "name": p.get("name"),
                    "difficulty": p.get("difficulty", "medium"),
                    "prerequisites": p.get("prerequisites", []),
                }
                for p in planning_points
            ] if planning_points else [],
        }

        prompt = f"""根据以下信息，生成一个 {total_days} 天的学习路径。

用户最新要求：{user_message}

对话上下文：
{conversation_context}

课程与画像数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}

要求：
1. 生成3-5个阶段，总天数必须正好{total_days}天
2. 每个阶段包含：stage_id, title, duration, goal, tasks, resource_types, reason
3. title必须以具体的学习内容命名（如"极限与连续"、"导数与微分"、"不定积分"），绝对不要用"第一阶段"、"补齐基础"这种模板化标题
4. 如果用户要求"以学习内容为阶段划分"，严格按照内容主题划分阶段
5. 如果用户提到特定教材（如同济版高等数学），参考该教材的章节结构来划分阶段
6. 体现学生基础水平（如"高中导数学过"、"零基础"）和时间约束
7. 如果对话中已经有诊断信息，参考薄弱点来调整阶段重点
8. 只输出JSON，格式：{{"learning_path": [...]}}"""

        try:
            raw = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是学习路径规划专家，擅长根据学生情况设计个性化学习阶段。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1600,
            )
            logger.info(f"LLM raw response (first 800 chars): {raw[:800]}")
            parsed = self._parse_json(raw)
            path = parsed.get("learning_path") if isinstance(parsed, dict) else None
            if isinstance(path, list) and len(path) >= 1:
                return self._normalize_path(path, planning_points, total_days)
        except Exception as e:
            logger.warning(f"LLM path generation failed: {e}")
            logger.exception("Full traceback:")

        return None

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start:end + 1]
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result

    def _normalize_path(self, path: list, planning_points: list, total_days: int) -> list[dict]:
        allowed = {
            (p.get("name") or p.get("title") or "").strip()
            for p in planning_points
        }
        allowed.discard("")

        result = []
        for i, item in enumerate(path[:5], 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", f"第{i}阶段")).strip()
            tasks = [str(t).strip() for t in item.get("tasks", []) if str(t).strip()]

            if allowed:
                skip_check = (len(allowed) == 1 and "基础诊断与薄弱点确认" in allowed)
                if not skip_check:
                    text_blob = f"{title} {item.get('goal', '')} {' '.join(tasks)}"
                    if not any(term and term in text_blob for term in allowed):
                        continue

            result.append({
                "stage_id": str(item.get("stage_id", f"stage_{i}")),
                "title": title,
                "duration": str(item.get("duration", f"第{i}阶段")),
                "goal": str(item.get("goal", "完成本阶段核心知识学习。")),
                "tasks": tasks or ["学习课程讲义", "完成配套练习"],
                "resource_types": self._clean_types(item.get("resource_types", [])),
                "reason": str(item.get("reason", "根据学生画像和课程结构自动规划。")),
                "source": "llm_generated",
            })

        logger.info(f"Normalized path count: {len(result)}")
        return result if len(result) >= 1 else []

    def _clean_types(self, types: Any) -> list[str]:
        aliases = {"case_study": "practice", "code": "practice", "video": "multimodal",
                    "diagram": "mindmap", "text": "lecture", "exercise": "quiz"}
        allowed = {"lecture", "mindmap", "quiz", "reading", "practice", "multimodal"}
        if not isinstance(types, list):
            return ["lecture", "quiz"]
        result = []
        for t in types:
            norm = aliases.get(str(t).strip(), str(t).strip())
            if norm in allowed and norm not in result:
                result.append(norm)
        return result or ["lecture", "quiz"]

    # ── 规则兜底 ──

    def _build_rule_path(self, points, profile, total_days, diag_meta) -> list[dict]:
        n_stages = min(5, max(3, len(points))) if points else 3
        groups = self._group_points(points, n_stages) if points else []
        path = []

        if not groups:
            return [
                {
                    "stage_id": "stage_1",
                    "title": "基础概念与入门",
                    "duration": f"第1-{max(1, total_days // 3)}天",
                    "goal": "建立课程核心概念框架，掌握基本定义和术语。",
                    "tasks": ["阅读入门讲义", "完成基础概念练习", "整理知识结构图"],
                    "resource_types": ["lecture", "quiz", "mindmap"],
                    "reason": f"学习周期{total_days}天，从基础概念起步。",
                    "source": "rule_fallback",
                },
                {
                    "stage_id": "stage_2",
                    "title": "核心技能与方法",
                    "duration": f"第{max(1, total_days // 3) + 1}-{max(2, total_days * 2 // 3)}天",
                    "goal": "掌握核心计算方法和解题技巧。",
                    "tasks": ["学习核心方法讲义", "完成专项练习题", "分析典型例题"],
                    "resource_types": ["lecture", "quiz", "practice"],
                    "reason": "在基础概念之上，深入核心技能训练。",
                    "source": "rule_fallback",
                },
                {
                    "stage_id": "stage_3",
                    "title": "综合应用与复习",
                    "duration": f"第{max(2, total_days * 2 // 3) + 1}-{total_days}天",
                    "goal": "综合运用所学知识解决实际问题，查漏补缺。",
                    "tasks": ["完成综合测试", "整理错题本", "复习薄弱环节"],
                    "resource_types": ["quiz", "reading", "practice"],
                    "reason": f"最后{total_days - max(2, total_days * 2 // 3)}天集中复习和综合应用。",
                    "source": "rule_fallback",
                },
            ]

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
                "resource_types": self._make_resource_types(profile, i),
                "reason": self._make_reason(group, profile, total_days),
                "source": "rule_fallback",
            })

        return path

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

    def _make_reason(self, group, profile, total_days):
        names = "、".join(p.get("name", "") for p in group if p.get("name"))
        goal = str(profile.get("learning_goal", {}).get("value", ""))
        if total_days <= 3:
            return f"学习周期仅{total_days}天，优先安排{names}等核心内容。"
        if "考试" in goal:
            return f"目标偏考试通过，{names}是高频模块。"
        return f"根据课程先修关系，当前阶段适合集中处理{names}。"

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