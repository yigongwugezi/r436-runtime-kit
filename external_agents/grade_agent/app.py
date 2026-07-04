"""
GRADE Grading Agent — 自动批改评估服务
基于 GRADE (AIM-SCU) 的 4 维评分 + 5 类错误归类设计（BEA 2025 Shared Task）
接收题目信息 + 学生作答，输出结构化判卷结果
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("grade-agent")

app = FastAPI(title="GRADE Grading Agent", version="1.0.0")

# ── 讯飞 Spark 客户端 ──

class LLMClient:
    """通用 LLM 客户端 — 支持所有 OpenAI 兼容接口"""

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = os.getenv("LLM_MODEL", "qwen-plus")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 2048) -> str:
        if not self.api_key:
            return ""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = await self._client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error("Spark API call failed: %s", exc)
            return ""

    async def close(self) -> None:
        await self._client.aclose()


llm = LLMClient()

# ── 错误类型定义 ──

ERROR_TYPES = ["concept", "calculation", "misreading", "method", "forgetting", "null"]

ERROR_LABELS: dict[str, str] = {
    "concept": "概念错误",
    "calculation": "计算失误",
    "misreading": "审题偏差",
    "method": "方法不当",
    "forgetting": "知识遗忘",
    "null": "无",
}

ERROR_ACTIONS: dict[str, dict[str, Any]] = {
    "concept": {
        "action": "recommend_concept_review",
        "label": "推送概念讲解",
        "reason": "概念理解有误，推荐回顾基础定义和区分对比材料",
    },
    "calculation": {
        "action": "suggest_calculation_practice",
        "label": "同类计算练习",
        "reason": "计算过程出错，推荐同类计算训练和验算方法",
    },
    "misreading": {
        "action": "flag_keyword_training",
        "label": "审题能力训练",
        "reason": "未正确理解题意或遗漏关键条件，推荐关键词标注训练",
    },
    "method": {
        "action": "recommend_better_solution",
        "label": "更优解法推荐",
        "reason": "解题方法可行但非最优，推荐更高效的解法",
    },
    "forgetting": {
        "action": "add_to_review_queue",
        "label": "加入间隔复习",
        "reason": "前置知识点遗忘，已加入艾宾浩斯复习队列",
    },
}

# ── 持久化存储 ──

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grades.db")


def _ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grading_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                grading_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_student ON grading_records(student_id)")
        conn.commit()


_ensure_db()

# ── 数据模型 ──

class GradingRequest(BaseModel):
    student_id: str = Field(default="")
    question_id: str = Field(default="")
    question_type: str = Field(default="shortanswer", description="choice|truefalse|fill|shortanswer")
    stem: str = Field(default="", description="题目内容")
    options: list[str] = Field(default_factory=list, description="选择题选项")
    correct: str = Field(default="", description="正确答案（选择题选项字母/判断题truefalse/填空题答案）")
    reference_answer: str = Field(default="", description="参考答案（解答题）")
    explanation: str = Field(default="", description="题目解析")
    scoring_rubric: list[dict] = Field(default_factory=list, description="评分标准")
    knowledge_points: list[str] = Field(default_factory=list, description="考察知识点")
    student_answer: str = Field(default="", description="学生作答内容")
    difficulty: str = Field(default="medium")

    @property
    def has_answer(self) -> bool:
        return bool(self.student_answer.strip())


class DimensionScore(BaseModel):
    name: str
    label: str
    score: int = 0
    max_score: int = 100
    weight: float = 0.0
    feedback: str = ""


class GradingResult(BaseModel):
    student_id: str
    question_id: str
    question_type: str
    student_answer: str
    total_score: int | None = None
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    error_type: str = "null"
    error_label: str = "无"
    error_explanation: str = ""
    auto_action: dict | None = None
    suggestions: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    source: str = "rule_based_fallback"
    quality_status: str = "fallback"
    timestamp: int = 0


# ── 规则兜底 ──

DIMENSIONS = [
    {"name": "reasoning", "label": "思路正确性", "weight": 0.4},
    {"name": "completeness", "label": "步骤完整性", "weight": 0.3},
    {"name": "calculation", "label": "计算准确性", "weight": 0.2},
    {"name": "expression", "label": "表达规范性", "weight": 0.1},
]


def _rule_grade_choice(req: GradingRequest) -> GradingResult:
    """选择题：直接比对答案"""
    student = req.student_answer.strip().upper()
    correct = req.correct.strip().upper()
    is_correct = student[:1] == correct[:1] if student and correct else False

    dims = [
        DimensionScore(name=d["name"], label=d["label"], score=100 if is_correct else 0, weight=d["weight"],
                       feedback="答案正确" if is_correct else f"正确答案应为 {req.correct}。{req.explanation}")
        for d in DIMENSIONS
    ]

    return GradingResult(
        student_id=req.student_id,
        question_id=req.question_id,
        question_type=req.question_type,
        student_answer=req.student_answer,
        total_score=100 if is_correct else 0,
        dimension_scores=dims,
        error_type="null" if is_correct else "concept",
        error_label=ERROR_LABELS["null" if is_correct else "concept"],
        error_explanation="" if is_correct else f"选择了错误选项 {req.student_answer}。{req.explanation}",
        auto_action=None if is_correct else ERROR_ACTIONS["concept"],
        suggestions=[] if is_correct else ["回顾相关概念，理解各选项的正确含义"],
        strengths=[],
        knowledge_points=req.knowledge_points,
        source="rule_based_grading",
        quality_status="passed" if is_correct else "warning",
        timestamp=int(time.time()),
    )


def _rule_grade_truefalse(req: GradingRequest) -> GradingResult:
    """判断题：比对正误"""
    student = req.student_answer.strip().lower()
    correct_raw = req.correct
    if isinstance(correct_raw, str):
        correct_bool = correct_raw.lower() in ("true", "对", "正确", "yes", "t")
    else:
        correct_bool = bool(correct_raw)
    student_bool = student in ("true", "对", "正确", "yes", "t")
    is_correct = student_bool == correct_bool

    dims = [
        DimensionScore(name=d["name"], label=d["label"], score=100 if is_correct else 0, weight=d["weight"],
                       feedback="判断正确" if is_correct else "判断错误")
        for d in DIMENSIONS
    ]

    return GradingResult(
        student_id=req.student_id,
        question_id=req.question_id,
        question_type=req.question_type,
        student_answer=req.student_answer,
        total_score=100 if is_correct else 0,
        dimension_scores=dims,
        error_type="null" if is_correct else "misreading",
        error_label=ERROR_LABELS["null" if is_correct else "misreading"],
        error_explanation="" if is_correct else req.explanation or "对题干关键条件的判断有误",
        auto_action=None if is_correct else ERROR_ACTIONS["misreading"],
        suggestions=[] if is_correct else ["仔细审题，注意题干中的关键条件和限定词"],
        strengths=[],
        knowledge_points=req.knowledge_points,
        source="rule_based_grading",
        quality_status="passed" if is_correct else "warning",
        timestamp=int(time.time()),
    )


def _rule_grade_open(req: GradingRequest) -> GradingResult:
    """填空/解答题：规则兜底——返回参考性评价，提示启用 LLM"""
    dims = [
        DimensionScore(
            name=d["name"], label=d["label"],
            score=None, weight=d["weight"],
            feedback="规则兜底模式无法对开放题自动评分，请启用 LLM。"
        )
        for d in DIMENSIONS
    ]
    return GradingResult(
        student_id=req.student_id,
        question_id=req.question_id,
        question_type=req.question_type,
        student_answer=req.student_answer,
        total_score=None,
        dimension_scores=dims,
        error_type="null",
        error_label="无法判定",
        error_explanation="规则兜底模式不支持对填空和解答题进行自动评分，建议启用 LLM 或人工批改。",
        auto_action=None,
        suggestions=["启用 LLM 模式以获得自动批改能力"],
        strengths=[],
        knowledge_points=req.knowledge_points,
        source="rule_based_fallback",
        quality_status="fallback",
        timestamp=int(time.time()),
    )


# ── LLM 批改 ──

async def _llm_grade(req: GradingRequest) -> GradingResult | None:
    """调用 LLM 进行 4 维评分 + 错误归类"""
    q_type_label = {"choice": "选择题", "truefalse": "判断题", "fill": "填空题", "shortanswer": "解答题"}.get(req.question_type, "解答题")

    rubric_text = ""
    if req.scoring_rubric:
        rubric_lines = [f"- {r.get('criterion', '')}: {r.get('points', 0)}分" for r in req.scoring_rubric if isinstance(r, dict)]
        rubric_text = "## 评分标准\n" + "\n".join(rubric_lines)

    options_text = ""
    if req.options:
        options_text = "选项：" + " | ".join(f"{chr(65+i)}. {o}" for i, o in enumerate(req.options))

    prompt = f"""你是 EduAgent 的自动批改智能体。请对以下学生作答进行多维评分和错误分析。

