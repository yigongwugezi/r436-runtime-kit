"""Web search client abstraction with multiple providers.

Mirrors the pattern of ``llm_client.py``: a factory function returns a
provider-specific implementation of ``BaseSearchClient``.  Agents import
``get_search_client`` and call ``.search(query)`` to fetch web results.

Provides:
- BaseSearchClient: abstract interface
- MockSearchClient: returns deterministic mock results (dev only)
- DuckDuckGoSearchClient: free, no API key required
- TavilySearchClient: paid, RAG-optimised, requires TAVILY_API_KEY
- SearchCache: simple in-memory TTL cache
- get_search_client(): factory function
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Lock
from urllib import error, request
from urllib.parse import urlencode
from xml.etree import ElementTree

from app.config import settings

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class SearchError(Exception):
    """Raised when a search API call fails after all retries are exhausted."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ── Internal data classes (lightweight, no Pydantic overhead) ──────────────


@dataclass
class SearchResultItem:
    """A single search result from any provider."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""
    source: str = ""
    provider: str = ""
    published_at: str = ""
    authors: list[str] = field(default_factory=list)
    doi: str = ""
    raw_rank: int = 0
    access_hint: str = ""


@dataclass
class SearchResponse:
    """Aggregated response from a search provider."""

    query: str
    results: list[SearchResultItem] = field(default_factory=list)
    total_estimated: int = 0
    source: str = ""


# ── Abstract base ──────────────────────────────────────────────────────────


class BaseSearchClient(ABC):
    """Abstract contract for web search providers used by agents."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        """Execute a web search and return structured results.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return.
            **kwargs: Provider-specific overrides (e.g. search_depth for Tavily).

        Returns:
            A SearchResponse with ranked results.

        Raises:
            SearchError: On any failure.
        """
        ...

    def is_available(self) -> bool:
        """Quick health check — returns True if the provider is reachable."""
        return True


# ── Mock client ────────────────────────────────────────────────────────────


class MockSearchClient(BaseSearchClient):
    """Deterministic mock client for development and testing.

    Returns up to 3 fake results so tests are predictable.
    """

    def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        count = min(max_results, 3)
        return SearchResponse(
            query=query,
            results=[
                SearchResultItem(
                    title=f"Mock Result {i + 1} for: {query[:50]}",
                    url=f"https://example.com/result/{i + 1}?q={query[:30].replace(' ', '+')}",
                    snippet=f"This is a mock search result #{i + 1} related to '{query[:80]}'.",
                    content=(
                        f"Full mock content for result #{i + 1}. "
                        f"This simulates web page content retrieved for the query: {query}."
                    ),
                    source="mock",
                )
                for i in range(count)
            ],
            total_estimated=count,
            source="mock",
        )

    def is_available(self) -> bool:
        return True


# ── DDGS client ────────────────────────────────────────────────────────────


class DuckDuckGoSearchClient(BaseSearchClient):
    """Free real search through ``ddgs`` with bounded backend fallback."""

    _BACKENDS = ("auto", "bing", "brave")
    _circuit_lock = Lock()
    _circuits: dict[str, tuple[int, float, bool]] = {}

    def __init__(self, timeout: int = 10, total_timeout: int = 15, proxy: str | None = None) -> None:
        self.timeout = timeout
        self.total_timeout = max(timeout, total_timeout)
        self.proxy = proxy if proxy is not None else self._configured_proxy()

    @staticmethod
    def _configured_proxy() -> str:
        import os

        return (
            settings.search_proxy.strip()
            or os.getenv("HTTP_PROXY", "").strip()
            or os.getenv("HTTPS_PROXY", "").strip()
            or os.getenv("ALL_PROXY", "").strip()
        )

    def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        try:
            from ddgs import DDGS  # type: ignore[import-untyped]
        except ImportError:
            raise SearchError(
                "Real search requires the 'ddgs' package. Install it with: pip install ddgs"
            )

        deadline = time.monotonic() + self.total_timeout
        last_error: Exception | None = None
        for backend in self._BACKENDS:
            if not self._allow_backend(backend):
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw = DDGS(proxy=self.proxy or None, timeout=max(1, int(remaining))).text(
                    query,
                    backend=backend,
                    max_results=max_results,
                )
                if raw:
                    self._record_success(backend)
                    return self._response(query, raw, backend)
            except Exception as exc:
                last_error = exc
                self._record_failure(backend)
                logger.info("DDGS backend %s failed: %s", backend, exc)

        raise SearchError(f"DDGS search failed after real backends: {last_error or 'no results'}", cause=last_error)

    @classmethod
    def _allow_backend(cls, backend: str) -> bool:
        """Skip only a repeatedly failing backend; empty results remain healthy."""
        now = time.monotonic()
        with cls._circuit_lock:
            failures, opened_at, probing = cls._circuits.get(backend, (0, 0.0, False))
            if not opened_at:
                return True
            if now - opened_at < settings.search_circuit_open_seconds:
                return False
            if probing:
                return False
            cls._circuits[backend] = (failures, opened_at, True)
            return True

    @classmethod
    def _record_success(cls, backend: str) -> None:
        with cls._circuit_lock:
            cls._circuits.pop(backend, None)

    @classmethod
    def _record_failure(cls, backend: str) -> None:
        with cls._circuit_lock:
            failures, opened_at, _ = cls._circuits.get(backend, (0, 0.0, False))
            failures += 1
            cls._circuits[backend] = (
                failures,
                time.monotonic() if failures >= settings.search_circuit_failure_threshold else opened_at,
                False,
            )

    @classmethod
    def reset_circuits(cls) -> None:
        with cls._circuit_lock:
            cls._circuits.clear()

    @staticmethod
    def _response(query: str, raw: list[dict[str, object]], backend: str) -> SearchResponse:
        results = [
            SearchResultItem(
                title=str(item.get("title", "")),
                url=str(item.get("href") or item.get("url") or ""),
                snippet=str(item.get("body") or item.get("snippet") or ""),
                content=str(item.get("body") or item.get("snippet") or ""),
                source=f"ddgs:{backend}",
                provider="ddgs",
                raw_rank=index,
            )
            for index, item in enumerate(raw, start=1)
        ]

        return SearchResponse(
            query=query,
            results=results,
            total_estimated=len(results),
            source=f"ddgs:{backend}",
        )

    def is_available(self) -> bool:
        try:
            return bool(self.search("test", max_results=1).results)
        except Exception:
            logger.debug("DDGS availability check failed", exc_info=True)
            return False


# ── Tavily client ─────────────────────────────────────────────────────────


class TavilySearchClient(BaseSearchClient):
    """Tavily search client optimised for AI-agent RAG workflows.

    Uses ``urllib.request`` directly (no external HTTP dependency),
    matching the pattern of ``DeepSeekLLMClient``.

    Requires ``TAVILY_API_KEY`` to be set in ``.env``.
    """

    def __init__(self, api_key: str, timeout: int = 10) -> None:
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        if not self.api_key:
            raise SearchError("TAVILY_API_KEY is not configured.")

        payload: dict[str, object] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": kwargs.get("search_depth", "basic"),
        }

        # Include answer if requested (gives an LLM-friendly summary)
        if kwargs.get("include_answer"):
            payload["include_answer"] = True

        try:
            req = request.Request(
                url=f"{self.base_url}/search",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=self.timeout) as response:  # type: ignore[arg-type]
                body = json.loads(response.read().decode("utf-8"))

        except error.HTTPError as exc:
            status = exc.code if hasattr(exc, "code") else None
            raise SearchError(
                f"Tavily API returned HTTP {status}: {self._read_error_body(exc)}",
                cause=exc,
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise SearchError(
                f"Tavily API is unreachable: {exc}", cause=exc
            ) from exc
        except json.JSONDecodeError as exc:
            raise SearchError(
                f"Failed to parse Tavily response: {exc}", cause=exc
            ) from exc

        results = [
            SearchResultItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", "")[:300],
                content=item.get("content", ""),
                source="tavily",
            )
            for item in body.get("results", [])
        ]

        # Optionally prepend the AI-generated answer as a synthetic result
        answer = body.get("answer", "")
        if answer:
            results.insert(
                0,
                SearchResultItem(
                    title="AI Summary (Tavily)",
                    url="",
                    snippet=answer[:300],
                    content=answer,
                    source="tavily",
                ),
            )

        return SearchResponse(
            query=query,
            results=results,
            total_estimated=body.get("total_results", len(results)),
            source="tavily",
        )

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self.search("ping", max_results=1)
            return True
        except Exception:
            logger.debug("Tavily availability check failed")
            return False

    @staticmethod
    def _read_error_body(exc: error.HTTPError) -> str:
        try:
            return exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            return str(exc)


def search_crossref(query: str, max_results: int = 5, timeout: int = 5) -> SearchResponse:
    """Query Crossref's public metadata API without a key or PDF download."""
    try:
        url = f"https://api.crossref.org/works?{urlencode({'query': query, 'rows': max_results})}"
        with request.urlopen(url, timeout=timeout) as response:
            items = json.loads(response.read().decode("utf-8")).get("message", {}).get("items", [])
    except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SearchError("Crossref public search is unavailable", cause=exc) from exc
    results = []
    for rank, item in enumerate(items, start=1):
        doi = str(item.get("DOI") or "")
        title = " ".join(item.get("title") or [])
        authors = [" ".join(filter(None, (author.get("given"), author.get("family")))) for author in item.get("author") or []]
        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = (published.get("date-parts") or [[]])[0]
        results.append(SearchResultItem(
            title=title,
            url=f"https://doi.org/{doi}" if doi else str(item.get("URL") or ""),
            snippet=str(item.get("abstract") or "")[:360],
            source="crossref",
            provider="crossref",
            published_at="-".join(str(part) for part in date_parts),
            authors=[author for author in authors if author],
            doi=doi,
            raw_rank=rank,
            access_hint="metadata",
        ))
    return SearchResponse(query=query, results=results, total_estimated=len(results), source="crossref")


