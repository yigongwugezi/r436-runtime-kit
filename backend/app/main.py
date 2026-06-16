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
    title="EduAgent Backend",
    description="EduAgent MVP with SQLite persistence for session, profile, path, resource and event data.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(product.router)
app.include_router(product.router, prefix="/api")
