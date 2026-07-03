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
        mode = str(context.get("mode", "plan"))

        # ── 动态调整模式：基于诊断结果调整已有路径 ──
        if mode == "adjust" and context.get("existing_path"):
            return self._run_adjustment(context, diagnosis, profile)

        # ── 全新规划模式 ──
        weak_points = self._extract_weak_points(diagnosis)
        planning_points = self._get_planning_points(context, weak_points)

        time_text = self._collect_time_text(context)
        total_days = self._infer_days(time_text, profile)

        diag_meta = self._build_diagnosis_meta(diagnosis, weak_points, total_days, profile, time_text)

        if diag_meta["needs_more_diagnosis"] and not weak_points and not planning_points:
            planning_points = [self._make_probe_point(diagnosis)]

        llm_path = self._try_generate_with_llm(context, profile, planning_points, total_days, diag_meta)
        if llm_path:
            result = self._make_result(llm_path, total_days, diag_meta)
            result["review_tasks"] = self._generate_review_tasks(llm_path)
            return result

        logger.info("LLM unavailable or failed, using rule-based path")
        rule_path = self._build_rule_path(planning_points, profile, total_days, diag_meta)
        result = self._make_result(rule_path, total_days, diag_meta)
        result["review_tasks"] = self._generate_review_tasks(rule_path)
        return result

    # ── 动态调整（M5）──

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
1. 生成4-5个阶段，总天数必须正好{total_days}天
2. 每个阶段包含字段：
   - stage_id: 字符串格式 "stage_N"（N为阶段序号，如"stage_1"、"stage_2"）
   - title: 必须以具体学习内容命名，严禁模板化标题
   - duration: 字符串格式 "第X-Y天"（单天用"第X天"），如"第1-3天"
   - goal, tasks, daily_tasks, resource_types, reason 同上
3. title必须以具体的学习内容命名（如"极限与连续"、"导数与微分"），绝对不要用"第一阶段"、"补齐基础"这种模板化标题
4-7. 同上
8. daily_tasks 格式：\n   [{{"day": 1, "tasks": ["任务1", "任务2"]}}, ...]\n   长度等于该阶段天数
9. 只输出JSON，格式：{{"learning_path": [...]}}
10. 对于微积分/高等数学，参考同济版章节结构，至少包含：极限与连续、导数与微分、导数应用、不定积分、定积分与综合复习"""

        try:
            raw = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是学习路径规划专家，擅长根据学生情况设计个性化学习阶段。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
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
        from app.utils.llm_json import parse_safe

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

    def _normalize_path(self, path: list, planning_points: list, total_days: int) -> list[dict]:
        """标准化 LLM 生成的学习路径。
        只做基本清洗：过滤模板化标题、补全缺失字段。不再用不完整课程目录做关键词过滤。
        """
        result = []
        for i, item in enumerate(path[:5], 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", f"第{i}阶段")).strip()
            # 只过滤明显的模板化标题
            if self._is_goal_like_title(title):
                continue
            tasks = [str(t).strip() for t in item.get("tasks", []) if str(t).strip()]

            result.append({
                "stage_id": str(item.get("stage_id", f"stage_{i}")),
                "title": title,
                "duration": str(item.get("duration", f"第{i}阶段")),
                "goal": str(item.get("goal", "完成本阶段核心知识学习。")),
                "tasks": tasks or ["学习课程讲义", "完成配套练习"],
                "daily_tasks": self._normalize_daily_tasks(
                    item.get("daily_tasks", []),
                    str(item.get("duration", f"第{i}阶段")),
                    tasks,
                ),
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

    def _normalize_daily_tasks(
        self,
        daily_tasks_raw: Any,
        duration: str,
        stage_tasks: list[str],
    ) -> list[dict]:
        """Normalize daily_tasks from LLM output or derive from stage tasks.

        If the LLM provided a valid per-day breakdown, validate and use it.
        Otherwise, distribute stage_tasks round-robin across the stage's day range.
        """
        if isinstance(daily_tasks_raw, list) and daily_tasks_raw:
            result = []
            for entry in daily_tasks_raw:
                if isinstance(entry, dict):
                    day = int(entry.get("day", 1))
                    day_tasks = entry.get("tasks", [])
                    if isinstance(day_tasks, list):
                        cleaned = [str(t).strip() for t in day_tasks if str(t).strip()]
                        if cleaned:
                            result.append({"day": day, "tasks": cleaned})
            if result:
                return result

        # Derive from duration + stage_tasks
        day_nums = re.findall(r"\d+", duration)
        if len(day_nums) >= 2:
            start_day, end_day = int(day_nums[0]), int(day_nums[1])
        elif len(day_nums) == 1:
            start_day = end_day = int(day_nums[0])
        else:
            start_day = end_day = 1

        num_days = max(1, end_day - start_day + 1)
        if not stage_tasks:
            stage_tasks = ["学习课程讲义", "完成配套练习"]

        daily: dict[int, list[str]] = {d: [] for d in range(start_day, end_day + 1)}
        for idx, task in enumerate(stage_tasks):
            day = start_day + (idx % num_days)
            daily[day].append(task)

        return [
            {"day": day, "tasks": day_tasks}
            for day, day_tasks in sorted(daily.items())
            if day_tasks
        ]

    def _derive_daily_tasks_from_fallback(
        self,
        tasks: list[str],
        duration: str,
        stage_idx: int,
        n_stages: int,
        total_days: int,
    ) -> list[dict]:
        """Derive daily tasks for the rule-based fallback path."""
        day_nums = re.findall(r"\d+", duration)
        if len(day_nums) >= 2:
            start_day, end_day = int(day_nums[0]), int(day_nums[1])
        elif len(day_nums) == 1:
            start_day = end_day = int(day_nums[0])
        else:
            dps = max(1, ceil(total_days / n_stages))
            start_day = min(total_days, (stage_idx - 1) * dps + 1)
            end_day = min(total_days, max(start_day, stage_idx * dps))

        num_days = max(1, end_day - start_day + 1)
        if not tasks:
            tasks = ["学习课程讲义", "完成配套练习"]

        daily: dict[int, list[str]] = {d: [] for d in range(start_day, end_day + 1)}
        for idx, task in enumerate(tasks):
            day = start_day + (idx % num_days)
            daily[day].append(task)

        return [
            {"day": day, "tasks": day_tasks}
            for day, day_tasks in sorted(daily.items())
            if day_tasks
        ]

    # ── 规则兜底 ──

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