def search_arxiv(query: str, max_results: int = 5, timeout: int = 5) -> SearchResponse:
    """Query arXiv's public Atom API without a key or PDF download."""
    try:
        url = f"https://export.arxiv.org/api/query?{urlencode({'search_query': f'all:{query}', 'start': 0, 'max_results': max_results})}"
        with request.urlopen(url, timeout=timeout) as response:
            root = ElementTree.fromstring(response.read())
    except (error.URLError, error.HTTPError, TimeoutError, OSError, ElementTree.ParseError) as exc:
        raise SearchError("arXiv public search is unavailable", cause=exc) from exc
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for rank, entry in enumerate(root.findall("atom:entry", ns), start=1):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns)).split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns)).split())
        url = entry.findtext("atom:id", default="", namespaces=ns)
        results.append(SearchResultItem(
            title=title,
            url=url,
            snippet=summary[:360],
            source="arxiv",
            provider="arxiv",
            published_at=entry.findtext("atom:published", default="", namespaces=ns),
            authors=[author.findtext("atom:name", default="", namespaces=ns) for author in entry.findall("atom:author", ns)],
            raw_rank=rank,
            access_hint="abstract",
        ))
    return SearchResponse(query=query, results=results, total_estimated=len(results), source="arxiv")


# ── In-memory cache ───────────────────────────────────────────────────────


