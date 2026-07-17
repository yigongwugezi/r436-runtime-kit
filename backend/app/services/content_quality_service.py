"""Unified content quality gate for all resource types (spec §6).

Every resource passes through this gate before being saved.  The service
implements per-type deterministic checks (§6.2–§6.8) and maps legacy
internal statuses to the four public contract statuses (§2.1).

Public statuses (only these four are allowed):
  passed               — all checks passed
  needs_review         — human review recommended
  blocked              — safety / renderability issue
  provider_unavailable — external dependency missing
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.structured_multimodal_resources import sanitize_mermaid

logger = logging.getLogger(__name__)

# ── Public contract statuses (spec §2.1) ─────────────────────────────────

PUBLIC_STATUSES = frozenset({"passed", "needs_review", "blocked", "provider_unavailable"})

# ── Legacy → public status mapping ───────────────────────────────────────

LEGACY_MAP: dict[str, str] = {
    "repaired":             "passed",
    "failed":               "needs_review",
    "pending":              "needs_review",
    "warning":              "needs_review",
    "fallback":             "passed",
    "fallback_passed":       "passed",
    "insufficient_context": "needs_review",
    "passed":               "passed",
    "blocked":              "blocked",
    "needs_review":         "needs_review",
    "provider_unavailable": "provider_unavailable",
}

# ── Placeholder / generic tokens that should not appear in real content ──

_PLACEHOLDERS = ("TODO", "example.com", "<placeholder>", "概念A", "概念B", "[TODO]", "[placeholder]")
_GENERIC_PHRASES = ("核心定义", "关键步骤", "理解与练习", "复盘与自测", "相关知识")
_RISKY_DOMAINS: set[str] = set()  # populated lazily from a small curated list

# ── QualityReviewResult ──────────────────────────────────────────────────


@dataclass
class QualityReviewResult:
    """Deterministic quality gate output for a single resource (spec §6.1).

    ``status`` is always one of the four public statuses.
    ``checks`` records individual pass/fail results.
    ``issues`` lists any failures with severity and detail.
    """

    status: str  # passed | needs_review | blocked | provider_unavailable
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    reviewer: str = "ContentQualityService"
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── ContentQualityService ────────────────────────────────────────────────


class ContentQualityService:
    """Per-type deterministic quality checks for generated learning resources."""

    # ── Public helpers ────────────────────────────────────────────────

    @classmethod
    def map_legacy_status(cls, status: str) -> str:
        """Map an old internal status to one of the four public statuses."""
        mapped = LEGACY_MAP.get(status)
        if mapped is None:
            logger.debug("Unknown legacy quality status %r → needs_review", status)
            return "needs_review"
        return mapped

    @classmethod
    def review(cls, resource: dict[str, Any]) -> QualityReviewResult:
        """Main entry point — dispatch by resource type.

        Returns a ``QualityReviewResult`` whose ``status`` is guaranteed
        to be one of the four public statuses.
        """
        rtype = str(resource.get("type") or "lecture").lower()

        # Detect search results: URL content or online_search metadata
        content = str(resource.get("content") or "")
        is_url = content.startswith("http://") or content.startswith("https://")
        meta = resource.get("metadata") or resource.get("resource_metadata") or {}
        is_search = isinstance(meta, dict) and meta.get("online_search")

        try:
            # Search-result types: always use search review
            if is_search or rtype in ("course", "document", "paper"):
                return cls._review_search_result(resource)
            # URL content for article/video types → search review
            if is_url and rtype in ("article", "video"):
                return cls._review_search_result(resource)
            if rtype in ("lecture", "reading", "case_study", "practice", "textbook", "article"):
                return cls._review_lecture(resource)
            if rtype == "mindmap":
                return cls._review_mindmap(resource)
            if rtype == "quiz":
                return cls._review_quiz(resource)
            if rtype in ("ppt", "pptx"):
                return cls._review_ppt(resource)
            if rtype in ("video", "animation", "manim"):
                return cls._review_video_animation(resource)
            # Any other type with URL content → search result
            if is_url:
                return cls._review_search_result(resource)
            return cls._review_generic(resource)
        except Exception:
            logger.exception("Quality review crashed for type=%s — marking needs_review", rtype)
            return QualityReviewResult(
                status="needs_review",
                issues=[{"check": "review_crash", "severity": "error",
                         "detail": "Quality checker threw an exception"}],
            )

    # ── §6.2 Lecture / reading ──────────────────────────────────────────

    @classmethod
    def _review_lecture(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        content = str(resource.get("content") or "").strip()
        title = str(resource.get("title") or "").strip()
        kps = resource.get("knowledge_points") or resource.get("knowledgePoints") or []
        if isinstance(kps, list):
            kp_text = " ".join(str(k) for k in kps)
        else:
            kp_text = str(kps)

        # Content not empty
        checks["content_not_empty"] = bool(content)
        if not checks["content_not_empty"]:
            issues.append({"check": "content_not_empty", "severity": "error",
                          "detail": "内容为空"})

        # Content length ≥ 100 chars
        checks["content_length"] = len(content) >= 100
        if not checks["content_length"]:
            issues.append({"check": "content_length", "severity": "warning",
                          "detail": f"内容过短 ({len(content)} 字符)"})

        # Topic relevance — title or KP appears in content
        topic_text = f"{title} {kp_text}"
        checks["topic_relevant"] = _topic_in_content(topic_text, content)
        if not checks["topic_relevant"]:
            issues.append({"check": "topic_relevant", "severity": "warning",
                          "detail": "标题/知识点未在内容中出现"})

        # Structure — at least 2 markdown headings or 2 sections
        headings = re.findall(r"^#{1,3}\s+", content, re.MULTILINE)
        checks["has_structure"] = len(headings) >= 2 or len(content.split("\n\n")) >= 3
        if not checks["has_structure"]:
            issues.append({"check": "has_structure", "severity": "warning",
                          "detail": "缺少章节结构（建议使用标题分段）"})

        # Placeholder-free
        checks["placeholder_free"] = not _contains_any(content, _PLACEHOLDERS)
        if not checks["placeholder_free"]:
            issues.append({"check": "placeholder_free", "severity": "error",
                          "detail": "包含占位符文本"})

        # Not purely generic phrases
        checks["not_generic"] = not _is_purely_generic(content)
        if not checks["not_generic"]:
            issues.append({"check": "not_generic", "severity": "warning",
                          "detail": "内容仅包含通用模板文本"})

        # No obvious self-contradiction (simple heuristics)
        checks["no_contradiction"] = not _has_contradiction(content)
        if not checks["no_contradiction"]:
            issues.append({"check": "no_contradiction", "severity": "warning",
                          "detail": "检测到可能的自相矛盾"})

        return _verdict(checks, issues)

    # ── §6.3 Mindmap / diagram ──────────────────────────────────────────

    @classmethod
    def _review_mindmap(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        mermaid = str(resource.get("mermaid_def") or resource.get("content") or "").strip()
        title = str(resource.get("title") or "").strip()

        # Has content
        checks["has_content"] = bool(mermaid)
        if not checks["has_content"]:
            issues.append({"check": "has_content", "severity": "error", "detail": "思维导图内容为空"})

        # Root node present
        has_root = "root((" in mermaid or "root((" in mermaid.replace(" ", "")
        checks["root_node"] = has_root
        if not has_root and mermaid:
            issues.append({"check": "root_node", "severity": "warning",
                          "detail": "思维导图缺少根节点"})

        # Sanitize — safety check
        normalized = sanitize_mermaid(mermaid) if mermaid else ""
        checks["safe_mermaid"] = bool(normalized) if mermaid else True
        if mermaid and not normalized:
            issues.append({"check": "safe_mermaid", "severity": "error",
                          "detail": "Mermaid 内容包含不安全元素"})

        # Node count — count lines that look like nodes (indented, with label brackets)
        node_lines = [l for l in mermaid.splitlines() if l.strip() and not l.strip().startswith(("root(", "mindmap"))]
        node_count = len(node_lines)
        checks["reasonable_nodes"] = node_count <= 40
        if node_count > 40:
            issues.append({"check": "reasonable_nodes", "severity": "warning",
                          "detail": f"节点过多 ({node_count} > 40)"})

        # At least 3 nodes (not just root alone)
        checks["min_nodes"] = node_count >= 3 if mermaid else True
        if mermaid and node_count < 3:
            issues.append({"check": "min_nodes", "severity": "warning",
                          "detail": f"节点过少 ({node_count})"})

        # Title relevant
        if title and mermaid:
            title_word = _longest_chinese_word(title)
            checks["topic_relevant"] = title_word in mermaid if title_word else True
            if not checks.get("topic_relevant", True):
                issues.append({"check": "topic_relevant", "severity": "warning",
                              "detail": "标题与图内容可能不匹配"})

        # No dangerous patterns (duplicated from sanitize — belt+ suspenders)
        checks["no_dangerous"] = not _has_dangerous_mermaid(mermaid)
        if not checks["no_dangerous"]:
            issues.append({"check": "no_dangerous", "severity": "error",
                          "detail": "Mermaid 包含危险指令"})

        # Topical hierarchy check
        kps = resource.get("knowledge_points") or resource.get("knowledgePoints") or []
        if isinstance(kps, list) and len(kps) > 0:
            coverage = sum(1 for kp in kps if str(kp) in mermaid)
            checks["kp_coverage"] = coverage >= min(2, len(kps))
            if not checks["kp_coverage"]:
                issues.append({"check": "kp_coverage", "severity": "warning",
                              "detail": f"仅 {coverage}/{len(kps)} 个知识点出现在图中"})
        else:
            checks["kp_coverage"] = bool(mermaid)

        return _verdict(checks, issues)

    # ── §6.4 Quiz ───────────────────────────────────────────────────────

    @classmethod
    def _review_quiz(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        questions = resource.get("questions") or []
        if not isinstance(questions, list) or len(questions) == 0:
            return QualityReviewResult(
                status="needs_review",
                checks={"has_questions": False},
                issues=[{"check": "has_questions", "severity": "error", "detail": "没有题目"}],
            )

        all_passed = True
        has_blocker = False
        seen_stems: set[str] = set()

        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            stem = str(q.get("stem") or "").strip()
            qtype = str(q.get("type") or "choice").lower()
            correct = str(q.get("correct") or q.get("answer") or "").strip()
            options = q.get("options")
            explanation = str(q.get("explanation") or "").strip()

            # Stem not empty and not too short
            if not stem or len(stem) < 10:
                issues.append({"check": "stem_valid", "severity": "error",
                              "detail": f"第{i+1}题题干为空或过短", "location": f"q{i}"})
                has_blocker = True
                all_passed = False

            # Stem not a generic template
            if stem and _contains_any(stem, _GENERIC_PHRASES[:2]):
                issues.append({"check": "stem_generic", "severity": "warning",
                              "detail": f"第{i+1}题题干可能为模板化生成", "location": f"q{i}"})
                all_passed = False

            # Duplicate stem detection
            stem_key = stem[:60]
            if stem_key in seen_stems:
                issues.append({"check": "unique_stem", "severity": "warning",
                              "detail": f"第{i+1}题题干与前题重复", "location": f"q{i}"})
                all_passed = False
            seen_stems.add(stem_key)

            # Correct answer validation (choice/truefalse only)
            if qtype in ("choice",) and isinstance(options, list) and len(options) > 0 and correct:
                option_labels = [_option_label(o) for o in options]
                if correct not in option_labels:
                    issues.append({"check": "answer_in_options", "severity": "error",
                                  "detail": f"第{i+1}题正确答案 '{correct}' 不在选项 {option_labels} 中",
                                  "location": f"q{i}"})
                    has_blocker = True
                    all_passed = False

            # Options distinct
            if isinstance(options, list) and len(options) > 1:
                norm_opts = [str(o).strip() for o in options]
                if len(set(norm_opts)) != len(norm_opts):
                    issues.append({"check": "distinct_options", "severity": "warning",
                                  "detail": f"第{i+1}题存在重复选项", "location": f"q{i}"})
                    all_passed = False

            # Explanation not empty
            if not explanation or len(explanation) < 10:
                issues.append({"check": "explanation_valid", "severity": "warning",
                              "detail": f"第{i+1}题解析为空或过短", "location": f"q{i}"})
                all_passed = False

            # No answer leaked in stem (simple check)
            if correct and stem and len(correct) >= 2 and correct in stem:
                issues.append({"check": "no_answer_leak", "severity": "warning",
                              "detail": f"第{i+1}题题干可能泄露答案", "location": f"q{i}"})
                all_passed = False

        # Difficulty
        difficulty = str(resource.get("difficulty") or "medium").lower()
        checks["valid_difficulty"] = difficulty in {"easy", "medium", "hard"}
        if not checks["valid_difficulty"]:
            issues.append({"check": "valid_difficulty", "severity": "warning",
                          "detail": f"非标准难度: {difficulty}"})

        checks["all_questions_ok"] = all_passed and not has_blocker

        if has_blocker:
            return QualityReviewResult(status="blocked", checks=checks, issues=issues)
        if not all_passed:
            return QualityReviewResult(status="needs_review", checks=checks, issues=issues)
        return QualityReviewResult(status="passed", checks=checks, issues=issues)

    # ── §6.5 Answer / explanation ──────────────────────────────────────

    @classmethod
    def _review_answer(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        explanation = str(resource.get("explanation") or resource.get("content") or "").strip()
        is_correct = resource.get("isCorrect") or resource.get("is_correct")
        score = resource.get("score") or resource.get("total_score") or resource.get("totalScore")

        checks["explanation_not_empty"] = len(explanation) >= 20
        if not checks["explanation_not_empty"]:
            issues.append({"check": "explanation_not_empty", "severity": "warning",
                          "detail": "解析内容为空或过短"})

        checks["score_consistent"] = True
        if is_correct is not None and score is not None:
            try:
                correct_val = bool(is_correct) if not isinstance(is_correct, str) else is_correct.lower() in ("true", "1", "yes")
                score_val = int(score)
                if correct_val and score_val < 60:
                    checks["score_consistent"] = False
                    issues.append({"check": "score_consistent", "severity": "warning",
                                  "detail": f"判为正确但得分过低 ({score_val})"})
            except (ValueError, TypeError):
                pass

        return _verdict(checks, issues)

    # ── §6.6 PPT ────────────────────────────────────────────────────────

    @classmethod
    def _review_ppt(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        content = str(resource.get("content") or "").strip()
        title = str(resource.get("title") or "").strip()
        ppt_path = content  # content field holds the file path for PPT resources

        checks["title_not_empty"] = bool(title)
        if not checks["title_not_empty"]:
            issues.append({"check": "title_not_empty", "severity": "warning",
                          "detail": "PPT 标题为空"})

        checks["content_not_empty"] = bool(ppt_path)
        if not checks["content_not_empty"]:
            issues.append({"check": "content_not_empty", "severity": "error",
                          "detail": "PPT 文件路径为空"})

        # Check file exists and has minimum size
        if ppt_path:
            import os
            try:
                if os.path.isfile(ppt_path):
                    fsize = os.path.getsize(ppt_path)
                    # Minimum PPTX file size ~4KB (ZIP structure)
                    checks["file_readable"] = fsize >= 3500
                    if not checks["file_readable"]:
                        issues.append({"check": "file_readable", "severity": "error",
                                      "detail": f"PPT 文件过小 ({fsize} bytes)，可能损坏"})
                else:
                    checks["file_readable"] = False
                    issues.append({"check": "file_readable", "severity": "error",
                                  "detail": "PPT 文件不存在"})
            except OSError:
                checks["file_readable"] = False
                issues.append({"check": "file_readable", "severity": "error",
                              "detail": "无法读取 PPT 文件"})

        # File path safety
        checks["safe_path"] = ppt_path and ".." not in ppt_path
        if not checks["safe_path"]:
            issues.append({"check": "safe_path", "severity": "error",
                          "detail": "PPT 文件路径不安全"})

        return _verdict(checks, issues)

    # ── §6.7 Online search results ──────────────────────────────────────

    @classmethod
    def _review_search_result(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        url = str(resource.get("content") or resource.get("original_url") or "")
        title = str(resource.get("title") or "").strip()
        metadata = resource.get("metadata") or resource.get("resource_metadata") or {}
        if isinstance(metadata, dict):
            url = str(metadata.get("original_url") or metadata.get("canonical_url") or url)

        # URL format
        checks["valid_url"] = bool(url) and (url.startswith("http://") or url.startswith("https://"))
        if not checks["valid_url"]:
            issues.append({"check": "valid_url", "severity": "error",
                          "detail": f"URL 格式无效: {url[:80]}"})

        # Title not empty
        checks["title_not_empty"] = bool(title)
        if not checks["title_not_empty"]:
            issues.append({"check": "title_not_empty", "severity": "warning",
                          "detail": "搜索结果标题为空"})

        # Risky domain check
        if url:
            domain = _extract_domain(url)
            checks["safe_domain"] = not _is_risky_domain(domain)
            if not checks["safe_domain"]:
                issues.append({"check": "safe_domain", "severity": "error",
                              "detail": f"域名在风险列表中: {domain}"})

        # No obviously fake URL
        checks["no_fake_url"] = "example.com" not in url and "test.com" not in url
        if not checks["no_fake_url"]:
            issues.append({"check": "no_fake_url", "severity": "error",
                          "detail": "疑似伪造 URL"})

        return _verdict(checks, issues)

    # ── §6.8 Video / animation ──────────────────────────────────────────

    @classmethod
    def _review_video_animation(cls, resource: dict[str, Any]) -> QualityReviewResult:
        """Check video/animation provider availability.

        Per spec §6.8: if the provider is unavailable, return
        ``provider_unavailable`` — don't fake success, don't generate
        empty files, don't block other resource types.
        """
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        rtype = str(resource.get("type") or "video").lower()
        content = str(resource.get("content") or "").strip()

        # Check if this is already flagged as unavailable
        qs = resource.get("quality_status") or resource.get("qualityStatus") or ""
        if qs == "provider_unavailable":
            return QualityReviewResult(
                status="provider_unavailable",
                checks={"provider_available": False},
                issues=[{"check": "provider_available", "severity": "info",
                        "detail": "视频/动画服务不可用"}],
            )

        # Check provider availability via registry
        provider_available = True
        try:
            from app.services.multimodal_registry import default_registry
            capability = "manim_generation" if rtype in ("animation", "manim") else "video_generation"
            _, tool = default_registry().select_tool(capability)
            if tool is None:
                provider_available = False
        except Exception:
            provider_available = False

        checks["provider_available"] = provider_available
        if not provider_available:
            issues.append({"check": "provider_available", "severity": "info",
                          "detail": f"{rtype} 服务未配置或不可用"})
            return QualityReviewResult(
                status="provider_unavailable",
                checks=checks, issues=issues,
            )

        # Provider exists — content verification is limited
        checks["has_content"] = bool(content)
        if not checks["has_content"]:
            issues.append({"check": "has_content", "severity": "warning",
                          "detail": "视频/动画内容 URL 为空"})

        # Can't programmatically verify video content → needs_review
        return QualityReviewResult(
            status="needs_review",
            checks=checks, issues=issues,
            reviewer="ContentQualityService",
        )

    # ── Generic fallback ────────────────────────────────────────────────

    @classmethod
    def _review_generic(cls, resource: dict[str, Any]) -> QualityReviewResult:
        checks: dict[str, bool] = {}
        issues: list[dict] = []

        content = str(resource.get("content") or "").strip()
        title = str(resource.get("title") or "").strip()

        checks["has_content"] = bool(content) or bool(title)
        if not checks["has_content"]:
            issues.append({"check": "has_content", "severity": "error",
                          "detail": "资源内容为空"})

        checks["placeholder_free"] = not _contains_any(content, _PLACEHOLDERS)
        if not checks["placeholder_free"]:
            issues.append({"check": "placeholder_free", "severity": "error",
                          "detail": "包含占位符文本"})

        return _verdict(checks, issues)


# ── Verdict helper ─────────────────────────────────────────────────────────


def _verdict(checks: dict[str, bool], issues: list[dict]) -> QualityReviewResult:
    """Determine the public quality status from check results.

    - Any ``severity=="error"`` issue → ``blocked``
    - Any failed check → ``needs_review``
    - Everything passed → ``passed``
    """
    errors = [i for i in issues if i.get("severity") == "error"]
    if errors:
        return QualityReviewResult(status="blocked", checks=checks, issues=issues)
    if not all(checks.values()):
        return QualityReviewResult(status="needs_review", checks=checks, issues=issues)
    return QualityReviewResult(status="passed", checks=checks, issues=issues)


# ── Content analysis helpers ──────────────────────────────────────────────


def _topic_in_content(topic_text: str, content: str) -> bool:
    """Check whether at least one meaningful topic token appears in content."""
    if not topic_text.strip():
        return True  # can't check — assume OK
    tokens = [t for t in re.split(r"[\s,，、]+", topic_text) if len(t) >= 2]
    if not tokens:
        return True
    content_lower = content.lower()
    return any(t.lower() in content_lower for t in tokens)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    """Return True if any token appears in text (case-insensitive)."""
    lower = text.lower()
    return any(t.lower() in lower for t in tokens)


def _is_purely_generic(content: str) -> bool:
    """Return True if content is composed almost entirely of generic phrases."""
    if len(content) < 80:
        return False
    stripped = content
    for phrase in _GENERIC_PHRASES:
        stripped = stripped.replace(phrase, "")
    # If removing generic phrases leaves very little, it's generic
    return len(stripped.strip()) < max(30, len(content) * 0.2)


def _has_contradiction(content: str) -> bool:
    """Simple contradiction heuristics."""
    contradiction_pairs = [
        ("正确", "错误"),
        ("是", "不是"),
        ("可以", "不可以"),
    ]
    lower = content.lower()
    for a, b in contradiction_pairs:
        # Both present in close proximity (same paragraph)
        paragraphs = lower.split("\n\n")
        for para in paragraphs:
            if a.lower() in para and b.lower() in para and len(para) < 500:
                return True
    return False


def _has_dangerous_mermaid(mermaid: str) -> bool:
    """Check for dangerous Mermaid directives."""
    dangerous = ("click ", "style ", "classDef ", "linkStyle ", "<script>", "<iframe>",
                 "javascript:", "onerror=", "onload=")
    lower = mermaid.lower()
    return any(d.lower() in lower for d in dangerous)


def _option_label(option: str) -> str:
    """Extract the label from an option like 'A. Answer text' → 'A'."""
    opt = option.strip()
    m = re.match(r"^([A-Da-d])[\.\、\)]", opt)
    if m:
        return m.group(1).upper()
    return opt[:1].upper() if opt else ""


def _longest_chinese_word(text: str) -> str:
    """Return the longest Chinese word in text for topic matching."""
    words = re.findall(r"[一-鿿]{2,}", text)
    if not words:
        return ""
    return max(words, key=len)


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1).lower() if m else ""


def _is_risky_domain(domain: str) -> bool:
    """Check a small curated list of known risky/noise domains."""
    risky = {
        "example.com", "test.com", "localhost", "127.0.0.1",
        "0.0.0.0", "malware.com", "phishing.test",
        # Common noise/advert domains
        "doubleclick.net", "googlesyndication.com",
    }
    return domain in risky or any(domain.endswith(f".{d}") for d in risky if not d.startswith("127"))
