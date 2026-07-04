"""
Socratic Profiler Agent — 学生画像构建服务
基于 Socratic Education System 的 Profiler Agent 设计（MIT 协议）
接收 NoteAgent 的结构化摘要，输出 6 维动态学生画像
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 自动找项目根目录的 .env
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("socratic-profiler")

app = FastAPI(title="Socratic Profiler Agent", version="1.0.0")

# ── 讯飞 Spark 客户端 ──

class LLMClient:
    """通用 LLM 客户端 — 支持所有 OpenAI 兼容接口"""

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = os.getenv("LLM_MODEL", "qwen-plus")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 2048) -> str:
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
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error("Spark API call failed: %s", exc)
            return ""

    async def close(self) -> None:
        await self._client.aclose()


llm = LLMClient()

# ── 持久化存储 ──

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "profiles.db")


def _ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                student_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                change_reason TEXT,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.commit()


_ensure_db()

# ── 数据模型 ──

PROFILE_DIMENSIONS = [
    "major_background",
    "knowledge_base",
    "learning_goal",
    "cognitive_style",
    "error_patterns",
    "learning_progress",
]

DIMENSION_LABELS: dict[str, str] = {
    "major_background": "专业背景",
    "knowledge_base": "知识基础",
    "learning_goal": "学习目标",
    "cognitive_style": "认知风格",
    "error_patterns": "易错点",
    "learning_progress": "学习进度",
}


class NoteAnalysis(BaseModel):
    """NoteAgent 传入的结构化分析结果"""
    session_id: str = Field(default="")
    student_id: str = Field(default="")
    background: str = Field(default="", description="专业/年级/相关课程")
    knowledge_base: str = Field(default="", description="已有知识掌握情况")
    learning_goal: str = Field(default="", description="学习目标")
    time_budget: str = Field(default="", description="可用学习时间")
    cognitive_preference: str = Field(default="", description="偏好的学习方式")
    evidence_chain: list[dict] = Field(default_factory=list, description="证据链")


class ProfileDimension(BaseModel):
    key: str
    label: str
    value: str
    score: int = Field(default=50, ge=0, le=100)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    explanation: str = ""
    evidence: str = ""
    source: str = "llm_generated"


class StudentProfile(BaseModel):
    student_id: str
    session_id: str
    dimensions: dict[str, ProfileDimension] = Field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class GradingFeedback(BaseModel):
    """GRADE Agent 批改后的反馈，用于更新画像"""
    student_id: str
    question_id: str = ""
    error_types: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    mastery_scores: dict[str, int] = Field(default_factory=dict)


# ── 规则兜底：从 NoteAnalysis 直接构建画像 ──

def _rule_based_profile(analysis: NoteAnalysis, student_id: str) -> dict[str, Any]:
    """不依赖 LLM，直接从结构化分析构建画像（LLM 不可用时的兜底）"""
    now = datetime.now(timezone.utc).isoformat()

    def _dim(key: str, value: str, score: int, confidence: float, explanation: str, evidence: str, source: str) -> dict:
        return {
            "key": key,
            "label": DIMENSION_LABELS[key],
            "value": value.strip() or "待补充",
            "score": max(0, min(100, score)),
            "confidence": max(0.0, min(1.0, confidence)),
            "explanation": explanation.strip(),
            "evidence": evidence.strip(),
            "source": source,
        }

    dims = {}

    dims["major_background"] = _dim(
        "major_background", analysis.background,
        score=82 if analysis.background else 50,
        confidence=0.92 if analysis.background else 0.35,
        explanation=f"从学生描述中提取的专业背景信息。" if analysis.background else "当前对话中缺少专业背景信息，可在后续补充。",
        evidence=analysis.background,
        source="user_input" if analysis.background else "rule_based_fallback",
    )

    kb = analysis.knowledge_base
    kb_low_words = ["零基础", "不会", "比较弱", "较弱", "薄弱", "一般"]
    kb_score = 78 if any(w in kb for w in ["熟悉", "掌握", "扎实"]) else (42 if any(w in kb for w in kb_low_words) else 60)
    dims["knowledge_base"] = _dim(
        "knowledge_base", kb or "基础信息待补充",
        score=kb_score,
        confidence=0.90 if kb else 0.40,
        explanation="根据学生提到的已有基础、薄弱点和课程经历总结。",
        evidence=kb,
        source="user_input" if kb else "rule_based_fallback",
    )

    goal = analysis.learning_goal
    dims["learning_goal"] = _dim(
        "learning_goal", goal or "学习目标待明确",
        score=82 if goal else 50,
        confidence=0.88 if goal else 0.40,
        explanation="从学生描述中归纳的学习目标。" if goal else "建议引导学生明确短期和长期学习目标。",
        evidence=goal,
        source="user_input" if goal else "inferred",
    )

    pref = analysis.cognitive_preference
    dims["cognitive_style"] = _dim(
        "cognitive_style", pref or "偏好图解、练习和代码结合的讲解方式",
        score=70 if pref else 60,
        confidence=0.88 if pref else 0.60,
        explanation="根据学生明确提到的偏好形式或默认学习偏好。",
        evidence=pref,
        source="user_input" if pref else "inferred",
    )

    dims["error_patterns"] = _dim(
        "error_patterns", "暂未诊断",
        score=50,
        confidence=0.35,
        explanation="需完成首次练习后由 GRADE 批改结果自动更新。",
        evidence="",
        source="inferred",
    )

    progress = "处于入门阶段"
    if analysis.time_budget:
        progress = f"计划在{analysis.time_budget}内完成学习"
    dims["learning_progress"] = _dim(
        "learning_progress", progress,
        score=48,
        confidence=0.70,
        explanation="根据学生提供的时间预算和学习目标推断当前阶段。",
        evidence=analysis.time_budget,
        source="inferred",
    )

    return {
        "student_id": student_id,
        "session_id": analysis.session_id,
        "dimensions": dims,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


# ── LLM 画像构建 ──

async def _llm_profile(analysis: NoteAnalysis, student_id: str, existing_profile: dict | None = None) -> dict | None:
    """调用 LLM 构建 6 维画像"""
    existing_text = ""
    if existing_profile:
        existing_text = f"\n当前已存画像：\n{json.dumps(existing_profile.get('dimensions', {}), ensure_ascii=False, indent=2)}"

    prompt = f"""你是 EduAgent 的学习画像构建智能体（教育心理学家角色）。

