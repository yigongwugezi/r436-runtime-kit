from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import agents, courses, health, product
from app.services.conversation_state import conversation_store
from app.services.learning_tracker import learning_tracker


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

app.include_router(health.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(product.router)
app.include_router(product.router, prefix="/api")
