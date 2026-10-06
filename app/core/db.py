"""SQLAlchemy 2.x database configuration and session management."""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


def create_db_engine():
    """Create SQLAlchemy engine dynamically based on the current settings."""
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )


# Engine and sessionmaker factory
engine = create_db_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create all database tables on application startup."""
    # Ensure all models are imported before calling create_all
    import app.models.job  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for injecting database sessions per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Independent database session context manager for background workers and services.

    Ensures that background tasks manage their own session lifecycle, transaction,
    and cleanup, isolated from the HTTP request context.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