请根据以下学生信息，构建包含 6 个维度的学习画像 JSON。

## 学生分析数据
- 专业背景：{analysis.background or '未提及'}
- 知识基础：{analysis.knowledge_base or '未提及'}
- 学习目标：{analysis.learning_goal or '未提及'}
- 时间预算：{analysis.time_budget or '未提及'}
- 认知偏好：{analysis.cognitive_preference or '未提及'}
{existing_text}

## 画像维度要求
对于每个维度，提供：value（描述文本）、score（0-100 整数）、confidence（0-1 小数）、explanation（说明）、evidence（证据）、source（user_input/inferred/llm_generated）

6 个维度：
1. major_background — 专业背景
2. knowledge_base — 知识基础
3. learning_goal — 学习目标
4. cognitive_style — 认知风格（图解/代码/讲义/视频）
5. error_patterns — 易错点（首次可为"待诊断"）
6. learning_progress — 学习进度

## 规则
- 优先采用学生明确描述的信息
- score 和 confidence 必须合理：有证据的 confidence≥0.8，推断的≤0.6，缺失的≤0.4
- 所有内容用中文
- 只输出 JSON，不要 Markdown 包裹"""

    raw = await llm.chat([
        {"role": "system", "content": "你是教育心理学家，擅长构建学习者画像。只输出 JSON，不要解释。"},
        {"role": "user", "content": prompt},
    ], temperature=0.2, max_tokens=2048)

    if not raw:
        return None

    try:
        # 提取 JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(raw[start:end])
            if isinstance(parsed, dict):
                return _normalize_llm_output(parsed, analysis, student_id)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse LLM profile output: %s", exc)

    return None


def _normalize_llm_output(raw: dict, analysis: NoteAnalysis, student_id: str) -> dict:
    """标准化 LLM 输出为统一格式"""
    now = datetime.now(timezone.utc).isoformat()
    dims: dict[str, dict] = {}

    for key in PROFILE_DIMENSIONS:
        item = raw.get(key, {})
        if not isinstance(item, dict):
            item = {}

        value = str(item.get("value", "")).strip()
        try:
            score = max(0, min(100, int(item.get("score", 50))))
        except (TypeError, ValueError):
            score = 50
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5

        dims[key] = {
            "key": key,
            "label": DIMENSION_LABELS[key],
            "value": value or "待补充",
            "score": score,
            "confidence": confidence,
            "explanation": str(item.get("explanation", value or "待补充")),
            "evidence": str(item.get("evidence", "")),
            "source": str(item.get("source", "llm_generated")),
        }

    return {
        "student_id": student_id,
        "session_id": analysis.session_id,
        "dimensions": dims,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


# ── 持久化操作 ──

def _save_profile(profile: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT version FROM profiles WHERE student_id = ?", (profile["student_id"],)).fetchone()
        version = (existing[0] + 1) if existing else 1
        profile["version"] = version
        profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not profile.get("created_at"):
            profile["created_at"] = profile["updated_at"]

        conn.execute(
            """INSERT OR REPLACE INTO profiles (student_id, profile_json, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (profile["student_id"], json.dumps(profile, ensure_ascii=False), version, profile["created_at"], profile["updated_at"]),
        )
        conn.execute(
            "INSERT INTO profile_history (student_id, profile_json, change_reason, recorded_at) VALUES (?, ?, ?, ?)",
            (profile["student_id"], json.dumps(profile, ensure_ascii=False), "profile_update", profile["updated_at"]),
        )
        conn.commit()


