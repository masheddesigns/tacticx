"""Phase-1.5 test suite — real-provider validation support, 100% mocked.

No real API calls here: smoke scripts under backend/scripts/ cover live calls.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.db.models.core import Match
from app.db.models.logs import ProviderRequestLog
from app.db.session import get_session_local
from app.services import ingestion
from app.services.caching import cache as cache_mod
from app.services.caching.rate_limiter import reset_limiter
from app.services.dtos import OddsSelectionDTO, OddsSnapshotDTO
from app.services.football.api_football import ApiFootballProvider
from app.services.http_client import ProviderHTTPError, logged_request
from app.services.odds.odds_api import LEAGUE_SPORT_KEYS, OddsApiProvider
from app.services.quota import extract_quota_remaining
from app.utils.odds_math import movement


def _mock_client(payload, status=200, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or {})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _isolate_cache_and_limiter():
    """Provider mocks differ per test but cache keys overlap — isolate."""
    cache_mod.reset_cache()
    reset_limiter()
    yield
    cache_mod.reset_cache()
    reset_limiter()


STATS_RESPONSE = {
    "response": [
        {"team": {"id": 42, "name": "Arsenal"},
         "statistics": [{"type": "Shots on Goal", "value": 5},
                        {"type": "Ball Possession", "value": "54%"}]},
        {"team": {"id": 49, "name": "Chelsea"},
         "statistics": [{"type": "Shots on Goal", "value": 3}]},
    ]
}

EVENTS_RESPONSE = {
    "response": [
        {"time": {"elapsed": 23}, "type": "Goal", "detail": "Normal Goal",
         "team": {"name": "Arsenal"}, "player": {"name": "Saka"}},
        {"time": {"elapsed": None}, "type": "Card", "detail": "Yellow Card",
         "team": {"name": "Chelsea"}, "player": {}},
    ]
}

LINEUPS_RESPONSE = {
    "response": [
        {"startXI": [{"player": {"name": "Raya", "pos": "G"}}],
         "substitutes": [{"player": {"name": "Kepa", "pos": "G"}}]},
        {"startXI": [], "substitutes": []},
    ]
}

LIVE_FIXTURE = {
    "response": [
        {"fixture": {"id": 12345, "date": "2025-05-01T18:00:00+00:00",
                     "status": {"short": "2H", "elapsed": 63}},
         "league": {"id": 39, "name": "Premier League"},
         "teams": {"home": {"id": 42, "name": "Arsenal"},
                   "away": {"id": 49, "name": "Chelsea"}},
         "goals": {"home": 1, "away": 0}, "score": {}},
    ]
}

SPARSE_FIXTURE = {
    "response": [
        {"fixture": {"id": 999, "status": {"short": "ZZZ"}},
         "league": {}, "teams": {}, "goals": {}, "score": {}},
    ]
}


# --- Step 1: configuration validation (never exposes secrets) ---


def test_diagnose_reports_presence_not_values():
    s = Settings(FOOTBALL_API_KEY="super-secret-football", ODDS_API_KEY="super-secret-odds")
    diag = s.diagnose()
    assert diag["FOOTBALL_API_KEY"] == "configured"
    assert diag["ODDS_API_KEY"] == "configured"
    assert "super-secret-football" not in str(diag.values())
    assert "super-secret-odds" not in str(diag.values())
    assert s.is_football_configured and s.is_odds_configured


def test_diagnose_reports_missing():
    s = Settings(FOOTBALL_API_KEY="", ODDS_API_KEY="")
    diag = s.diagnose()
    assert diag["FOOTBALL_API_KEY"] == "missing"
    assert diag["ODDS_API_KEY"] == "missing"
    assert diag["DATABASE"] == "configured"


# --- Response mapping: missing optional fields + malformed payloads ---


@pytest.mark.asyncio
async def test_sparse_fixture_maps_to_defaults():
    p = ApiFootballProvider(api_key="x", client=_mock_client(SPARSE_FIXTURE))
    fixtures = await p.get_fixtures("39", "2024")
    assert len(fixtures) == 1
    fx = fixtures[0]
    assert fx.status == "SCHEDULED"  # unknown short code -> safe default
    assert fx.kickoff_at is None and fx.home_score is None and fx.minute is None
    assert fx.home_team_name == ""  # missing -> absent, never invented


@pytest.mark.asyncio
async def test_malformed_rows_are_skipped_not_fatal():
    p = ApiFootballProvider(api_key="x", client=_mock_client({"response": ["junk", 42, None]}))
    assert await p.get_fixtures("39", "2024") == []
    p2 = OddsApiProvider(api_key="x", client=_mock_client([None, "junk", {"bookmakers": "nope"}]))
    assert await p2.get_odds() == []


@pytest.mark.asyncio
async def test_statistics_events_lineups_mapping():
    p = ApiFootballProvider(api_key="x", client=_mock_client(STATS_RESPONSE))
    stats = await p.get_match_statistics("12345")
    assert {(s.team, s.stat_name, s.stat_value) for s in stats} == {
        ("home", "shots_on_goal", "5"), ("home", "ball_possession", "54%"),
        ("away", "shots_on_goal", "3")}

    p.client = _mock_client(EVENTS_RESPONSE)
    events = await p.get_match_events("12345")
    assert events[0].player_name == "Saka" and events[0].minute == 23
    assert events[1].player_name == "" and events[1].minute is None  # absent stays absent

    p.client = _mock_client(LINEUPS_RESPONSE)
    lineup = await p.get_lineups("12345")
    by_name = {lu.player_name: lu.is_starting for lu in lineup}
    assert by_name == {"Raya": 1, "Kepa": 0}


# --- Provider failure modes: timeout, persistent 429 ---


@pytest.mark.asyncio
async def test_provider_timeout_surfaces(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(get_settings(), "PROVIDER_RETRY_BASE_SECONDS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connection timed out")

    reset_limiter()
    with pytest.raises(ProviderHTTPError):
        await logged_request("p_timeout", "GET", "http://x.test/",
                             client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    reset_limiter()


@pytest.mark.asyncio
async def test_persistent_429_raises_with_status():
    client = _mock_client({}, status=429, headers={"Retry-After": "0"})
    reset_limiter()
    with pytest.raises(ProviderHTTPError) as ei:
        await logged_request("p_429x", "GET", "http://x.test/", client=client)
    assert ei.value.status_code == 429
    reset_limiter()


@pytest.mark.asyncio
async def test_client_error_not_retried():
    """422/400 must fail fast — retrying burns provider quota."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422, json={"message": "Invalid market"})

    reset_limiter()
    with pytest.raises(ProviderHTTPError) as ei:
        await logged_request("p_422", "GET", "http://x.test/",
                             client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert ei.value.status_code == 422
    assert calls["n"] == 1
    reset_limiter()


def test_secret_redaction():
    from app.logging_config import redact_secrets

    dirty = "GET https://odds.test/odds?apiKey=abcdef123&regions=uk 200 OK"
    clean = redact_secrets(dirty)
    assert "abcdef123" not in clean and "apiKey=***" in clean
    assert redact_secrets("no secrets here") == "no secrets here"


# --- Quota information ---


def test_quota_header_extraction():
    assert extract_quota_remaining(httpx.Headers({"x-requests-remaining": "481"})) == 481.0
    assert extract_quota_remaining(httpx.Headers({"X-RateLimit-Remaining": "97"})) == 97.0
    assert extract_quota_remaining(httpx.Headers({})) is None
    assert extract_quota_remaining(httpx.Headers({"x-requests-remaining": "n/a"})) is None
    assert extract_quota_remaining(object()) is None


@pytest.mark.asyncio
async def test_quota_persisted_on_request_log():
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(get_engine())
    reset_limiter()
    client = _mock_client({"ok": True}, headers={"x-requests-remaining": "479"})
    await logged_request("p_quota", "GET", "http://x.test/", db_session_factory=get_session_local,
                         client=client)
    s2 = get_session_local()()
    try:
        row = s2.query(ProviderRequestLog).filter_by(provider="p_quota").one()
        assert row.success is True and row.status_code == 200
        assert row.quota_remaining == 479.0
        assert row.response_time_ms >= 0
    finally:
        s2.close()
    reset_limiter()


def test_league_sport_key_mapping():
    assert LEAGUE_SPORT_KEYS["EPL"] == "soccer_epl"
    assert LEAGUE_SPORT_KEYS["UCL"] == "soccer_uefa_champs_league"
    assert len(LEAGUE_SPORT_KEYS) == 6


# --- Odds history: multi-step movement with manual verification ---


def test_odds_movement_chain_matches_manual_math(db, sample_match):
    from datetime import datetime, timedelta, timezone

    from app.db.models.odds import OddsSelection

    base = datetime(2025, 4, 30, 10, 0, tzinfo=timezone.utc)
    for i, price in enumerate((1.80, 1.76, 1.72)):
        ingestion.store_odds_snapshots(
            db, sample_match.id,
            [OddsSnapshotDTO(bookmaker="B", bookmaker_provider_id="b", market_type="h2h",
                             timestamp=base + timedelta(minutes=5 * i),
                             selections=[OddsSelectionDTO(selection="home", odds=price)])],
            "odds_api")
    prices = sorted(s.odds for s in db.query(OddsSelection).all())
    assert prices == [1.72, 1.76, 1.80]  # every legitimate move stored, none overwritten

    m = movement(1.80, 1.72, minutes_elapsed=10.0)
    assert m["opening"] == 1.80 and m["current"] == 1.72
    assert m["absolute_change"] == pytest.approx(-0.08)
    assert m["percentage_change"] == pytest.approx(round(-0.08 / 1.80 * 100, 2))  # rounded to 2dp by design
    assert m["direction"] == "down"
    assert m["velocity_per_hour"] == pytest.approx(-0.48)

    # Exact re-delivery deduplicates.
    ingestion.store_odds_snapshots(
        db, sample_match.id,
        [OddsSnapshotDTO(bookmaker="B", bookmaker_provider_id="b", market_type="h2h",
                         timestamp=base, selections=[OddsSelectionDTO(selection="home", odds=1.80)])],
        "odds_api")
    assert sorted(s.odds for s in db.query(OddsSelection).all()) == [1.72, 1.76, 1.80]


# --- Live match update: one row, mutable fields refresh ---


@pytest.mark.asyncio
async def test_live_match_update_no_duplicates(db):
    from app.services.dtos import FixtureDTO
    from datetime import datetime, timezone

    fx = FixtureDTO(provider="api_football", provider_match_id="12345",
                    home_team_id="42", home_team_name="Arsenal",
                    away_team_id="49", away_team_name="Chelsea",
                    kickoff_at=datetime(2025, 5, 1, 18, 0, tzinfo=timezone.utc),
                    status="SCHEDULED")
    ingestion.sync_fixtures(db, [fx])
    p = ApiFootballProvider(api_key="x", client=_mock_client(LIVE_FIXTURE))
    live = await p.get_match("12345")
    assert live is not None and live.status == "LIVE" and live.minute == 63
    ingestion.sync_fixtures(db, [live])
    ingestion.sync_fixtures(db, [live])  # repeat -> still one row
    rows = db.query(Match).filter_by(provider_match_id="12345").all()
    assert len(rows) == 1
    assert (rows[0].status, rows[0].minute, rows[0].home_score) == ("LIVE", 63, 1)


# --- Odds->match linking ---


def test_find_match_for_odds_event(db, sample_match):
    from app.db.models.core import Team

    home = db.get(Team, sample_match.home_team_id)
    away = db.get(Team, sample_match.away_team_id)
    found = ingestion.find_match_for_odds_event(db, home.name, away.name)
    assert found is not None and found.id == sample_match.id
    # Case-insensitive exact still links; unknown teams never link.
    assert ingestion.find_match_for_odds_event(db, home.name.upper(), away.name.lower()) is not None
    assert ingestion.find_match_for_odds_event(db, "Nope FC", away.name) is None
    assert ingestion.find_match_for_odds_event(db, None, away.name) is None


# --- Data-quality report ---


def test_data_quality_report(db, sample_match):
    from scripts.data_quality_report import build_report

    report = build_report(db)
    assert report["matches"] == 1 and report["teams"] == 2 and report["leagues"] == 1
    assert report["matches_missing_teams"] == 0
    assert report["matches_missing_kickoff"] == 0
    assert report["duplicate_provider_match_ids"] == 0
    assert report["has_xg"] is False  # absent reported, never invented


# --- Step 8: cache + single-flight ---


def test_cache_backend_is_explicit():
    status = cache_mod.backend_status()
    assert status["backend"] in ("redis", "memory")
    assert status["fallback_active"] == (status["backend"] == "memory")
    assert cache_mod.backend_name() == status["backend"]


@pytest.mark.asyncio
async def test_single_flight_dedupes_concurrent_requests():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"ok": True})

    reset_limiter()
    cache_mod.reset_cache()
    transport = httpx.MockTransport(handler)
    clients = [httpx.AsyncClient(transport=transport) for _ in range(3)]
    try:
        results = await asyncio.gather(*[
            logged_request("p_single", "GET", "http://x.test/same",
                           cache_key="single:test", cache_ttl=60, client=c)
            for c in clients
        ])
    finally:
        for c in clients:
            await c.aclose()
    assert all(r == {"ok": True} for r in results)
    assert calls["n"] == 1  # one provider hit for three concurrent callers
    reset_limiter()
    cache_mod.reset_cache()
