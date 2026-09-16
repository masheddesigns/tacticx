"""DB session dependency for routes."""
from __future__ import annotations

from collections.abc import Generator
from sqlalchemy.orm import Session

from app.db.session import get_session_local


def get_db() -> Generator[Session, None, None]:
    session = get_session_local()()
    try:
        yield session
    finally:
        session.close()
