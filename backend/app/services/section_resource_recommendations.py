"""Real, transient external recommendations for one learning section."""

from __future__ import annotations

import copy
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import logging
import re
import time
from hashlib import sha256
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass
from threading import Event, Lock
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from app.config import settings
from app.services.search_client import SearchError, get_search_client, search_arxiv, search_crossref
from app.services.user_ai_config import copy_context_wrap as _ai_ctx_wrap

logger = logging.getLogger(__name__)


RESOURCE_TYPES = ("article", "video", "course", "document", "paper")
_ACTION_TERMS = ("用纸笔", "手动模拟", "画出", "一个简单", "每一层", "请", "完成")
_CONCEPTS = (
    ("数据结构", "data structure"), ("算法", "algorithm"),
    ("时间复杂度", "time complexity"), ("空间复杂度", "space complexity"),
    ("大O", "big o"), ("线性表", "linear list"),
    ("顺序表", "array"), ("链表", "linked list"),
    ("递归", "recursion"), ("调用栈", "call stack"), ("栈帧", "stack frame"),
    ("局部变量", "local variables"), ("返回地址", "return address"),
    ("阶乘", "factorial"), ("斐波那契", "fibonacci"),
)
_TOPIC_FALLBACK = "\u5b66\u4e60\u4e3b\u9898"
_REQUEST_PREFIX = re.compile(
    r"^(?:"
    r"\u8bf7(?:\u5e2e\u6211)?(?:\u627e|\u63a8\u8350)(?:\u4e00\u4e9b)?(?:\u5173\u4e8e)?|"
    r"(?:\u7ed9\u6211)?\u63a8\u8350(?:\u4e00\u4e9b)?(?:\u9002\u5408(?:\u5165\u95e8|\u521d\u5b66\u8005|\u5927\u4e8c\u5b66\u751f)?\u7684)?|"
    r"(?:\u6211)?\u60f3(?:\u8981)?(?:\u7b80\u5355)?(?:\u5b66\u4e60|\u4e86\u89e3)(?:\u4e00\u4e0b)?|"
    r"(?:\u5e2e\u6211)?\u627e(?:\u4e00\u4e9b)?(?:\u5173\u4e8e)?"
    r")"
)
_RESOURCE_SUFFIX = re.compile(
    r"(?:\u7684)?(?:\u6559\u5b66)?(?:\u89c6\u9891|\u8d44\u6599|\u8d44\u6e90|\u6587\u7ae0|\u8bfe\u7a0b|\u6587\u6863|\u8bba\u6587|\u6559\u7a0b|\u8bb2\u4e49)$"
)
_PAPER_HOSTS = ("arxiv.org", "semanticscholar.org", "dl.acm.org", "ieeexplore.ieee.org", "dblp.org", "doi.org", "cnki", "wanfang")
_COURSE_HOSTS = ("icourse163.org", "xuetangx.com", "smartedu.cn", "imooc.com", "coursera.org", "edx.org", "ocw.mit.edu")
_DOMESTIC_VIDEO_PLATFORMS = {"bilibili", "icourse163", "xuetangx", "icourses", "smartedu"}

ProgressCallback = Callable[[dict[str, Any]], None]


class SearchCancelled(Exception):
    """Internal signal used to stop a cancelled section search."""


@dataclass
class _CachedCandidates:
    created_at: float
    candidates: list[dict[str, Any]]
    queries: list[str]


class SearchCascade:
    """Process-local public candidate cache for ResourceAgent's section search.

    It deliberately stores neither session/profile data nor ranked reasons. Each
    request reruns feedback filtering and personalised ranking over the cached
    public candidates.
    """

    _cache: OrderedDict[str, _CachedCandidates] = OrderedDict()
    _lock = Lock()
    _stats = Counter()

    @classmethod
    def get(cls, key: str) -> tuple[str, _CachedCandidates | None]:
        if not settings.search_cache_enabled:
            return "miss", None
        with cls._lock:
            entry = cls._cache.get(key)
            if not entry:
                cls._stats["misses"] += 1
                return "miss", None
            age = time.time() - entry.created_at
            if age <= settings.search_cache_ttl_seconds:
                cls._cache.move_to_end(key)
                cls._stats["hits"] += 1
                return "fresh", copy.deepcopy(entry)
            if age <= settings.search_stale_cache_seconds:
                cls._stats["stale_hits"] += 1
                return "stale", copy.deepcopy(entry)
            cls._cache.pop(key, None)
            cls._stats["misses"] += 1
        return "miss", None

    @classmethod
    def put(cls, key: str, candidates: list[dict[str, Any]], queries: list[str]) -> None:
        if not settings.search_cache_enabled or not candidates:
            return
        safe_candidates = []
        for candidate in candidates:
            item = candidate.get("item") if isinstance(candidate, dict) else None
            if hasattr(item, "__dataclass_fields__"):
                item = asdict(item)
            if isinstance(item, dict):
                item = {key: item.get(key, "") for key in ("title", "url", "snippet", "source", "published_at", "authors", "doi", "raw_rank", "access_hint")}
            safe_candidates.append({**candidate, "item": item})
        with cls._lock:
            cls._cache[key] = _CachedCandidates(time.time(), copy.deepcopy(safe_candidates), list(queries))
            cls._cache.move_to_end(key)
            while len(cls._cache) > settings.search_cache_max_entries:
                cls._cache.popitem(last=False)

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._cache.clear()
            cls._stats.clear()

    @classmethod
    def stats(cls) -> dict[str, int]:
        with cls._lock:
            return dict(cls._stats)


def normalize_url(value: str) -> str:
    """Keep only safe, stable http(s) resource URLs."""
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.netloc.lower().removeprefix("www.")
    if host.startswith("m."):
        host = host[2:]
    query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith(("utm_", "fbclid", "gclid"))])
    return urlunparse(("https", host, parsed.path.rstrip("/") or "/", "", query, ""))


