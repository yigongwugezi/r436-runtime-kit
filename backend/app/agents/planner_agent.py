import json
import re
from math import ceil
from typing import Any

from app.agents.base import BaseAgent
from app.services.course_catalog import course_catalog
from app.services.llm_client import LLMClientError


class PlannerAgent(BaseAgent):
    agent_id = "planner_agent"
    agent_name = "学习路径规划智能体"

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return safe defaults for estimatedDays and learning_path.

        When the planner cannot produce real output (timeout, LLM error),
        callers must still receive a reasonable integer for estimatedDays
        — not an empty dict or None.
        Fallback data is marked with ``source: "rule_based_fallback"`` and
        ``quality_status: "fallback"``.
        """
        return {
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": f"Agent '{self.agent_id}' fell back to defaults.",
                "error_reason": "Planner agent failed, returning empty learning path",
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "started_at": None,
                "finished_at": None,
            },
            "learning_path": [],
            "source": "rule_based_fallback",
            "quality_status": "fallback",
            "reason": "智能体生成失败，使用规则兜底",
            "estimatedDays": self._infer_days(
                str((context or {}).get("user_message", "")),
                (context or {}).get("profile", {}),
            ),
        }

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        diagnosis = context.get("diagnosis") if isinstance(context.get("diagnosis"), dict) else {}
        weak_points = self._weak_points(diagnosis)
        profile = context.get("profile", {})
        total_days = self._infer_days(self._context_time_text(context), profile)
        diagnosis_meta = self._diagnosis_meta(diagnosis, weak_points, total_days, profile)
        planning_points = self._planning_points(context, weak_points)

        if diagnosis_meta["needs_more_diagnosis"] and not weak_points:
            planning_points = [self._diagnosis_probe_point(diagnosis)]

        if not planning_points:
            return self._result([], total_days, diagnosis_meta)

        llm_path = self._generate_with_llm(context, profile, planning_points, total_days, diagnosis_meta)
        if llm_path:
            return self._result(llm_path, total_days, diagnosis_meta)

        return self._result(
            self._build_rule_path(planning_points, profile, total_days),
            total_days,
            diagnosis_meta,
        )

    def _build_rule_path(
        self,
        planning_points: list[dict[str, Any]],
        profile: dict[str, Any],
        total_days: int,
    ) -> list[dict[str, Any]]:
        stage_count = self._stage_count(planning_points, total_days)
        grouped_points = self._group_points(planning_points, stage_count)

        learning_path = []
        for index, point_group in enumerate(grouped_points, start=1):
            lead_point = point_group[0]
            names = [str(point.get("name", "重点知识点")) for point in point_group]
            if lead_point.get("point_id") == "diagnosis_probe":
                learning_path.append(
                    {
                        "stage_id": f"stage_{index}",
                        "title": str(lead_point["name"]),
                        "duration": self._duration_for_index(index, stage_count, total_days),
                        "goal": "先完成基础测验或练习记录，确认真实薄弱点后再进入针对性学习。",
                        "tasks": ["完成一次基础测验", "回顾最近错题或困惑点", "确认需要优先补齐的薄弱点"],
                        "resource_types": ["quiz", "practice"],
                        "reason": str(lead_point["reason"]),
                        "source": "agent_generated",
                    }
                )
                continue
            learning_path.append(
                {
                    "stage_id": f"stage_{index}",
                    "title": self._stage_title(index, "、".join(names[:2])),
                    "duration": self._duration_for_index(index, stage_count, total_days),
                    "goal": self._goal(lead_point, profile, names),
                    "tasks": self._tasks(lead_point, profile, index, names),
                    "resource_types": self._resource_types(profile, index),
                    "reason": self._reason(point_group, profile, total_days),
                    "source": "agent_generated",
                }
            )

        if total_days <= 3 and len(learning_path) < 5:
            learning_path.append(
                {
                    "stage_id": f"stage_{len(learning_path) + 1}",
                    "title": "快速复盘与考前检查",
                    "duration": f"第 {total_days} 天",
                    "goal": "用练习题和错题复盘检查核心概念，保证短周期学习能形成可交付结果。",
                    "tasks": ["完成重点练习题", "整理易错点清单", "回看高优先级章节讲义"],
                    "resource_types": ["quiz", "reading"],
                    "reason": "学习时间较短，需要把最后阶段压缩为检测和复盘，避免只学不练。",
                    "source": "agent_generated",
                }
            )

        return learning_path

    def _generate_with_llm(
        self,
        context: dict[str, Any],
        profile: dict[str, Any],
        planning_points: list[dict[str, Any]],
        total_days: int,
        diagnosis_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self.llm_client:
            return []

        course_id = str(context.get("course_id") or "")
        course = course_catalog.get_course(course_id) or {
            "course_id": course_id,
            "course_name": context.get("knowledge_context", {}).get("course_name", course_id),
            "chapters": planning_points,
        }
        payload = {
            "session_id": context.get("session_id"),
            "course_id": course_id,
            "estimated_days": total_days,
            "profile_facts": context.get("profile_facts", {}),
            "profile": self._compact_profile(profile),
            "diagnosis": diagnosis_meta,
            "course": {
                "course_id": course.get("course_id", course_id),
                "course_name": course.get("course_name", course_id),
                "chapters": [
                    {
                        "chapter_id": item.get("chapter_id", index),
                        "title": item.get("title") or item.get("name"),
                        "difficulty": item.get("difficulty", "medium"),
                        "prerequisites": item.get("prerequisites", []),
                    }
                    for index, item in enumerate(course.get("chapters", planning_points), start=1)
                ],
            },
            "candidate_points": planning_points,
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 EduAgent 的学习路径规划智能体。你必须根据学生画像、课程知识库和时间安排生成个性化学习路径。\n"
                    "要求：只输出 JSON；不要输出 Markdown；不要编造课程中不存在的章节；"
                    "必须体现学生基础、薄弱点、学习目标、时间安排和学习偏好；"
                    "如果诊断证据不足，第一阶段必须先安排诊断测验或薄弱点确认；"
                    "每个阶段必须包含 stage_id、title、duration、goal、tasks、resource_types、reason。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"下面是规划输入 JSON，请生成 3-5 个阶段，estimated_days 必须等于 {total_days}。\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]

        try:
            raw = self.llm_client.chat(messages, temperature=0.2, max_tokens=1600)
            parsed = self._parse_json(raw)
        except (LLMClientError, json.JSONDecodeError, TypeError, ValueError):
            return []

        path = parsed.get("learning_path") if isinstance(parsed, dict) else None
        if not isinstance(path, list):
            return []
        return self._normalize_llm_path(path, planning_points, total_days)

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
            raise ValueError("Planner LLM output must be a JSON object.")
        return parsed

    def _normalize_llm_path(
        self,
        path: list[Any],
        planning_points: list[dict[str, Any]],
        total_days: int,
    ) -> list[dict[str, Any]]:
        allowed_terms = {
            str(point.get("name") or point.get("title") or "").strip()
            for point in planning_points
            if str(point.get("name") or point.get("title") or "").strip()
        }
        normalized = []
        for index, item in enumerate(path[:5], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"第 {index} 阶段").strip()
            tasks = [str(task).strip() for task in item.get("tasks", []) if str(task).strip()]
            text = " ".join([title, str(item.get("goal", "")), " ".join(tasks)])
            if allowed_terms and not any(term in text for term in allowed_terms):
                continue
            resource_types = self._clean_resource_types(item.get("resource_types", []))
            normalized.append(
                {
                    "stage_id": str(item.get("stage_id") or f"stage_{index}"),
                    "title": title,
                    "duration": str(item.get("duration") or self._duration_for_index(index, min(len(path), 5), total_days)),
                    "goal": str(item.get("goal") or "完成本阶段核心知识学习。"),
                    "tasks": tasks[:5] or ["阅读课程讲义", "完成配套练习"],
                    "resource_types": resource_types or ["lecture", "quiz"],
                    "reason": str(item.get("reason") or "根据学生画像和课程知识库自动规划。"),
                    "source": "agent_generated",
                }
            )
        return normalized if len(normalized) >= 2 else []

    def _planning_points(self, context: dict[str, Any], weak_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        course_id = str(context.get("course_id") or "")
        course = course_catalog.get_course(course_id) or {}
        chapters = [
            {
                "point_id": f"{course_id}_{chapter.get('chapter_id', index)}",
                "chapter_id": str(chapter.get("chapter_id", index)).zfill(2),
                "name": str(chapter.get("title", f"第 {index} 章")),
                "title": str(chapter.get("title", f"第 {index} 章")),
                "priority": "high" if index <= 3 else "medium",
                "difficulty": chapter.get("difficulty", "medium"),
                "prerequisites": chapter.get("prerequisites", []),
            }
            for index, chapter in enumerate(course.get("chapters", []), start=1)
        ]
        text = " ".join(
            [
                str(context.get("user_message", "")),
                " ".join(str(value) for value in context.get("profile_facts", {}).values()),
            ]
        )
        if chapters and self._is_whole_course_request(text):
            return chapters
        return weak_points or chapters

    def _weak_points(self, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(diagnosis.get("weak_knowledge_points") or [], start=1):
            if isinstance(item, dict):
                point = dict(item)
                name = str(point.get("name") or point.get("topic") or "").strip()
            else:
                point = {}
                name = str(item).strip()
            if not name or self._is_placeholder_weak_point(name):
                continue
            point["name"] = name
            point.setdefault("title", name)
            point.setdefault("point_id", f"diagnosis_{index}")
            point.setdefault("priority", "high")
            point.setdefault("difficulty", "medium")
            point.setdefault("prerequisites", [])
            result.append(point)
        return result

    def _is_placeholder_weak_point(self, name: str) -> bool:
        normalized = name.strip().lower()
        return normalized in {"无诊断数据", "暂无诊断数据", "unknown", "none", "未知", "无", "待诊断", "未诊断"}

    def _diagnosis_meta(
        self,
        diagnosis: dict[str, Any],
        weak_points: list[dict[str, Any]],
        total_days: int,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_chain = diagnosis.get("evidence_chain") if isinstance(diagnosis.get("evidence_chain"), list) else []
        weak_names = [str(point.get("name")) for point in weak_points if point.get("name")]
        references = [f"薄弱点：{name}" for name in weak_names]
        for item in evidence_chain[:3]:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "unknown")
            related = str(item.get("related_knowledge_point") or item.get("signal") or "").strip()
            reference = self._diagnosis_reference(source, related)
            if reference:
                references.append(reference)

        needs_more_evidence = diagnosis.get("needs_more_evidence") is True
        fallback_only = bool(evidence_chain) and all(
            isinstance(item, dict) and item.get("source") in {"fallback_rule", "rule_based"}
            for item in evidence_chain
        )
        needs_more_diagnosis = (bool(diagnosis) and not weak_points) or (needs_more_evidence and fallback_only)
        raw_flags = diagnosis.get("risk_flags")
        risk_flags = list(raw_flags) if isinstance(raw_flags, list) else []
        if needs_more_diagnosis and "evidence_insufficient" not in risk_flags:
            risk_flags.append("evidence_insufficient")
        time_limited = total_days <= 3 or self._has_limited_daily_time(profile)
        if time_limited and "time_budget_tight" not in risk_flags:
            risk_flags.append("time_budget_tight")

        priority_basis = ["weak_point_severity" if weak_points else "diagnosis_confirmation"]
        if time_limited:
            priority_basis.append("time_budget")
        if diagnosis.get("recommended_next_actions"):
            priority_basis.append("recommended_next_actions")

        return {
            "diagnosis_used": bool(diagnosis),
            "diagnosis_references": references[:8],
            "needs_more_diagnosis": needs_more_diagnosis,
            "priority_basis": priority_basis,
            "risk_flags": list(dict.fromkeys(str(flag) for flag in risk_flags if flag)),
            "recommended_resource_strategy": (
                "先用基础资料和小测确认薄弱点，再进入针对性练习。"
                if needs_more_diagnosis
                else "先补基础资料，再做专项练习，最后用测验复盘诊断薄弱点。"
            ),
        }

    def _diagnosis_probe_point(self, diagnosis: dict[str, Any]) -> dict[str, Any]:
        actions = diagnosis.get("recommended_next_actions") if isinstance(diagnosis.get("recommended_next_actions"), list) else []
        return {
            "point_id": "diagnosis_probe",
            "name": "基础诊断与薄弱点确认",
            "title": "基础诊断与薄弱点确认",
            "priority": "high",
            "difficulty": "medium",
            "prerequisites": [],
            "reason": "当前诊断证据不足，需要先通过基础测验或追问确认具体薄弱点。",
            "recommended_next_actions": actions,
        }

    def _diagnosis_reference(self, source: str, related: str) -> str:
        labels = {
            "user_message": "用户表达",
            "profile": "学习画像",
            "learning_path": "学习路径",
            "course_catalog": "课程目录",
            "quiz_result": "测验记录",
            "practice_result": "练习记录",
            "fallback_rule": "诊断证据不足",
            "rule_based": "诊断证据不足",
            "unknown": "诊断证据",
        }
        label = labels.get(source, "诊断证据")
        clean_related = self._friendly_visible_text(related)
        if self._is_placeholder_weak_point(clean_related):
            clean_related = ""
        return f"{label}：{clean_related}" if clean_related else label

    def _friendly_visible_text(self, text: str) -> str:
        raw = str(text or "")
        if "Complete one" in raw and ("quiz_result" in raw or "practice_result" in raw):
            return "建议先完成一次基础测验或练习记录，以便确认薄弱点。"
        if "Submit feedback" in raw:
            return "使用推荐资源后，可以补充学习反馈，便于后续调整路径。"
        replacements = {
            "Complete one quiz_result or practice_result so the next diagnosis has behavioral evidence.": "建议先完成一次基础测验或练习记录，以便确认薄弱点。",
            "Submit feedback after using the recommended resource.": "使用推荐资源后，可以补充学习反馈，便于后续调整路径。",
            "quiz_result": "测验记录",
            "practice_result": "练习记录",
            "recommended resource": "推荐资源",
            "fallback_rule": "诊断证据不足",
        }
        result = raw
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result

    def _result(
        self,
        learning_path: list[dict[str, Any]],
        total_days: int,
        diagnosis_meta: dict[str, Any],
    ) -> dict[str, Any]:
        stage_rationales = [
            {
                "stage_id": stage.get("stage_id"),
                "rationale": stage.get("reason", ""),
            }
            for stage in learning_path
            if isinstance(stage, dict)
        ]
        summary = self._plan_summary(learning_path, diagnosis_meta, total_days)
        return {
            "learning_path": learning_path,
            "stages": learning_path,
            "estimatedDays": total_days,
            "plan_summary": summary,
            "summary": summary,
            "diagnosis_used": diagnosis_meta["diagnosis_used"],
            "diagnosis_references": diagnosis_meta["diagnosis_references"],
            "stage_rationales": stage_rationales,
            "needs_more_diagnosis": diagnosis_meta["needs_more_diagnosis"],
            "priority_basis": diagnosis_meta["priority_basis"],
            "recommended_resource_strategy": diagnosis_meta["recommended_resource_strategy"],
            "risk_flags": diagnosis_meta["risk_flags"],
            "agent_step": self.agent_step(),
        }

    def _plan_summary(
        self,
        learning_path: list[dict[str, Any]],
        diagnosis_meta: dict[str, Any],
        total_days: int,
    ) -> str:
        if diagnosis_meta["needs_more_diagnosis"]:
            return f"诊断证据不足，先用快速测验确认薄弱点，再按结果压缩安排 {total_days} 天学习。"
        titles = [str(stage.get("title", "")) for stage in learning_path[:2] if isinstance(stage, dict)]
        if diagnosis_meta["diagnosis_references"]:
            return f"根据诊断证据优先安排 {'、'.join(titles) or '核心薄弱点'}，总周期 {total_days} 天。"
        return f"根据课程目录和学生画像生成 {total_days} 天学习路径。"

    def _is_whole_course_request(self, text: str) -> bool:
        return any(word in text for word in ["考试", "复习", "完整", "系统", "整门", "全", "通过"])

    def _stage_count(self, planning_points: list[dict[str, Any]], total_days: int) -> int:
        if total_days <= 2:
            return min(3, len(planning_points))
        if total_days <= 5:
            return min(4, len(planning_points))
        return min(5, len(planning_points))

    def _group_points(self, planning_points: list[dict[str, Any]], stage_count: int) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = []
        for index in range(stage_count):
            start = round(index * len(planning_points) / stage_count)
            end = round((index + 1) * len(planning_points) / stage_count)
            groups.append(planning_points[start:end] or [planning_points[min(index, len(planning_points) - 1)]])
        return groups

    def _infer_days(self, message: str, profile: dict[str, Any]) -> int:
        # Collect time-relevant text from the agent prompt and ALL profile dimensions,
        # not just learning_goal / learning_progress.  This catches time_budget stored
        # in learning_rhythm as well as free-form day counts anywhere in the profile.
        profile_texts = [message]
        for key in ("learning_goal", "learning_progress", "learning_rhythm", "time_budget",
                     "knowledge_base", "learning_goal_knowledge", "interests"):
            item = profile.get(key, {})
            val = item.get("value", "") if isinstance(item, dict) else item
            if isinstance(val, str) and val.strip():
                profile_texts.append(str(val))

        text = " ".join(profile_texts)
        text = self._normalize_cn_number_time(text)

        # --- Arabic-digit patterns (already normalised from Chinese) ---
        # Allow optional measure-word "个" between digit and unit
        # (e.g. "2个小时" → 2, "1个星期" → 7)
        hour_match = re.search(r"(\d+)\s*个?\s*(?:小时|h|H)", text)
        if hour_match and "每天" not in text:
            return max(1, ceil(int(hour_match.group(1)) / 24))
        day_match = re.search(r"(\d+)\s*(?:天|日)", text)
        if day_match:
            return max(1, min(60, int(day_match.group(1))))
        week_match = re.search(r"(\d+)\s*个?\s*(?:周|星期)", text)
        if week_match:
            return max(1, min(60, int(week_match.group(1)) * 7))
        month_match = re.search(r"(\d+)\s*个?\s*月", text)
        if month_match:
            return max(1, min(60, int(month_match.group(1)) * 30))

        # --- Compound Chinese numbers (fallback for edge cases that
        #     _normalize_cn_number_time may miss) ---
        # e.g. "十二天" (12), "二十五天" (25), "二十天" (20)
        cn_compound_match = re.search(
            r"([一二两三四五六七八九])?十([一二三四五六七八九])?\s*个?\s*(天|日|周|星期|月)",
            text,
        )
        if cn_compound_match:
            tens = cn_compound_match.group(1)
            ones = cn_compound_match.group(2)
            unit = cn_compound_match.group(3)
            cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                       "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
            total = (cn_map.get(tens, 1) * 10 if tens else 10) + cn_map.get(ones, 0)
            if unit in ("周", "星期"):
                return max(1, min(60, total * 7))
            if unit == "月":
                return max(1, min(60, total * 30))
            return max(1, min(60, total))

        # --- Simple Chinese number + time unit (fallback) ---
        cn_simple_match = re.search(
            r"([一二两三四五六七八九])\s*个?\s*(天|日|周|星期|月)", text
        )
        if cn_simple_match:
            cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                       "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
            total = cn_map.get(cn_simple_match.group(1), 7)
            if cn_simple_match.group(2) in ("周", "星期"):
                return max(1, min(60, total * 7))
            if cn_simple_match.group(2) == "月":
                return max(1, min(60, total * 30))
            return max(1, min(60, total))

        # Default: no time information found — use a reasonable default.
        # 14 days is a typical two-week study plan; not hardcoded to any
        # specific course or user — callers should always prefer
        # user-provided time budget when available.
        return 14

    def _normalize_cn_number_time(self, text: str) -> str:
        cn_all = "一二两三四五六七八九"
        cn_digits = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
                      "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        time_units = r"(?:天|日|周|星期|个小时|小时|个月|月|分钟)"
        tu = time_units  # shorthand

        # 0. Strip measure-word "个" between a Chinese number and a time unit
        #    so that "一个星期" → "一星期", "两个小时" → "两小时", etc.
        text = re.sub(rf"([{cn_all}十])\s*个\s*({tu})", r"\1\2", text)

        # Order matters: most-specific patterns first to avoid partial matches.
        #
        # 1. Y十Z → YZ  (e.g. 二十五天 → 25天) — Chinese 21-99
        for tens_char, tens_val in cn_digits.items():
            for ones_char, ones_val in cn_digits.items():
                text = re.sub(
                    rf"{tens_char}十{ones_char}\s*({tu})",
                    rf"{tens_val}{ones_val}\1",
                    text,
                )

        # 2. Y十 → Y0  (e.g. 二十天 → 20天, 三十天 → 30天)
        #    Must run AFTER Y十Z so "二十五" isn't partially consumed.
        for tens_char, tens_val in cn_digits.items():
            text = re.sub(
                rf"{tens_char}十\s*({tu})",
                rf"{tens_val}0\1",
                text,
            )

        # 3. 十X → 1X  (e.g. 十二天 → 12天) — Chinese 11-19
        #    Negative lookbehind: NOT preceded by another CN digit (prevents
        #    matching "十五" inside "二十五").
        for ones_char, ones_val in cn_digits.items():
            text = re.sub(
                rf"(?<![{cn_all}])十{ones_char}\s*({tu})",
                rf"1{ones_val}\1",
                text,
            )

        # 4. 十 → 10  (bare 十天 → 10天; negative lookbehind prevents matching
        #    "十" inside "二十" or "十二")
        text = re.sub(rf"(?<![{cn_all}])十\s*({tu})", rf"10\1", text)

        # 5. Simple single-digit Chinese numbers (三天 → 3天, 七天 → 7天)
        for cn, digit in cn_digits.items():
            text = re.sub(rf"{cn}\s*({tu})", rf"{digit}\1", text)
        # 半
        text = re.sub(rf"半\s*({tu})", rf"0\1", text)

        return text

    def _context_time_text(self, context: dict[str, Any]) -> str:
        profile_facts = context.get("profile_facts") if isinstance(context.get("profile_facts"), dict) else {}
        return " ".join(
            str(value)
            for value in (
                context.get("user_message", ""),
                context.get("time_budget", ""),
                context.get("learning_goal", ""),
                profile_facts.get("time_budget", ""),
            )
            if value
        )

    def _has_limited_daily_time(self, profile: dict[str, Any]) -> bool:
        text = " ".join(
            str(item.get("value", "") if isinstance(item, dict) else item)
            for item in profile.values()
        )
        return "每天" in text and "小时" in text

    def _stage_title(self, index: int, point_name: str) -> str:
        prefixes = ["补齐基础", "攻克核心", "专项练习", "综合复盘"]
        return f"{prefixes[min(index - 1, len(prefixes) - 1)]}：{point_name}"

    def _compact_profile(self, profile: dict[str, Any]) -> dict[str, str]:
        compact = {}
        for key, item in profile.items():
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
                if value and value != "未提及":
                    compact[key] = value
        return compact

    def _clean_resource_types(self, value: Any) -> list[str]:
        aliases = {
            "case_study": "practice",
            "code": "practice",
            "diagram": "mindmap",
            "text": "lecture",
            "exercise": "quiz",
        }
        allowed = {"lecture", "mindmap", "quiz", "reading", "practice", "multimodal"}
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            normalized = aliases.get(str(item).strip(), str(item).strip())
            if normalized in allowed and normalized not in result:
                result.append(normalized)
        return result

    def _duration_for_index(self, index: int, stage_count: int, total_days: int) -> str:
        days_per_stage = max(1, ceil(total_days / max(1, stage_count)))
        start_day = min(total_days, (index - 1) * days_per_stage + 1)
        end_day = min(total_days, max(start_day, index * days_per_stage))
        return f"第 {start_day}-{end_day} 天" if start_day != end_day else f"第 {start_day} 天"

    def _goal(self, point: dict[str, Any], profile: dict[str, Any], names: list[str] | None = None) -> str:
        prerequisites = "、".join(str(item) for item in point.get("prerequisites", []) if item)
        point_names = "、".join(names or [str(point.get("name", "该知识点"))])
        base = f"理解并掌握 {point_names} 的核心概念、典型题型和常见误区。"
        if prerequisites:
            base += f" 同时补齐前置要求：{prerequisites}。"
        if "考试" in str(profile.get("learning_goal", {}).get("value", "")):
            base += " 重点服务考试通过和基础题型稳定得分。"
        return base

    def _tasks(
        self,
        point: dict[str, Any],
        profile: dict[str, Any],
        index: int,
        names: list[str] | None = None,
    ) -> list[str]:
        name = "、".join(names or [str(point.get("name", "知识点"))])
        tasks = [
            f"阅读《{name}》个性化讲义",
            f"完成 {name} 的概念辨析练习",
        ]
        preference = str(profile.get("cognitive_style", {}).get("value", ""))
        if any(word in preference for word in ["代码", "实操", "实验"]):
            tasks.append(f"运行一个与 {name} 相关的代码/伪代码案例")
        elif any(word in preference for word in ["图解", "思维导图"]):
            tasks.append(f"查看 {name} 的结构图并复述知识关系")
        else:
            tasks.append(f"整理 {name} 的易错点清单")
        if index > 1:
            tasks.append("复盘上一阶段错题和未掌握概念")
        return tasks

    def _reason(self, point_group: list[dict[str, Any]], profile: dict[str, Any], total_days: int) -> str:
        goal = str(profile.get("learning_goal", {}).get("value", ""))
        base = "、".join(str(point.get("name", "")) for point in point_group if point.get("name"))
        if total_days <= 3:
            return f"学习周期只有 {total_days} 天，优先压缩安排 {base} 等高频基础内容。"
        if self._has_limited_daily_time(profile):
            return f"每天学习时间有限，优先安排 {base}，用基础资料和短练习压缩推进。"
        if "考试" in goal:
            return f"学生目标偏考试通过，{base} 是课程复习中的基础或高频模块。"
        return f"根据课程先修关系和学生画像，当前阶段适合集中处理 {base}。"

    def _resource_types(self, profile: dict[str, Any], index: int) -> list[str]:
        preference = str(profile.get("cognitive_style", {}).get("value", ""))
        types = ["lecture", "quiz"]
        if any(word in preference for word in ["图解", "思维导图"]):
            types.append("mindmap")
        if any(word in preference for word in ["代码", "实操", "实验"]):
            types.append("practice")
        if index == 1:
            types.append("reading")
        return list(dict.fromkeys(types))
