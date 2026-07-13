"""Real, transient external recommendations for one learning section."""

from __future__ import annotations

import copy
import logging
import re
import time
from hashlib import sha256
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.config import settings
from app.services.search_client import SearchError, get_search_client, search_arxiv, search_crossref

logger = logging.getLogger(__name__)


RESOURCE_TYPES = ("article", "video", "course", "document", "paper")
_ACTION_TERMS = ("用纸笔", "手动模拟", "画出", "一个简单", "每一层", "请", "完成")
_CONCEPTS = (
    ("递归", "recursion"), ("调用栈", "call stack"), ("栈帧", "stack frame"),
    ("局部变量", "local variables"), ("返回地址", "return address"),
    ("阶乘", "factorial"), ("斐波那契", "fibonacci"),
)
_PAPER_HOSTS = ("arxiv.org", "semanticscholar.org", "dl.acm.org", "ieeexplore.ieee.org", "dblp.org", "doi.org", "cnki", "wanfang")
_COURSE_HOSTS = ("icourse163.org", "xuetangx.com", "smartedu.cn", "imooc.com", "coursera.org", "edx.org", "ocw.mit.edu")

ProgressCallback = Callable[[dict[str, Any]], None]


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

    @classmethod
    def get(cls, key: str) -> tuple[str, _CachedCandidates | None]:
        if not settings.search_cache_enabled:
            return "miss", None
        with cls._lock:
            entry = cls._cache.get(key)
            if not entry:
                return "miss", None
            age = time.time() - entry.created_at
            if age <= settings.search_cache_ttl_seconds:
                cls._cache.move_to_end(key)
                return "fresh", copy.deepcopy(entry)
            if age <= settings.search_stale_cache_seconds:
                return "stale", copy.deepcopy(entry)
            cls._cache.pop(key, None)
        return "miss", None

    @classmethod
    def put(cls, key: str, candidates: list[dict[str, Any]], queries: list[str]) -> None:
        if not settings.search_cache_enabled or not candidates:
            return
        with cls._lock:
            cls._cache[key] = _CachedCandidates(time.time(), copy.deepcopy(candidates), list(queries))
            cls._cache.move_to_end(key)
            while len(cls._cache) > settings.search_cache_max_entries:
                cls._cache.popitem(last=False)

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._cache.clear()


def normalize_url(value: str) -> str:
    """Keep only safe, stable http(s) resource URLs."""
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_")])
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", query, ""))


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
    if isinstance(direct, dict):
        return direct
    nested = ((profile.get("preferences") or {}).get("profile_v2") or {}).get("subject_context")
    return nested if isinstance(nested, dict) else {}


