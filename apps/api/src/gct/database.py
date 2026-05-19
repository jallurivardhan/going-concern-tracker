from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from gct.config import settings


def _normalize_db_url(url: str) -> str:
    """Ensure the URL uses the psycopg3 (psycopg) driver, not psycopg2."""
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


engine = create_engine(
    _normalize_db_url(settings.database_url),
    pool_pre_ping=True,  # Neon connections can silently drop; re-validate before use
    echo=settings.log_level == "DEBUG",
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and ensures it's closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(db: Session) -> bool:
    """Execute a trivial query to confirm the database is reachable."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
