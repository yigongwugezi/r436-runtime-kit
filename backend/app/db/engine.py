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
        "learners": {
            "phone": "VARCHAR(20)",
            "wechat_openid": "VARCHAR(64)",
            "student_no": "VARCHAR(32)",
            "password_hash": "VARCHAR(256)",
            "role": "VARCHAR(16) DEFAULT 'student'",
            "grade": "VARCHAR(16)",
            "target_exam": "VARCHAR(64)",
            "employee_id": "VARCHAR(32)",
            "pending_child_student_no": "VARCHAR(32)",
            "school": "VARCHAR(128)",
            "avatar_url": "VARCHAR(512)",
            "parent_id": "VARCHAR(64)",
        },
        "sessions": {
            "learner_id": "VARCHAR(64)",
            "subject_id": "VARCHAR(64)",
        },
        "learning_paths": {
            "description": "TEXT",
            "textbook_id": "VARCHAR(64)",
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
            "metadata": "JSON",
            "bookmarked": "BOOLEAN DEFAULT 0",
            "study_status": "VARCHAR(16) DEFAULT 'new'",
            "source": "VARCHAR(16) DEFAULT 'agent_generated'",
            "related_stage_id": "VARCHAR(64)",
            "related_chapter_id": "VARCHAR(64)",
            "related_section_id": "VARCHAR(64)",
            "task_id": "VARCHAR(64)",
            "completed_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "questions": {
            "subject": "VARCHAR(64)",
            "knowledge_point": "VARCHAR(128)",
            "type": "VARCHAR(16) DEFAULT 'choice'",
            "difficulty": "VARCHAR(8) DEFAULT 'medium'",
            "content": "JSON",
            "tags": "JSON",
            "status": "VARCHAR(16) DEFAULT 'draft'",
            "usage_count": "INTEGER DEFAULT 0",
            "avg_score": "FLOAT DEFAULT 0.0",
            "created_by": "VARCHAR(64)",
            "updated_at": "DATETIME",
            "review_status": "VARCHAR(16)",
            "review_comment": "TEXT",
            "reviewed_by": "VARCHAR(64)",
            "reviewed_at": "DATETIME",
            "calibrated_difficulty": "FLOAT",
        },
        "knowledge_points": {
            "subject": "VARCHAR(64)",
            "name": "VARCHAR(128)",
            "description": "TEXT",
            "prerequisites": "JSON",
            "difficulty": "VARCHAR(8) DEFAULT 'medium'",
            "importance": "INTEGER DEFAULT 5",
            "chapter": "VARCHAR(128)",
            "grade_level": "VARCHAR(16)",
            "metadata": "JSON",
            "updated_at": "DATETIME",
        },
        "student_questions": {
            "needs_review": "BOOLEAN DEFAULT 0",
            "review_reason": "VARCHAR(256)",
            "review_status": "VARCHAR(32)",
            "revision_note": "TEXT",
        },
        "system_config": {
            "value": "TEXT",
            "description": "VARCHAR(256)",
            "category": "VARCHAR(32) DEFAULT 'general'",
            "updated_by": "VARCHAR(64)",
            "updated_at": "DATETIME",
        },
        "user_preferences": {
            "preferences": "JSON",
        },
        "answer_records": {
            "attempt_id": "VARCHAR(64)",
        },
        "personal_subjects": {
            "textbook_id": "VARCHAR(64)",
        },
        "attempts": {
            "subject_id": "VARCHAR(64)",
            "idempotency_key": "VARCHAR(128)",
            "attempt_number": "INTEGER DEFAULT 1",
            "graded_at": "DATETIME",
            "answers_revealed_at": "DATETIME",
            "assessment_eligible": "BOOLEAN DEFAULT 1",
            "processing_task_id": "VARCHAR(64)",
            "diagnosis_task_id": "VARCHAR(64)",
        },
    }
    for table, columns in migrations.items():
        for column, definition in columns.items():
            add_column_if_missing(table, column, definition)

    # ── Attempt idempotency unique indexes ────────────────────────────
    _migrate_attempts_idempotency_indexes()

    # ── Fix stale FK on student_questions.session_id ──────────────────
    # Earlier versions had session_id -> sessions.id FK.  Teacher-pushed
    # questions use synthetic ids like "class_cs_xxx" which don't exist
    # in the sessions table, so the FK must be removed.
    _migrate_student_questions_session_fk()

    # ── Fix stale FK on answer_records.session_id ─────────────────────
    # Same issue — quiz attempts and practice answers use synthetic
    # session IDs that may not exist in the sessions table.
    _migrate_answer_records_session_fk()


