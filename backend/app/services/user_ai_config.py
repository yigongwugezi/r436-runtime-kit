"""Per-user AI credential resolver — the single entry point for ALL AI
credential reads in the application.

Credentials are configured by each learner in 系统设置 → AI 模型配置 and
stored in the ``user_ai_config`` table.  They are **never** read from
``.env`` / ``os.environ``; technical tuning (timeouts, retries, role model
overrides, endpoint URLs) stays in ``.env``.

Resolution modes
----------------
1. Request context (default): ``middleware.auth.get_auth`` calls
   :func:`set_current_learner`; the config is lazily loaded from the DB on
   first credential access and cached per-context in a ``ContextVar``.
2. Explicit snapshot: background threads / workflow runners either wrap
   their target with :func:`copy_context_wrap` (propagates the ContextVars)
   or pass ``config=<dict>`` explicitly to the resolver functions.

ContextVars live in this module (not ``middleware.auth``) so that services
can import the resolver without touching FastAPI middleware and no import
cycle forms.
"""

from __future__ import annotations

import contextvars
import logging
from contextvars import ContextVar
from typing import Any, Callable

from app.utils.errors import AIConfigMissingError

logger = logging.getLogger(__name__)

# ── Per-request identity + lazy config cache ────────────────────────────

_current_learner_id: ContextVar[str] = ContextVar("ai_cfg_learner_id", default="")
_config_cache: ContextVar[dict | None] = ContextVar("ai_cfg_cache", default=None)


def set_current_learner(learner_id: str) -> None:
    """Bind the current context to a learner (called by ``get_auth``).

    Cheap: no DB access here — the config is loaded lazily on first
    credential read.  Always resets the cached config so a context reused
    for another learner (e.g. a scheduler loop) never sees stale keys.
    """
    _current_learner_id.set(str(learner_id or ""))
    _config_cache.set(None)


def get_current_learner_id() -> str:
    return _current_learner_id.get()


def _get_config() -> dict:
    """Return the current learner's AI config, loading from DB on first use."""
    cached = _config_cache.get()
    if cached is not None:
        return cached
    learner_id = _current_learner_id.get()
    config: dict = {}
    if learner_id:
        try:
            from app.db.engine import SessionLocal
            from app.db.repository import get_user_ai_config

            db = SessionLocal()
            try:
                config = get_user_ai_config(db, learner_id)
            finally:
                db.close()
        except Exception:  # pragma: no cover - DB unavailable
            logger.warning("Failed to load AI config for learner %s", learner_id)
            config = {}
    _config_cache.set(config)
    return config


def get_config_snapshot() -> dict:
    """Resolve the current context's config as a plain dict.

    Use before returning an SSE generator or spawning work the harness
    cannot guarantee runs in this context; pass the result back in via the
    ``config=`` parameter of the resolver functions.
    """
    return dict(_get_config())


def load_config_for_learner(db, learner_id: str) -> dict:
    """Explicitly load a learner's AI config (request-less background jobs)."""
    from app.db.repository import get_user_ai_config

    return get_user_ai_config(db, learner_id)


