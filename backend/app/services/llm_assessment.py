"""LLM 驱动的多维度学习评估引擎。

汇总画像、行为事件、诊断结果、资源反馈等多源数据，
调用大模型生成结构化评估报告，并反馈到推荐和路径调整。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.llm_client import BaseLLMClient, get_llm_client
from app.config import settings

logger = logging.getLogger(__name__)

# 评估维度 —— 覆盖知识、能力、偏好、状态、行为各层面
ASSESSMENT_DIMENSIONS = [
    "knowledge_mastery",       # 知识掌握程度
    "learning_progress",       # 学习进度
    "learning_efficiency",     # 学习效率
    "learning_regularity",     # 学习规律性
    "engagement_level",        # 投入度
    "weakness_awareness",      # 薄弱点认知准确度
    "improvement_trend",       # 进步趋势
]


def build_assessment_context(
    profile: dict[str, Any] | None = None,
    analytics: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
) -> str:
    """将多源数据拼接为 LLM 可读的评估上下文。"""
    parts = []

    # 画像
    if profile:
        dims = profile.get("dimensions") or []
        if dims:
            lines = []
            for d in dims:
                if isinstance(d, dict):
                    lines.append(f"  {d.get('label', d.get('key',''))}: {d.get('value','')}（得分{d.get('score',50)}，置信度{d.get('confidence',0.5)}）")
            if lines:
                parts.append("## 学生画像\n" + "\n".join(lines))

    # 分析统计
    if analytics:
        stats = []
        total_min = analytics.get("totalStudyMinutes", 0)
        if total_min:
            stats.append(f"累计学习时长：{total_min}分钟")
        streak = analytics.get("streak", 0)
        if streak:
            stats.append(f"连续学习天数：{streak}天")
        accuracy = analytics.get("quizAccuracy")
        if accuracy is not None:
            stats.append(f"练习正确率：{accuracy}%")
        completed = analytics.get("resourceCompleteCount", 0)
        if completed:
            stats.append(f"完成资源数：{completed}")
        weak = analytics.get("weakTopics", [])
        if weak:
            topics = "、".join([w.get("topic", "") for w in weak[:5] if w.get("topic")])
            stats.append(f"薄弱知识点：{topics}")
        if stats:
            parts.append("## 学习统计\n" + "\n".join(stats))

    # 诊断
    if diagnosis:
        diag_summary = diagnosis.get("diagnosis_summary") or diagnosis.get("summary", "")
        weak_points = diagnosis.get("weak_knowledge_points", [])
        diag_lines = []
        if diag_summary:
            diag_lines.append(f"诊断结论：{diag_summary}")
        if weak_points:
            for wp in weak_points[:5]:
                if isinstance(wp, dict):
                    diag_lines.append(f"  - {wp.get('name','')}（{wp.get('reason','')}）")
        if diag_lines:
            parts.append("## 诊断结果\n" + "\n".join(diag_lines))

    return "\n\n".join(parts)


def _parse_dimension(text: str, dim: str, default: int = 50) -> int:
    """从 LLM 回复中提取单个维度的数值评分。"""
    import re
    patterns = [
        rf'"{dim}"\s*:\s*(\d+)',
        rf'{dim}\s*[：:]\s*(\d+)',
        rf'{dim}.*?(\d+)/100',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                return max(0, min(100, int(m.group(1))))
            except ValueError:
                pass
    return default


def _parse_text_after(text: str, marker: str) -> str:
    """提取 LLM 回复中某个标记后的文本块。"""
    idx = text.find(marker)
    if idx == -1:
        return ""
    start = idx + len(marker)
    # 取到下一个 ## 或结尾
    end = text.find("\n##", start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()


def run_llm_assessment(
    *,
    session_id: str,
    profile: dict[str, Any] | None = None,
    analytics: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
    llm_client: BaseLLMClient | None = None,
) -> dict[str, Any]:
    """执行多维度学习评估，返回结构化报告。"""
    ctx = build_assessment_context(profile, analytics, diagnosis, events, resources)
    if not ctx:
        return {"status": "insufficient_data", "summary": "暂无足够学习数据用于评估。"}

    client = llm_client or get_llm_client(settings.llm_provider)
    if type(client).__name__ == "MockLLMClient":
        return _mock_assessment(analytics)

    dims_str = "、".join(ASSESSMENT_DIMENSIONS)
    prompt = f"""你是一个学习分析专家。根据以下学生数据，完成多维度评估。

{ctx}

## 评估要求
从以下维度进行评估（每个维度 0-100 分）：
{dims_str}

## 输出格式
先输出 JSON 维度评分，再输出分析文本：

```json
{{"knowledge_mastery": 分数, "learning_progress": 分数, "learning_efficiency": 分数, "learning_regularity": 分数, "engagement_level": 分数, "weakness_awareness": 分数, "improvement_trend": 分数}}
```

## 综合分析
用一段话总结学生的学习状态、主要问题和改进建议。

## 推荐行动
列出 2-3 条具体、可操作的建议。"""

    try:
        raw = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
    except Exception as e:
        logger.error("LLM assessment failed: %s", e)
        return _mock_assessment(analytics)

    # 解析维度评分
    import re as _re
    json_match = _re.search(r'```json\s*(\{.*?\})\s*```', raw, _re.DOTALL)
    scores: dict[str, int] = {}
    if json_match:
        try:
            scores = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 兜底解析
    for dim in ASSESSMENT_DIMENSIONS:
        if dim not in scores:
            scores[dim] = _parse_dimension(raw, dim)

    summary = _parse_text_after(raw, "## 综合分析") or "暂无分析"
    actions = _parse_text_after(raw, "## 推荐行动") or "暂无建议"

    return {
        "status": "completed",
        "scores": scores,
        "summary": summary,
        "recommended_actions": actions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _mock_assessment(analytics: dict[str, Any] | None) -> dict[str, Any]:
    """无 LLM 时的规则兜底评估。"""
    scores: dict[str, int] = {}
    for dim in ASSESSMENT_DIMENSIONS:
        scores[dim] = 50

    if analytics:
        acc = analytics.get("quizAccuracy")
        if acc is not None:
            scores["knowledge_mastery"] = min(100, max(0, acc))
            scores["improvement_trend"] = min(100, max(0, acc - 10))
        streak = analytics.get("streak", 0)
        scores["learning_regularity"] = min(100, streak * 8)
        completed = analytics.get("resourceCompleteCount", 0)
        scores["learning_progress"] = min(100, completed * 5)

    return {
        "status": "completed",
        "scores": scores,
        "summary": "基于学习数据的综合评估完成。建议持续学习以获得更准确的分析。",
        "recommended_actions": "坚持每天学习；完成练习后及时复习错题；针对薄弱知识点专项突破。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
