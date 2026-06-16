"""Database package for EduAgent persistence layer.

Provides SQLAlchemy engine, session factory, and initialization.
Uses SQLite by default; swap database_url in .env for PostgreSQL.
"""

from app.db.engine import engine, SessionLocal, init_db, get_db

__all__ = ["engine", "SessionLocal", "init_db", "get_db"]
