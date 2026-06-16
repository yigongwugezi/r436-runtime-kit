"""SQLAlchemy engine and session factory."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _ensure_data_dir() -> None:
    """Ensure the directory for the SQLite database file exists."""
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = str(settings.project_root / "backend" / db_path[2:])
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)


_ensure_data_dir()

# Resolve relative path to absolute for the engine
_db_url = settings.database_url
if _db_url.startswith("sqlite:///./"):
    resolved = str(settings.project_root / "backend" / _db_url.removeprefix("sqlite:///./"))
    _db_url = f"sqlite:///{resolved}"

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
    """Enable WAL mode and foreign keys for SQLite connections."""
    if "sqlite" in str(engine.url):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist."""
    from app.db.models import Base  # noqa: PLC0415

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