class SearchCache:
    """Simple TTL cache for search results — no database dependency.

    Module-level singleton: ``search_cache``.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._cache: dict[str, tuple[float, SearchResponse]] = {}
        self._ttl = ttl_seconds

    def _make_key(self, query: str, max_results: int) -> str:
        return f"{query.strip().lower()}:{max_results}"

    def get(self, query: str, max_results: int = 5) -> SearchResponse | None:
        """Return cached results if still fresh, otherwise None."""
        key = self._make_key(query, max_results)
        if key in self._cache:
            timestamp, response = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return response
            del self._cache[key]
        return None

    def set(self, query: str, max_results: int, response: SearchResponse) -> None:
        """Store search results in the cache."""
        key = self._make_key(query, max_results)
        self._cache[key] = (time.time(), response)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._cache.clear()


search_cache = SearchCache()


# ── Factory ────────────────────────────────────────────────────────────────


def get_search_client(provider: str = "mock") -> BaseSearchClient:
    """Return a search client instance for the given provider.

    Args:
        provider: ``"mock"``, ``"duckduckgo"``, or ``"tavily"``.

    Returns:
        A BaseSearchClient subclass instance.

    Raises:
        ValueError: If the provider name is unrecognised.
    """
    if provider == "mock":
        return MockSearchClient()
    if provider == "duckduckgo":
        return DuckDuckGoSearchClient(
            timeout=settings.search_timeout,
            total_timeout=settings.search_total_timeout,
        )
    if provider == "tavily":
        return TavilySearchClient(
            api_key=settings.tavily_api_key,
            timeout=settings.search_timeout,
        )
    raise ValueError(f"Unsupported search provider: {provider}")
