"""Phase-1 test suite — all provider I/O mocked, no live APIs."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from app.db.models.core import League, Match
from app.db.models.logs import ProviderRequestLog
from app.db.session import get_engine
from app.services import ingestion
from app.services.caching import cache as cache_mod
from app.services.caching.rate_limiter import RateLimitExceeded, acquire, reset_limiter
from app.services.dtos import FixtureDTO, OddsSelectionDTO, OddsSnapshotDTO
from app.services.football.api_football import ApiFootballProvider
from app.services.http_client import ProviderHTTPError, logged_request
from app.services.odds.odds_api import OddsApiProvider
from app.services.predictions.base import StubPredictionProvider
from tests.fixtures.mock_responses import FIXTURES_RESPONSE, ODDS_RESPONSE


def _mock_client(payload, status=200, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or {})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- infra ---


def test_database_connection():
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_health_endpoint(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_endpoint(client):
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


# --- provider adapters (mocked) ---


@pytest.mark.asyncio
async def test_football_provider_parses_fixtures():
    p = ApiFootballProvider(api_key="x", client=_mock_client(FIXTURES_RESPONSE))
    fixtures = await p.get_fixtures("39", "2024")
    assert len(fixtures) == 2
    assert fixtures[0].home_team_name == "Arsenal"
    assert fixtures[0].status == "SCHEDULED"


@pytest.mark.asyncio
async def test_odds_provider_parses_snapshots():
    p = OddsApiProvider(api_key="x", client=_mock_client(ODDS_RESPONSE))
    snaps = await p.get_odds()
    assert len(snaps) == 1
    assert snaps[0].market_type == "h2h"
    assert {s.selection for s in snaps[0].selections} == {"home", "draw", "away"}


# --- cache / rate limiter / retry / 429 ---


def test_cache_roundtrip_and_ttl():
    cache_mod.reset_cache()
    cache_mod.cache_set("k", "v", 60)
    assert cache_mod.cache_get("k") == "v"
    cache_mod.cache_set("k2", "v", -1)
    assert cache_mod.cache_get("k2") is None


def test_rate_limiter_blocks_when_exhausted(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "PROVIDER_MAX_REQUESTS_PER_MINUTE", 1)
    reset_limiter()
    assert acquire("p") is True
    assert acquire("p") is False
    reset_limiter()


@pytest.mark.asyncio
async def test_retry_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reset_limiter()
    data = await logged_request("p_retry", "GET", "http://x.test/", client=client)
    assert data == {"ok": True} and calls["n"] == 3


@pytest.mark.asyncio
async def test_429_respected_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        if not hasattr(handler, "n"):
            handler.n = 0
        handler.n += 1
        if handler.n == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reset_limiter()
    assert await logged_request("p_429", "GET", "http://x.test/", client=client) == {"ok": True}


@pytest.mark.asyncio
async def test_rate_limit_exceeded_raises(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "PROVIDER_MAX_REQUESTS_PER_MINUTE", 1)
    reset_limiter()
    client = _mock_client({"ok": True})
    await logged_request("p_rl", "GET", "http://x.test/", client=client)
    with pytest.raises(RateLimitExceeded):
        await logged_request("p_rl", "GET", "http://x.test/", client=client)
    reset_limiter()


@pytest.mark.asyncio
async def test_request_log_written(db):
    from app.db.models import Base
    from app.db.session import get_engine, get_session_local

    Base.metadata.create_all(get_engine())  # request log uses the app engine

    reset_limiter()
    client = _mock_client({"ok": True})
    await logged_request("p_log", "GET", "http://x.test/ep",
                         db_session_factory=get_session_local, client=client)
    # logged_request opens its own session; query a fresh one
    s2 = get_session_local()()
    try:
        rows = s2.query(ProviderRequestLog).filter_by(provider="p_log").all()
        assert len(rows) == 1 and rows[0].success is True
    finally:
        s2.close()


# --- ingestion idempotency ---


def _fx(pid="12345", home=("42", "Arsenal"), away=("49", "Chelsea")):
    from datetime import datetime, timezone

    return FixtureDTO(
        provider="api_football", provider_match_id=pid, home_team_id=home[0],
        home_team_name=home[1], away_team_id=away[0], away_team_name=away[1],
        kickoff_at=datetime(2025, 5, 1, 18, 0, tzinfo=timezone.utc), status="SCHEDULED")


def test_match_ingestion_idempotent(db):
    for _ in range(5):
        ingestion.sync_fixtures(db, [_fx()], league_code="EPL")
    assert db.query(Match).filter_by(provider_match_id="12345").count() == 1


def test_match_update_on_refetch(db):
    ingestion.sync_fixtures(db, [_fx()], league_code="EPL")
    fx = _fx()
    fx.status = "LIVE"
    fx.minute = 63
    fx.home_score = 1
    ingestion.sync_fixtures(db, [fx], league_code="EPL")
    m = db.query(Match).filter_by(provider_match_id="12345").one()
    assert (m.status, m.minute, m.home_score) == ("LIVE", 63, 1)
    assert db.query(Match).count() == 1


def test_odds_snapshot_append_and_dedup(db, sample_match):
    from datetime import datetime, timezone

    from app.db.models.odds import OddsSelection, OddsSnapshot

    def snap(price, ts):
        return OddsSnapshotDTO(bookmaker="Bet365", bookmaker_provider_id="bet365",
                               market_type="h2h", timestamp=ts, is_live=False,
                               selections=[OddsSelectionDTO(selection="home", odds=price)])

    t1 = datetime(2025, 4, 30, 18, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 4, 30, 18, 10, tzinfo=timezone.utc)
    ingestion.store_odds_snapshots(db, sample_match.id, [snap(1.80, t1)], "odds_api")
    ingestion.store_odds_snapshots(db, sample_match.id, [snap(1.80, t1)], "odds_api")  # duplicate
    ingestion.store_odds_snapshots(db, sample_match.id, [snap(1.76, t2)], "odds_api")  # movement
    selections = db.query(OddsSelection).all()
    assert sorted(s.odds for s in selections) == [1.76, 1.80]
    assert db.query(OddsSnapshot).count() == 3  # snapshots stay, dup selection skipped


# --- API ---


def test_matches_list_pagination_and_filters(client, sample_match):
    r = client.get("/api/v1/matches?page=1&page_size=1")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] >= 1 and len(body["data"]) == 1
    assert client.get("/api/v1/matches?league=EPL").json()["meta"]["total"] >= 1
    assert client.get("/api/v1/matches?league=NOPE").status_code == 400
    assert client.get("/api/v1/matches").json()["meta"]["total"] >= 1


def test_match_detail_and_subresources(client, sample_match):
    assert client.get(f"/api/v1/matches/{sample_match.id}").status_code == 200
    assert client.get("/api/v1/matches/999999").status_code == 404
    for sub in ("statistics", "events"):
        assert client.get(f"/api/v1/matches/{sample_match.id}/{sub}").status_code == 200


def test_upcoming_and_live(client, db, sample_match):
    upcoming = client.get("/api/v1/matches/upcoming").json()["data"]
    assert any(m["id"] == sample_match.id for m in upcoming)
    sample_match.status = "LIVE"
    db.commit()
    live = client.get("/api/v1/matches/live").json()["data"]
    assert any(m["id"] == sample_match.id for m in live)


def test_odds_endpoints_and_movement(client, db, sample_match):
    from datetime import datetime, timezone

    t = [datetime(2025, 4, 30, h, 0, tzinfo=timezone.utc) for h in (18, 19)]
    ingestion.store_odds_snapshots(db, sample_match.id, [
        OddsSnapshotDTO(bookmaker="B", bookmaker_provider_id="b", market_type="h2h",
                        timestamp=t[0], selections=[OddsSelectionDTO(selection="home", odds=1.80)]),
    ], "odds_api")
    ingestion.store_odds_snapshots(db, sample_match.id, [
        OddsSnapshotDTO(bookmaker="B", bookmaker_provider_id="b", market_type="h2h",
                        timestamp=t[1], selections=[OddsSelectionDTO(selection="home", odds=1.65)]),
    ], "odds_api")
    hist = client.get(f"/api/v1/odds/{sample_match.id}/history").json()["data"]
    assert len(hist) == 2  # history preserved
    mov = client.get(f"/api/v1/odds/{sample_match.id}/movement").json()["data"][0]
    assert mov["opening"] == 1.80 and mov["current"] == 1.65
    assert mov["absolute_change"] == pytest.approx(-0.15)
    assert mov["direction"] == "down"
    assert client.get("/api/v1/odds/999999/history").status_code == 404


def test_predictions_stub_and_storage(client, db, sample_match):
    out = StubPredictionProvider().predict({})
    assert abs(out.home_win_probability + out.draw_probability + out.away_win_probability - 1.0) < 1e-9
    from app.services.backtesting.service import record_prediction, resolve_predictions

    record_prediction(db, match_id=sample_match.id, model_version="stub-0.1",
                      prediction_type="1x2", predicted_probability=0.33,
                      probabilities={"home": 0.33, "draw": 0.33, "away": 0.34},
                      input_snapshot={"as_of": "2025-04-30"})
    r = client.get(f"/api/v1/predictions/{sample_match.id}")
    assert r.status_code == 200 and len(r.json()["data"]) == 1
    sample_match.status = "FINISHED"
    sample_match.home_score = 2
    sample_match.away_score = 0
    db.commit()
    assert resolve_predictions(db, sample_match.id) == 1


def test_openapi_available(client):
    assert client.get("/openapi.json").status_code == 200
