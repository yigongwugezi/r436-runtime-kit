"""
学习诊断智能体 — 综合分析学习行为、画像、用户自述等多源证据。
LLM 优先进行综合诊断，规则保留完整兜底。
"""

import json
import logging
import re
from collections import Counter
from typing import Any

from app.agents.base import BaseAgent
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)


def _spaced_repetition_interval(score: float) -> int:
    """Ebbinghaus-based spaced repetition scheduler. Returns days until next review."""
    if score < 30:   return 1
    if score < 50:   return 2
    if score < 65:   return 4
    if score < 80:   return 7
    if score < 90:   return 15
    if score < 95:   return 30
    return 60  # mastered — review in 2 months


class DiagnosisAgent(BaseAgent):
    agent_id = "diagnosis_agent"
    agent_name = "学习诊断智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """主入口。支持 mode="adaptive" 进行三步自适应诊断。"""
        mode = str(context.get("mode", "standard"))

        if mode == "adaptive":
            return self._run_adaptive_diagnosis(context)

        return self._run_standard_diagnosis(context)

    def _run_standard_diagnosis(self, context: dict[str, Any]) -> dict[str, Any]:
        """标准诊断模式（原有逻辑）。"""
        user_message = str(context.get("user_message") or "").strip()
        profile = self._profile_map(context.get("profile"))
        profile_facts = context.get("profile_facts") if isinstance(context.get("profile_facts"), dict) else {}
        stages = self._stages(context.get("learning_path"))
        resources = list(context.get("resources") or [])
        points = list(context.get("knowledge_context", {}).get("retrieved_points", []))
        analytics = context.get("analytics") if isinstance(context.get("analytics"), dict) else {}
        existing_diagnosis = context.get("diagnosis") if isinstance(context.get("diagnosis"), dict) else {}

        if self.llm_client:
            try:
                llm_result = self._try_llm_diagnosis(
                    user_message=user_message, profile=profile, profile_facts=profile_facts,
                    analytics=analytics, existing_diagnosis=existing_diagnosis,
                    stages=stages, resources=resources, points=points,
                )
                if llm_result:
                    return llm_result
                logger.warning("DiagnosisAgent LLM returned None (parsing or validation failed)")
            except Exception as e:
                logger.error("DiagnosisAgent LLM call crashed: %s", e, exc_info=True)

        logger.info("LLM unavailable or failed, using rule-based diagnosis")
        return self._rule_based_diagnosis(
            user_message=user_message, profile=profile, profile_facts=profile_facts,
            stages=stages, resources=resources, points=points,
            analytics=analytics, existing_diagnosis=existing_diagnosis,
        )

    # ── 自适应诊断（三步流程）──

    def _run_adaptive_diagnosis(self, context: dict[str, Any]) -> dict[str, Any]:
        """三步自适应诊断。

        Step 1: 生成覆盖性诊断题（10-15道）
        Step 2: 基于作答结果，针对薄弱区追加变式题（20-30道）
        Step 3: 综合分析 → 掌握度分级 → 输出知识状态矩阵
        """
        user_message = str(context.get("user_message", "")).strip()
        profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}
        knowledge_points = self._collect_knowledge_points(context)

        # ── Step 1: 快速定位测试 ──
        step1_questions = []
        if self.llm_client and knowledge_points:
            step1_questions = self._generate_diagnostic_questions(
                knowledge_points, count=min(15, len(knowledge_points) * 2),
                difficulty="easy", step_label="快速定位"
            )

        # ── Step 2: 如果有作答数据，追加精细诊断题 ──
        step2_questions = []
        previous_grades = context.get("previous_grades", []) or []
        if previous_grades and self.llm_client:
            weak_points = self._analyze_weak_areas(previous_grades, knowledge_points)
            if weak_points:
                step2_questions = self._generate_diagnostic_questions(
                    weak_points, count=min(30, len(weak_points) * 4),
                    difficulty="medium", step_label="精细诊断"
                )

        # ── Step 3: 掌握度分析 ──
        all_grades = (context.get("previous_grades", []) or []) + previous_grades
        mastery = self._estimate_mastery(all_grades, knowledge_points)
        weak_kps = self._rank_weak_points(mastery)

        # 综合置信度：各知识点置信度的均值
        overall_confidence = round(sum(m.get("confidence", 0) for m in mastery) / max(1, len(mastery)), 2)
        # 趋势统计
        declining_count = sum(1 for m in mastery if m.get("trend") == "declining")
        improving_count = sum(1 for m in mastery if m.get("trend") == "improving")

        # ── DeepTutor-style knowledge type classification ──
        knowledge_types = {"记忆型": "memory", "概念型": "concept", "程序型": "procedure", "设计型": "design"}
        error_type_map = {"知识结构性": "structural", "理解偏差型": "deviation", "应用错误": "application", "元认知型": "metacognitive"}
        for m in mastery:
            name = str(m.get("name", "")).lower()
            if any(w in name for w in ["定义", "概念", "原理", "是什么"]):
                m["knowledge_type"] = "concept"
            elif any(w in name for w in ["算法", "步骤", "流程", "方法", "计算"]):
                m["knowledge_type"] = "procedure"
            elif any(w in name for w in ["设计", "架构", "模式", "项目"]):
                m["knowledge_type"] = "design"
            else:
                m["knowledge_type"] = "memory"
            m.setdefault("error_type", "structural" if m.get("score", 50) < 40 else "deviation" if m.get("score", 50) < 60 else "")
            # ── 7-stage mastery loop ──
            score = m.get("score", 50)
            if score < 30:     m["stage"] = "diagnostic"
            elif score < 50:   m["stage"] = "explain"
            elif score < 65:   m["stage"] = "feynman_check"
            elif score < 80:   m["stage"] = "practice"
            elif score < 90:   m["stage"] = "error_diagnosis"
            elif score < 95:   m["stage"] = "review"
            else:              m["stage"] = "completed"
            m.setdefault("review_interval_days", _spaced_repetition_interval(score))

        diagnosis = {
            "diagnosis_summary": self._adaptive_summary(mastery, weak_kps, len(step1_questions), len(step2_questions)),
            "summary": self._adaptive_summary(mastery, weak_kps, len(step1_questions), len(step2_questions)),
            "weak_topics": weak_kps[:5],
            "weak_knowledge_points": weak_kps[:8],
            "strengths": [kp["name"] for kp in sorted(mastery, key=lambda x: -(x.get("score", 0)))[:3]],
            "confidence": overall_confidence,
            "diagnosis_confidence": max(0.4, overall_confidence),
            "source": "adaptive_diagnosis",
            "diagnosis_used": True,
            "needs_more_evidence": overall_confidence < 0.5,
            "evidence_chain": [{"source": "adaptive_diagnosis", "signal": f"自适应诊断{len(step1_questions)+len(step2_questions)}题",
                                "weight": 0.7, "reason": "基于学生作答数据的自适应诊断"}],
            "next_actions": ["继续回答追加的诊断题以提升掌握度估计精度"] if len(step2_questions) > 0 else ["完成全部诊断题后自动输出掌握度报告"],
            "recommended_next_actions": [],
            "limitations": [] if previous_grades else ["当前为初步诊断，置信度较低。完成全部题目后精度提升。"],
            "risk_flags": (["initial_diagnosis"] if not previous_grades else []) +
                          (["declining_trend"] if declining_count > improving_count else []),
            "mastery_levels": mastery,  # 掌握度矩阵（含 knowledge_type, error_type, review_interval_days）
            "diagnostic_questions": step1_questions + step2_questions,
            "diagnostic_question_count": len(step1_questions) + len(step2_questions),
            "diagnostic_phase": "step1" if not previous_grades else "step2",
            "trend_stats": {"declining": declining_count, "improving": improving_count,
                           "total": len(mastery)},
        }

        return {"diagnosis": diagnosis, "agent_step": self.agent_step()}

    def _collect_knowledge_points(self, context: dict) -> list[dict]:
        """Collect knowledge points from file, context, and diagnosis data."""
        points = []
        # 1. Load from generated knowledge graph
        try:
            import json, os
            kp_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'knowledge_points.json')
            if os.path.exists(kp_file):
                with open(kp_file, 'r', encoding='utf-8') as f:
                    for kp in json.load(f):
                        points.append({'name': kp['name'], 'type': kp.get('type', 'concept'),
                                       'module': kp.get('module', '')})
        except Exception:
            pass
        # 2. From context
        old = self._collect_knowledge_points_legacy(context)
        if old:
            points.extend(old)
        return points[:20]

    def _collect_knowledge_points_legacy(self, context: dict) -> list[dict]:
        """收集课程知识点作为诊断范围。"""
        points = []
        course = context.get("course", {}) if isinstance(context.get("course"), dict) else {}
        for ch in course.get("chapters", []):
            if isinstance(ch, dict) and ch.get("title"):
                points.append({"name": str(ch["title"]), "difficulty": ch.get("difficulty", "medium")})
        if not points:
            # 从学习路径
            stages = context.get("learning_path", []) or []
            for s in stages[:8]:
                if isinstance(s, dict) and s.get("title"):
                    points.append({"name": str(s["title"]), "difficulty": "medium"})
        if not points:
            # 从画像
            profile_facts = context.get("profile_facts", {})
            course_name = str(profile_facts.get("target_course", ""))
            if course_name:
                points.append({"name": course_name, "difficulty": "medium"})
        return points

    def _generate_diagnostic_questions(self, knowledge_points: list[dict], count: int,
                                        difficulty: str, step_label: str) -> list[dict]:
        """内部调用 QuestionAgent 生成诊断题。"""
        try:
            from app.agents.question_agent import QuestionAgent
            qa = QuestionAgent(mock_data={}, llm_client=self.llm_client)
            q_context = {
                "user_message": f"为{step_label}生成{count}道诊断题",
                "profile_facts": {"_raw_user_message": f"生成{count}道诊断题，难度{difficulty}"},
                "diagnosis": {"weak_knowledge_points": knowledge_points},
                "course": {"chapters": knowledge_points},
            }
            result = qa.run(q_context)
            questions = result.get("questions", [])
            for q in questions:
                q["diagnostic_step"] = step_label
                q["diagnostic"] = True
            return questions
        except Exception as e:
            logger.warning(f"Failed to generate diagnostic questions: {e}")
            return []

    def _analyze_weak_areas(self, grades: list[dict], knowledge_points: list[dict]) -> list[dict]:
        """分析作答结果，识别薄弱知识点（增强版：错误分类 + 难度加权 + 趋势判定）。"""
        ERROR_TYPE_LABELS = {
            "concept": "概念理解错误", "calculation": "计算失误", "misreading": "审题偏差",
            "method": "解题方法不当", "forgetting": "知识点遗忘", "null": "未归类",
        }
        weak = {}
        for g in grades:
            if not isinstance(g, dict):
                continue
            score = g.get("total_score")
            if score is None:
                continue
            kps = g.get("knowledge_points", [])
            error_type = g.get("error_type", "null")
            q_difficulty = g.get("difficulty", "medium")

            for kp in kps:
                name = str(kp) if isinstance(kp, str) else kp.get("name", str(kp))
                if name not in weak:
                    weak[name] = {"errors": 0, "total": 0, "error_types": [], "low_scores": [], "difficulties": []}
                weak[name]["total"] += 1
                weak[name]["difficulties"].append(q_difficulty)
                if score < 60:
                    weak[name]["errors"] += 1
                    weak[name]["low_scores"].append(score)
                    if error_type != "null":
                        weak[name]["error_types"].append(error_type)

        result = []
        for name, stats in weak.items():
            error_rate = stats["errors"] / max(1, stats["total"])
            if error_rate >= 0.3 or stats["total"] >= 3:  # 降低阈值，更敏感
                # 主要错误类型
                if stats["error_types"]:
                    top_error = Counter(stats["error_types"]).most_common(1)[0]
                    error_label = ERROR_TYPE_LABELS.get(top_error[0], top_error[0])
                else:
                    error_label = "综合表现不佳"

                # 平均低分
                avg_low = round(sum(stats["low_scores"]) / max(1, len(stats["low_scores"]))) if stats["low_scores"] else 0

                # 难度分布
                has_hard = any(d == "hard" for d in stats["difficulties"])

                # 优先级判定
                if error_rate >= 0.7 or (error_rate >= 0.5 and has_hard):
                    priority = "high"
                elif error_rate >= 0.4:
                    priority = "medium"
                else:
                    priority = "low"

                result.append({
                    "name": name,
                    "priority": priority,
                    "reason": f"正确率 {100-error_rate:.0f}%，主要问题：{error_label}{'（含难题）' if has_hard else ''}，平均低分 {avg_low}",
                    "error_rate": round(error_rate, 2),
                    "error_type": error_label,
                    "evidence": [
                        f"答题 {stats['total']} 次，错误 {stats['errors']} 次",
                        f"错误类型: {', '.join(set(stats['error_types']))}" if stats["error_types"] else "无明确错误类型",
                        f"平均低分: {avg_low}" if stats["low_scores"] else "",
                    ],
                })
        # 按优先级 + 错误率排序
        result.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["priority"]], -x["error_rate"]))
        return result

    def _estimate_mastery(self, grades: list[dict], knowledge_points: list[dict]) -> list[dict]:
        """基于作答结果估计每个知识点的掌握度（增强版）。

        改进点：
        - 贝叶斯风格更新：alpha（掌握证据）vs beta（未掌握证据）
        - 时间衰减：每30天衰减一半，遗忘的知识点分数回归先验
        - 难度加权：难题答对=更强掌握信号，简单题答错=更强薄弱信号
        - 置信度：随证据量增长，随遗忘衰减
        - 初始先验：50分（无信息先验）
        """
        from datetime import datetime, timezone
        from collections import Counter as _Counter
        now = datetime.now(timezone.utc)
        HALF_LIFE_DAYS = 30  # 半衰期
        DIFF_WEIGHT = {"easy": 0.7, "medium": 1.0, "hard": 1.5}

        mastery: dict[str, dict[str, Any]] = {}
        for kp in knowledge_points:
            name = str(kp.get("name", ""))
            if name:
                mastery[name] = {
                    "name": name,
                    "score": 50,
                    "level": "未学",
                    "evidence_count": 0,
                    "total_weight": 0.0,
                    "difficulty": kp.get("difficulty", "medium"),
                    "confidence": 0.0,
                    "last_updated": None,  # datetime
                    "trend": "stable",  # improving | declining | stable
                    "prior_weight": 3.0,  # 先验权重：需积累多少证据才能偏离先验
                }

        # 按时间排序，保证更新顺序正确
        sorted_grades = sorted(
            [g for g in grades if isinstance(g, dict)],
            key=lambda g: g.get("timestamp", 0) if isinstance(g.get("timestamp"), (int, float)) else 0
        )

        for g in sorted_grades:
            score = g.get("total_score")
            if score is None:
                continue
            score = max(0, min(100, int(score)))

            kps = g.get("knowledge_points", [])
            q_difficulty = str(g.get("difficulty", "medium"))

            # 时间戳处理
            ts = g.get("timestamp")
            if isinstance(ts, (int, float)) and ts > 0:
                grade_time = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                grade_time = now

            diff_w = DIFF_WEIGHT.get(q_difficulty, 1.0)

            for kp in kps:
                name = str(kp) if isinstance(kp, str) else kp.get("name", str(kp))
                if name not in mastery:
                    continue

                m = mastery[name]

                # ── 时间衰减：移动分数向先验 50 回归 ──
                if m["last_updated"] is not None and m["evidence_count"] > 0:
                    days_elapsed = max(0, (grade_time - m["last_updated"]).total_seconds() / 86400)
                    if days_elapsed > 1:
                        decay = 0.5 ** (days_elapsed / HALF_LIFE_DAYS)
                        m["score"] = int(50 + (m["score"] - 50) * decay)
                        m["total_weight"] *= decay
                        m["confidence"] *= decay

                # 记录更新前的分数用于趋势判定
                prev_score = m["score"]

                # ── 加权贝叶斯更新 ──
                # evidence_weight: 难度越高，信息量越大
                # 对于答对的情况：高分=更多的掌握证据；对于答错的情况：低分=更多的薄弱证据
                evidence_w = 1.0 * diff_w

                m["evidence_count"] += 1
                old_w = max(m["total_weight"], 0.01)
                m["total_weight"] = old_w + evidence_w

                # 加权移动平均（本质上是基于 evidence_count 和 evidence_weight 的指数平滑）
                m["score"] = int(round(
                    (m["score"] * old_w + score * evidence_w) / m["total_weight"]
                ))

                # ── 趋势判定：连续比较 ──
                if m["evidence_count"] >= 2:
                    delta = m["score"] - prev_score
                    if delta > 5:
                        m["trend"] = "improving"
                    elif delta < -5:
                        m["trend"] = "declining"
                    else:
                        m["trend"] = "stable"

                m["last_updated"] = grade_time

        # ── 最终化：最后一次衰减 + 置信度 + 分级 ──
        for m in mastery.values():
            if m["last_updated"] is not None and m["evidence_count"] > 0:
                days_elapsed = max(0, (now - m["last_updated"]).total_seconds() / 86400)
                if days_elapsed > 1:
                    decay = 0.5 ** (days_elapsed / HALF_LIFE_DAYS)
                    m["score"] = int(50 + (m["score"] - 50) * decay)
                    m["total_weight"] *= decay

            # 置信度 = f(总证据量)：从0增长至0.95，3个单位权重即达50%
            w = m["total_weight"]
            m["confidence"] = round(min(0.95, w / (w + 3.0)), 2)

            # 分级
            s = m["score"]
            if m["evidence_count"] == 0:
                m["level"] = "未学"
            elif s >= 90:
                m["level"] = "精通"
            elif s >= 70:
                m["level"] = "熟练"
            elif s >= 40:
                m["level"] = "初步"
            else:
                m["level"] = "未学"

            # 确保 JSON 可序列化
            if m["last_updated"] is not None:
                m["last_updated"] = m["last_updated"].isoformat()

        return sorted(mastery.values(), key=lambda x: x["score"])

    def _rank_weak_points(self, mastery: list[dict]) -> list[dict]:
        """按多维度排序薄弱点（增强版）。

        排序维度（按权重）：
        1. 掌握度分数（权重最高）
        2. 置信度（分数高才可信）
        3. 趋势（持续下降 > 稳定 > 上升）
        4. 证据量（证据太少不可靠）
        """
        weak = [m for m in mastery if m.get("level") in ("未学", "初步")]
        # 综合排序分：score越低越前，confidence越高越可信（在低分区中），declining趋势更需关注
        weak.sort(key=lambda x: (
            x.get("score", 50),  # 越低越前
            -(x.get("confidence", 0)),  # 置信度高的优先
            0 if x.get("trend") == "declining" else 1 if x.get("trend") == "stable" else 2,  # 下降趋势优先
        ))
        result = []
        for m in weak:
            s = m.get("score", 50)
            conf = m.get("confidence", 0)
            trend = m.get("trend", "stable")
            trend_label = {"improving": "↑", "declining": "↓", "stable": "→"}.get(trend, "")
            # 生成针对性建议
            if m.get("evidence_count", 0) == 0:
                suggested = "尚未有答题数据，建议先完成诊断测试"
                priority = "medium"
            elif s < 30:
                suggested = "基础严重薄弱，建议从入门资源开始系统学习"
                priority = "high"
            elif s < 50:
                suggested = "需重点强化，建议每日专项练习 + 错题回顾"
                priority = "high"
            elif trend == "declining":
                suggested = "掌握度正在下降，可能存在遗忘，建议安排复习"
                priority = "medium"
            else:
                suggested = "按照学习路径逐步提升即可"
                priority = "medium" if s < 60 else "low"

            result.append({
                "name": m["name"],
                "priority": priority,
                "reason": f"掌握度 {s} 分（{m.get('level', '初步')}）{trend_label}，置信度 {conf:.0%}",
                "mastery_score": s,
                "confidence": round(conf, 2),
                "trend": trend,
                "difficulty": m.get("difficulty", "medium"),
                "evidence_count": m.get("evidence_count", 0),
                "suggested_action": suggested,
            })
        return result

    def _adaptive_summary(self, mastery: list[dict], weak_kps: list[dict],
                           step1_count: int, step2_count: int) -> str:
        levels = {"未学": 0, "初步": 0, "熟练": 0, "精通": 0}
        for m in mastery:
            levels[m.get("level", "未学")] = levels.get(m.get("level", "未学"), 0) + 1
        total = sum(levels.values()) or 1
        return (
            f"自适应诊断完成（共{step1_count+step2_count}题）。"
            f"掌握度分布：精通 {levels['精通']}、熟练 {levels['熟练']}、初步 {levels['初步']}、未学 {levels['未学']}。"
            f"最需加强：{'、'.join(kp['name'] for kp in weak_kps[:3]) or '暂无明确薄弱点'}。"
        )

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        return {
            "diagnosis": {
                "weak_topics": [],
                "weak_knowledge_points": [],
                "diagnosis_summary": "诊断智能体暂时不可用，请稍后重试。",
                "summary": "诊断智能体暂时不可用，请稍后重试。",
                "strengths": [],
                "confidence": 0.0,
                "reason": "智能体生成失败，使用规则兜底",
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "needs_more_evidence": True,
                "evidence": [],
                "evidence_chain": [],
                "next_actions": [],
                "recommended_next_actions": [],
                "limitations": ["诊断智能体当前不可用"],
                "risk_flags": ["diagnosis_unavailable"],
                "recommended_stage_id": None,
                "recommended_resource_ids": [],
                "priority": "medium",
                "recommended_strategy": "智能体恢复后建议重新诊断",
            },
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "DiagnosisAgent fell back to defaults.",
                "error_reason": "Diagnosis agent failed",
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "started_at": None,
                "finished_at": None,
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # LLM 路径
    # ═══════════════════════════════════════════════════════════════

    def _try_llm_diagnosis(
        self,
        user_message: str,
        profile: dict,
        profile_facts: dict,
        analytics: dict,
        existing_diagnosis: dict,
        stages: list,
        resources: list,
        points: list,
    ) -> dict | None:
        """尝试用 LLM 进行综合诊断"""
        try:
            evidence = self._collect_llm_evidence(
                user_message, profile, profile_facts, analytics,
                existing_diagnosis, stages, resources, points
            )
            raw = self._call_llm_for_diagnosis(evidence)
            parsed = self._parse_llm_diagnosis(raw)
            if parsed and parsed.get("weak_topics"):
                return self._format_llm_diagnosis(parsed, evidence, stages, resources, analytics)
        except Exception as e:
            logger.warning(f"LLM diagnosis failed: {e}")
        return None

    def _collect_llm_evidence(
        self,
        user_message: str,
        profile: dict,
        profile_facts: dict,
        analytics: dict,
        existing_diagnosis: dict,
        stages: list,
        resources: list,
        points: list,
    ) -> dict:
        """收集所有证据供 LLM 分析"""
        evidence = {
            "user_message": user_message,
            "profile": {},
            "analytics_summary": {},
            "previous_diagnosis": {},
            "learning_path_summary": [],
            "knowledge_points": [],
        }

        # 画像
        for key, item in profile.items():
            if isinstance(item, dict):
                val = str(item.get("value", "")).strip()
                if val and val != "未提及":
                    evidence["profile"][key] = val

        for key, val in profile_facts.items():
            if val and str(val).strip():
                evidence["profile"][key] = str(val)

        # 行为数据摘要
        if analytics:
            evidence["analytics_summary"] = {
                "eventCount": analytics.get("eventCount", 0),
                "quizAccuracy": analytics.get("quizAccuracy"),
                "weakTopics": analytics.get("weakTopics", [])[:10],
                "eventBreakdown": analytics.get("eventBreakdown", {}),
            }
            recent = analytics.get("recentEvents", [])
            if recent:
                evidence["analytics_summary"]["recentEvents"] = [
                    {
                        "event": e.get("event"),
                        "metadata": e.get("metadata", {}),
                    }
                    for e in recent[:10] if isinstance(e, dict)
                ]

        # 历史诊断
        if existing_diagnosis:
            evidence["previous_diagnosis"] = {
                "weak_topics": existing_diagnosis.get("weak_topics", [])[:5],
                "confidence": existing_diagnosis.get("confidence", 0),
                "summary": existing_diagnosis.get("diagnosis_summary", ""),
            }

        # 学习路径
        for s in stages[:5]:
            if isinstance(s, dict):
                evidence["learning_path_summary"].append({
                    "title": s.get("title", ""),
                    "progress": s.get("progress", s.get("overallProgress", "")),
                })

        # 知识点
        for p in points[:10]:
            if isinstance(p, dict):
                evidence["knowledge_points"].append({
                    "name": p.get("name", ""),
                    "difficulty": p.get("difficulty", "medium"),
                })

        return evidence

    def _call_llm_for_diagnosis(self, evidence: dict) -> str:
        """调用 LLM 进行诊断分析"""
        prompt = f"""你是学习诊断专家。请分析以下学生数据，诊断薄弱知识点。