def resource_feedback_key(url: str) -> str:
    """Stable, non-reversible key for one normalized external URL."""
    normalized = normalize_url(url)
    return sha256(normalized.encode("utf-8")).hexdigest()[:24] if normalized else ""


def classify_platform(url: str) -> str | None:
    """Recognize concrete public video or course-video pages only."""
    parsed = urlparse(url)
    host, path = parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if host.endswith("bilibili.com") and path.startswith("/video/"):
        return "bilibili"
    if host.endswith("youtube.com") and ((path == "/watch" and query.get("v")) or path.startswith("/shorts/")):
        return "youtube"
    if host == "youtu.be" and path.count("/") == 1 and len(path) > 1:
        return "youtube"
    if host.endswith("vimeo.com") and re.fullmatch(r"/[0-9]+", path):
        return "vimeo"
    if host.endswith("youku.com") and path.startswith("/v_show/"):
        return "youku"
    if host.endswith("iqiyi.com") and path.startswith("/v_"):
        return "iqiyi"
    if host.endswith("douyin.com") and re.fullmatch(r"/video/[0-9]+", path):
        return "douyin"
    if host.endswith("v.qq.com") and path.startswith("/x/page/") and path.endswith(".html"):
        return "tencent_video"
    if host.endswith("icourse163.org") and "/learn/" in path:
        return "icourse163"
    if host.endswith("xuetangx.com") and ("/learn/" in path or "/course/" in path):
        return "xuetangx"
    if host.endswith("icourses.cn") and path not in {"", "/"}:
        return "icourses"
    if host.endswith("smartedu.cn") and ("/course/" in path or "/resource/" in path):
        return "smartedu"
    if host.endswith("smartedu.cn") and ("/course/" in path or "/resource/" in path):
        return "smartedu"
    if host.endswith("imooc.com") and ("/learn/" in path or "/video/" in path):
        return "imooc"
    return None


def _is_paper_source(host: str) -> bool:
    return any(name in host for name in _PAPER_HOSTS)


def _is_course_url(host: str, path: str) -> bool:
    if "ocw.mit.edu" in host:
        return path.startswith("/course") or path.startswith("/courses")
    if not any(name in host for name in _COURSE_HOSTS):
        return False
    return bool(path and path != "/")


def _is_document_url(url: str, title: str, snippet: str) -> bool:
    parsed = urlparse(url)
    text = f"{parsed.path} {title} {snippet}".lower()
    return parsed.path.lower().endswith(".pdf") or any(token in text for token in ("lecture notes", "slides", "handout", "课件", "讲义", "实验指导"))


def classify_resource_type(url: str, title: str = "", snippet: str = "") -> str:
    parsed = urlparse(url)
    host, path = parsed.netloc.lower().removeprefix("www."), parsed.path.lower()
    if _is_paper_source(host):
        return "paper"
    if classify_platform(url) and not _is_course_url(host, path):
        return "video"
    if _is_course_url(host, path):
        return "course"
    if _is_document_url(url, title, snippet):
        return "document"
    return "article"


def validate_resource_url(url: str, resource_type: str | None = None, title: str = "", snippet: str = "") -> str:
    """Reject home pages, search pages, unsafe schemes, and type mismatches."""
    if urlparse(str(url or "").strip()).netloc.lower().removeprefix("www.") == "b23.tv":
        try:
            url = urlopen(Request(str(url), method="HEAD"), timeout=3).geturl()
        except Exception:
            return ""
    normalized = normalize_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    host, path = parsed.netloc.lower().removeprefix("www."), parsed.path.lower()
    if host == "example.com" or host.endswith(".example.com") or host == "localhost" or not path or path == "/":
        return ""
    if "/search" in path or "/results" in path or "search_query" in parsed.query:
        return ""
    inferred = classify_resource_type(normalized, title, snippet)
    # Post-filter by resource type.  We don't use site: in queries because
    # DDGS doesn't support it well; instead we classify after free-form search.
    if resource_type == "video" and not classify_platform(normalized):
        return ""
    if resource_type == "paper" and not _is_paper_source(host):
        return ""
    if resource_type == "course" and not _is_course_url(host, path):
        return ""
    if resource_type == "document" and not _is_document_url(normalized, title, snippet):
        return ""
    return normalized


