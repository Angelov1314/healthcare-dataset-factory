"""Database engine and session creation."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the supplied or configured database URL."""

    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create a session factory without hidden global state."""

    return sessionmaker(bind=create_db_engine(database_url), expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields one database session."""

    session = create_session_factory()()
    try:
        yield session
    finally:
        session.close()