## 题目（{q_type_label}）
{req.stem}
{options_text}

## 参考答案 / 正确选项
{req.correct or req.reference_answer}

## 题目解析
{req.explanation}

{rubric_text}

## 知识点
{', '.join(req.knowledge_points) if req.knowledge_points else '未标注'}

## 学生作答
{req.student_answer}

## 请输出 JSON 格式判卷结果：
{{
    "total_score": 0-100,
    "dimension_scores": {{
        "reasoning": {{ "score": 0-100, "feedback": "思路点评" }},
        "completeness": {{ "score": 0-100, "feedback": "步骤点评" }},
        "calculation": {{ "score": 0-100, "feedback": "计算点评" }},
        "expression": {{ "score": 0-100, "feedback": "表达点评" }}
    }},
    "error_type": "concept|calculation|misreading|method|forgetting|null",
    "error_explanation": "错误原因分析（如果完全正确则为空字符串）",
    "suggestions": ["改进建议1", "改进建议2"],
    "strengths": ["做得好的方面"]
}}

规则：
- total_score = reasoning*0.4 + completeness*0.3 + calculation*0.2 + expression*0.1
- 选择题/判断题：答案对→全维度 100 分，error_type=null；答案错→按实际错误归类
- 解答题：分维度仔细评分，每维度 feedback 写清楚扣分原因
- 如果完全正确，error_type 为 null
- 禁止写"学生可能""学生选择了"等学情推测——直接分析作答内容本身
- 只输出 JSON，不要 Markdown 包裹"""

    raw = await llm.chat([
        {"role": "system", "content": "你是专业的试卷批改专家。严格按评分标准判卷。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ], temperature=0.1, max_tokens=2048)

    if not raw:
        return None

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        parsed = json.loads(raw[start:end])
        return _normalize_llm_result(parsed, req)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse LLM grading output: %s", exc)
        return None


def _normalize_llm_result(raw: dict, req: GradingRequest) -> GradingResult:
    """标准化 LLM 批改输出"""
    total = max(0, min(100, int(raw.get("total_score", 0) or 0)))

    dim_raw = raw.get("dimension_scores", {}) or {}
    dims = []
    for d in DIMENSIONS:
        item = dim_raw.get(d["name"], {})
        if not isinstance(item, dict):
            item = {}
        dims.append(DimensionScore(
            name=d["name"], label=d["label"],
            score=max(0, min(100, int(item.get("score", 0) or 0))),
            weight=d["weight"],
            feedback=str(item.get("feedback", "")),
        ))

    error_type = str(raw.get("error_type", "")).strip()
    if error_type not in ERROR_TYPES:
        error_type = "null"

    return GradingResult(
        student_id=req.student_id,
        question_id=req.question_id,
        question_type=req.question_type,
        student_answer=req.student_answer,
        total_score=total,
        dimension_scores=dims,
        error_type=error_type,
        error_label=ERROR_LABELS.get(error_type, "无"),
        error_explanation=str(raw.get("error_explanation", "")),
        auto_action=ERROR_ACTIONS.get(error_type) if error_type != "null" else None,
        suggestions=raw.get("suggestions", []) or [],
        strengths=raw.get("strengths", []) or [],
        knowledge_points=req.knowledge_points,
        source="llm_generated",
        quality_status="passed",
        timestamp=int(time.time()),
    )


# ── 存储 ──

def _save_grading(result: GradingResult) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO grading_records (student_id, question_id, grading_json, recorded_at) VALUES (?, ?, ?, ?)",
            (result.student_id, result.question_id, result.model_dump_json(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


# ── API 端点 ──

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": "grade-agent", "version": "1.0.0"}


@app.post("/api/grade/assess")
async def assess(req: GradingRequest) -> dict:
    """
    主入口：接收题目 + 学生作答，返回结构化批改结果。
    """
    if not req.has_answer:
        raise HTTPException(status_code=400, detail="student_answer is required")

    result: GradingResult | None = None

    # 选择题：规则直接判
    if req.question_type == "choice":
        result = _rule_grade_choice(req)

    # 判断题：规则直接判
    elif req.question_type == "truefalse":
        result = _rule_grade_truefalse(req)

    # 填空/解答题：LLM 优先
    else:
        result = await _llm_grade(req)
        if result is None:
            logger.info("LLM grading failed, using rule-based fallback")
            result = _rule_grade_open(req)

    _save_grading(result)
    return result.model_dump()


@app.post("/api/grade/batch")
async def batch_assess(requests: list[GradingRequest]) -> list[dict]:
    """批量批改"""
    results = []
    for req in requests:
        try:
            r = await assess(req)
            results.append(r)
        except HTTPException:
            results.append({"error": "grading_failed", "question_id": req.question_id})
    return results


@app.get("/api/grade/records/{student_id}")
async def get_records(student_id: str, limit: int = 20) -> list[dict]:
    """获取学生的历史批改记录"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT grading_json, recorded_at FROM grading_records WHERE student_id = ? ORDER BY recorded_at DESC LIMIT ?",
            (student_id, limit),
        ).fetchall()
    return [{"grading": json.loads(row[0]), "recorded_at": row[1]} for row in rows]