def _profile_context(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = profile or {}
    direct = profile.get("subject_context")
    nested = ((profile.get("preferences") or {}).get("profile_v2") or {}).get("subject_context")
    context = direct if isinstance(direct, dict) else nested if isinstance(nested, dict) else {}
    records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
    if records:
        context = dict(context)
        for key, record in records.items():
            if isinstance(record, dict) and record.get("is_disabled_for_personalization"):
                context.pop(key, None)
    return context


def _profile_mastery(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    profile = profile or {}
    direct = profile.get("knowledge_mastery")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    nested = ((profile.get("preferences") or {}).get("profile_v2") or {}).get("knowledge_mastery")
    return [item for item in nested if isinstance(item, dict)] if isinstance(nested, list) else []


def normalize_search_topic(value: Any) -> str:
    """Remove request wording while retaining the complete knowledge phrase."""
    topic = re.sub(r"\s+", " ", str(value or "")).strip(" \uff0c,\u3001\u3002\uff1b;")
    if not topic:
        return _TOPIC_FALLBACK

    requested = _REQUEST_PREFIX.sub("", topic).strip(" \u7684\uff0c,\u3001\u3002\uff1b;")
    if requested != topic:
        requested = _RESOURCE_SUFFIX.sub("", requested).strip(" \u7684\uff0c,\u3001\u3002\uff1b;")
        return requested or _TOPIC_FALLBACK

    head = re.sub(r"[\uff08(][^()\uff08\uff09]*[\uff09)]", "", topic)
    head = re.split(r"[\uff0c,\u3001\u3002\uff1b;]", head, maxsplit=1)[0]
    matches = []
    for concept, _ in _CONCEPTS:
        position = head.find(concept)
        if position >= 0:
            matches.append((position, concept))
    matches.sort()
    if matches:
        return "".join(dict.fromkeys(concept for _, concept in matches))

    for term in _ACTION_TERMS:
        head = head.replace(term, "")
    return head.strip(" \u7684\uff0c,\u3001\u3002\uff1b;") or _TOPIC_FALLBACK


def normalize_search_context(
    *,
    course_name: str = "",
    path_title: str = "",
    stage_title: str = "",
    chapter_title: str = "",
    section_title: str = "",
    lecture_title: str = "",
    knowledge_points: list[str] | None = None,
    weak_points: list[str] | None = None,
    learner_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract stable search concepts without requiring an LLM."""
    profile_context = _profile_context(learner_profile)
    course = str(course_name or profile_context.get("subject_name") or profile_context.get("course_name") or "").strip()
    text = " ".join(str(value or "") for value in (path_title, stage_title, chapter_title, section_title, lecture_title, *(knowledge_points or [])))
    if not course and "数据结构" in text:
        course = "数据结构"
    # Derive keywords from knowledge points + section title, not a hardcoded list
    lowered = text.lower()
    pairs = [(cn, en) for cn, en in _CONCEPTS if cn in text or en in lowered]
    # Keep concepts as search terms, but derive the primary topic from the most
    # specific available title instead of the first vocabulary match.
    keywords = list(dict.fromkeys(cn for cn, _ in pairs))
    topic_source = section_title or lecture_title or chapter_title or (knowledge_points or [""])[0]
    primary_topic = normalize_search_topic(topic_source)
    if primary_topic != _TOPIC_FALLBACK and primary_topic not in keywords:
        keywords.append(primary_topic)
    for kp in knowledge_points or []:
        kp_name = str(kp).strip()
        if kp_name and len(kp_name) >= 2:
            keywords.append(kp_name)
    keywords = list(dict.fromkeys(keywords))
    english_keywords = list(dict.fromkeys(en for _, en in pairs))
    for term in ("\u6570\u7ec4", "\u94fe\u8868", "\u6811", "\u6808", "\u961f\u5217", "\u9012\u5f52"):
        if term in text and term not in keywords:
            keywords.append(term)
    relevant_weak = [point for point in weak_points or [] if str(point).strip() and str(point).strip().lower() in text.lower()]
    for item in _profile_mastery(learner_profile):
        name = str(item.get("label") or item.get("knowledge_id") or "").strip()
        if item.get("status") == "weak" and name and name.lower() in text.lower() and name not in relevant_weak:
            relevant_weak.append(name)
    for point in relevant_weak:
        if point not in keywords:
            keywords.append(point)
    prior = " ".join(str(item) for item in profile_context.get("prior_experience") or [])
    beginner = any(token in prior for token in ("零基础", "没学过", "基础薄弱", "初学"))
    # ── 学习历史精炼水平判断 ──
    # 优先从 profile 维度读取，其次从 subject_context 读取
    learning_history_raw = None
    if isinstance(learner_profile, dict):
        lh = learner_profile.get("learning_history")
        if isinstance(lh, dict):
            learning_history_raw = lh
        elif isinstance(lh, str) and lh.strip():
            learning_history_raw = {"value": lh}
    if learning_history_raw is None:
        lh_ctx = profile_context.get("learning_history", "")
        learning_history_raw = {"value": str(lh_ctx)} if lh_ctx else {}
    history_text = str(learning_history_raw.get("value", "") or "")
    history_lower = history_text.lower()
    # 判断学生过往学习经历的深度
    has_strong_history = any(kw in history_lower for kw in (
        "高分", "优秀", "掌握", "熟练", "精通", "90", "95", "100",
        "passed", "grade a", "score 90", "completed with",
    ))
    has_prior_relevant = any(kw in history_lower for kw in (
        "学过", "修过", "上过", "学过一些", "接触过", "及格", "成绩",
        "taken", "studied", "learned", "passed", "grade", "score",
    ))
    # 三级水平：beginner → intermediate → advanced
    if beginner:
        level = "beginner"
    elif has_strong_history:
        level = "advanced"
    elif has_prior_relevant:
        level = "intermediate"
    else:
        level = "general"
    preferences = profile_context.get("content_preferences") if isinstance(profile_context.get("content_preferences"), list) else []
    resource_preferences = profile_context.get("resource_preferences") if isinstance(profile_context.get("resource_preferences"), list) else []
    # ── 认知风格提取：映射到资源类型偏好权重 ──
    cognitive_style: dict[str, float] = {}
    raw_style: dict | None = None
    if isinstance(learner_profile, dict):
        cs = learner_profile.get("cognitive_style")
        if isinstance(cs, dict):
            raw_style = cs
        elif isinstance(cs, str) and cs.strip():
            raw_style = {"value": cs}
    if raw_style is None and isinstance(learner_profile, dict):
        for state in (learner_profile.get("general_states") or []):
            if isinstance(state, dict) and state.get("key") == "cognitive_style":
                raw_style = {"value": str(state.get("label", "") or state.get("value", ""))}
                break
    if raw_style is None:
        cs_ctx = profile_context.get("cognitive_style", "")
        if cs_ctx:
            raw_style = {"value": str(cs_ctx)}
    style_value = str(raw_style.get("value", "") or "").lower() if isinstance(raw_style, dict) else ""
    # 认知风格 → 资源类型偏好映射
    _style_map: dict[str, dict[str, float]] = {
        "visual_explanation": {"video": 0.10, "document": -0.03},
        "图解": {"video": 0.10, "document": -0.03},
        "definition_first": {"article": 0.08, "document": 0.08, "video": -0.04},
        "先讲定义": {"article": 0.08, "document": 0.08, "video": -0.04},
        "example_first": {"article": 0.06, "video": 0.06, "course": 0.04},
        "先看例题": {"article": 0.06, "video": 0.06, "course": 0.04},
        "practice_after_explanation": {"document": 0.06},
        "理解讲解后练习": {"document": 0.06},
        "step_by_step": {"article": 0.06, "document": 0.06, "course": 0.04},
        "分步讲解": {"article": 0.06, "document": 0.06, "course": 0.04},
        "concise_explanation": {"video": 0.04},
        "简洁讲解": {"video": 0.04},
    }
    cognitive_style = _style_map.get(style_value, {})
    # 综合弱项掌握度：用于提升弱项相关资源权重
    weak_mastery_map: dict[str, float] = {}
    for item in _profile_mastery(learner_profile):
        name = str(item.get("label") or item.get("knowledge_id") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        if name and status in ("weak", "薄弱", "learning", "学习中"):
            weak_mastery_map[name] = 0.15  # 弱项相关资源大幅提权
        elif name and status in ("partial", "部分掌握", "developing", "发展中"):
            weak_mastery_map[name] = 0.08
    return {
        "course_name": course,
        "primary_topic": primary_topic,
        "keywords": keywords[:7],
        "english_keywords": english_keywords[:7],
        "preferences": preferences,
        "resource_preferences": resource_preferences,
        "level": level,
        "learning_history_text": history_text[:200] if history_text else "",
        "relevant_weak_points": relevant_weak[:4],
        "cognitive_style": cognitive_style,
        "weak_mastery_map": weak_mastery_map,
    }


def _split_compound_keyword(keyword: str) -> list[str]:
    """Split a compound Chinese keyword into individual sub-words for partial matching.

    e.g. "计算机发展简史与分类" → ["计算机发展简史与分类", "计算机发展简史", "分类"]
    """
    parts = [keyword]
    for sep in ("与", "和", "及", "、", "的", "之"):
        if sep in keyword:
            parts.extend(p for p in keyword.split(sep) if len(p) >= 2)
    return list(dict.fromkeys(parts))


def _keyword_matches(text: str, context: dict[str, Any]) -> list[str]:
    """Check which context keywords appear in text, splitting compound keywords."""
    matched: list[str] = []
    matched_original: set[str] = set()
    for term in context["keywords"]:
        term_lower = term.lower()
        if term_lower in text:
            matched.append(term)
            matched_original.add(term_lower)
        else:
            for sub in _split_compound_keyword(term_lower):
                if sub in text and sub not in matched_original:
                    matched.append(term)
                    matched_original.add(term_lower)
                    break
    for term in context["english_keywords"]:
        term_lower = term.lower()
        if term_lower in text and term not in {m for m in matched}:
            matched.append(term)
    return list(dict.fromkeys(matched))


def score_relevance(title: str, snippet: str, context: dict[str, Any], resource_type: str, match_level: str, trust_level: str) -> tuple[float, list[str]]:
    """画像驱动的多维度相关性评分。

    评分维度（按权重）：
    1. 关键词匹配 (0.26 base + 0.10/keyword)
    2. 主题词命中 (+0.20)
    3. 薄弱知识点匹配 (+0.15/weak_point) ← 画像驱动
    4. 信任度 (official +0.16 / educational +0.11 / general +0.03)
    5. 认知风格匹配 (+0.08~0.12) ← 画像驱动
    6. 内容偏好匹配 (+0.08) ← 画像驱动
    7. 资源类型偏好 (+0.08~0.10) ← 画像驱动
    8. 水平匹配 (+0.08) ← 画像驱动
    """
    text = f"{title} {snippet}".lower()
    matched = _keyword_matches(text, context)
    score = 0.26 + min(0.50, len(matched) * 0.10)
    if matched:
        score += 0.1
    if context["primary_topic"].lower() in text:
        score += 0.2
    if context["course_name"] and context["course_name"].lower() in text:
        score += 0.12
    if resource_type == "video" and context["course_name"]:
        for cn_char in context["course_name"]:
            if cn_char in text:
                score += 0.04
                break
    if match_level == "course_level":
        score += 0.08
    if match_level == "expanded_research":
        score -= 0.05
    score += {"official": 0.16, "educational": 0.11, "general": 0.03}[trust_level]
    # ── 画像驱动：薄弱点匹配（大幅提权）──
    weak_mastery_map = context.get("weak_mastery_map", {})
    weak_hits = 0
    weak_names: list[str] = []
    for wname, wboost in weak_mastery_map.items():
        if wname.lower() in text:
            score += wboost
            weak_hits += 1
            weak_names.append(wname)
    if weak_hits >= 2:
        score += 0.05  # 多弱项命中额外奖励
    # ── 画像驱动：认知风格匹配 ──
    cog_style = context.get("cognitive_style", {})
    if isinstance(cog_style, dict) and resource_type in cog_style:
        score += cog_style[resource_type]
    # ── 画像驱动：内容偏好匹配 ──
    if "example_first" in context["preferences"] and any(token in text for token in ("示例", "例题", "example", "walkthrough")):
        score += 0.08
    if "definition_first" in context["preferences"] and any(token in text for token in ("定义", "概念", "原理", "definition", "concept")):
        score += 0.08
    if "step_by_step" in context["preferences"] and any(token in text for token in ("步骤", "教程", "tutorial", "step", "guide")):
        score += 0.08
    # ── 画像驱动：水平匹配 ──
    if context["level"] == "beginner" and any(token in text for token in ("入门", "基础", "beginner", "basics")):
        score += 0.08
    # ── 画像驱动：资源类型偏好 ──
    res_prefs = context.get("resource_preferences", [])
    if resource_type == "video" and any("视频" in str(item) for item in res_prefs):
        score += 0.10
    if resource_type in ("document", "article") and any("文档" in str(item) or "讲义" in str(item) for item in res_prefs):
        score += 0.08
    return min(0.98, score), matched


def diversify_results(resources: list[dict[str, Any]], per_domain: int = 2) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    result: list[dict[str, Any]] = []
    for item in sorted(resources, key=lambda resource: resource["relevance_score"], reverse=True):
        if counts[item["source"]] >= per_domain:
            continue
        counts[item["source"]] += 1
        result.append(item)
    return result


class SectionResourceRecommendationService:
    """Adapt real search results for the lecture workspace without persistence."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or get_search_client(settings.search_provider if settings.search_provider != "mock" else "duckduckgo")
        self._use_cache = client is None

    _normal_url = staticmethod(normalize_url)
    _video_platform = staticmethod(classify_platform)
    _resource_type = staticmethod(classify_resource_type)

    @staticmethod
    def _point_names(items: list[Any] | None) -> list[str]:
        names = []
        for item in items or []:
            name = (item.get("name") or item.get("topic") or "") if isinstance(item, dict) else str(item)
            name = str(name).strip()
            if name and name not in names:
                names.append(name)
        return names[:6]

    @staticmethod
    def _trust_level(source: str) -> str:
        source = source.lower()
        if source.endswith((".gov", ".edu", ".edu.cn")) or any(part in source for part in ("docs.python.org", "developer.mozilla.org", "openai.com", "microsoft.com", "w3.org")):
            return "official"
        if any(part in source for part in ("ocw", "coursera", "edx", "mooc", "icourse163", "xuetangx", "mit.edu", "stanford.edu", "arxiv", "acm", "ieee", "dblp")):
            return "educational"
        return "general"

    @staticmethod
    def _query_layers(context: dict[str, Any], resource_type: str, language: str) -> list[tuple[str, str]]:
        course = context["course_name"] or ""
        topic = context["primary_topic"]
        keywords = " ".join(context["keywords"][:3]) or topic
        english = " ".join(context["english_keywords"][:3]) or ""
        cn_hints = []
        en_hints = []
        if "example_first" in context["preferences"]:
            cn_hints.extend(["示例", "例题", "分步讲解"]); en_hints.extend(["example", "walkthrough"])
        if context["level"] == "beginner":
            cn_hints.extend(["入门", "基础"]); en_hints.extend(["beginner", "basics"])
        hint = " ".join(cn_hints)
        english_hint = " ".join(en_hints)
        if resource_type == "video":
            return [(f"site:bilibili.com/video {course} {topic} 视频".strip(), "exact_topic"),
                    (f"site:icourse163.org {course} {topic} 视频".strip(), "chapter_level"),
                    (f"site:xuetangx.com {course} {topic} 视频".strip(), "chapter_level")]
        if resource_type == "article":
            base = [(f"{course} {topic} {hint}".strip(), "exact_topic"),
                    (f"{keywords} 教程 {hint}".strip(), "exact_topic")]
            if english:
                base.append((f"{english} tutorial {english_hint}".strip(), "chapter_level"))
            if course and course not in {q for q, _ in base}:
                base.append((f"{course} {topic} 教学".strip(), "course_level"))
            return [q for q in base if q[0]][:3]
        if resource_type == "video":
            base = [(f"{course} {topic} 视频教程".strip(), "exact_topic"),
                    (f"{topic} 视频教程 bilibili".strip(), "chapter_level"),
                    (f"{course} {topic} 视频".strip(), "chapter_level")]
            if english:
                base.append((f"{english} video tutorial".strip(), "course_level"))
            return [q for q in base if q[0]][:3]
        if resource_type == "course":
            base = [(f"{course} {topic} 课程".strip(), "exact_topic"),
                    (f"{course} {topic} mooc".strip(), "chapter_level"),
                    (f"{course} 在线课程".strip(), "course_level")]
            return [q for q in base if q[0]][:3]
        if resource_type == "document":
            base = [(f"{topic} {hint}".strip(), "exact_topic"),
                    (f"{topic} 课件 讲义".strip(), "exact_topic")]
            if english:
                base.append((f"{english} lecture notes {english_hint}".strip(), "chapter_level"))
            return [q for q in base if q[0]][:3]
        if not english:
            return [(f"{topic} paper".strip(), "exact_topic"),
                    (f"{topic} 论文".strip(), "expanded_research")]
        return [(f"{english} paper".strip(), "exact_topic"),
                (f"{english} research paper".strip(), "expanded_research"),
                (f"{topic} paper".strip(), "chapter_level")][:3]

    def _rank(
        self,
        candidates: list[dict[str, Any]],
        context: dict[str, Any],
        language: str,
        diagnostics: dict[str, Any],
        feedback_by_url: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        seen_identifiers: set[str] = set()
        for candidate in candidates:
            item, expected, match_level = candidate["item"], candidate["resource_type"], candidate["match_level"]
            data = asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item)
            title = re.sub(r"\s+", " ", str(data.get("title") or "").strip())[:140]
            snippet = re.sub(r"\s+", " ", str(data.get("snippet") or data.get("content") or "").strip())[:360]
            url = validate_resource_url(str(data.get("url") or ""), expected, title, snippet)
            if not url:
                diagnostics["filtered"]["invalid_url_or_type"] += 1
                continue
            diagnostics["url_valid_count"] += 1
            title_key = title.lower()
            identifier = str(data.get("doi") or "").lower().strip()
            if not identifier:
                arxiv = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:)([0-9.]+(?:v\d+)?)", url.lower())
                identifier = f"arxiv:{arxiv.group(1)}" if arxiv else ""
            if not title or url in seen_urls or title_key in seen_titles or (identifier and identifier in seen_identifiers):
                diagnostics["filtered"]["duplicate"] += 1
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            if identifier:
                seen_identifiers.add(identifier)
            source = urlparse(url).netloc.lower().removeprefix("www.")
            trust = self._trust_level(source)
            diagnostics["relevance_candidate_count"] += 1
            text = f"{title} {snippet}".lower()
            score, matched = score_relevance(title, snippet, context, expected, match_level, trust)
            if expected == "paper":
                paper_core = ("call stack", "stack frame", "activation record", "return address", "runtime stack", "function recursion", "recursive function")
                core_hits = sum(term in text for term in paper_core)
                if core_hits == 0 and len(matched) < 2:
                    diagnostics["filtered"]["paper_topic_mismatch"] += 1
                    continue
            feedback = (feedback_by_url or {}).get(resource_feedback_key(url))
            if feedback == "helpful":
                score += 0.1
            elif feedback == "not_relevant":
                score -= 0.14
            elif feedback in {"too_hard", "too_easy"}:
                score -= 0.04
            primary_topic_hit = context["primary_topic"].lower() in text if context.get("primary_topic") else False
            if score < 0.25 or (not matched and match_level == "exact_topic" and not primary_topic_hit):
                diagnostics["filtered"]["low_relevance"] += 1
                continue
            diagnostics["relevant_count"] += 1
            platform = classify_platform(url)
            relation = {"exact_topic": "精确对应当前知识点", "chapter_level": "对应相关章节", "course_level": "课程级拓展", "expanded_research": "拓展论文"}[match_level]
            reason_parts: list[str] = [f"{relation}：覆盖「{context['primary_topic']}」"]
            if matched:
                reason_parts.append(f"及「{'、'.join(matched[:2])}」")
            # ── 画像驱动：认知风格匹配说明 ──
            cog_style = context.get("cognitive_style", {})
            if isinstance(cog_style, dict) and expected in cog_style and cog_style[expected] > 0:
                reason_parts.append("契合你的学习风格偏好")
            # ── 画像驱动：薄弱点命中 ──
            weak_mastery_map = context.get("weak_mastery_map", {})
            hit_weak = [wname for wname in weak_mastery_map if wname.lower() in text]
            if hit_weak:
                reason_parts.append(f"针对你的薄弱点「{'、'.join(hit_weak[:2])}」")
            # ── 画像驱动：内容偏好说明 ──
            if "example_first" in context["preferences"]:
                reason_parts.append("按先看例题偏好补充了示例导向搜索")
            if "definition_first" in context["preferences"]:
                reason_parts.append("按概念优先偏好强化了定义与原理关键词")
            if "step_by_step" in context["preferences"]:
                reason_parts.append("按分步讲解偏好匹配了教程类资源")
            # ── 画像驱动：水平匹配说明 ──
            if context["level"] == "beginner":
                reason_parts.append("匹配当前入门阶段")
            # ── 画像驱动：资源类型偏好说明 ──
            res_prefs = context.get("resource_preferences", [])
            if expected == "video" and any("视频" in str(item) for item in res_prefs):
                reason_parts.append("匹配你的视频资源偏好")
            if expected in ("document", "article") and any("文档" in str(item) or "讲义" in str(item) for item in res_prefs):
                reason_parts.append("匹配你的文档阅读偏好")
            reason = "，".join(reason_parts)
            resources.append({
                "title": title, "url": url, "source": source, "resource_type": expected,
                "platform": platform, "snippet": snippet, "reason": reason + "。",
                "relevance_score": round(score, 2), "language": language or "zh-CN",
                "trust_level": trust, "match_level": match_level, "quality_status": "passed",
                "feedback": feedback,
            })
        return diversify_results(resources)

    @staticmethod
    def _prefer_domestic_videos(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        videos = [item for item in resources if item.get("resource_type") == "video"]
        domestic = [item for item in videos if item.get("platform") in _DOMESTIC_VIDEO_PLATFORMS]
        if domestic:
            domestic_urls = {item["url"] for item in domestic}
            return [item for item in resources if item.get("resource_type") != "video" or item["url"] in domestic_urls]
        for item in videos:
            item["access_region"] = "overseas"
            item["access_note"] = "部分地区可能无法访问"
            item["reason"] = f"{item.get('reason', '')}；部分地区可能无法访问"
        return resources

    @staticmethod
    def _cache_key(context: dict[str, Any], requested: list[str], language: str, scope_key: str = "") -> str:
        public_key = "|".join((
            str(context.get("primary_topic") or "").strip().lower(),
            str(context.get("course_name") or "").strip().lower(),
            ",".join(requested),
            language or "zh-CN",
            settings.search_strategy,
            scope_key,
        ))
        return sha256(public_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, status: str, **counts: int | bool) -> None:
        if callback:
            callback({"event": "search_progress", "stage": stage, "status": status, **counts})

    def _preview_rank(
        self,
        candidates: list[dict[str, Any]],
        context: dict[str, Any],
        language: str,
        feedback_by_url: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        return self._rank(
            candidates,
            context,
            language,
            {"filtered": Counter(), "url_valid_count": 0, "relevance_candidate_count": 0, "relevant_count": 0},
            feedback_by_url,
        )

    @staticmethod
    def _enough(ranked: list[dict[str, Any]], requested: list[str]) -> bool:
        if len(requested) == 1:
            return len(ranked) >= settings.search_min_results_single_type
        types = {item["resource_type"] for item in ranked}
        return len(ranked) >= settings.search_min_results_all and len(types) >= settings.search_min_types_all

    @staticmethod
    def _paper_fallbacks(context: dict[str, Any], max_calls: int) -> tuple[list[tuple[Any, str]], int]:
        query = " ".join(context.get("english_keywords") or []) or str(context.get("primary_topic") or "")
        results: list[tuple[Any, str]] = []
        calls = 0
        for search in (search_crossref, search_arxiv):
            if calls >= max_calls:
                break
            calls += 1
            try:
                results.extend((item, "expanded_research") for item in search(query, max_results=5, timeout=settings.search_provider_timeout_seconds).results)
            except SearchError:
                continue
        return results, calls

    def _search_layers(
        self,
        *,
        resource_type: str,
        layers: list[tuple[str, str]],
        candidates: list[dict[str, Any]],
        queries: list[str],
        context: dict[str, Any],
        language: str,
        diagnostics: dict[str, Any],
        warnings: list[str],
        feedback_by_url: dict[str, str] | None,
        target_count: int,
        provider_call_limit: int,
        future_type_call_reserve: int,
        progress_callback: ProgressCallback | None,
        cancel_event: Event | None,
    ) -> None:
        """Run one preferred query, then overlap bounded fallbacks.

        The provider API is synchronous, so the executor is intentionally
        request-scoped. Provider calls have a hard wait budget and are
        cancelled as soon as the quality threshold is met.
        """
        if not layers:
            return
        started = time.monotonic()
        configured_deadline = diagnostics.get("_deadline")
        total_budget = max(0.1, float(configured_deadline - started)) if configured_deadline else settings.search_total_timeout_single_seconds
        hard_timeout = max(0.1, settings.search_provider_hard_timeout_seconds)
        grace = max(0.0, settings.search_primary_grace_seconds)
        max_workers = max(1, settings.search_max_concurrent_providers)
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="edu-search")
        pending: dict[Any, tuple[str, str]] = {}
        next_index = 0

        def submit(index: int) -> None:
            nonlocal next_index
            query, match_level = layers[index]
            if diagnostics["provider_calls"] >= provider_call_limit - future_type_call_reserve:
                return
            diagnostics["provider_calls"] += 1
            diagnostics["provider_calls_by_type"][resource_type] += 1
            queries.append(query)
            pending[executor.submit(_ai_ctx_wrap(self._client.search), query, settings.search_max_results_single_type)] = (query, match_level)
            next_index = max(next_index, index + 1)

        def add_response(query: str, match_level: str, response: Any) -> None:
            items = list(getattr(response, "results", []) or [])
            diagnostics["queries"].append({"query": query, "resource_type": resource_type, "match_level": match_level, "raw_count": len(items)})
            diagnostics["raw_count"] += len(items)
            candidates.extend({"item": item, "resource_type": resource_type, "match_level": match_level} for item in items)

        try:
            # Fire the first two queries in parallel — double coverage without double wall-clock.
            submit(0)
            if len(layers) > 1:
                submit(1)
            while pending and time.monotonic() - started < total_budget:
                if cancel_event and cancel_event.is_set():
                    raise SearchCancelled()
                ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
                if len([item for item in ranked if item["resource_type"] == resource_type]) >= target_count:
                    break
                wait_for = grace if next_index == 1 and not any(f.done() for f in pending) else min(hard_timeout, max(0.05, total_budget - (time.monotonic() - started)))
                done, _ = wait(tuple(pending), timeout=wait_for, return_when=FIRST_COMPLETED)
                if not done:
                    if next_index < len(layers):
                        self._emit(progress_callback, "fallback_search", "running", fallback_used=True)
                        submit(next_index)
                    continue
                for future in done:
                    query, match_level = pending.pop(future)
                    try:
                        add_response(query, match_level, future.result(timeout=0))
                    except SearchCancelled:
                        raise
                    except Exception as exc:
                        logger.warning("Search layer failed for query=%r type=%r: %s", query, resource_type, exc)
                        warnings.append("外部资源搜索暂不可用，请稍后重试。")
                ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
                if len([item for item in ranked if item["resource_type"] == resource_type]) >= target_count:
                    break
                # Both preferred layers are already in flight.  Wait for the
                # outstanding result before spending another fallback call;
                # it may satisfy the target on its own.
                if pending:
                    continue
                if next_index < len(layers):
                    self._emit(progress_callback, "fallback_search", "running", fallback_used=True)
                    submit(next_index)
        finally:
            for future in pending:
                future.cancel()
            # ponytail: synchronous providers cannot be force-killed; their own
            # HTTP timeout is the cleanup boundary, while the request returns now.
            executor.shutdown(wait=False, cancel_futures=True)

    def recommend(
        self,
        *,
        session_id: str,
        section_id: str,
        section_title: str,
        knowledge_points: list[Any] | None = None,
        language: str = "zh-CN",
        resource_types: list[str] | None = None,
        profile: dict[str, Any] | None = None,
        weak_points: list[Any] | None = None,
        feedback_by_url: dict[str, str] | None = None,
        course_name: str = "",
        collect_diagnostics: bool = False,
        progress_callback: ProgressCallback | None = None,
        refresh: bool = False,
        cancel_event: Event | None = None,
        cache_scope: str = "",
    ) -> dict[str, Any]:
        requested = [kind for kind in RESOURCE_TYPES if kind in {str(item).lower() for item in resource_types or RESOURCE_TYPES}]
        points = self._point_names(knowledge_points)
        weak = self._point_names(weak_points)
        context = normalize_search_context(course_name=course_name, section_title=section_title, knowledge_points=points, weak_points=weak, learner_profile=profile)
        candidates: list[dict[str, Any]] = []
        queries: list[str] = []
        warnings: list[str] = []
        total_budget = settings.search_total_timeout_all_seconds if len(requested) > 1 else settings.search_total_timeout_single_seconds
        multi_type = len(requested) > 1
        per_type_calls = settings.search_min_provider_calls_per_type if multi_type else 0
        fallback_reserve = settings.search_fallback_provider_call_reserve if multi_type and "paper" in requested else 0
        provider_call_limit = max(settings.search_max_provider_calls, len(requested) * per_type_calls + fallback_reserve)
        primary_call_limit = provider_call_limit - fallback_reserve
        diagnostics: dict[str, Any] = {"queries": [], "raw_count": 0, "url_valid_count": 0, "relevance_candidate_count": 0, "relevant_count": 0, "final_count": 0, "filtered": Counter(), "provider_calls": 0, "provider_call_limit": provider_call_limit, "provider_calls_by_type": Counter(), "cache": "miss", "_deadline": time.monotonic() + total_budget}
        target_count = 1 if len(requested) > 1 else settings.search_min_results_single_type
        cache_key = self._cache_key(context, requested, language, cache_scope or f"{session_id}|{section_id}")
        cache_state, cached = SearchCascade.get(cache_key) if self._use_cache else ("miss", None)
        stale = cached if cache_state == "stale" else None
        self._emit(progress_callback, "topic_analysis", "completed")
        if cached and cache_state == "fresh" and not refresh:
            candidates, queries = cached.candidates, cached.queries
            diagnostics["cache"] = "fresh"
            search_requested: list[str] = []
            self._emit(progress_callback, "cache", "completed")
        else:
            search_requested = requested
            self._emit(progress_callback, "primary_search", "running")

        try:
            for idx, resource_type in enumerate(search_requested):
                if cancel_event and cancel_event.is_set():
                    raise SearchCancelled()
                # Small stagger between types reduces search-engine rate-limiting.
                if idx > 0 and len(search_requested) > 1:
                    time.sleep(0.6)
                self._search_layers(
                    resource_type=resource_type,
                    layers=self._query_layers(context, resource_type, language),
                    candidates=candidates, queries=queries, context=context, language=language,
                    diagnostics=diagnostics, warnings=warnings, feedback_by_url=feedback_by_url,
                    target_count=target_count, provider_call_limit=primary_call_limit,
                    future_type_call_reserve=(len(search_requested) - idx - 1) * per_type_calls,
                    progress_callback=progress_callback, cancel_event=cancel_event,
                )
                ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
                if self._use_cache and resource_type == "paper" and len([item for item in ranked if item["resource_type"] == "paper"]) < target_count:
                    self._emit(progress_callback, "fallback_search", "running", fallback_used=True)
                    fallback_items, fallback_calls = self._paper_fallbacks(context, max(0, provider_call_limit - diagnostics["provider_calls"]))
                    diagnostics["provider_calls"] += fallback_calls
                    diagnostics["provider_calls_by_type"]["paper_fallback"] += fallback_calls
                    for item, paper_match in fallback_items:
                        if cancel_event and cancel_event.is_set():
                            break
                        diagnostics["raw_count"] += 1
                        candidates.append({"item": item, "resource_type": "paper", "match_level": paper_match})
        except SearchCancelled:
            diagnostics["cancelled"] = True
            return {"query": queries, "resources": [], "status": "cancelled", "warnings": ["搜索已取消。"], "diagnostics": {**diagnostics, "filtered": dict(diagnostics["filtered"])} if collect_diagnostics else None}

        live_ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
        if stale and not self._enough(live_ranked, requested):
            def candidate_url(candidate: dict[str, Any]) -> str:
                item = candidate.get("item")
                if hasattr(item, "url"):
                    return str(item.url)
                return str(item.get("url") or "") if isinstance(item, dict) else ""
            existing_urls = {candidate_url(item) for item in candidates}
            candidates.extend(item for item in stale.candidates if candidate_url(item) not in existing_urls)
            if not queries:
                queries = stale.queries
            diagnostics["cache"] = "stale"
            warnings.append("\u5b9e\u65f6\u641c\u7d22\u6682\u65f6\u4e0d\u7a33\u5b9a\uff0c\u6b63\u5728\u5c55\u793a\u8fd1\u671f\u6709\u6548\u7ed3\u679c\u3002")
            self._emit(progress_callback, "stale_cache", "completed", stale=True)
        elif candidates and diagnostics["cache"] == "miss" and self._use_cache:
            SearchCascade.put(cache_key, candidates, queries)

        self._emit(progress_callback, "quality_filter", "running")
        ranked = self._rank(candidates, context, language, diagnostics, feedback_by_url)
        self._emit(progress_callback, "personalized_ranking", "running")
        if len(requested) == 1:
            resources = ranked[:settings.search_max_results_single_type]
        else:
            resources = []
            selected_urls: set[str] = set()
            for resource_type in requested:
                item = next((candidate for candidate in ranked if candidate["resource_type"] == resource_type), None)
                if item:
                    resources.append(item)
                    selected_urls.add(item["url"])
            resources.extend(item for item in ranked if item["url"] not in selected_urls)
            resources = resources[:settings.search_max_results_all]
        resources = self._prefer_domestic_videos(resources)
        diagnostics["final_count"] = len(resources)
        if resources:
            status = "completed"
        elif diagnostics["raw_count"] == 0 and warnings:
            status = "search_unavailable"
        elif diagnostics["raw_count"] > 0 and diagnostics["url_valid_count"] == 0:
            status = "invalid_urls"
        elif diagnostics["raw_count"] == 0 and not warnings:
            status = "empty_response"
        elif any(entry["match_level"] in {"course_level", "expanded_research"} for entry in diagnostics["queries"]):
            status = "expanded_no_results"
            warnings.append("已扩大搜索范围，仍未找到高相关公开资源。")
        else:
            status = "no_high_relevance"
            warnings.append("暂未找到高相关公开资源。")
        # Auto-ingest top results into knowledge base (background, best-effort)
        if resources and not refresh:
            self._auto_ingest(resources[:3])

        result = {
            "query": queries,
            "canonical_query": context["primary_topic"],
            "context": {"topic": context["primary_topic"], "course_name": context["course_name"]},
            "resources": resources,
            "status": status,
            "warnings": list(dict.fromkeys(warnings)),
        }
        self._emit(progress_callback, "completed", "completed", candidate_count=diagnostics["raw_count"], result_count=len(resources), source_count=len({item["source"] for item in resources}))
        if collect_diagnostics:
            result["diagnostics"] = {key: value for key, value in {**diagnostics, "filtered": dict(diagnostics["filtered"]), "provider_calls_by_type": dict(diagnostics["provider_calls_by_type"]), "cache_stats": SearchCascade.stats()}.items() if not key.startswith("_")}
        return result

    @staticmethod
    def _auto_ingest(resources: list[dict[str, Any]]) -> None:
        """Silently ingest top search results into the RAG knowledge base."""
        import threading

        def _ingest() -> None:
            from app.services.web_ingest import ingest_url_sync
            for r in resources:
                url = str(r.get("url", "")).strip()
                if not url:
                    continue
                try:
                    result = ingest_url_sync(url)
                    if result.ok:
                        logger.info("Auto-ingested: %s (%d chunks)", url, result.chunks)
                except Exception:
                    pass  # Best-effort, never blocks the user

        t = threading.Thread(target=_ingest, daemon=True, name="rag-auto-ingest")
        t.start()
