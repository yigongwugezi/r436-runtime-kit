"""
自动批改智能体 — 多维评分 + 错误归类 + 改进建议。
接收题目信息 + 学生作答 + 参考答案，输出结构化判卷结果。
"""

import json
import logging
from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.utils.llm_json import parse_safe

logger = logging.getLogger(__name__)

ERROR_TYPES = ["concept", "calculation", "misreading", "method", "forgetting"]
ERROR_LABELS: dict[str, str] = {
    "concept": "概念错误",
    "calculation": "计算失误",
    "misreading": "审题不清",
    "method": "方法不当",
    "forgetting": "知识遗忘",
}
ERROR_ACTIONS: dict[str, str] = {
    "concept": "推送对应概念讲解，回溯前置知识",
    "calculation": "提示验算方法，建议同类计算练习",
    "misreading": "标注关键词训练，提升审题习惯",
    "method": "推荐更优解法，拓展思维",
    "forgetting": "加入艾宾浩斯复习队列",
}

# 自动衔接：错误类型 → 系统动作
ERROR_AUTO_ACTIONS: dict[str, dict[str, Any]] = {
    "concept": {"action": "recommend_resources", "reason": "概念错误，推荐基础知识资源"},
    "calculation": {"action": "suggest_practice", "reason": "计算失误，推荐同类练习"},
    "misreading": {"action": "flag_keyword_training", "reason": "审题偏差，标注关键词训练"},
    "method": {"action": "recommend_better_solution", "reason": "方法不当，推荐更优解法"},
    "forgetting": {"action": "add_to_review_queue", "reason": "知识遗忘，加入艾宾浩斯复习队列",
                   "review_intervals": [1, 2, 4, 7, 15, 30]},
}


@register_agent
class GradingAgent(BaseAgent):
    agent_id = "grading_agent"
    agent_name = "自动批改智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """主入口。context 需包含 question 和 student_answer。"""
        question = context.get("question", {}) if isinstance(context.get("question"), dict) else {}
        student_answer = str(context.get("student_answer", "")).strip()
        profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}

        if not question or not student_answer:
            return {"grading_result": None, "limitations": ["缺少题目信息或学生作答。"],
                    "agent_step": self.agent_step()}

        # ── LLM 优先 ──
        if self.llm_client:
            result = self._grade_with_llm(question, student_answer)
            if result:
                return {"grading_result": result, "agent_step": self.agent_step()}

        # ── 规则兜底 ──
        logger.info("LLM unavailable, using rule-based grading")
        result = self._rule_based_grading(question, student_answer)
        return {"grading_result": result, "agent_step": self.agent_step()}

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"grading_result": None, "limitations": ["批改智能体暂时不可用。"],
                "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name,
                               "status": "failed", "summary": "GradingAgent fell back to defaults.",
                               "source": "rule_based_fallback", "quality_status": "fallback"}}

    # ── LLM 路径 ──

    def _grade_with_llm(self, question: dict, student_answer: str) -> dict | None:
        q_type = question.get("type", "shortanswer")
        stem = question.get("stem", "")
        reference = question.get("reference_answer", "") or question.get("correct", "")
        explanation = question.get("explanation", "")

        # 提取评分标准
        rubric_text = ""
        rubric = question.get("scoring_rubric", [])
        if isinstance(rubric, list) and rubric:
            rubric_text = "## 评分标准\n" + "\n".join(
                f"- {r.get('criterion', '')}: {r.get('points', 0)}分" for r in rubric if isinstance(r, dict)
            )

        prompt = f"""你是 EduAgent 的自动批改智能体。请对以下学生作答进行多维评分和错误分析。

## 题目（{q_type}）
{stem}

## 参考答案
{reference}
{rubric_text}

## 答案解析
{explanation}

## 学生作答
{student_answer}

## 请输出 JSON 格式判卷结果：
{{
    "total_score": 0-100,
    "dimension_scores": {{
        "reasoning": 0-100,      // 思路正确性（40%）
        "completeness": 0-100,   // 步骤完整性（30%）
        "calculation": 0-100,    // 计算准确性（20%）
        "expression": 0-100      // 表达规范性（10%）
    }},
    "dimension_feedback": {{
        "reasoning": "思路点评",
        "completeness": "步骤点评",
        "calculation": "计算点评",
        "expression": "表达点评"
    }},
    "error_type": "concept|calculation|misreading|method|forgetting|null",
    "error_explanation": "错误原因分析",
    "suggestions": ["改进建议1", "改进建议2"],
    "strengths": ["做得好的方面"]
}}

