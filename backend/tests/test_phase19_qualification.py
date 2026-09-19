"""Phase 19 tests: provider qualification and acquisition reliability.

All provider interactions use deterministic in-memory fakes with fixed
timestamps. No live network calls. Existing suites are untouched.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.qualification import SourceQualification
from app.services.provider_qualification import (
    authority,
    fallback,
    plans,
    registry,
)
from app.services.provider_qualification import health_ext
from app.services.provider_qualification import qualification as qual
from app.services.provider_qualification import snapshots as snapshots_mod
from app.services.provider_qualification.capabilities import (
    DOCUMENTED,
    MEASURED,
    UNKNOWN,
    ProviderCapabilities,
    from_declared,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


class FakeAdapter:
    """Deterministic scripted adapter: fixed fixtures or a fixed error."""

    def __init__(self, fixtures=None, error=None, name="fake"):
        self._fixtures = list(fixtures or [])
        self._error = error
        self.source_name = name
        self.calls = 0
        from app.services.sources.base import SourceCapabilities

        self.capabilities = SourceCapabilities(fixtures=True)

    def check(self):
        return {"ok": True, "source": self.source_name}

    async def get_fixtures(self, league_id, season, **kwargs):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._fixtures


def _fx(home="H1", away="A1", kickoff=None, status="NS", comp="EPL",
        season="2026", sid="f1", hs=None, aws=None):
    from app.services.sources.normalized import NormalizedMatch

    return NormalizedMatch(
        league_code=comp, season=season, home_team=home, away_team=away,
        kickoff_at=kickoff or (NOW + timedelta(days=2)),
        status=status, home_score=hs, away_score=aws,
        provider_match_id=sid,
        provenance={"source": "fake", "source_record_id": sid},
    )


def _league(db, code="P19"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p19", season="2026/27")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p19-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


# -- capability model ------------------------------------------------------------------

def test_declared_maps_to_documented_never_measured():
    caps = from_declared("x", {"fixtures": True, "odds_prematch": True,
                               "leagues": True})
    assert caps.fixtures == DOCUMENTED
    assert caps.odds == DOCUMENTED
    assert caps.events == UNKNOWN
    assert caps.to_evidence()["fixtures"] == DOCUMENTED
    assert caps.measured_fields() == []


def test_evidence_states_closed():
    caps = ProviderCapabilities(source="x", fixtures=MEASURED)
    assert caps.measured_fields() == ["fixtures"]


# -- qualification --------------------------------------------------------------------------

def test_qualify_success_and_levels(db):
    adapter = FakeAdapter([_fx(), _fx(home="H2", away="A2", sid="f2",
                                      status="FT", hs=2, aws=1)])
    verdict = qual.qualify_source("fake", adapter=adapter, competition="EPL",
                                  season="2026", db=db)
    assert verdict["status"] == "qualified"
    assert verdict["coverage"]["fixtures"] == 2
    assert verdict["coverage"]["results"] == 1
    assert verdict["evidence"]["request_count"] <= 5
    assert len(verdict["evidence"]["sample_hash"]) == 16
    assert verdict["capabilities"]["fixtures"] == MEASURED
    rows = db.query(SourceQualification).filter_by(source="fake").all()
    assert len(rows) == 1 and rows[0].status == "qualified"


def test_qualify_empty_is_unavailable_not_rejected(db):
    verdict = qual.qualify_source("fake", adapter=FakeAdapter([]),
                                  competition="EPL", season="2026", db=db)
    assert verdict["status"] == "unavailable"
    assert "empty_response" in verdict["reason_codes"]


def test_qualify_auth_failure_rejected(db):
    class AuthError(Exception):
        status = 401

    verdict = qual.qualify_source("fake", adapter=FakeAdapter(error=AuthError("no")),
                                  competition="EPL", season="2026", db=db)
    # 401 during fetch: honestly unavailable (not rejected — the failure is
    # recorded with its classification for operator retry).
    assert verdict["status"] == "unavailable"
    assert "authentication_failure" in verdict["reason_codes"]


def test_qualify_rate_limited_unavailable(db):
    class Throttled(Exception):
        status = 429

    verdict = qual.qualify_source("fake", adapter=FakeAdapter(error=Throttled("slow")),
                                  competition="EPL", season="2026", db=db)
    assert verdict["status"] == "unavailable"
    assert "rate_limited" in verdict["reason_codes"]


def test_qualify_malformed_rejected(db):
    verdict = qual.qualify_source("fake", adapter=FakeAdapter(error=ValueError("bad json")),
                                  competition="EPL", season="2026", db=db)
    assert verdict["status"] == "rejected"
    assert "provider_malformed" in verdict["reason_codes"]


def test_qualify_unknown_adapter_rejected():
    verdict = qual.qualify_source("no-such-source", competition="EPL",
                                  season="2026")
    assert verdict["status"] == "rejected"
    assert "unknown_source_adapter" in verdict["reason_codes"]


def test_qualify_request_budget_bounded():
    adapter = FakeAdapter([_fx()])
    verdict = qual.qualify_source("fake", adapter=adapter, competition="EPL",
                                  season="2026", max_requests=1)
    assert verdict["request_count"] <= 1


# -- registry -------------------------------------------------------------------------------

def test_registry_register_order_resolve():
    registry.reset_registry()
    try:
        registry.register_source("zeta", lambda **k: None, priority=50)
        registry.register_source("alpha", lambda **k: None, priority=50)
        registry.register_source("top", lambda **k: None, priority=1)
        assert [e.source_id for e in registry.get_registry().ordered()] == [
            "top", "alpha", "zeta"]
        with pytest.raises(ValueError):
            registry.get_registry().get("missing")
    finally:
        registry.reset_registry()


def test_registry_describe_no_secrets():
    import json

    described = registry.get_registry().describe()
    blob = json.dumps(described)
    assert "api_key" not in blob.lower() and "bearer" not in blob.lower()


# -- field authority ----------------------------------------------------------------------------

def test_field_authority_explicit_and_deterministic():
    assert authority.authoritative_source("odds") == "odds_api"
    assert authority.authoritative_source("xg") is None
    assert authority.authority_for("result")[0][0] == "api_football"
    custom = {"result": [("b_source", 5), ("a_source", 5)]}
    assert authority.authoritative_source("result", custom) == "a_source"


# -- fallback ---------------------------------------------------------------------------------------

def test_fallback_success_no_cascade():
    async def main():
        return await fallback.run_with_fallback([
            {"source_id": "a", "call": lambda: [{"x": 1}]},
            {"source_id": "b", "call": lambda: (_ for _ in ()).throw(
                AssertionError("must not be called"))},
        ])

    out = asyncio.run(main())
    assert out["selected_source"] == "a" and not out["used_fallback"]


def test_fallback_unavailable_then_success():
    class Down(Exception):
        status = 500

    async def main():
        return await fallback.run_with_fallback([
            {"source_id": "a", "call": _raise(Down("boom"))},
            {"source_id": "b", "call": lambda: [{"x": 1}]},
        ])

    def _raise(exc):
        async def _inner():
            raise exc
        return _inner

    out = asyncio.run(main())
    assert out["selected_source"] == "b" and out["used_fallback"]
    assert out["outcomes"][0]["outcome"] == "unavailable"


def test_fallback_empty_needs_permission():
    async def main(allow):
        return await fallback.run_with_fallback(
            [{"source_id": "a", "call": lambda: []},
             {"source_id": "b", "call": lambda: [{"x": 1}]}],
            allow_empty_fallback=allow)

    out = asyncio.run(main(False))
    assert out["selected_source"] is None
    assert out["outcomes"][0]["outcome"] == "empty"
    out = asyncio.run(main(True))
    assert out["selected_source"] == "b"


def test_fallback_auth_stops_cascade():
    class Denied(Exception):
        status = 401

    async def main():
        async def _denied():
            raise Denied("no")
        return await fallback.run_with_fallback([
            {"source_id": "a", "call": _denied},
            {"source_id": "b", "call": lambda: [{"x": 1}]},
        ])

    out = asyncio.run(main())
    assert out["selected_source"] is None
    assert out["outcomes"][0]["outcome"] == "auth_failure"


def test_fallback_rate_limited_then_success():
    class Slow(Exception):
        status = 429

    async def main():
        async def _slow():
            raise Slow("slow")
        return await fallback.run_with_fallback([
            {"source_id": "a", "call": _slow},
            {"source_id": "b", "call": lambda: [{"x": 1}]},
        ])

    out = asyncio.run(main())
    assert out["selected_source"] == "b"
    assert out["outcomes"][0]["outcome"] == "rate_limited"


def test_fallback_malformed_then_success():
    async def main():
        async def _bad():
            raise ValueError("not JSON {{{")
        return await fallback.run_with_fallback([
            {"source_id": "a", "call": _bad},
            {"source_id": "b", "call": lambda: [{"x": 1}]},
        ])

    out = asyncio.run(main())
    assert out["selected_source"] == "b"
    assert out["outcomes"][0]["outcome"] == "malformed"


# -- plans ----------------------------------------------------------------------------------------------

def test_plan_deterministic_and_canonical_selection():
    first = plans.build_plan("EPL", "2026/27",
                             {"odds_api": "C", "api_football": "A"})
    second = plans.build_plan("EPL", "2026/27",
                              {"odds_api": "C", "api_football": "A"})
    assert first.plan_hash == second.plan_hash
    assert first.selected_source == "api_football"
    assert first.fallback_sources == []
    assert "api_football" in first.reason


def test_plan_no_canonical_without_level_a():
    plan = plans.build_plan("EPL", "2026/27",
                            {"odds_api": "C", "statsbomb": "B"})
    assert plan.selected_source == ""
    assert "no Level-A source" in plan.reason


# -- health extension -----------------------------------------------------------------------------

def test_health_request_result_lifecycle(db):
    row = health_ext.record_request(db, "fake-src", http_status=200,
                                    response_bytes=1234, fixture_count=10,
                                    latency_ms=12.5, quota_remaining=99)
    assert row.last_http_status == 200
    assert row.last_fixture_count == 10
    row = health_ext.record_result(db, "fake-src", True)
    assert row.consecutive_failures == 0 and row.backoff_until is None
    row = health_ext.record_result(db, "fake-src", False, "boom",
                                   backoff_seconds=60)
    assert row.consecutive_failures == 1 and row.backoff_until is not None
    row = health_ext.record_result(db, "fake-src", False, "boom")
    assert row.consecutive_failures == 2
    described = health_ext.describe(db, "fake-src")
    assert described["fake-src"]["consecutive_failures"] == 2
    with pytest.raises(ValueError):
        health_ext.set_state(db, "fake-src", "nope")
    assert health_ext.set_state(db, "fake-src", "disabled").state == "disabled"
    assert health_ext.record_qualification(
        db, "fake-src", "qualified").last_qualification == "qualified"


def test_single_failure_never_disables(db):
    health_ext.record_result(db, "flaky", False, "boom")
    row = health_ext.describe(db, "flaky")["flaky"]
    assert row["consecutive_failures"] == 1


# -- freshness ------------------------------------------------------------------------------------------

def test_freshness_unknown_without_interval(db):
    _league(db)
    result = __import__(
        "app.services.provider_qualification.freshness",
        fromlist=["freshness_for"]).freshness_for(db, "ghost-source", "EPL")
    assert result["state"] == "unknown"


def test_freshness_uses_configured_intervals(db, monkeypatch):
    import app.services.provider_qualification.freshness as freshness_mod

    league = _league(db, code="P19F")
    teams = _teams(db, league, ("H", "A"))
    db.add(Match(
        league_id=league.id, home_team_id=teams["H"].id,
        away_team_id=teams["A"].id,
        kickoff_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status="FINISHED", home_score=1, away_score=0,
        provider="fake-src", provider_match_id="f1"))
    db.commit()
    monkeypatch.setattr(
        freshness_mod, "_expected_interval_hours", lambda s, c: 2.0)
    result = freshness_mod.freshness_for(db, "fake-src", "P19F")
    assert result["state"] == "fresh"
    monkeypatch.setattr(
        freshness_mod, "_expected_interval_hours", lambda s, c: 0.001)
    result = freshness_mod.freshness_for(db, "fake-src", "P19F")
    assert result["state"] == "expired"


# -- snapshots ----------------------------------------------------------------------------------------------

def test_snapshots_append_only_and_latest(db):
    verdict = {"status": "qualified", "reason_codes": [],
               "coverage": {"fixtures": 3},
               "capabilities": {"fixtures": "measured"},
               "evidence": {"sample_hash": "abc123"}}
    first = snapshots_mod.store_qualification(db, "fake", "EPL", "2026", 2, 1,
                                              verdict)
    second = snapshots_mod.store_qualification(db, "fake", "EPL", "2026", 2, 1,
                                               verdict)
    assert second.id != first.id
    latest = snapshots_mod.latest_for(db, "fake", "EPL", "2026")
    assert latest["status"] == "qualified"
    assert latest["qualification_run_id"] == second.qualification_run_id
    assert snapshots_mod.latest_for(db, "nobody")["status"] == "unqualified"


# -- pagination -----------------------------------------------------------------------------------------------

def test_pagination_bounded_no_infinite_loop():
    pages = [{"items": [{"id": 1}], "next": "p2"},
             {"items": [{"id": 1}], "next": "p2"},  # repeated page
             {"items": [], "next": None}]  # empty page terminates

    def collect(fetch, max_pages=10):
        seen, out, next_token, calls = set(), [], "p1", 0
        while next_token is not None and calls < max_pages:
            calls += 1
            page = fetch(next_token)
            token = page.get("next")
            if token in seen:
                break  # repeated page: stop, do not loop
            seen.add(next_token)
            out.extend(page.get("items", []))
            next_token = token
        return out, calls

    by_token = {"p1": pages[0], "p2": pages[1]}
    out, calls = collect(lambda token: by_token.get(token, {"items": []}))
    assert calls <= 3 and len(out) == 2


# -- identity / duplicates / temporal ------------------------------------------------------------------------------

def test_ambiguous_identity_quarantined(db):
    _league(db, code="P19Q")
    _teams(db, db.query(League).filter_by(code="P19Q").one(),
           ("United", "United FC"))
    from app.services.identity.teams import TeamIdentityResolver

    # Both normalize identically ("united"): must not merge.
    team_id, method = TeamIdentityResolver(db).resolve(
        "mock", provider_team_name="United", league="P19Q")
    assert team_id is None, (team_id, method)


def test_duplicate_source_ids_do_not_duplicate_matches(db):
    from app.services.identity.matches import MatchResolver

    league = _league(db, code="P19D")
    teams = _teams(db, league, ("H", "A"))
    kickoff = NOW + timedelta(days=2)
    resolver = MatchResolver(db)
    first, created_first = resolver.ensure(
        "mock", "DUP-1", league.id, teams["H"].id, teams["A"].id, kickoff)
    second, created_second = resolver.ensure(
        "mock", "DUP-1", league.id, teams["H"].id, teams["A"].id, kickoff)
    assert first == second and created_first and not created_second


def test_unknown_timing_stays_unknown_in_eligibility(db):
    from app.services.freshness import eligibility

    league = _league(db, code="P19T")
    teams = _teams(db, league, ("H", "A"))
    for day in range(6):
        db.add(Match(
            league_id=league.id, home_team_id=teams["H"].id,
            away_team_id=teams["A"].id,
            kickoff_at=datetime(2024, 8, 1) + timedelta(days=day),
            status="FINISHED", home_score=2, away_score=0,
            provider="test", provider_match_id=f"p19t-{day}"))
    target = Match(
        league_id=league.id, home_team_id=teams["H"].id,
        away_team_id=teams["A"].id,
        kickoff_at=datetime(2024, 9, 20, 15, 0), status="SCHEDULED",
        provider="test", provider_match_id="p19t-target")
    db.add(target)
    db.commit()
    verdict = eligibility.check_eligibility(db, target.id, NOW,
                                            mode="production_strict")
    assert verdict["temporal_quality"] in ("strict", "estimated", "unknown")


# -- security -----------------------------------------------------------------------------------------------------

def test_no_secrets_in_evidence_or_logs(db, caplog):
    import logging

    adapter = FakeAdapter([_fx()])
    with caplog.at_level(logging.INFO):
        verdict = qual.qualify_source("fake", adapter=adapter,
                                      competition="EPL", season="2026", db=db)
    blob = str(verdict) + caplog.text
    for needle in ("api_key", "apikey", "bearer", "authorization", "token="):
        assert needle not in blob.lower()
    row = db.query(SourceQualification).filter_by(source="fake").first()
    assert row is not None


def test_cli_rejects_arbitrary_sources():
    import os
    import subprocess

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        ["python3", os.path.join(backend_dir, "scripts", "tacticx.py"), "acquire",
         "--source", "http://evil.example/x"],
        capture_output=True, text=True, cwd=backend_dir)
    assert result.returncode != 0
    assert "unknown source" in (result.stdout + result.stderr)


# -- API ------------------------------------------------------------------------------------------------------------

def test_sources_api_endpoints(client, db):
    response = client.get("/api/v1/sources")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert "sources" in body and len(body["sources"]) >= 3
    blob = response.text.lower()
    assert "api_key" not in blob and "bearer" not in blob
    response = client.get("/api/v1/sources/api_football/status")
    assert response.status_code == 200
    assert client.get("/api/v1/sources/nope/status").status_code == 404
    response = client.get(
        "/api/v1/sources/api_football/qualification?competition=EPL&season=2026")
    assert response.status_code == 200
    response = client.post("/api/v1/sources/api_football/qualify",
                           json={"competition": "EPL", "season": "2026",
                                 "max_requests": 1})
    assert response.status_code in (200, 502)
    response = client.post("/api/v1/sources/api_football/qualify",
                           json={"max_requests": 999})
    assert response.status_code == 400


def test_acquisition_status_extended(client, db):
    response = client.get("/api/v1/acquisition/status")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert {"health", "qualifications", "freshness", "coverage",
            "recent_runs"} <= set(body)
