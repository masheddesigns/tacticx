"""DB engine/session helpers. SQLite is supported for tests; Postgres for prod."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().DATABASE_URL
        if url.startswith("postgresql://"):
            try:
                import psycopg  # noqa: F401
            except ImportError:
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {}
        _engine = create_engine(url, **kwargs)
    return _engine



def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def reset_engine() -> None:
    """Test helper: drop cached engine/session so DATABASE_URL changes take effect."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
