"""
LLM JSON 解析工具 —— 所有 Agent 共用的统一 JSON 提取和修复逻辑。

三层保障：
1. 直接解析
2. 机械修复（补全截断的括号/结构）
3. LLM 自修复（将损坏的 JSON 送回模型要求修复）
"""

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


def extract_json(text: str) -> str:
    """从 LLM 原始输出中提取 JSON 文本。处理 markdown 代码块包裹等情况。"""
    stripped = text.strip()
    # 去除 markdown 代码块
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    # 定位第一个 { 和最后一个 }
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start:end + 1]
    return stripped


def repair_truncated(text: str) -> str:
    """机械修复被截断的 JSON。
    从末尾逐字符回退，找到最后一个有效的 JSON 结构边界，补全未闭合的括号。
    """
    repaired = text.rstrip(",\n\r \t")
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")

    # 从末尾回退找到安全截断点
    i = len(repaired) - 1
    while i >= 0:
        ch = repaired[i]
        if ch == "}":
            open_braces -= 1
        elif ch == "{":
            open_braces += 1
        elif ch == "]":
            open_brackets -= 1
        elif ch == "[":
            open_brackets += 1
        if open_braces <= 0 and open_brackets <= 0 and ch in (",", "}", "]"):
            repaired = repaired[:i + 1]
            break
        i -= 1

    # 补全未闭合的结构
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    repaired += "]" * max(0, open_brackets)
    repaired += "}" * max(0, open_braces)
    return repaired


def _extract_individual_resources(text: str) -> list[dict] | None:
    """最后手段：从损坏的 JSON 中逐个提取 resource 对象。"""
    resources = []
    # 查找所有 { ... } 对象，尝试独立解析
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    obj = json.loads(sanitize_json(text[start:i + 1]))
                    if isinstance(obj, dict) and obj.get("title"):
                        resources.append(obj)
                except Exception:
                    pass
                start = -1
    return resources if len(resources) >= 1 else None


def sanitize_json(text: str) -> str:
    """在 JSON 字符串值内部转义字面换行/制表符。
    90% 以上的 LLM JSON 失败是因为 content 字段里的 markdown 有字面换行。
    """
    result: list[str] = []
    in_string = False
    escape_next = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            i += 1
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def parse_safe(text: str, *, llm_fix_fn: Callable[[str], str] | None = None) -> dict:
    """安全解析 LLM 输出的 JSON。四层保障逐步尝试。

    Args:
        text: LLM 原始输出文本
        llm_fix_fn: 可选的 LLM 修复回调，签名为 (broken_json: str) -> str。
                    传入时将损坏的 JSON 送回模型修复后重新解析。

    Returns:
        解析后的 dict。解析失败抛出 ValueError。
    """
    json_text = extract_json(text)

    # ── 第1层：直接解析 + 自动 sanitize ──
    sanitized = sanitize_json(json_text)
    try:
        result = json.loads(sanitized)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        pos = e.pos if hasattr(e, 'pos') else 0
        snippet = sanitized[max(0, pos - 60):pos + 60] if pos else ''
        logger.warning("JSON direct parse failed at pos %s: %s | snippet: ...%s...", pos, e, snippet)

    # ── 第2层：机械修复 ──
    try:
        repaired = repair_truncated(json_text)
        repaired_san = sanitize_json(repaired)
        result = json.loads(repaired_san)
        if isinstance(result, dict):
            logger.info("JSON repaired mechanically (truncation fix)")
            return result
    except json.JSONDecodeError as e:
        pos = e.pos if hasattr(e, 'pos') else 0
        logger.warning("JSON mechanical repair failed at pos %s: %s", pos, e)

    # ── 第3层：LLM 自修复 ──
    if llm_fix_fn:
        try:
            fixed_text = llm_fix_fn(json_text[:4000])
            result = json.loads(sanitize_json(fixed_text))
            if isinstance(result, dict):
                logger.info("JSON repaired by LLM self-correction")
                return result
        except Exception as e:
            logger.warning("JSON LLM repair failed: %s", e)

    # 最后手段：尝试逐资源提取
    resources = _extract_individual_resources(json_text)
    if resources:
        logger.info("JSON partially recovered: extracted %d individual resources", len(resources))
        return {"resources": resources}

    raise ValueError("All JSON parsing strategies failed")