## 学生自述
{evidence['user_message']}

## 学习画像
{json.dumps(evidence['profile'], ensure_ascii=False, indent=2)}

## 行为数据
{json.dumps(evidence['analytics_summary'], ensure_ascii=False, indent=2)}

## 历史诊断
{json.dumps(evidence['previous_diagnosis'], ensure_ascii=False, indent=2)}

## 学习路径
{json.dumps(evidence['learning_path_summary'], ensure_ascii=False, indent=2)}

## 课程知识点
{json.dumps(evidence['knowledge_points'], ensure_ascii=False, indent=2)}

请返回 JSON 格式诊断结果：
{{
    "weak_topics": [
        {{
            "topic": "知识点名称（完整准确，来自数据或学生自述）",
            "confidence": 0.0-1.0,
            "reason": "诊断依据（综合多源证据说明）",
            "priority": "high|medium|low",
            "source": "证据来源（user_message|analytics|profile|previous_diagnosis|course_knowledge）",
            "evidence": ["具体证据1", "具体证据2"]
        }}
    ],
    "strengths": ["学生掌握较好的知识点"],
    "diagnosis_summary": "诊断总结（自然语言描述，3-5句话）",
    "overall_confidence": 0.0-1.0,
    "overall_reason": "综合判断依据",
    "limitations": ["诊断的局限性说明"],
    "needs_more_evidence": true/false,
    "next_actions": ["建议的下一步行动"],
    "risk_flags": ["风险标记"]
}}