def _load_profile(student_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT profile_json FROM profiles WHERE student_id = ?", (student_id,)).fetchone()
        if row:
            return json.loads(row[0])
    return None


# ── API 端点 ──

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": "socratic-profiler", "version": "1.0.0"}


@app.post("/api/profile/analyze")
async def analyze_profile(analysis: NoteAnalysis) -> dict:
    """
    主入口：接收 NoteAgent 的结构化分析，返回 6 维学生画像。
    """
    student_id = analysis.student_id or f"student_{uuid.uuid4().hex[:8]}"
    existing = _load_profile(student_id)

    # 1. 先尝试 LLM 构建
    profile = await _llm_profile(analysis, student_id, existing)

    # 2. LLM 失败 → 规则兜底
    if profile is None:
        logger.info("LLM profile generation failed, using rule-based fallback")
        profile = _rule_based_profile(analysis, student_id)
        for dim in profile["dimensions"].values():
            dim["source"] = "rule_based_fallback"

    # 3. 持久化
    _save_profile(profile)

    logger.info("Profile built for student %s, version %d", student_id, profile["version"])
    return profile


@app.post("/api/profile/update")
async def update_profile(feedback: GradingFeedback) -> dict:
    """
    接收 GRADE 批改反馈，更新画像的易错点和知识基础维度。
    """
    profile = _load_profile(feedback.student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found. Run /analyze first.")

    dims = profile["dimensions"]
    now = datetime.now(timezone.utc).isoformat()

    # 更新易错点
    if feedback.error_types or feedback.weak_topics:
        error_dim = dims.get("error_patterns", {})
        existing_errors = set(error_dim.get("value", "").replace("待诊断", "").replace("暂未诊断", "").split("、"))
        existing_errors.discard("")

        new_errors = set(feedback.weak_topics)
        error_type_labels = {
            "concept": "概念混淆",
            "calculation": "计算失误",
            "misreading": "审题偏差",
            "method": "方法不当",
            "forgetting": "知识遗忘",
        }
        for et in feedback.error_types:
            new_errors.add(error_type_labels.get(et, et))

        all_errors = existing_errors | new_errors
        error_dim["value"] = "、".join(sorted(all_errors)[:8]) if all_errors else "待诊断"
        error_dim["score"] = max(30, error_dim.get("score", 50) - len(new_errors) * 5)
        error_dim["confidence"] = min(0.95, error_dim.get("confidence", 0.5) + 0.1)
        error_dim["evidence"] = f"GRADE 批改反馈：{', '.join(sorted(new_errors))}"
        error_dim["source"] = "grading_feedback"
        dims["error_patterns"] = error_dim

    # 更新知识基础评分
    if feedback.mastery_scores:
        kb_dim = dims.get("knowledge_base", {})
        avg_mastery = sum(feedback.mastery_scores.values()) / max(1, len(feedback.mastery_scores))
        kb_dim["score"] = max(0, min(100, int(avg_mastery)))
        kb_dim["confidence"] = min(0.95, kb_dim.get("confidence", 0.5) + 0.05)
        kb_dim["evidence"] = f"GRADE 掌握度评估均值：{avg_mastery:.0f}"
        kb_dim["source"] = "grading_feedback"
        dims["knowledge_base"] = kb_dim

    # 更新学习进度
    progress_dim = dims.get("learning_progress", {})
    progress_dim["value"] = "已完成阶段练习并收到批改反馈"
    progress_dim["score"] = min(100, progress_dim.get("score", 48) + 10)
    progress_dim["confidence"] = 0.85
    progress_dim["evidence"] = f"最近批改时间：{now}"
    dims["learning_progress"] = progress_dim

    profile["dimensions"] = dims
    _save_profile(profile)

    logger.info("Profile updated for student %s after grading feedback", feedback.student_id)
    return profile


@app.get("/api/profile/{student_id}")
async def get_profile(student_id: str) -> dict:
    """获取指定学生的当前画像"""
    profile = _load_profile(student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.get("/api/profile/{student_id}/history")
async def get_profile_history(student_id: str) -> list[dict]:
    """获取画像变更历史"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT profile_json, change_reason, recorded_at FROM profile_history WHERE student_id = ? ORDER BY recorded_at DESC LIMIT 20",
            (student_id,),
        ).fetchall()
    return [
        {"profile": json.loads(row[0]), "change_reason": row[1], "recorded_at": row[2]}
        for row in rows
    ]


# ── 原始 Socratic ES Profiler Agent：对话复盘 + 弱点分析 ──

class ConversationHistory(BaseModel):
    student_id: str = ""
    history: list[dict] = Field(default_factory=list, description="对话历史 [{'role':'user'/'assistant','content':'...'}]")


@app.post("/api/profile/analyze-conversation")
async def analyze_conversation(conv: ConversationHistory) -> dict:
    """
    原始 Socratic Education System Profiler Agent 逻辑：
    对话结束后复盘，提取核心知识点 + 识别逻辑断裂点，记录到弱点日志。
    """
    if not conv.history:
        raise HTTPException(status_code=400, detail="对话历史不能为空")

    student_id = conv.student_id or f"student_{uuid.uuid4().hex[:8]}"
    chat_content = "\n".join([f"{m['role']}: {m['content']}" for m in conv.history])

    prompt = f"""请分析以下师生对话内容：
{chat_content}

任务：
1. 总结本次对话涉及的3个核心知识点（用简短的词语表示）。
2. 识别学生在哪个环节出现了逻辑断裂或理解偏差。

请严格按以下 JSON 格式输出，不要包含任何其他文字：
{{
    "topic": "知识点1, 知识点2, 知识点3",
    "logic_gap": "具体逻辑断裂点的描述"
}}"""

    try:
        raw = await llm.chat([
            {"role": "system", "content": "你是一名资深教育专家，擅长诊断学生思维障碍。只输出JSON。"},
            {"role": "user", "content": prompt},
        ], temperature=0.2, max_tokens=500)

        analysis = json.loads(raw) if raw else {"topic": "未能识别", "logic_gap": "分析失败"}

        # 写入弱点日志
        profile = _load_profile(student_id) or {}
        now = datetime.now(timezone.utc).isoformat()
        new_log = {
            "timestamp": now,
            "topic": analysis.get("topic", "未知知识点"),
            "logic_gap": analysis.get("logic_gap", "未识别到明显逻辑断裂"),
        }

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weakness_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    log_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO weakness_log (student_id, log_json, recorded_at) VALUES (?, ?, ?)",
                (student_id, json.dumps(new_log, ensure_ascii=False), now),
            )
            conn.commit()

        return {
            "student_id": student_id,
            "analysis": analysis,
            "weakness_logged": True,
            "timestamp": now,
        }

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Conversation analysis failed: %s", e)
        return {"student_id": student_id, "analysis": {"topic": "解析失败", "logic_gap": str(e)}, "weakness_logged": False}


@app.get("/api/profile/{student_id}/weaknesses")
async def get_weakness_log(student_id: str) -> list[dict]:
    """获取学生的历史弱点记录"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT log_json, recorded_at FROM weakness_log WHERE student_id = ? ORDER BY recorded_at DESC LIMIT 20",
            (student_id,),
        ).fetchall()
    return [{"log": json.loads(row[0]), "recorded_at": row[1]} for row in rows]


@app.on_event("shutdown")
async def shutdown() -> None:
    await llm.close()