def _migrate_attempts_idempotency_indexes() -> None:
    """Create partial unique indexes for attempt idempotency if they don't exist.

    SQLite 3.8+ supports partial unique indexes.  These enforce that
    (learner_id, quiz_id, idempotency_key) and (learner_id, exam_set_id,
    idempotency_key) are unique when both key fields are non-NULL.
    """
    with engine.connect() as conn:
        # Check that the table exists first
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='attempts'")
            ).fetchall()
        }
        if "attempts" not in tables:
            return

        for name, parent_col in (
            ("uq_attempts_quiz_idemkey", "quiz_id"),
            ("uq_attempts_exam_idemkey", "exam_set_id"),
        ):
            try:
                conn.execute(
                    text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {name} "
                        f"ON attempts(learner_id, {parent_col}, idempotency_key) "
                        f"WHERE {parent_col} IS NOT NULL AND idempotency_key IS NOT NULL"
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()


def _migrate_student_questions_session_fk() -> None:
    """Drop the stale FK on student_questions.session_id if it exists."""
    with engine.connect() as conn:
        # Check if the student_questions table exists
        tables = {row[0] for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='student_questions'")
        ).fetchall()}
        if "student_questions" not in tables:
            return

        # Check for FKs on session_id
        fks = conn.execute(
            text("PRAGMA foreign_key_list(student_questions)")
        ).fetchall()
        has_session_fk = any(row[3] == "session_id" for row in fks)

        if not has_session_fk:
            return

        # Recreate the table without the FK
        conn.execute(text("BEGIN TRANSACTION"))
        try:
            conn.execute(text("""
                CREATE TABLE student_questions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id VARCHAR(64) UNIQUE NOT NULL,
                    question_set_id VARCHAR(64) DEFAULT '',
                    session_id VARCHAR(64) NOT NULL,
                    source_question_id VARCHAR(64),
                    type VARCHAR(16) DEFAULT 'choice',
                    stem TEXT DEFAULT '',
                    options JSON,
                    correct VARCHAR(512),
                    explanation TEXT,
                    difficulty VARCHAR(8) DEFAULT 'medium',
                    knowledge_points JSON,
                    tags JSON,
                    scoring_rubric JSON,
                    reference_answer TEXT,
                    source VARCHAR(32) DEFAULT 'llm_generated',
                    quality_status VARCHAR(16) DEFAULT 'passed',
                    needs_review BOOLEAN DEFAULT 0,
                    review_reason VARCHAR(256),
                    review_status VARCHAR(32),
                    revision_note TEXT,
                    created_at DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO student_questions_new SELECT
                    id, question_id, question_set_id, session_id,
                    source_question_id, type, stem, options, correct,
                    explanation, difficulty, knowledge_points, tags,
                    scoring_rubric, reference_answer, source,
                    quality_status, needs_review, review_reason,
                    review_status, revision_note, created_at
                FROM student_questions
            """))
            conn.execute(text("DROP TABLE student_questions"))
            conn.execute(text("ALTER TABLE student_questions_new RENAME TO student_questions"))
            # Recreate indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_questions_question_id ON student_questions(question_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_questions_question_set_id ON student_questions(question_set_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_questions_session_id ON student_questions(session_id)"))
            conn.execute(text("COMMIT"))
        except Exception:
            conn.execute(text("ROLLBACK"))
            raise


def _migrate_answer_records_session_fk() -> None:
    """Drop the stale FK on answer_records.session_id if it exists.

    Quiz attempts and practice answers use synthetic session IDs that
    may not exist in the sessions table (e.g. ``lecture_xxx``).
    """
    with engine.connect() as conn:
        tables = {row[0] for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='answer_records'")
        ).fetchall()}
        if "answer_records" not in tables:
            return

        fks = conn.execute(
            text("PRAGMA foreign_key_list(answer_records)")
        ).fetchall()
        has_session_fk = any(row[3] == "session_id" for row in fks)

        if not has_session_fk:
            return

        conn.execute(text("BEGIN TRANSACTION"))
        try:
            conn.execute(text("""
                CREATE TABLE answer_records_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(64) NOT NULL,
                    question_id VARCHAR(32) NOT NULL,
                    attempt_id VARCHAR(64),
                    student_answer TEXT NOT NULL,
                    total_score INTEGER,
                    dimension_scores JSON,
                    dimension_feedback JSON,
                    error_type VARCHAR(16),
                    error_label VARCHAR(16),
                    error_explanation TEXT,
                    error_action TEXT,
                    suggestions JSON,
                    strengths JSON,
                    source VARCHAR(32) DEFAULT 'llm_generated',
                    created_at DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO answer_records_new SELECT
                    id, session_id, question_id, attempt_id,
                    student_answer, total_score, dimension_scores,
                    dimension_feedback, error_type, error_label,
                    error_explanation, error_action, suggestions,
                    strengths, source, created_at
                FROM answer_records
            """))
            conn.execute(text("DROP TABLE answer_records"))
            conn.execute(text("ALTER TABLE answer_records_new RENAME TO answer_records"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_answer_records_session_id ON answer_records(session_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_answer_records_question_id ON answer_records(question_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_answer_records_attempt_id ON answer_records(attempt_id)"))
            conn.execute(text("COMMIT"))
        except Exception:
            conn.execute(text("ROLLBACK"))
            raise


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