@app.get("/api/grade/stats/{student_id}")
async def get_stats(student_id: str) -> dict:
    """获取学生的学习统计"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT grading_json FROM grading_records WHERE student_id = ?",
            (student_id,),
        ).fetchall()

    if not rows:
        return {"student_id": student_id, "total_questions": 0}

    gradings = [json.loads(row[0]) for row in rows]
    scores = [g["total_score"] for g in gradings if g.get("total_score") is not None]
    error_counts: dict[str, int] = {}
    for g in gradings:
        et = g.get("error_type", "null")
        if et != "null":
            error_counts[et] = error_counts.get(et, 0) + 1

    all_kps: list[str] = []
    for g in gradings:
        all_kps.extend(g.get("knowledge_points", []))

    kp_stats: dict[str, dict] = {}
    for g in gradings:
        for kp in g.get("knowledge_points", []):
            if kp not in kp_stats:
                kp_stats[kp] = {"total": 0, "correct": 0}
            kp_stats[kp]["total"] += 1
            if g.get("total_score", 0) and g["total_score"] >= 60:
                kp_stats[kp]["correct"] += 1

    weak_kps = [
        {"name": kp, "accuracy": round(s["correct"] / max(1, s["total"]) * 100)}
        for kp, s in kp_stats.items()
        if s["correct"] / max(1, s["total"]) < 0.6
    ]

    return {
        "student_id": student_id,
        "total_questions": len(gradings),
        "average_score": round(sum(scores) / max(1, len(scores)), 1) if scores else None,
        "error_distribution": error_counts,
        "weak_knowledge_points": sorted(weak_kps, key=lambda x: x["accuracy"])[:10],
    }


@app.on_event("shutdown")
async def shutdown() -> None:
    await spark.close()