规则：
- total_score = reasoning*0.4 + completeness*0.3 + calculation*0.2 + expression*0.1
- 如果学生作答完全正确，error_type 为 null
- 如果完全错误或未作答，每个维度都给低分并说明原因
- 对于选择题/判断题，直接比对答案即可，维度评分简化为：正确→100全维度；错误→在error_explanation中解释
- 只输出 JSON，不要 Markdown 包裹"""

        try:
            raw = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是专业的试卷批改专家。严格按照评分标准判卷。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            parsed = parse_safe(raw)
            if isinstance(parsed, dict) and "total_score" in parsed:
                return self._normalize_grading_result(parsed, question, student_answer)
        except Exception as e:
            logger.warning(f"GradingAgent LLM call failed: {e}")
        return None

    def _normalize_grading_result(self, raw: dict, question: dict, student_answer: str) -> dict:
        total_score = max(0, min(100, int(raw.get("total_score", 0) or 0)))
        dim_scores = raw.get("dimension_scores", {}) or {}
        dim_feedback = raw.get("dimension_feedback", {}) or {}
        error_type = str(raw.get("error_type", "")).strip()
        if error_type not in ERROR_TYPES:
            error_type = "null"

        return {
            "question_id": question.get("question_id", ""),
            "student_answer": student_answer,
            "total_score": total_score,
            "dimension_scores": {
                "reasoning": max(0, min(100, int(dim_scores.get("reasoning", 0) or 0))),
                "completeness": max(0, min(100, int(dim_scores.get("completeness", 0) or 0))),
                "calculation": max(0, min(100, int(dim_scores.get("calculation", 0) or 0))),
                "expression": max(0, min(100, int(dim_scores.get("expression", 0) or 0))),
            },
            "dimension_feedback": {
                "reasoning": str(dim_feedback.get("reasoning", "")),
                "completeness": str(dim_feedback.get("completeness", "")),
                "calculation": str(dim_feedback.get("calculation", "")),
                "expression": str(dim_feedback.get("expression", "")),
            },
            "error_type": error_type,
            "error_label": ERROR_LABELS.get(error_type, "无"),
            "error_explanation": str(raw.get("error_explanation", "")),
            "error_action": ERROR_ACTIONS.get(error_type, ""),
            "suggestions": raw.get("suggestions", []) or [],
            "strengths": raw.get("strengths", []) or [],
            "source": "llm_generated",
            "quality_status": "passed",
            "timestamp": int(__import__("time").time()),
            "auto_actions": ERROR_AUTO_ACTIONS.get(error_type) if error_type != "null" else None,
        }

    # ── 规则兜底 ──

    def _rule_based_grading(self, question: dict, student_answer: str) -> dict:
        q_type = question.get("type", "shortanswer")

        if q_type == "choice":
            correct = str(question.get("correct", "")).strip()
            student = str(student_answer).strip().upper()
            is_correct = student[:1] == correct[:1]

            return {
                "question_id": question.get("question_id", ""),
                "student_answer": student_answer,
                "total_score": 100 if is_correct else 0,
                "dimension_scores": {"reasoning": 100 if is_correct else 0, "completeness": 100, "calculation": 100, "expression": 100},
                "dimension_feedback": {"reasoning": "答案正确" if is_correct else f"正确答案应为 {correct}", "completeness": "", "calculation": "", "expression": ""},
                "error_type": "null" if is_correct else "concept",
                "error_label": "无" if is_correct else "概念错误",
                "error_explanation": "" if is_correct else f"选项 {student} 不正确。{question.get('explanation', '')}",
                "error_action": "" if is_correct else ERROR_ACTIONS["concept"],
                "suggestions": [] if is_correct else ["建议重新学习相关概念"],
                "strengths": [],
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "timestamp": int(__import__("time").time()),
            }

        if q_type == "truefalse":
            correct = question.get("correct")
            if isinstance(correct, str):
                correct = correct.lower() in ("true", "对", "正确", "yes")
            student = str(student_answer).strip().lower()
            is_correct = (student in ("true", "对", "正确", "yes", "t")) == bool(correct)

            return {
                "question_id": question.get("question_id", ""),
                "student_answer": student_answer,
                "total_score": 100 if is_correct else 0,
                "dimension_scores": {"reasoning": 100 if is_correct else 0, "completeness": 100, "calculation": 100, "expression": 100},
                "dimension_feedback": {"reasoning": "判断正确" if is_correct else "判断错误", "completeness": "", "calculation": "", "expression": ""},
                "error_type": "null" if is_correct else "misreading",
                "error_label": "无" if is_correct else "审题不清",
                "error_explanation": "" if is_correct else question.get("misconception_explanation", "常见误区"),
                "error_action": "" if is_correct else ERROR_ACTIONS["misreading"],
                "suggestions": [] if is_correct else ["注意题干中的关键条件和限定词"],
                "strengths": [],
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "timestamp": int(__import__("time").time()),
            }

        # 填空、解答：规则无力，返回参考性评价
        return {
            "question_id": question.get("question_id", ""),
            "student_answer": student_answer,
            "total_score": None,
            "dimension_scores": {"reasoning": None, "completeness": None, "calculation": None, "expression": None},
            "dimension_feedback": {"reasoning": "规则兜底无法评分，建议启用 LLM 进行批改。", "completeness": "", "calculation": "", "expression": ""},
            "error_type": "null",
            "error_label": "无法判定",
            "error_explanation": "规则兜底模式不支持对填空和解答题进行自动评分。",
            "error_action": "建议启用 LLM 或人工批改。",
            "suggestions": ["启用 LLM 模式以获得自动批改能力"],
            "strengths": [],
            "source": "rule_based_fallback",
            "quality_status": "fallback",
            "timestamp": int(__import__("time").time()),
        }