def copy_context_wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Capture the caller's context and return a callable that re-enters it.

    Native ``threading.Thread`` / ``ThreadPoolExecutor`` targets do NOT
    inherit ContextVars — wrap them at spawn time::

        threading.Thread(target=copy_context_wrap(work), args=(...,))
        executor.submit(copy_context_wrap(fn), *args)
    """
    ctx = contextvars.copy_context()

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return ctx.run(fn, *args, **kwargs)

    return wrapped


# ── Provider defaults (main LLM) ────────────────────────────────────────
# Base URL and model names are fixed official defaults in code — per user
# decision, they are configurable neither per-user nor via .env for the
# main LLM.  Role-specific model overrides (LLM_PLANNER_MODEL …) remain
# .env technical tuning in llm_factory.

PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "default_url": "https://api.deepseek.com",
        "models": {"text": "deepseek-chat", "vision": None},
    },
    "qwen": {
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {"text": "qwen-coder-plus", "vision": "qwen-vl-max"},
    },
    "glm": {
        "default_url": "https://open.bigmodel.cn/api/paas/v4/",
        "models": {"text": "glm-5.2", "vision": "glm-4v-plus"},
    },
    "openai": {
        "default_url": "https://api.openai.com/v1/",
        "models": {"text": "gpt-4o", "vision": "gpt-4o"},
    },
}

# Credential fields per service; ALL of them must be non-empty for the
# service to count as configured.  ``llm.provider`` is a plain field.
SERVICE_FIELDS: dict[str, list[str]] = {
    "llm": ["apiKey"],
    "qwen": ["apiKey"],
    "spark": ["appId", "apiKey", "apiSecret"],
    "sparkVision": ["appId", "apiKey", "apiSecret"],
    "wan": ["apiKey"],
    "ark": ["apiKey"],
    "aippt": ["appId", "apiSecret"],
    "tavily": ["apiKey"],
    "glm": ["apiKey"],
    "openai": ["apiKey"],
}

LLM_PROVIDERS = tuple(PROVIDER_DEFAULTS.keys())


# ── Credential resolution ───────────────────────────────────────────────


def get_credential(
    service: str, field: str = "apiKey", *, config: dict | None = None
) -> str:
    """Resolve one credential from user config; empty string if unset."""
    cfg = config if config is not None else _get_config()
    svc = cfg.get(service) if isinstance(cfg, dict) else None
    if not isinstance(svc, dict):
        return ""
    return str(svc.get(field, "") or "").strip()


def require_credential(
    service: str,
    field: str = "apiKey",
    *,
    provider: str = "",
    config: dict | None = None,
) -> str:
    """Resolve a credential or raise :class:`AIConfigMissingError`."""
    value = get_credential(service, field, config=config)
    if not value:
        raise AIConfigMissingError(
            service=service,
            provider=provider or service,
            authenticated=bool(_current_learner_id.get()) or config is not None,
        )
    return value


def get_llm_credentials(*, config: dict | None = None) -> dict[str, Any]:
    """Resolve main-LLM ``{provider, api_key, base_url, model}``.

    Resolution order:
    1. The user's configured key always wins — a per-user key means real
       calls regardless of ``LLM_PROVIDER``.
    2. No user key and ``settings.llm_provider == "mock"`` → mock provider
       (automated-test escape hatch; mock has no key, so nothing key-related
       depends on ``.env``).
    3. No user key otherwise → real provider with empty key; clients turn
       this into ``AIConfigMissingError`` on first use.
    """
    from app.config import settings

    cfg = config if config is not None else _get_config()
    llm = cfg.get("llm") if isinstance(cfg, dict) else None
    llm = llm if isinstance(llm, dict) else {}
    provider = str(llm.get("provider", "") or "").strip().lower() or "deepseek"
    if provider not in PROVIDER_DEFAULTS:
        provider = "deepseek"
    api_key = str(llm.get("apiKey", "") or "").strip()

    if not api_key and settings.llm_provider.lower() == "mock":
        return {"provider": "mock", "api_key": "", "base_url": "", "model": ""}

    defaults = PROVIDER_DEFAULTS[provider]
    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": defaults["default_url"],
        "model": defaults["models"]["text"],
    }


def require_llm_credentials(*, config: dict | None = None) -> dict[str, Any]:
    """Resolve main-LLM credentials or raise :class:`AIConfigMissingError`."""
    creds = get_llm_credentials(config=config)
    if creds["provider"] == "mock":
        return creds
    if not creds["api_key"]:
        raise AIConfigMissingError(
            service="llm",
            provider=creds["provider"],
            authenticated=bool(_current_learner_id.get()) or config is not None,
        )
    return creds


def resolve_provider_key(provider: str, *, config: dict | None = None) -> str:
    """Key for an arbitrary LLM provider (role overrides in llm_factory).

    If the user's main LLM is this provider, its key is used; otherwise the
    provider's own service entry (``qwen``/``glm``/``openai``) is consulted.
    DeepSeek has no standalone service entry — its key exists only as the
    main-LLM key.
    """
    provider = str(provider or "").strip().lower()
    creds = get_llm_credentials(config=config)
    if creds["provider"] == provider:
        return creds["api_key"]
    if provider in ("qwen", "glm", "openai"):
        return get_credential(provider, "apiKey", config=config)
    return ""


# ── Masking / safe API responses ────────────────────────────────────────


def mask_secret(value: str) -> str:
    """``sk-2601…1d4f`` → ``sk-26****1d4f``; short values → ``******``."""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) < 8:
        return "******"
    return text[:5] + "****" + text[-4:]


def service_configured(service: str, *, config: dict | None = None) -> bool:
    """True when ALL credential fields of the service are non-empty."""
    fields = SERVICE_FIELDS.get(service, ["apiKey"])
    return all(get_credential(service, f, config=config) for f in fields)


def to_safe_response(config: dict | None) -> dict[str, Any]:
    """Masked view of a config for the frontend — full keys never leave.

    Always emits the complete skeleton of all known services so the
    frontend needs no shape guessing.
    """
    cfg = config if isinstance(config, dict) else {}
    safe: dict[str, Any] = {}
    for service, fields in SERVICE_FIELDS.items():
        entry: dict[str, Any] = {}
        if service == "llm":
            provider = str(
                (cfg.get("llm") or {}).get("provider", "") or ""
            ).strip().lower()
            entry["provider"] = provider if provider in PROVIDER_DEFAULTS else "deepseek"
        for field in fields:
            entry[field] = mask_secret(get_credential(service, field, config=cfg))
        entry["configured"] = service_configured(service, config=cfg)
        safe[service] = entry
    return safe


# ── Per-user capabilities ───────────────────────────────────────────────


def user_capabilities(config: dict | None = None) -> dict[str, Any]:
    """Per-user capability flags (mirrors ``runtime_capabilities`` keys,
    but based on the learner's own credentials instead of the process env)."""
    import shutil

    from app.config import settings

    cfg = config if config is not None else _get_config()
    creds = get_llm_credentials(config=cfg)
    llm_ok = creds["provider"] == "mock" or bool(creds["api_key"])
    search = settings.search_provider.lower()
    search_ok = search in {"mock", "duckduckgo"} or bool(
        get_credential("tavily", config=cfg)
    )
    ppt_ok = service_configured("aippt", config=cfg)
    qwen_key = get_credential("qwen", config=cfg)
    video_ok = bool(
        get_credential("wan", config=cfg) or qwen_key or shutil.which("manim")
    )
    image_ok = bool(
        qwen_key
        or service_configured("spark", config=cfg)
        or (
            get_credential("ark", config=cfg)
            and creds["provider"] == "deepseek"
            and creds["api_key"]
        )
    )
    return {
        "llmProvider": creds["provider"],
        "llmConfigured": llm_ok,
        "searchProvider": search,
        "searchConfigured": search_ok,
        "pptConfigured": ppt_ok,
        "videoConfigured": video_ok,
        "imageConfigured": image_ok,
    }
