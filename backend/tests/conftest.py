"""Shared test fixtures: SQLite DB, FastAPI client, mocked providers. No live APIs."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.api.dependencies import get_db  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB = "/tmp/bet_predictor_test.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

engine = create_engine(f"sqlite:///{TEST_DB}")
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)


def override_get_db():
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    # Truncate all tables between tests for isolation.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def _clean_app_engine():
    """Tests that exercise the app engine (request/quota logs) share a file
    DB across runs — truncate its log tables so counts stay deterministic."""
    from app.db.models.logs import DataSyncLog, ProviderRequestLog
    from app.db.session import get_engine, get_session_local

    Base.metadata.create_all(get_engine())
    session = get_session_local()()
    try:
        session.query(DataSyncLog).delete()
        session.query(ProviderRequestLog).delete()
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture()
def db():
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sample_match(db):
    """One scheduled EPL match: Arsenal vs Chelsea (kicks off 5h from now)."""
    from datetime import datetime, timedelta, timezone

    from app.db.models.core import League, Match, Team

    lg = League(code="EPL", name="Premier League", provider="api_football",
                provider_league_id="39", season="2024")
    db.add(lg)
    db.flush()
    home = Team(league_id=lg.id, name="Arsenal", provider="api_football", provider_team_id="42")
    away = Team(league_id=lg.id, name="Chelsea", provider="api_football", provider_team_id="49")
    db.add_all([home, away])
    db.flush()
    m = Match(league_id=lg.id, home_team_id=home.id, away_team_id=away.id,
              kickoff_at=datetime.now(timezone.utc) + timedelta(hours=5),
              status="SCHEDULED", provider="api_football", provider_match_id="12345")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m