重要：
- topic 必须是完整知识点名，如"微积分的极限概念"而不能是"微积"或"极限"
- 如果数据不足，在 limitations 和 needs_more_evidence 中诚实说明
- 不要编造不存在的知识点
- 如果学生自述了薄弱点，优先采纳并结合数据验证
- 如果完全没有行为数据，降低 overall_confidence
- 只输出 JSON，不要 Markdown 包裹
"""
        return self.llm_client.chat(
            messages=[
                {"role": "system", "content": "你是学习诊断专家。综合分析多源数据。只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
        )

    def _parse_llm_diagnosis(self, raw: str) -> dict | None:
        """解析 LLM 诊断输出（使用统一 JSON 工具）"""
        from app.utils.llm_json import parse_safe

        try:
            def llm_fix(broken: str) -> str:
                return self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": "你是 JSON 修复器。修复以下损坏的 JSON，只输出修复后的 JSON。"},
                        {"role": "user", "content": broken},
                    ],
                    temperature=0,
                    max_tokens=1000,
                )

            result = parse_safe(raw, llm_fix_fn=llm_fix if self.llm_client else None)
            if isinstance(result, dict):
                return result
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse LLM diagnosis JSON: {e}")
        return None

    def _format_llm_diagnosis(
        self,
        parsed: dict,
        evidence: dict,
        stages: list,
        resources: list,
        analytics: dict,
    ) -> dict:
        """将 LLM 诊断结果格式化为标准输出"""
        weak_topics = parsed.get("weak_topics", [])
        strengths = parsed.get("strengths", [])
        summary = parsed.get("diagnosis_summary", "")
        confidence = float(parsed.get("overall_confidence", 0.5))
        reason = parsed.get("overall_reason", "LLM 综合诊断")
        limitations = parsed.get("limitations", [])
        needs_more = parsed.get("needs_more_evidence", False)
        next_actions = parsed.get("next_actions", [])
        risk_flags = parsed.get("risk_flags", [])

        # 转换 weak_topics 为标准格式
        formatted_topics = []
        for i, item in enumerate(weak_topics, 1):
            topic = str(item.get("topic", "")).strip()
            if not topic or topic in {"无诊断数据", "unknown", "none", ""}:
                continue
            formatted_topics.append({
                "topic": topic,
                "reason": str(item.get("reason", "")),
                "confidence": float(item.get("confidence", 0.5)),
                "priority": str(item.get("priority", "medium")),
                "source": str(item.get("source", "llm_diagnosis")),
                "evidence": list(item.get("evidence", [])),
                "difficulty": "medium",
                "prerequisites": [],
                "recommended_stage_id": None,
                "recommended_resource_ids": [],
                "next_actions": [],
            })

        # 生成 weak_knowledge_points（兼容旧格式）
        weak_knowledge_points = []
        for i, item in enumerate(formatted_topics, 1):
            weak_knowledge_points.append({
                "point_id": f"diagnosis_{i}",
                "chapter_id": None,
                "name": item["topic"],
                "reason": item["reason"],
                "priority": item["priority"],
                "difficulty": item.get("difficulty", "medium"),
                "prerequisites": item.get("prerequisites", []),
            })

        # 收集证据
        all_evidence = []
        for item in formatted_topics:
            all_evidence.extend(item.get("evidence", []))
        if analytics.get("quizAccuracy") is not None:
            all_evidence.append(f"测验正确率：{analytics['quizAccuracy']}%")

        # 证据链
        evidence_chain = []
        for item in formatted_topics:
            evidence_chain.append({
                "source": item.get("source", "llm_diagnosis"),
                "signal": item.get("evidence", [""])[0] if item.get("evidence") else item["topic"],
                "related_knowledge_point": item["topic"],
                "weight": item.get("confidence", 0.5),
                "reason": item.get("reason", ""),
            })

        if not evidence_chain:
            evidence_chain.append({
                "source": "llm_diagnosis",
                "signal": evidence.get("user_message", ""),
                "related_knowledge_point": None,
                "weight": 0.3,
                "reason": "诊断证据不足",
            })

        # 匹配学习路径阶段
        recommended_stage_id = None
        if formatted_topics and stages:
            first_topic = formatted_topics[0]["topic"]
            for stage in stages:
                if isinstance(stage, dict) and first_topic in str(stage.get("title", "")):
                    recommended_stage_id = stage.get("stage_id") or stage.get("id")
                    break

        # 匹配推荐资源
        recommended_resource_ids = []
        for topic_item in formatted_topics[:3]:
            topic = topic_item["topic"]
            for res in resources[:10]:
                if isinstance(res, dict) and topic in str(res.get("title", "")):
                    rid = res.get("resource_id") or res.get("id")
                    if rid:
                        recommended_resource_ids.append(str(rid))
        recommended_resource_ids = list(dict.fromkeys(recommended_resource_ids))[:5]

        diagnosis = {
            "summary": summary,
            "diagnosis_summary": summary,
            "weak_topics": formatted_topics,
            "weak_knowledge_points": weak_knowledge_points,
            "strengths": strengths,
            "reason": reason,
            "source": "llm_generated",
            "confidence": confidence,
            "next_actions": next_actions,
            "recommended_next_actions": next_actions,
            "limitations": limitations,
            "evidence": all_evidence,
            "evidence_chain": evidence_chain,
            "needs_more_evidence": needs_more,
            "risk_flags": risk_flags,
            "recommended_stage_id": recommended_stage_id,
            "recommended_resource_ids": recommended_resource_ids,
            "priority": formatted_topics[0].get("priority", "medium") if formatted_topics else "low",
            "recommended_strategy": "；".join(next_actions) if next_actions else "根据诊断结果针对性学习",
        }

        return {
            "diagnosis": diagnosis,
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed",
                "summary": f"LLM 诊断完成，发现 {len(formatted_topics)} 个薄弱点",
                "source": "llm_generated",
                "quality_status": "passed",
                "started_at": None,
                "finished_at": None,
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # 规则兜底（完整保留原 DiagnosisAgent 全部逻辑）
    # ═══════════════════════════════════════════════════════════════

    def _rule_based_diagnosis(
        self,
        user_message: str,
        profile: dict,
        profile_facts: dict,
        stages: list,
        resources: list,
        points: list,
        analytics: dict,
        existing_diagnosis: dict,
    ) -> dict:
        """完整保留的规则诊断逻辑"""
        candidates = self._event_candidates(analytics)
        candidates.extend(self._existing_diagnosis_candidates(existing_diagnosis))
        candidates.extend(self._message_candidates(user_message))
        candidates.extend(self._profile_candidates(profile, profile_facts))
        candidates = self._deduplicate(candidates)

        if not candidates and stages:
            candidates.extend(self._path_candidates(stages))
        if len(candidates) < 2 and points:
            candidates.extend(self._knowledge_candidates(points))

        weak_topics = [
            self._enrich_topic(candidate, stages, resources, analytics)
            for candidate in self._deduplicate(candidates)[:4]
        ]
        limitations = self._limitations(profile, stages, resources, analytics, weak_topics)
        next_actions = self._next_actions(weak_topics, analytics)
        confidence = self._overall_confidence(weak_topics, analytics)
        reason = self._overall_reason(weak_topics)
        evidence_chain = self._evidence_chain(weak_topics, user_message)
        needs_more_evidence = self._needs_more_evidence(weak_topics, analytics)
        risk_flags = self._risk_flags(weak_topics, analytics, profile, stages, resources)

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
            "diagnosis_summary": self._summary(weak_topics),
            "weak_topics": weak_topics,
            "weak_knowledge_points": weak_knowledge_points,
            "strengths": [],
            "reason": reason,
            "source": "rule_based_diagnosis",
            "confidence": confidence,
            "next_actions": next_actions,
            "recommended_next_actions": next_actions,
            "limitations": limitations,
            "evidence": self._collect_evidence(weak_topics, analytics),
            "evidence_chain": evidence_chain,
            "needs_more_evidence": needs_more_evidence,
            "risk_flags": risk_flags,
            "recommended_stage_id": weak_topics[0].get("recommended_stage_id") if weak_topics else None,
            "recommended_resource_ids": self._recommended_resource_ids(weak_topics),
            "priority": weak_topics[0].get("priority", "low") if weak_topics else "low",
            "recommended_strategy": "；".join(next_actions),
        }

        return {
            "diagnosis": diagnosis,
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed",
                "summary": f"规则诊断完成，发现 {len(weak_topics)} 个薄弱点",
                "source": "rule_based",
                "quality_status": "warning",
                "started_at": None,
                "finished_at": None,
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # 以下完整保留原 DiagnosisAgent 所有辅助方法
    # ═══════════════════════════════════════════════════════════════

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
        candidates: dict[str, dict[str, Any]] = {}
        for item in analytics.get("weakTopics") or []:
            if not isinstance(item, dict) or not item.get("topic"):
                continue
            risk = self._clamp(item.get("risk"), default=0.5)
            topic = str(item["topic"]).strip()
            candidates[topic.lower()] = {
                "topic": topic,
                "reason": (
                    f"学习行为记录显示该知识点答错 {item.get('wrongCount', 0)} 次，"
                    f"共记录 {item.get('totalCount', 0)} 次作答。"
                ),
                "source": "analytics",
                "confidence": round(0.65 + 0.25 * risk, 2),
                "priority": "high" if risk >= 0.5 else "medium",
                "evidence": [
                    f"行为数据：{topic} 错误 {item.get('wrongCount', 0)}/"
                    f"{item.get('totalCount', 0)}，风险 {risk:.2f}"
                ],
            }

        for event in self._recent_events(analytics):
            event_type = str(event.get("event") or "")
            if event_type not in {"quiz_result", "quiz_submit", "practice_result"}:
                continue
            metadata = self._event_metadata(event)
            topic = str(metadata.get("topic") or metadata.get("knowledgePoint") or "").strip()
            if not topic:
                continue
            result_fields = {"wrong", "accuracy", "score", "correct", "total"}
            if event_type == "practice_result" and not result_fields.intersection(metadata):
                continue

            wrong, total, accuracy = self._performance(metadata)
            if wrong <= 0 and (accuracy is None or accuracy >= 70):
                continue

            key = topic.lower()
            candidate = candidates.get(key)
            label = "测验" if event_type in {"quiz_result", "quiz_submit"} else "练习"
            details = []
            if total > 0:
                details.append(f"错误 {wrong}/{total}")
            elif wrong > 0:
                details.append(f"错误 {wrong} 次")
            if accuracy is not None:
                details.append(f"正确率 {accuracy:.0f}%")
            evidence = f"行为数据：{topic} {label}{'，'.join(details)}"
            risk = wrong / total if total > 0 else (1 - accuracy / 100 if accuracy is not None else 0.5)
            confidence = 0.82 if event_type in {"quiz_result", "quiz_submit"} else 0.72

            if candidate:
                candidate["confidence"] = max(float(candidate.get("confidence", 0)), confidence)
                candidate["priority"] = "high" if event_type != "practice_result" or risk >= 0.5 else "medium"
                candidate.setdefault("evidence", []).append(evidence)
                candidate["reason"] = f"{candidate['reason']} 最近{label}结果进一步支持该判断。"
            else:
                candidates[key] = {
                    "topic": topic,
                    "reason": f"最近{label}结果显示该知识点存在错误或正确率低于 70%。",
                    "source": event_type,
                    "confidence": confidence,
                    "priority": "high" if event_type != "practice_result" or risk >= 0.5 else "medium",
                    "evidence": [evidence],
                }

        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda item: (priority_order.get(str(item.get("priority")), 3), -float(item.get("confidence", 0))),
        )
        for item in sorted_candidates:
            source = str(item.get("source") or "analytics")
            topic = str(item.get("topic") or "")
            item.setdefault("evidence", []).append(f"[{source}] weak topic candidate={topic}")
        return sorted_candidates

    def _recent_events(self, analytics: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in (analytics.get("recentEvents") or []) if isinstance(item, dict)]

    def _event_metadata(self, event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    def _performance(self, metadata: dict[str, Any]) -> tuple[int, int, float | None]:
        try:
            wrong = max(0, int(metadata.get("wrong", 0) or 0))
        except (TypeError, ValueError):
            wrong = 0
        try:
            total = max(0, int(metadata.get("total", 0) or 0))
        except (TypeError, ValueError):
            total = 0

        accuracy = None
        for key in ("accuracy", "score"):
            if key not in metadata:
                continue
            try:
                accuracy = float(metadata[key])
                accuracy = accuracy * 100 if accuracy <= 1 else accuracy
                break
            except (TypeError, ValueError):
                pass
        if accuracy is None and total > 0 and "correct" in metadata:
            try:
                accuracy = int(metadata["correct"]) / total * 100
            except (TypeError, ValueError):
                pass
        return wrong, total, accuracy

    def _existing_diagnosis_candidates(self, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = []
        raw_topics = diagnosis.get("weak_topics") or diagnosis.get("weak_knowledge_points") or []
        if not isinstance(raw_topics, list):
            return candidates
        for item in raw_topics[:3]:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic") or item.get("name") or "").strip()
            if not topic:
                continue
            candidates.append({
                "topic": topic,
                "reason": str(item.get("reason") or "Previous structured diagnosis marked this as a weak topic."),
                "source": "previous_diagnosis",
                "confidence": min(self._clamp(item.get("confidence"), default=0.62), 0.68),
                "priority": str(item.get("priority") or "medium"),
                "evidence": [f"[previous_diagnosis] weak topic candidate={topic}"],
                "recommended_stage_id": item.get("recommended_stage_id"),
                "recommended_resource_ids": item.get("recommended_resource_ids") or [],
            })
        return candidates

    def _message_candidates(self, message: str) -> list[dict[str, Any]]:
        topics = self._message_topics(message)
        candidates = []
        for topic in topics:
            candidates.append({
                "topic": topic,
                "reason": "用户消息明确表达该知识点不会、混淆或基础薄弱。",
                "source": "user_message",
                "confidence": 0.74,
                "priority": "high",
                "evidence": [f"用户自述：{message}"],
            })
        return candidates

    def _message_topics(self, message: str) -> list[str]:
        text = message.strip()
        if not text:
            return []
        normalized = re.sub(r"[\s。！？!?]", "", text)
        if any(phrase in normalized for phrase in ("学得很乱", "不太会", "哪里有问题", "不知道哪里", "问题在哪")):
            return []

        patterns = (
            r"我?(.+?)(?:都)?不会",
            r"我?(.+?)(?:总是)?搞混",
            r"我?(.+?)基础差",
            r"我?(.+?)不好",
            r"我?(.+?)不懂",
        )
        topics: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, normalized):
                raw = match.group(1)
                raw = re.split(r"但|但是|想学|需要|所以|然后|再", raw)[0]
                for topic in re.split(r"和|与|、|，|,", raw):
                    topic = topic.strip("我也还的了")
                    if topic and topic not in {"感觉", "哪里", "什么", "基础"}:
                        topics.append(topic)
        return list(dict.fromkeys(topics))[:4]

    def _profile_candidates(self, profile: dict[str, Any], profile_facts: dict[str, Any]) -> list[dict[str, Any]]:
        weak_text = self._profile_value(profile, "error_patterns", "weak_points")
        weak_text = weak_text or str(profile_facts.get("weak_points", "")).strip()
        candidates = []
        for topic in self._split_topics(weak_text):
            candidates.append({
                "topic": topic,
                "reason": "学习画像或用户输入明确提到该知识点掌握较弱，需要优先验证和补齐。",
                "source": "profile",
                "confidence": 0.68,
                "priority": "high",
                "evidence": [f"画像薄弱点：{weak_text}"],
            })
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
                return [{
                    "topic": title,
                    "reason": "当前学习路径尚未完成该阶段，暂将其作为需要验证的学习重点。",
                    "source": "learning_path_inference",
                    "confidence": 0.42,
                    "priority": "medium",
                    "evidence": [f"未完成路径阶段：{title}"],
                    "recommended_stage_id": stage.get("stage_id") or stage.get("id"),
                }]
        return []

    def _knowledge_candidates(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for index, point in enumerate(points[:3], start=1):
            topic = str(point.get("name") or f"重点知识点 {index}").strip()
            candidates.append({
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
            })
        return candidates

    def _split_topics(self, value: str) -> list[str]:
        normalized = re.sub(r"[\s：:，,。！？!?]", "", value)
        if not value or any(
            phrase in normalized
            for phrase in ("哪里比较薄", "哪里薄弱", "薄弱点是什么", "哪些知识漏洞")
        ):
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
            topic = topic.strip(" 。！？!?：:")
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
                tag = self._evidence_source_tag(str(item.get("source") or "unknown"))
                item.setdefault("evidence", []).append(f"[{tag}] weak topic candidate={topic}")
                seen.add(key)
                result.append(item)
        return result

    def _evidence_source_tag(self, source: str) -> str:
        if source in {"analytics", "quiz_result", "quiz_submit", "practice_result"}:
            return source
        if source == "profile":
            return "profile"
        if source in {"learning_path_inference", "course_knowledge_inference"}:
            return "learning_path"
        if source == "previous_diagnosis":
            return "previous_diagnosis"
        return source or "unknown"

    def _enrich_topic(self, candidate, stages, resources, analytics):
        item = dict(candidate)
        topic = str(item["topic"])
        stage = self._matching_stage(topic, stages)
        stage_id = item.get("recommended_stage_id") or (
            stage.get("stage_id") or stage.get("id") if stage else None
        )
        resource_ids = self._matching_resource_ids(topic, stage_id, resources, analytics)
        item["recommended_stage_id"] = stage_id
        item["recommended_resource_ids"] = resource_ids
        item["next_actions"] = self._topic_actions(topic, stage_id, resource_ids, analytics)
        item.setdefault("evidence", [])
        if stage_id:
            item["evidence"].append(f"[learning_path] recommended_stage_id={stage_id}")
        if resource_ids:
            item["evidence"].append(f"[resources] recommended_resource_ids={', '.join(resource_ids)}")
        item["evidence"].extend(self._mapped_supporting_evidence(topic, stage_id, resource_ids, analytics))
        item["evidence"].extend(self._resource_provenance_evidence(resource_ids, resources))
        return item

    def _resource_provenance_evidence(self, resource_ids, resources):
        selected = set(resource_ids)
        evidence = []
        for resource in resources:
            resource_id = str(resource.get("resource_id") or resource.get("id") or "")
            if resource_id not in selected:
                continue
            source = str(resource.get("source") or "unknown")
            source_type = str(resource.get("source_type") or "unknown")
            stage_id = str(resource.get("related_stage_id") or "unresolved")
            chapter = str(resource.get("related_chapter") or "unresolved")
            evidence.append(
                f"[resources] Resource provenance: {resource_id}, source={source}, "
                f"source_type={source_type}, stage={stage_id}, chapter={chapter}"
            )
        return evidence

    def _matching_stage(self, topic, stages):
        for stage in stages:
            text = " ".join(str(v) for v in [
                stage.get("title", ""),
                stage.get("goal", ""),
                " ".join(str(t) for t in stage.get("tasks", [])),
            ])
            if topic in text or any(token and token in text for token in self._topic_tokens(topic)):
                return stage
        return None

    def _matching_resource_ids(self, topic, stage_id, resources, analytics):
        activity = self._resource_activity(analytics)
        matches = []
        for resource in resources:
            knowledge_points = resource.get("related_knowledge_points") or resource.get("knowledge_points") or []
            text = " ".join([
                str(resource.get("title", "")),
                str(resource.get("description", "")),
                str(resource.get("related_chapter", "")),
                " ".join(str(p) for p in knowledge_points),
            ])
            same_stage = bool(stage_id and resource.get("related_stage_id") == stage_id)
            same_topic = topic in text or any(token and token in text for token in self._topic_tokens(topic))
            resource_id = resource.get("resource_id") or resource.get("id")
            if resource_id and str(resource_id) not in activity["completed"] and (same_stage or same_topic):
                matches.append(str(resource_id))
        unique_matches = list(dict.fromkeys(matches))
        unique_matches.sort(
            key=lambda rid: (
                0 if rid in activity["viewed"] else 1,
                -activity["counts"].get(rid, 0),
            )
        )
        return unique_matches[:3]

    def _topic_tokens(self, topic):
        return [token for token in re.split(r"[、，,；;\s/]|和|与", topic) if len(token) >= 2]

    def _topic_actions(self, topic, stage_id, resource_ids, analytics):
        actions = [f"先复习「{topic}」的核心概念和前置知识"]
        if resource_ids:
            activity = self._resource_activity(analytics)
            started = [rid for rid in resource_ids if rid in activity["viewed"]]
            if started:
                actions.append(f"先完成已浏览但未完成的资源：{', '.join(started)}")
            else:
                actions.append("完成推荐资源中的讲解与练习，并记录错因")
        else:
            actions.append("完成一组与该知识点直接相关的练习或实操")
        if stage_id:
            actions.append(f"回到学习路径阶段 {stage_id} 复核完成情况")
        if resource_ids:
            actions.append(f"Complete recommended resource(s): {', '.join(resource_ids[:2])}")
        else:
            actions.append(f"Complete one quiz_result or practice_result for {topic}.")
        if stage_id:
            actions.append(f"Review learning_path stage {stage_id}.")
        actions.append("Submit feedback after using the recommended resource.")
        return actions

    def _resource_activity(self, analytics):
        completed = set()
        viewed = set()
        counts = {}
        for item in analytics.get("topResources") or []:
            if not isinstance(item, dict) or not item.get("resourceId"):
                continue
            resource_id = str(item["resourceId"])
            try:
                counts[resource_id] = int(item.get("count", 0) or 0)
            except (TypeError, ValueError):
                counts[resource_id] = 0
        for event in self._recent_events(analytics):
            resource_id = str(event.get("resourceId") or "").strip()
            if not resource_id:
                continue
            if event.get("event") == "resource_complete":
                completed.add(resource_id)
            elif event.get("event") == "resource_view":
                viewed.add(resource_id)
        return {"completed": completed, "viewed": viewed - completed, "counts": counts}

    def _mapped_supporting_evidence(self, topic, stage_id, resource_ids, analytics):
        evidence = []
        for event in self._recent_events(analytics):
            metadata = self._event_metadata(event)
            event_topic = str(metadata.get("topic") or metadata.get("knowledgePoint") or "")
            event_stage = str(metadata.get("stageId") or metadata.get("stage_id") or "")
            resource_id = str(event.get("resourceId") or "")
            is_mapped = (
                (event_topic and event_topic == topic)
                or (stage_id and event_stage == stage_id)
                or (resource_id and resource_id in resource_ids)
            )
            if not is_mapped:
                continue
            if event.get("event") == "feedback" and self._is_negative_feedback(metadata):
                evidence.append(self._feedback_evidence(resource_id, metadata))
                evidence.append(f"[feedback] resource={resource_id or 'unresolved'}; negative=True")
            elif event.get("event") == "node_progress":
                status = metadata.get("status")
                evidence.append(f"阶段进度：{event_stage or resource_id} 状态 {status or 'unknown'}")
        return evidence

    def _limitations(self, profile, stages, resources, analytics, weak_topics):
        limitations = []
        if not profile:
            limitations.append("缺少结构化学习画像，无法充分判断基础、目标和学习偏好。")
        if not stages:
            limitations.append("缺少学习路径，无法将薄弱点精确绑定到学习阶段。")
        if not resources:
            limitations.append("缺少已生成资源，暂时无法给出可靠的资源级推荐。")
        event_count = analytics.get("eventCount", 0)
        events = self._recent_events(analytics)
        breakdown = analytics.get("eventBreakdown") if isinstance(analytics.get("eventBreakdown"), dict) else {}
        diagnostic_count = sum(
            int(breakdown.get(et, 0) or 0)
            for et in ("quiz_result", "quiz_submit", "practice_result", "feedback")
        )
        has_topic = any(
            self._event_metadata(e).get("topic") or self._event_metadata(e).get("knowledgePoint")
            for e in events
            if e.get("event") in {"quiz_result", "quiz_submit", "practice_result", "feedback"}
        )
        has_result = any(
            {"wrong", "accuracy", "score", "correct", "total", "mastery"}.intersection(
                self._event_metadata(e)
            )
            for e in events
        )
        resource_behavior_count = sum(
            int(breakdown.get(et, 0) or 0)
            for et in ("resource_view", "resource_complete", "node_progress")
        )

        if not event_count:
            limitations.append(
                "当前 session 暂无测验、练习、反馈或进度等学习事件，本次诊断主要基于画像与学习路径推断，行为数据仍为空。"
            )
        elif diagnostic_count and not has_topic:
            limitations.append(
                "已记录学习事件，但 quiz/practice/feedback 缺少 topic 或 knowledgePoint 标注，暂不能稳定定位到具体薄弱知识点。"
            )
        if resource_behavior_count and not has_result:
            limitations.append(
                "已记录资源浏览/完成行为，但缺少正确率、错题数或 mastery 结果字段，诊断置信度仍有限。"
            )
        if not weak_topics:
            limitations.append("当前证据不足，尚不能确认具体薄弱知识点。")
        if not event_count:
            limitations.append(
                "No quiz_result/practice_result/feedback/node_progress events are available; "
                "this is an initial diagnosis based on profile, learning_path and resources."
            )
        elif not diagnostic_count:
            limitations.append(
                "Learning events exist, but no quiz_result or practice_result outcome is available; "
                "confidence remains limited."
            )
        elif diagnostic_count and not has_topic:
            limitations.append(
                "Learning events exist, but quiz/practice/feedback records lack topic or knowledgePoint labels."
            )
        if resource_behavior_count and not has_result:
            limitations.append(
                "Resource behavior exists, but accuracy/wrong/correct/total/mastery result fields are missing."
            )
        if not weak_topics:
            limitations.append(
                "Insufficient evidence: complete at least one quiz_result or practice_result before relying on diagnosis."
            )
        return limitations

    def _next_actions(self, weak_topics, analytics):
        if not weak_topics:
            actions = [
                "补充目标课程、已有基础和自述薄弱点",
                "先生成学习路径和配套资源",
                "完成一次测验或实操后重新发起诊断",
            ]
        else:
            actions = []
            for item in weak_topics[:2]:
                actions.extend(item.get("next_actions", []))

        recommended_stages = {
            str(item.get("recommended_stage_id"))
            for item in weak_topics
            if item.get("recommended_stage_id")
        }
        for event in reversed(self._recent_events(analytics)):
            if event.get("event") != "node_progress":
                continue
            metadata = self._event_metadata(event)
            stage_id = str(metadata.get("stageId") or metadata.get("stage_id") or "")
            status = str(metadata.get("status") or "")
            if stage_id in recommended_stages and status in {"in_progress", "available"}:
                actions.append(f"继续推进阶段 {stage_id}，完成后再用测验结果复核诊断")
                break
        if not weak_topics:
            actions.append("Complete one quiz_result or practice_result so the next diagnosis has behavioral evidence.")
        return list(dict.fromkeys(actions))[:5]

    def _overall_confidence(self, weak_topics, analytics):
        if not weak_topics:
            return 0.15
        values = [self._clamp(item.get("confidence"), default=0.3) for item in weak_topics]
        confidence = sum(values) / len(values)
        if not self._has_behavioral_diagnosis_evidence(analytics):
            confidence = min(confidence, 0.58)
        return round(confidence, 2)

    def _has_behavioral_diagnosis_evidence(self, analytics):
        if analytics.get("weakTopics"):
            return True
        breakdown = analytics.get("eventBreakdown")
        if isinstance(breakdown, dict) and any(
            int(breakdown.get(et, 0) or 0) > 0
            for et in ("quiz_result", "quiz_submit", "practice_result")
        ):
            return True
        result_fields = {"wrong", "accuracy", "score", "correct", "total", "mastery"}
        for event in self._recent_events(analytics):
            if event.get("event") not in {"quiz_result", "quiz_submit", "practice_result"}:
                continue
            metadata = self._event_metadata(event)
            if result_fields.intersection(metadata):
                return True
        return False

    def _overall_reason(self, weak_topics):
        if not weak_topics:
            return "当前缺少可验证的画像薄弱点和学习行为证据，无法形成确定诊断。"
        sources = {str(item.get("source")) for item in weak_topics}
        if sources.intersection({"analytics", "learning_events", "quiz_result", "quiz_submit", "practice_result"}):
            return "诊断综合了当前学习行为、学习画像、路径阶段和可用资源。"
        return "诊断基于当前学习画像、学习路径和资源关联推断，仍需行为数据进一步验证。"

    def _summary(self, weak_topics):
        if not weak_topics:
            return "现有数据不足以确认具体薄弱点，建议先补充学习信息并完成一次可记录的练习。"
        names = "、".join(str(item["topic"]) for item in weak_topics[:3])
        return f"当前优先关注：{names}。请按建议行动验证并逐步收窄诊断范围。"

    def _collect_evidence(self, weak_topics, analytics):
        evidence = []
        for item in weak_topics:
            evidence.extend(str(v) for v in item.get("evidence", []) if v)
        evidence.extend(self._analytics_evidence(analytics))
        evidence.extend(self._event_source_evidence(analytics))
        return list(dict.fromkeys(evidence))

    def _evidence_chain(self, weak_topics, user_message):
        chain = []
        for item in weak_topics:
            source = self._chain_source(str(item.get("source") or "rule_based"))
            topic = str(item.get("topic") or "")
            signal = self._chain_signal(item, user_message)
            chain.append({
                "source": source,
                "signal": signal,
                "related_knowledge_point": topic,
                "weight": self._clamp(item.get("confidence"), default=0.4),
                "reason": str(item.get("reason") or "该证据支持当前薄弱点诊断。"),
            })
        if not chain:
            signal = user_message or "缺少明确薄弱点、学习路径或测验结果。"
            chain.append({
                "source": "fallback_rule",
                "signal": signal,
                "related_knowledge_point": None,
                "weight": 0.2,
                "reason": "当前输入只能说明存在学习困惑，尚不足以定位具体知识点。",
            })
        return chain

    def _chain_source(self, source):
        mapping = {
            "user_message": "user_message",
            "profile": "profile",
            "learning_path_inference": "learning_path",
            "course_knowledge_inference": "course_catalog",
            "quiz_result": "quiz_result",
            "quiz_submit": "quiz_result",
            "practice_result": "quiz_result",
            "analytics": "quiz_result",
        }
        return mapping.get(source, "rule_based")

    def _chain_signal(self, item, user_message):
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        if evidence:
            return str(evidence[0])
        if item.get("source") == "user_message" and user_message:
            return user_message
        return str(item.get("topic") or "weak topic candidate")

    def _needs_more_evidence(self, weak_topics, analytics):
        if not weak_topics:
            return True
        return not self._has_behavioral_diagnosis_evidence(analytics)

    def _risk_flags(self, weak_topics, analytics, profile, stages, resources):
        flags = []
        if not weak_topics:
            flags.append("insufficient_evidence")
        if not self._has_behavioral_diagnosis_evidence(analytics):
            flags.append("missing_quiz_or_practice_result")
        if not profile:
            flags.append("missing_profile")
        if not stages:
            flags.append("missing_learning_path")
        if not resources:
            flags.append("missing_resources")
        return flags

    def _event_source_evidence(self, analytics):
        evidence = []
        breakdown = analytics.get("eventBreakdown")
        if isinstance(breakdown, dict) and breakdown:
            evidence.append(f"[analytics] eventBreakdown={breakdown}")
        for event in self._recent_events(analytics):
            event_type = str(event.get("event") or "")
            if not event_type:
                continue
            resource_id = str(event.get("resourceId") or "unresolved")
            metadata = self._event_metadata(event)
            evidence.append(
                f"[{event_type}] resource={resource_id}; metadata_keys={','.join(sorted(metadata.keys()))}"
            )
        for item in analytics.get("topResources") or []:
            if isinstance(item, dict) and item.get("resourceId"):
                evidence.append(f"[resource_view] topResource={item['resourceId']}; count={item.get('count', 0)}")
                break
        return evidence

    def _analytics_evidence(self, analytics):
        evidence = []
        quiz_accuracy = analytics.get("quizAccuracy")
        if quiz_accuracy is not None:
            try:
                evidence.append(f"[analytics] quizAccuracy={float(quiz_accuracy):.0f}%")
            except (TypeError, ValueError):
                pass
            try:
                evidence.append(f"测验统计：累计正确率 {float(quiz_accuracy):.0f}%")
            except (TypeError, ValueError):
                pass

        breakdown = analytics.get("eventBreakdown")
        if isinstance(breakdown, dict) and breakdown:
            details = "，".join(f"{et} {c} 次" for et, c in breakdown.items() if c)
            if details:
                evidence.append(f"学习事件统计：{details}")

        for event in self._recent_events(analytics):
            event_type = str(event.get("event") or "")
            resource_id = str(event.get("resourceId") or "未标注资源")
            metadata = self._event_metadata(event)
            if event_type:
                evidence.append(
                    f"[{event_type}] resource={resource_id}; metadata_keys={','.join(sorted(metadata.keys()))}"
                )
            if event_type == "resource_complete":
                evidence.append(f"资源完成：{resource_id} 已完成")
            elif event_type == "feedback" and self._is_negative_feedback(metadata):
                evidence.append(self._feedback_evidence(resource_id, metadata))
            elif event_type == "node_progress":
                stage_id = metadata.get("stageId") or metadata.get("stage_id") or resource_id
                evidence.append(f"阶段进度：{stage_id} 状态 {metadata.get('status', 'unknown')}")
            elif event_type == "practice_result":
                has_topic = metadata.get("topic") or metadata.get("knowledgePoint")
                result_fields = {"wrong", "accuracy", "score", "correct", "total"}
                if not has_topic or not result_fields.intersection(metadata):
                    evidence.append(f"练习记录：{resource_id} 已记录，但缺少知识点标注或结果字段")

        for item in (analytics.get("topResources") or [])[:1]:
            if isinstance(item, dict) and item.get("resourceId"):
                evidence.append(f"[resource_view] topResource={item['resourceId']}; count={item.get('count', 0)}")
                evidence.append(f"资源活跃：{item['resourceId']} 累计 {item.get('count', 0)} 次学习事件")
        return evidence

    def _is_negative_feedback(self, metadata):
        try:
            low_rating = "rating" in metadata and float(metadata["rating"]) <= 2
        except (TypeError, ValueError):
            low_rating = False
        return low_rating or metadata.get("difficultyMatch") is False

    def _feedback_evidence(self, resource_id, metadata):
        details = []
        if "rating" in metadata:
            details.append(f"评分 {metadata['rating']}")
        if metadata.get("difficultyMatch") is False:
            details.append("难度不匹配")
        return f"资源反馈：{resource_id or '未标注资源'} {'，'.join(details)}"

    def _recommended_resource_ids(self, weak_topics):
        resource_ids = []
        for item in weak_topics:
            resource_ids.extend(str(v) for v in item.get("recommended_resource_ids", []) if v)
        return list(dict.fromkeys(resource_ids))[:5]

    def _clamp(self, value, default):
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default