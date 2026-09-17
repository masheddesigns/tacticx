"""Phase 7 tests: upcoming discovery/sync, lifecycle, cutoff safety, market
append-only, source health, batch, evaluation, integrity. No live network."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.enums import MatchStatus
from app.db.models.lifecycle import PredictionEvaluation, PredictionVersion
from app.services.features.temporal import TemporalMode
from app.services.lifecycle import cached, health, monitoring, sync, upcoming, versions
from app.services.lifecycle.evaluate import (
    evaluate_completed_predictions,
    evaluate_prediction,
)
from app.services.lifecycle.odds_refresh import (
    get_current_market_state,
    refresh_odds,
    store_snapshot,
)
from app.services.lifecycle.upcoming_predictions import UpcomingPredictionService
from app.services.dtos import OddsSnapshotDTO, OddsSelectionDTO

STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P7"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p7", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p7-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _add(db, league, teams, home, away, kickoff, hs=None, aws=None,
         status="SCHEDULED"):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=kickoff, status=status, home_score=hs, away_score=aws,
        provider="test", provider_match_id=f"p7-{home}-{away}-{kickoff.isoformat()}")
    db.add(match)
    db.commit()
    return match


def _history(db, code="P7H", teams=("A", "B", "C", "D"), start_day=1, rounds=6):
    league = _league(db, code)
    names = list(teams)
    team_map = _teams(db, league, names)
    base = datetime(2024, 8, start_day)
    scores = [(2, 0), (1, 1), (0, 1), (3, 1), (1, 0), (2, 2)]
    idx = day = 0
    for round_no in range(rounds):
        order = names[round_no:] + names[:round_no]
        for i in range(0, len(order) - 1, 2):
            hs, aws = scores[idx % len(scores)]
            idx += 1
            _add(db, league, team_map, order[i], order[i + 1],
                 base + timedelta(days=day), hs, aws, status="FINISHED")
            day += 1
    return league, team_map, base + timedelta(days=day + 1)


# -- upcoming discovery ------------------------------------------------------

def test_normalize_kickoff_utc_and_dst():
    from datetime import timezone as tz

    aware = datetime(2024, 6, 1, 15, 0, tzinfo=tz.utc)
    utc, original, _ = upcoming.normalize_kickoff(aware, "UTC")
    assert utc == aware and original == str(aware)
    # +02:00 zone (DST) normalizes to 13:00 UTC.
    berlin = datetime.fromisoformat("2024-06-01T15:00:00+02:00")
    utc2, _, _ = upcoming.normalize_kickoff(berlin, "Europe/Berlin")
    assert (utc2.hour, utc2.minute) == (13, 0)
    # Midnight boundary preserved, not shifted.
    midnight = datetime.fromisoformat("2024-06-02T00:00:00+02:00")
    utc3, _, _ = upcoming.normalize_kickoff(midnight, "Europe/Berlin")
    assert (utc3.day, utc3.hour) == (1, 22)
    # Missing stays missing.
    assert upcoming.normalize_kickoff(None) == (None, "", "")


def test_normalize_status_unknown_never_forced():
    assert upcoming.normalize_status("NS") == "scheduled"
    assert upcoming.normalize_status("PST") == "postponed"
    assert upcoming.normalize_status("CANC") == "cancelled"
    assert upcoming.normalize_status("FT") == "finished"
    assert upcoming.normalize_status("weird-status-xyz") == "unknown"


class _FakeSource:
    name = "fake"

    def __init__(self, records):
        self._records = records

    async def fetch(self, from_time, to_time, league_code=None):
        return [r for r in self._records
                if r.kickoff_utc is not None and from_time <= r.kickoff_utc <= to_time]


def _rec(home, away, kickoff, status="scheduled", league="P7SYNC", source="fake",
         sid="s1"):
    return upcoming.UpcomingMatch(
        league_code=league, home_team=home, away_team=away,
        kickoff_utc=kickoff, kickoff_source=str(kickoff), kickoff_timezone="UTC",
        status=status, source=source, source_match_id=sid)


def test_sync_dedup_and_idempotency(db):
    league = _league(db, "P7SYNC")
    _teams(db, league, ("Arsenal", "Chelsea"))
    kickoff = datetime(2025, 1, 5, 15, 0, tzinfo=timezone.utc)
    records = [_rec("Arsenal", "Chelsea", kickoff, sid="s1"),
               _rec("Arsenal FC", "Chelsea", kickoff, sid="s2")]
    first = sync.sync_upcoming_matches(db, records)
    assert first.received == 2 and first.inserted == 1
    assert db.query(Match).filter_by(league_id=league.id).count() == 1
    second = sync.sync_upcoming_matches(db, records)
    assert second.inserted == 0
    assert db.query(Match).filter_by(league_id=league.id).count() == 1


def test_sync_status_refresh_and_postponed(db):
    league = _league(db, "P7STAT")
    _teams(db, league, ("H", "A"))
    kickoff = datetime(2025, 2, 1, 15, 0, tzinfo=timezone.utc)
    sync.sync_upcoming_matches(db, [_rec("H", "A", kickoff, league="P7STAT")])
    match = db.query(Match).filter_by(league_id=league.id).one()
    assert match.status == MatchStatus.SCHEDULED.value
    later = kickoff + timedelta(hours=2)
    stats = sync.sync_upcoming_matches(
        db, [_rec("H", "A", later, status="postponed", league="P7STAT")])
    assert stats.updated == 1
    db.refresh(match)
    assert match.status == MatchStatus.POSTPONED.value


def test_sync_unresolved_teams_skipped_not_invented(db):
    _league(db, "P7UNR")
    kickoff = datetime(2025, 3, 1, 15, 0, tzinfo=timezone.utc)
    stats = sync.sync_upcoming_matches(
        db, [_rec("Nonexistent Rovers", "Imaginary United", kickoff, league="P7UNR")])
    assert stats.inserted == 0 and stats.skipped == 1


# -- lifecycle -----------------------------------------------------------------

def test_version_create_refresh_lock_flow(db):
    league, teams, _ = _history(db, code="P7LC")
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    target = _add(db, league, teams, "A", "B", future)
    service = UpcomingPredictionService()
    v1 = service.predict_one(db, target.id, cutoff=future - timedelta(days=1))
    assert v1["status"] in ("success", "partial")
    assert v1["version"]["version_number"] == 1
    assert v1["version"]["state"] == "generated"
    assert v1["quality"]["temporal_quality"] == "verified"
    cached = service.predict_one(db, target.id, cutoff=future - timedelta(days=1))
    assert cached["cached"] is True
    refreshed = service.refresh_one(db, target.id)
    assert refreshed["version"]["version_number"] == 2
    hist = versions.history(db, target.id)
    assert [v.state for v in hist] == ["superseded", "refreshed"]
    assert refreshed["diff"]["probability_changes"]["home_win"]["wording"] == \
        "probability shifted"
    # v1 prediction row unchanged by refresh.
    from app.db.models.predictions import Prediction

    v1_row = db.get(Prediction, hist[0].prediction_id)
    assert v1_row is not None


def test_kickoff_lock_and_post_kickoff_refusal(db):
    league, teams, kickoff = _history(db, code="P7LOCK")
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    target = _add(db, league, teams, "A", "B", past)
    service = UpcomingPredictionService()
    made = service.predict_one(db, target.id, cutoff=past - timedelta(hours=2))
    assert made["status"] in ("success", "partial")
    assert versions.lock_due_predictions(db, target.id) == 1
    assert versions.latest_version(db, target.id).state == "locked"
    refused = service.refresh_one(db, target.id)
    assert refused["status"] == "failed" and "kickoff passed" in refused["error"]
    with pytest.raises(ValueError):
        versions.generate_version(db, target.id, datetime.now(timezone.utc),
                                  STRICT)


def test_readiness_gate_levels(db):
    league, teams, kickoff = _history(db, code="P7RDY")
    target = _add(db, league, teams, "A", "B", kickoff)
    gate = versions.readiness_gate(db, target.id, kickoff - timedelta(days=1),
                                   STRICT)
    assert gate["readiness"] in ("ready", "partial")
    lonely_league = _league(db, "P7LONELY")
    lonely_teams = _teams(db, lonely_league, ("X", "Y"))
    lonely = _add(db, lonely_league, lonely_teams, "X", "Y",
                  datetime(2025, 5, 1, 15, 0))
    gate2 = versions.readiness_gate(db, lonely.id, datetime(2025, 4, 1), STRICT)
    assert gate2["readiness"] == "insufficient_data"
    with pytest.raises(ValueError):
        versions.generate_version(db, lonely.id, datetime(2025, 4, 1), STRICT)


def test_batch_partial_failure_isolation(db):
    league, teams, _ = _history(db, code="P7BATCH")
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    good = _add(db, league, teams, "A", "B", future)
    lonely_league = _league(db, "P7BATCH2")
    lonely_teams = _teams(db, lonely_league, ("X", "Y"))
    bad = _add(db, lonely_league, lonely_teams, "X", "Y", future)
    service = UpcomingPredictionService()
    # Direct per-match calls: one succeeds, one fails, neither corrupts.
    ok_result = service.predict_one(db, good.id, cutoff=future - timedelta(days=1))
    fail_result = service.predict_one(db, bad.id, cutoff=future - timedelta(days=1))
    assert ok_result["status"] in ("success", "partial")
    assert fail_result["status"] == "failed"
    assert versions.latest_version(db, good.id) is not None
    assert versions.latest_version(db, bad.id) is None


# -- market append-only + current state -------------------------------------------

def _dto(home="H", away="A", minute_ago=60, live=False):
    return OddsSnapshotDTO(
        bookmaker="TestBook", bookmaker_provider_id="TB", market_type="h2h",
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minute_ago),
        is_live=live,
        selections=[OddsSelectionDTO(selection="home", odds=2.0),
                    OddsSelectionDTO(selection="draw", odds=3.5),
                    OddsSelectionDTO(selection="away", odds=4.0)],
        home_team=home, away_team=away)


def test_odds_append_only_and_duplicate_poll(db):
    league = _league(db, "P7ODDS")
    teams = _teams(db, league, ("H", "A"))
    target = _add(db, league, teams, "H", "A", datetime(2025, 6, 1, 15, 0))
    dto = _dto()
    dto.home_team, dto.away_team = None, None  # force direct store path
    sid, created, _ = store_snapshot(db, target.id, dto)
    assert created is True
    sid2, created2, note = store_snapshot(db, target.id, dto)
    assert created2 is False and sid2 == sid
    from app.db.models.odds import OddsSnapshot

    assert db.query(OddsSnapshot).filter_by(match_id=target.id).count() == 1
    # Unknown timestamp refused (strict).
    dto2 = _dto()
    dto2.timestamp = None
    _, created3, note3 = store_snapshot(db, target.id, dto2)
    assert created3 is False and "refused" in note3


def test_current_market_state_excludes_closing(db):
    from app.db.models.odds import Bookmaker, OddsSnapshot

    league = _league(db, "P7CUR")
    teams = _teams(db, league, ("H", "A"))
    target = _add(db, league, teams, "H", "A", datetime(2025, 7, 1, 15, 0))
    dto = _dto()
    dto.home_team, dto.away_team = None, None
    store_snapshot(db, target.id, dto)
    snap = db.query(OddsSnapshot).filter_by(match_id=target.id).one()
    snap.source_market_id = "TBC:h2h"  # mark the only snapshot closing
    db.commit()
    state = get_current_market_state(db, target.id)
    assert state["consensus"]["bookmakers_used"] == 0
    assert any(b["is_closing"] for b in state["bookmakers"])


# -- source health ------------------------------------------------------------------

def test_health_success_failure_states(db):
    row = health.record_success(db, "fake_src", records=5, latency_ms=12.0)
    assert row.state == "healthy" and row.records_received == 5
    health.record_failure(db, "fake_src", "boom")
    health.record_failure(db, "fake_src", "boom")
    row = health.record_failure(db, "fake_src", "boom")
    assert row.state == "unavailable" and row.failure_count == 3
    assert "fake_src" in health.get_health(db)
    assert "boom" in health.get_health(db)["fake_src"]["last_error"]


def test_retries_backoff_and_auth_fail_fast():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result, meta = asyncio.run(health.run_with_retries("t", flaky, base_seconds=0.001))
    assert result == "ok" and meta["attempts"] == 3

    class AuthError(Exception):
        status = 401

    async def denied():
        raise AuthError("invalid api key")

    with pytest.raises(AuthError):
        asyncio.run(health.run_with_retries("t", denied, base_seconds=0.001))


def test_rate_limiter_per_provider_config():
    from app.services.caching import rate_limiter

    rate_limiter.reset_limiter()
    assert rate_limiter.acquire("api_football") is True
    assert rate_limiter.time_until_available("odds_api") == 0.0


# -- evaluation -----------------------------------------------------------------------

def test_evaluate_completed_and_idempotent(db):
    league, teams, _ = _history(db, code="P7EVAL")
    target = _add(db, league, teams, "A", "B", datetime(2024, 9, 20, 15, 0))
    service = UpcomingPredictionService()
    made = service.predict_one(db, target.id, cutoff=datetime(2024, 9, 19, 15, 0))
    assert made["status"] in ("success", "partial")
    target.status = MatchStatus.FINISHED.value
    target.home_score, target.away_score = 2, 1
    db.commit()
    stats = evaluate_completed_predictions(db, match_ids=[target.id])
    assert stats.inserted >= 1
    row = db.query(PredictionEvaluation).filter_by(
        prediction_id=made["version"]["prediction_id"]).one()
    assert row.actual_result == "home" and row.actual_home_goals == 2
    assert row.metrics["brier"] is not None
    rerun = evaluate_completed_predictions(db, match_ids=[target.id])
    assert rerun.inserted == 0


def test_evaluate_skips_unfinished_and_cancelled(db):
    league, teams, _ = _history(db, code="P7EVAL2")
    scheduled = _add(db, league, teams, "A", "B", datetime(2024, 10, 1, 15, 0))
    cancelled = _add(db, league, teams, "A", "B", datetime(2024, 10, 2, 15, 0),
                     status="CANCELLED")
    assert evaluate_prediction(db, 999999) is None
    stats = evaluate_completed_predictions(db, match_ids=[scheduled.id, cancelled.id])
    assert stats.inserted == 0


def test_monitoring_rolling_and_drift(db):
    league, teams, _ = _history(db, code="P7MON")
    service = UpcomingPredictionService()
    for i in range(4):
        target = _add(db, league, teams, "A", "B",
                      datetime(2024, 9, 21 + i, 15, 0))
        service.predict_one(db, target.id, cutoff=datetime(2024, 9, 20, 15, 0))
        target.status = MatchStatus.FINISHED.value
        target.home_score, target.away_score = 1, 0
        db.commit()
    evaluate_completed_predictions(db)
    rolling = monitoring.rolling_metrics(db, windows=[2, 50])
    assert rolling["windows"]["2"]["status"] == "ok"
    assert rolling["windows"]["50"]["status"] == "insufficient_sample"
    drift = monitoring.drift_status(db, reference_brier=0.60, window=2)
    assert drift["performance_status"] in ("normal", "watch", "degraded")
    assert drift["bands"]["watch_at"] == 0.02
    data = monitoring.data_drift(db)
    assert data["status"] in ("ok", "insufficient_sample")
    if data["status"] == "ok":
        assert "outcome_rates" in data
        assert abs(sum(data["outcome_rates"].values()) - 1.0) < 1e-3


# -- cache + integrity ------------------------------------------------------------------

def test_cached_fetch_stale_labeling():
    from app.services.caching import cache as cache_backend

    cache_backend.reset_cache()
    key = cached.cache_key("test", "x")
    first = cached.cached_fetch(key, 100, lambda: {"v": 1})
    assert first["data_status"] == "live" and not first["is_stale"]

    def broken():
        raise RuntimeError("source down")

    # Expire manually then reuse stale on failure.
    envelope = cache_backend.cache_get_json(key)
    envelope["expires_at"] = 0.0
    cache_backend.cache_set_json(key, envelope, 100)
    second = cached.cached_fetch(key, 100, broken)
    assert second["is_stale"] is True and second["data_status"] == "stale"
    assert second["data"] == {"v": 1}


def test_consistency_gate_rejects_malformed():
    from app.services.intelligence.schemas import ComposedPrediction
    from app.services.lifecycle.versions import _assert_consistent

    broken = ComposedPrediction(
        probabilities={"home": 0.5, "draw": 0.5, "away": 0.5},
        model={"version": "ensemble_v1"}, cutoff="2024-01-01")
    with pytest.raises(ValueError):
        _assert_consistent(broken)


# -- API ----------------------------------------------------------------------------------

def test_api_lifecycle_endpoints(client, db):
    league, teams, kickoff = _history(db, code="P7API")
    target = _add(db, league, teams, "A", "B", kickoff + timedelta(days=60))
    response = client.post(f"/api/v1/matches/{target.id}/predict",
                           json={"cutoff": (kickoff - timedelta(days=1)).isoformat()})
    assert response.status_code == 200, response.text[:300]
    v1 = response.json()["version"]
    response = client.get(f"/api/v1/matches/{target.id}/predictions")
    assert len(response.json()["data"]) == 1
    response = client.get(f"/api/v1/matches/{target.id}/prediction/latest")
    assert response.json()["version_number"] == 1
    response = client.get(f"/api/v1/matches/{target.id}/prediction/diff")
    assert response.status_code == 404  # single version: nothing to diff
    response = client.get("/api/v1/sources/health")
    assert response.status_code == 200
    response = client.get("/api/v1/sources/status")
    assert response.status_code == 200
    assert "football_configured" in response.json()["data"]
    response = client.post("/api/v1/lifecycle/evaluate", params={"limit": 10})
    assert response.status_code == 200
    response = client.get("/api/v1/lifecycle/monitoring")
    assert response.status_code == 200
    assert "rolling" in response.json()
    assert client.post("/api/v1/lifecycle/lock").status_code == 200
    assert client.get("/api/v1/matches/999999/predictions").status_code == 404


def test_end_to_end_lifecycle_fixture(db):
    """upcoming -> sync -> v1 -> market update -> v2 -> diff -> lock ->
    completion -> evaluation, with v1/v2 immutable throughout."""
    from app.db.models.predictions import Prediction

    league, teams, _ = _history(db, code="P7E2E")
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10)
    synced = sync.sync_upcoming_matches(
        db, [_rec("A", "B", future.replace(tzinfo=timezone.utc), league="P7E2E")])
    assert synced.inserted == 1
    target = db.query(Match).filter_by(league_id=league.id).order_by(
        Match.kickoff_at.desc()).first()
    service = UpcomingPredictionService()
    v1 = service.predict_one(db, target.id, cutoff=future - timedelta(days=2))
    assert v1["status"] in ("success", "partial")
    v1_probs = dict(db.get(Prediction, v1["version"]["prediction_id"]).probabilities)
    # Market update arrives pre-match.
    dto = _dto()
    dto.home_team, dto.away_team = None, None
    store_snapshot(db, target.id, dto)
    v2 = service.refresh_one(db, target.id)
    assert v2["version"]["version_number"] == 2
    assert v2["diff"]["from_version"] == 1
    # v1 untouched by everything after it.
    assert dict(db.get(Prediction, v1["version"]["prediction_id"]).probabilities) == v1_probs
    # Kickoff passes -> lock; completion -> evaluation without mutation.
    target.kickoff_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    db.commit()
    assert versions.lock_due_predictions(db, target.id) == 1
    target.status = MatchStatus.FINISHED.value
    target.home_score, target.away_score = 1, 1
    db.commit()
    stats = evaluate_completed_predictions(db, match_ids=[target.id])
    assert stats.inserted == 2  # v1 + v2 predictions evaluated
    assert dict(db.get(Prediction, v1["version"]["prediction_id"]).probabilities) == v1_probs
    row = db.query(PredictionEvaluation).filter_by(
        prediction_id=v1["version"]["prediction_id"]).one()
    assert row.actual_result == "draw"


class _FailingProvider:
    def __init__(self, mode):
        self.mode = mode
        self.calls = 0

    async def get_fixtures(self, *args, **kwargs):
        self.calls += 1
        if self.mode == "timeout":
            raise asyncio.TimeoutError("timed out")
        if self.mode == "401":
            exc = RuntimeError("401 Unauthorized: invalid api key")
            exc.status = 401
            raise exc
        if self.mode == "429":
            exc = RuntimeError("429 rate limit exceeded")
            exc.status = 429
            raise exc
        if self.mode == "malformed":
            raise ValueError("not JSON")
        if self.mode == "empty":
            return []
        raise AssertionError("unknown mode")


def test_provider_failure_modes_fail_safely(db):
    from app.services.lifecycle.upcoming import ApiFootballUpcomingSource

    start = datetime.now(timezone.utc)
    end = start + timedelta(days=2)
    for mode in ("timeout", "401", "429", "malformed", "empty"):
        provider = _FailingProvider(mode)
        source = ApiFootballUpcomingSource(
            provider=provider, league_map={"X": {"provider_id": "1", "season": "2024"}})
        grouped = upcoming.fetch_all([source], start, end)
        assert grouped["api_football"] == []
        row = health.record_failure(db, f"src-{mode}", f"{mode} simulated")
        assert row.state in ("degraded", "unavailable")
    # 401 fails fast (single attempt, no retry loop).
    provider = _FailingProvider("401")
    with pytest.raises(RuntimeError):
        asyncio.run(health.run_with_retries("t", provider.get_fixtures,
                                            base_seconds=0.001))
    assert provider.calls == 1
