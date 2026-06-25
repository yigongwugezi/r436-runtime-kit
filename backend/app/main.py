import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import init_db
from app.routers import agents, courses, health, product
from app.services.conversation_state import conversation_store
from app.services.learning_tracker import learning_tracker
from app.utils.errors import AppError

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Reduce noise from SQLAlchemy engine logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger("app.main")


# ── Lifespan ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and enable persistence on singletons at startup."""
    init_db()
    conversation_store.enable_db()
    learning_tracker.enable_db()
    yield


app = FastAPI(
    title="r436 Runtime Kit Backend",
    description="Course workflow demo backend with SQLite persistence for session, profile, path, resource and event data.",
    version="0.2.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request-id middleware ─────────────────────────────────────────────


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a unique request-id to every response for traceability."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global exception handlers ─────────────────────────────────────────


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert structured AppErrors into consistent, safe JSON responses.

    User errors (4xx) are logged at WARNING level.
    System errors (5xx) are logged at ERROR level with full traceback.
    Stack traces are NEVER exposed to the client.
    """
    log = logging.getLogger("app.exception")
    if exc.is_user_error:
        log.warning(
            "[%s] %s (code=%s, path=%s)",
            exc.__class__.__name__,
            exc.message,
            exc.code,
            request.url.path,
        )
    else:
        log.error(
            "[%s] %s (code=%s, path=%s)",
            exc.__class__.__name__,
            exc.message,
            exc.code,
            request.url.path,
            exc_info=exc.cause or exc,
        )

    body = exc.to_response_dict()
    # Inject request-local context if available
    body["sessionId"] = getattr(request.state, "session_id", "")
    body["subjectId"] = getattr(request.state, "subject_id", "")
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected exceptions.

    Logs the full traceback server-side but returns a generic,
    safe message to the client — no stack traces, no internal details.
    """
    log = logging.getLogger("app.exception")
    log.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "data": None,
            "message": "服务器内部错误，请稍后重试",
            "detail": "服务器内部错误，请稍后重试",
            "code": "INTERNAL_ERROR",
            "is_user_error": False,
            "sessionId": getattr(request.state, "session_id", ""),
            "subjectId": getattr(request.state, "subject_id", ""),
        },
    )


# ── Routers ───────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(product.router)
app.include_router(product.router, prefix="/api")
