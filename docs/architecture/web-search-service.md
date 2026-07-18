# Web Search Service

> **Added v0.6.0** — Provider-abstraction layer so agents can query the web.

## Overview

The web search service wraps external search APIs behind a common interface
(``BaseSearchClient``). Agents import the factory function and call ``.search()``
without knowing which provider is configured.

## Architecture

```
Agent (consumer)
    |
    v
get_search_client(provider)        <-- factory (mirrors get_llm_client)
    |
    v
BaseSearchClient (ABC)             <-- abstract contract
    |
    +-- MockSearchClient            <-- deterministic mock for dev/test
    +-- DuckDuckGoSearchClient      <-- free, no API key
    +-- TavilySearchClient          <-- paid, RAG-optimised
```

## Provider Comparison

| Feature | Mock | DuckDuckGo | Tavily |
|---------|------|------------|--------|
| API key required | No | No | Yes (per-user, 系统设置 → AI 模型配置) |
| Results per call | ≤ 3 (fake) | max_results param | max_results param |
| AI-optimised results | No | No | Yes (includes answer summary) |
| Rate limiting | None | Moderate (built-in) | Paid-tier limits |
| Use case | Dev / CI | Quick testing | Production RAG |

## Configuration

> **v1.1.0**: Tavily key 为每用户配置（`user_ai_config.tavily.apiKey`，经
> ``app/services/user_ai_config.py`` 解析），不再从 ``.env`` 读取。
> 其余技术设置仍在 ``.env`` 中并由 ``app/config.py`` 加载：

| Variable | Default | Description |
|----------|---------|-------------|
| ``SEARCH_PROVIDER`` | ``mock`` | ``mock``, ``duckduckgo``, or ``tavily`` |
| ``SEARCH_MAX_RESULTS`` | ``5`` | Default max results per search |
| ``SEARCH_TIMEOUT`` | ``10`` | HTTP request timeout (seconds) |
| ``SEARCH_CACHE_TTL`` | ``300`` | In-memory cache TTL (seconds) |

## Internal API

### BaseSearchClient

```python
class BaseSearchClient(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse: ...
    def is_available(self) -> bool: ...
```

### SearchResponse / SearchResultItem

Internal dataclasses (lightweight — no Pydantic overhead):

```python
@dataclass
class SearchResultItem:
    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""
    source: str = ""

@dataclass
class SearchResponse:
    query: str
    results: list[SearchResultItem]
    total_estimated: int = 0
    source: str = ""
```

### Factory

```python
def get_search_client(provider: str = "mock") -> BaseSearchClient:
```

### Cache

Module-level singleton ``search_cache`` (``SearchCache`` instance).  TTL-based,
in-memory only — no database dependency.  Cache key = ``query.lower().strip() + max_results``.

## Usage in Agents

Any agent can import and use the search service directly — it is **not** part
of the orchestrator pipeline:

```python
from app.services.search_client import get_search_client, SearchError
from app.config import settings

class MyAgent(BaseAgent):
    agent_id = "my_agent"
    agent_name = "My Agent"

    def run(self, context: dict) -> dict:
        client = get_search_client(settings.search_provider)
        try:
            results = client.search("relevant topic", max_results=3)
            for r in results.results:
                # r.title, r.url, r.snippet, r.content
                ...
        except SearchError:
            # Log and use fallback
            ...
```

The orchestrator does **not** invoke the search client — agents decide what
to search for and when.

## HTTP Diagnostic Endpoint

A lightweight ``POST /api/search`` endpoint is available for manual testing
through the Swagger UI (``/docs``).  It uses the same ``get_search_client``
factory and respects the cache.

See ``docs/api/api-contract.md`` Section 2 for the full endpoint specification.

## Error Handling

- All provider errors are wrapped in ``SearchError``.
- ``SearchError`` is caught by the global exception handler in ``main.py``
  via ``SearchServiceError`` (``AppError`` subclass, HTTP 503).
- Agents should catch ``SearchError`` and provide domain-appropriate fallbacks.

## Adding a New Provider

1. Create a class inheriting ``BaseSearchClient`` in ``services/search_client.py``.
2. Implement ``search()`` and optionally ``is_available()``.
3. Add a branch to ``get_search_client()``.
4. Add provider-specific config to ``config.py`` / ``.env``.
5. Add tests in ``tests/search_client_test.py``.