def _profile_mastery(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    profile = profile or {}
    direct = profile.get("knowledge_mastery")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    nested = ((profile.get("preferences") or {}).get("profile_v2") or {}).get("knowledge_mastery")
    return [item for item in nested if isinstance(item, dict)] if isinstance(nested, list) else []


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
    # Start with concept-matching keywords, then enrich from section title + knowledge points
    keywords = list(dict.fromkeys(cn for cn, _ in pairs))
    title_words = re.split(r"[，,。；;\s]+", str(section_title or ""))
    for word in title_words:
        cleaned = word.strip()
        if cleaned and len(cleaned) >= 2 and cleaned not in keywords and cleaned not in ("基本性质", "核心概念", "学习主题"):
            keywords.append(cleaned)
    for kp in knowledge_points or []:
        kp_name = str(kp).strip()
        if kp_name and len(kp_name) >= 2:
            keywords.append(kp_name)
    keywords = list(dict.fromkeys(keywords))
    # Determine primary topic from concept matches or section title
    if pairs:
        primary_topic = pairs[0][0]
    else:
        simplified = str(section_title or lecture_title or chapter_title or "学习主题")
        for term in _ACTION_TERMS:
            simplified = simplified.replace(term, "")
        primary_topic = re.sub(r"[，,。；;]+.*$", "", simplified).strip(" ：:，,。；;") or "学习主题"
    english_keywords = list(dict.fromkeys(en for _, en in pairs))
    for term in ("\u6570\u7ec4", "\u94fe\u8868", "\u6811", "\u6808", "\u961f\u5217", "\u9012\u5f52"):
        if term in text and term not in keywords:
            keywords.append(term)
    if primary_topic == "递归调用栈":
        for cn, en in _CONCEPTS:
            if cn in text and cn not in keywords:
                keywords.append(cn)
            if cn in text and en not in english_keywords:
                english_keywords.append(en)
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
    preferences = profile_context.get("content_preferences") if isinstance(profile_context.get("content_preferences"), list) else []
    resource_preferences = profile_context.get("resource_preferences") if isinstance(profile_context.get("resource_preferences"), list) else []
    return {
        "course_name": course,
        "primary_topic": primary_topic,
        "keywords": keywords[:7],
        "english_keywords": english_keywords[:7],
        "preferences": preferences,
        "resource_preferences": resource_preferences,
        "level": "beginner" if beginner else "general",
        "relevant_weak_points": relevant_weak[:4],
    }


def score_relevance(title: str, snippet: str, context: dict[str, Any], resource_type: str, match_level: str, trust_level: str) -> tuple[float, list[str]]:
    text = f"{title} {snippet}".lower()
    matched = [term for term in context["keywords"] if term.lower() in text]
    matched += [term for term in context["english_keywords"] if term.lower() in text]
    matched = list(dict.fromkeys(matched))
    score = 0.26 + min(0.50, len(matched) * 0.10)
    if matched:
        score += 0.1
    if context["primary_topic"].lower() in text:
        score += 0.2
    if context["course_name"] and context["course_name"].lower() in text:
        score += 0.12
    # For video results, course name match alone is a strong signal
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
    if "example_first" in context["preferences"] and any(token in text for token in ("示例", "例题", "example", "walkthrough")):
        score += 0.05
    if context["level"] == "beginner" and any(token in text for token in ("入门", "基础", "beginner", "basics")):
        score += 0.05
    if resource_type == "video" and any("视频" in str(item) for item in context["resource_preferences"]):
        score += 0.06
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
        self._client = client or get_search_client("duckduckgo")
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
        course = context["course_name"] or "数据结构"
        topic = context["primary_topic"]
        keywords = " ".join(context["keywords"][:3]) or topic
        english = " ".join(context["english_keywords"][:3]) or "recursion call stack"
        cn_hints = []
        en_hints = []
        if "example_first" in context["preferences"]:
            cn_hints.extend(["示例", "例题", "分步讲解"]); en_hints.extend(["example", "walkthrough"])
        if context["level"] == "beginner":
            cn_hints.extend(["入门", "基础"]); en_hints.extend(["beginner", "basics"])
        hint = " ".join(cn_hints)
        english_hint = " ".join(en_hints)
        if resource_type == "article":
            return [(f"{course} {keywords} 教程 {hint}".strip(), "exact_topic"), (f"{topic} 示例 {hint}".strip(), "exact_topic"), (f"{english} tutorial {english_hint}".strip(), "chapter_level"), (f"{course} {topic} 教学", "course_level")]
        if resource_type == "video":
            return [
                (f"{course} {topic} 视频".strip(), "exact_topic"),
                (f"{course} {keywords} 教学视频".strip(), "exact_topic"),
                (f"{topic} 视频教程 bilibili".strip(), "chapter_level"),
                (f"{course} {topic} 视频教程".strip(), "chapter_level"),
                (f"{english} calculus video tutorial".strip(), "course_level"),
            ]
        if resource_type == "course":
            return [(f"{course} {topic} {hint}".strip(), "exact_topic"), (f"{course} {topic} 课程".strip(), "chapter_level"), (f"{course} {topic} mooc".strip(), "chapter_level"), (f"{course} 在线课程".strip(), "course_level")]
        if resource_type == "document":
            return [(f"{topic} {hint}".strip(), "exact_topic"), (f"{topic} 课件".strip(), "exact_topic"), (f"{course} {topic} 讲义".strip(), "chapter_level"), (f"{english} lecture notes {english_hint}".strip(), "course_level")]
        expanded = "tail recursion" if "recursion" in english else english
        return [(f"{english} paper".strip(), "exact_topic"), (f"{english} research".strip(), "exact_topic"), (f"{expanded} optimization paper".strip(), "expanded_research"), (f"{english} design paper".strip(), "expanded_research")]

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
            if not title or url in seen_urls or title_key in seen_titles:
                diagnostics["filtered"]["duplicate"] += 1
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            source = urlparse(url).netloc.lower().removeprefix("www.")
            trust = self._trust_level(source)
            diagnostics["relevance_candidate_count"] += 1
            score, matched = score_relevance(title, snippet, context, expected, match_level, trust)
            feedback = (feedback_by_url or {}).get(resource_feedback_key(url))
            if feedback == "helpful":
                score += 0.1
            elif feedback == "not_relevant":
                score -= 0.14
            elif feedback in {"too_hard", "too_easy"}:
                score -= 0.04
            if score < 0.25 or (not matched and match_level == "exact_topic"):
                diagnostics["filtered"]["low_relevance"] += 1
                continue
            diagnostics["relevant_count"] += 1
            platform = classify_platform(url)
            relation = {"exact_topic": "精确对应当前知识点", "chapter_level": "对应相关章节", "course_level": "课程级拓展", "expanded_research": "拓展论文"}[match_level]
            reason = f"{relation}：覆盖「{context['primary_topic']}」"
            if matched:
                reason += f"及「{'、'.join(matched[:2])}」"
            if "example_first" in context["preferences"]:
                reason += "，按先看例题偏好补充了示例导向搜索"
            if context["level"] == "beginner":
                reason += "，按当前基础阶段加入了入门与基础查询词"
            if expected == "video" and any("视频" in str(item) for item in context["resource_preferences"]):
                reason += "，匹配视频资源偏好"
            related_weak = [point for point in context["relevant_weak_points"] if point.lower() in {term.lower() for term in matched}]
            if related_weak:
                reason += f"，命中当前小节薄弱点「{'、'.join(related_weak[:2])}」"
            resources.append({
                "title": title, "url": url, "source": source, "resource_type": expected,
                "platform": platform, "snippet": snippet, "reason": reason + "。",
                "relevance_score": round(score, 2), "language": language or "zh-CN",
                "trust_level": trust, "match_level": match_level,
                "feedback": feedback,
            })
        return diversify_results(resources)

    @staticmethod
    def _cache_key(context: dict[str, Any], requested: list[str], language: str) -> str:
        public_key = "|".join((
            str(context.get("primary_topic") or "").strip().lower(),
            str(context.get("course_name") or "").strip().lower(),
            ",".join(requested),
            language or "zh-CN",
            settings.search_strategy,
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
    def _paper_fallbacks(context: dict[str, Any]) -> list[tuple[Any, str]]:
        query = " ".join(context.get("english_keywords") or []) or str(context.get("primary_topic") or "")
        results: list[tuple[Any, str]] = []
        for search in (search_crossref, search_arxiv):
            try:
                results.extend((item, "expanded_research") for item in search(query, max_results=5, timeout=settings.search_provider_timeout_seconds).results)
            except SearchError:
                continue
        return results

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
    ) -> dict[str, Any]:
        del session_id, section_id  # External results are transient and never persisted.
        requested = [kind for kind in RESOURCE_TYPES if kind in {str(item).lower() for item in resource_types or RESOURCE_TYPES}]
        points = self._point_names(knowledge_points)
        weak = self._point_names(weak_points)
        context = normalize_search_context(course_name=course_name, section_title=section_title, knowledge_points=points, weak_points=weak, learner_profile=profile)
        candidates: list[dict[str, Any]] = []
        queries: list[str] = []
        warnings: list[str] = []
        diagnostics: dict[str, Any] = {"queries": [], "raw_count": 0, "url_valid_count": 0, "relevance_candidate_count": 0, "relevant_count": 0, "final_count": 0, "filtered": Counter(), "provider_calls": 0, "cache": "miss"}
        target_count = 1 if len(requested) > 1 else settings.search_min_results_single_type
        cache_key = self._cache_key(context, requested, language)
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

        for resource_type in search_requested:
            for layer_index, (query, match_level) in enumerate(self._query_layers(context, resource_type, language)):
                if diagnostics["provider_calls"] >= settings.search_max_provider_calls:
                    break
                if layer_index:
                    self._emit(progress_callback, "fallback_search", "running", fallback_used=True)
                queries.append(query)
                diagnostics["provider_calls"] += 1
                try:
                    response = self._client.search(query, max_results=settings.search_max_results_single_type)
                    items = list(response.results)
                    diagnostics["queries"].append({"query": query, "resource_type": resource_type, "match_level": match_level, "raw_count": len(items)})
                    diagnostics["raw_count"] += len(items)
                    candidates.extend({"item": item, "resource_type": resource_type, "match_level": match_level} for item in items)
                except SearchError:
                    warnings.append("外部资源搜索暂不可用，请稍后重试。")
                except Exception:
                    warnings.append("外部资源搜索暂不可用，请稍后重试。")
                ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
                if self._use_cache and resource_type == "paper" and layer_index == 0 and len([item for item in ranked if item["resource_type"] == "paper"]) < target_count:
                    self._emit(progress_callback, "fallback_search", "running", fallback_used=True)
                    for item, paper_match in self._paper_fallbacks(context):
                        if diagnostics["provider_calls"] >= settings.search_max_provider_calls:
                            break
                        diagnostics["provider_calls"] += 1
                        diagnostics["raw_count"] += 1
                        candidates.append({"item": item, "resource_type": "paper", "match_level": paper_match})
                    ranked = self._rank(candidates, context, language, {**diagnostics, "filtered": Counter()}, feedback_by_url)
                if len([item for item in ranked if item["resource_type"] == resource_type]) >= target_count:
                    break

        if not candidates and stale:
            candidates, queries = stale.candidates, stale.queries
            diagnostics["cache"] = "stale"
            warnings.append("\u5b9e\u65f6\u641c\u7d22\u6682\u65f6\u4e0d\u7a33\u5b9a\uff0c\u6b63\u5728\u5c55\u793a\u8fd1\u671f\u6709\u6548\u7ed3\u679c\u3002")
            self._emit(progress_callback, "cache", "completed", stale=True)
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
        diagnostics["final_count"] = len(resources)
        if resources:
            status = "completed"
        elif diagnostics["raw_count"] == 0 and warnings:
            status = "search_unavailable"
        elif any(entry["match_level"] in {"course_level", "expanded_research"} for entry in diagnostics["queries"]):
            status = "expanded_no_results"
            warnings.append("已扩大搜索范围，仍未找到高相关公开资源。")
        else:
            status = "no_high_relevance"
            warnings.append("暂未找到高相关公开资源。")
        # Auto-ingest top results into knowledge base (background, best-effort)
        if resources and not refresh:
            self._auto_ingest(resources[:3])

        result = {"query": queries, "resources": resources, "status": status, "warnings": list(dict.fromkeys(warnings))}
        self._emit(progress_callback, "completed", "completed", candidate_count=diagnostics["raw_count"], result_count=len(resources), source_count=len({item["source"] for item in resources}))
        if collect_diagnostics:
            result["diagnostics"] = {**diagnostics, "filtered": dict(diagnostics["filtered"])}
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
