"""SQLAlchemy engine and session factory."""

from pathlib import Path

from sqlalchemy import create_engine, event, text
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
    """Create all tables if they don't exist, and migrate existing ones."""
    from app.db.models import Base  # noqa: PLC0415

    Base.metadata.create_all(bind=engine)

    if "sqlite" not in _db_url:
        return

    def add_column_if_missing(table: str, column: str, definition: str) -> None:
        with engine.connect() as conn:
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if column not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    conn.commit()
                except Exception:
                    # Existing local SQLite files may already contain the column
                    # while reporting stale PRAGMA metadata on a reused connection.
                    conn.rollback()

    # SQLite does not auto-add new columns to existing tables.
    migrations = {
        "sessions": {
            "learner_id": "VARCHAR(64)",
        },
        "learning_paths": {
            "description": "TEXT",
        },
        "resources": {
            "knowledge_points": "JSON",
            "tags": "JSON",
            "difficulty": "VARCHAR(16) DEFAULT 'easy'",
            "estimated_minutes": "INTEGER DEFAULT 20",
            "format": "VARCHAR(16) DEFAULT 'text'",
            "mermaid_def": "TEXT",
            "code_blocks": "JSON",
            "questions": "JSON",
            "ppt_outline": "JSON",
            "bookmarked": "BOOLEAN DEFAULT 0",
            "study_status": "VARCHAR(16) DEFAULT 'new'",
            "source": "VARCHAR(16) DEFAULT 'agent_generated'",
            "related_stage_id": "VARCHAR(64)",
            "task_id": "VARCHAR(64)",
            "updated_at": "DATETIME",
        },
    }
    for table, columns in migrations.items():
        for column, definition in columns.items():
            add_column_if_missing(table, column, definition)


# Keep direct route imports and test scripts usable even when FastAPI lifespan
# is not executed. create_all is idempotent for SQLite and harmless on startup.
init_db()


def get_db():
    """FastAPI dependency: yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
