"""Real external resource recommendations for one learning section."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.services.search_client import SearchError, get_search_client


class SectionResourceRecommendationService:
    """Adapt real DuckDuckGo results for the lecture workspace without persistence."""

    def __init__(self, client: Any | None = None) -> None:
        # Production deliberately bypasses the configurable mock provider.
        self._client = client or get_search_client("duckduckgo")

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
    ) -> dict[str, Any]:
        del session_id, section_id, profile  # Context is used to shape the caller's query, never persisted.
        points = self._point_names(knowledge_points)
        weak_names = self._point_names(weak_points)
        query_points = list(dict.fromkeys([*points, *weak_names]))
        queries = self._queries(section_title, query_points, resource_types)
        warnings: list[str] = []
        raw_items: list[Any] = []

        for query in queries:
            try:
                raw_items.extend(self._client.search(query, max_results=5).results)
            except SearchError:
                warnings.append("外部资源检索暂不可用，请稍后重试。")
            except Exception:
                warnings.append("外部资源检索暂不可用，请稍后重试。")

        if not raw_items:
            return {
                "query": queries,
                "resources": [],
                "status": "search_unavailable" if warnings else "completed",
                "warnings": list(dict.fromkeys(warnings or ["未找到可用的外部学习资源。"])),
            }

        resources = self._deduplicate_and_rank(raw_items, section_title, query_points, weak_points, language)
        return {
            "query": queries,
            "resources": resources[:5],
            "status": "completed",
            "warnings": list(dict.fromkeys(warnings)),
        }

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
    def _queries(title: str, points: list[str], resource_types: list[str] | None) -> list[str]:
        topic = " ".join([title, *points[:4]]).strip() or "学习资料"
        queries = [f"{topic} 教程 讲解", f"{topic} 官方文档 大学课程"]
        requested = {str(kind).lower() for kind in resource_types or []}
        if requested & {"video", "course", "paper", "document"}:
            labels = {"video": "视频", "course": "公开课", "paper": "论文", "document": "文档"}
            suffix = " ".join(labels[kind] for kind in ("video", "course", "paper", "document") if kind in requested)
            queries.append(f"{topic} {suffix}")
        return queries[:3]

    @staticmethod
    def _normal_url(value: str) -> str:
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_")])
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", query, ""))

    def _deduplicate_and_rank(
        self,
        items: list[Any],
        section_title: str,
        points: list[str],
        weak_points: list[Any] | None,
        language: str,
    ) -> list[dict[str, Any]]:
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        resources: list[dict[str, Any]] = []
        terms = [section_title, *points, *self._point_names(weak_points)]

        for rank, item in enumerate(items):
            data = asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item)
            title = re.sub(r"\s+", " ", str(data.get("title") or "").strip())
            url = self._normal_url(str(data.get("url") or ""))
            title_key = title.lower()
            if not title or not url or url in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            snippet = re.sub(r"\s+", " ", str(data.get("snippet") or "").strip())[:360]
            source = urlparse(url).netloc.removeprefix("www.")
            trust = self._trust_level(source)
            matched = [term for term in terms if term and term.lower() in f"{title} {snippet}".lower()]
            score = min(0.98, 0.50 + min(0.24, len(matched) * 0.08) + {"official": 0.16, "educational": 0.10, "general": 0.04}[trust] - min(0.12, rank * 0.01))
            reason = f"匹配当前小节“{section_title}”"
            if matched:
                reason += f"及知识点“{'、'.join(matched[:2])}”"
            resources.append({
                "title": title,
                "url": url,
                "source": source,
                "resource_type": self._resource_type(url, title),
                "snippet": snippet,
                "reason": reason + "。",
                "relevance_score": round(score, 2),
                "language": language or "zh-CN",
                "trust_level": trust,
            })
        return sorted(resources, key=lambda resource: resource["relevance_score"], reverse=True)

    @staticmethod
    def _resource_type(url: str, title: str) -> str:
        text = f"{url} {title}".lower()
        if any(host in text for host in ("youtube.com", "youtu.be", "bilibili.com", "vimeo.com")):
            return "video"
        if "arxiv.org" in text or ".pdf" in text or "paper" in text:
            return "paper"
        if any(host in text for host in ("ocw.", "coursera.", "edx.", "mooc", "course")):
            return "course"
        if any(host in text for host in ("docs.", "developer.", "readthedocs", "w3.org")):
            return "document"
        return "article"

    @staticmethod
    def _trust_level(source: str) -> str:
        source = source.lower()
        if source.endswith(".gov") or source.endswith(".edu") or any(part in source for part in ("docs.python.org", "developer.mozilla.org", "openai.com", "microsoft.com", "w3.org")):
            return "official"
        if any(part in source for part in ("ocw", "coursera", "edx", "mooc", "mit.edu", "stanford.edu")):
            return "educational"
        return "general"
