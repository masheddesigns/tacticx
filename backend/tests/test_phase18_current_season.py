"""Phase 18 tests: current-season acquisition pipeline.

Deterministic mock sources with fixed timestamps (never today's fixture
list). No live network calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models.acquisition import AcquisitionRun
from app.db.models.core import League, Match, Team
from app.db.models.freshness import MatchObservation
from app.services.acquisition import current_season
from app.services.acquisition.workflow import classify_failure, run_acquisition
from app.services.features.temporal import TemporalMode
from app.services.freshness import provenance as prov
from app.services.lifecycle.upcoming import UpcomingMatch

NOW = datetime.now(timezone.utc)


def _league(db, code="P18"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p18", season="2026/27")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p18-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _rec(home, away, kickoff, status="scheduled", league="P18",
         source="mock", sid="m1", season="2026/27"):
    return UpcomingMatch(
        league_code=league, season=season, home_team=home, away_team=away,
        kickoff_utc=kickoff, kickoff_source=str(kickoff),
        kickoff_timezone="UTC", status=status, source=source,
        source_match_id=sid)


class MockSource:
    """Deterministic provider fixture: fixed records, scripted failures."""

    name = "mock"

    def __init__(self, records=None, fail_with=None):
        self._records = list(records or [])
        self._fail_with = fail_with
        self.calls = 0

    async def fetch(self, from_time, to_time, league_code=None):
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
        return [r for r in self._records
                if r.kickoff_utc is not None and from_time <= r.kickoff_utc <= to_time
                and (league_code is None or r.league_code == league_code)]


# -- season mapping + status taxonomy ------------------------------------------------

def test_season_mapping_deterministic_and_versioned():
    assert current_season.SEASON_MAP_VERSION == 1
    assert current_season.canonical_season_for("api_football", "2026", "EPL") == "2026/27"
    assert current_season.canonical_season_for("api_football", "9999", "EPL") is None
    assert current_season.canonical_season_for("nope", "2026", "EPL") is None
    assert current_season.current_canonical_season(
        datetime(2026, 9, 19, tzinfo=timezone.utc)) == "2026/27"
    assert current_season.current_canonical_season(
        datetime(2026, 2, 1, tzinfo=timezone.utc)) == "2025/26"


def test_status_taxonomy_covers_all_states():
    assert current_season.normalize_source_status("api_football", "1H") == "live"
    assert current_season.normalize_source_status("api_football", "FT") == "finished"
    assert current_season.normalize_source_status("api_football", "ABD") == "abandoned"
    assert current_season.normalize_source_status("api_football", "PST") == "postponed"
    assert current_season.normalize_source_status("api_football", "CANC") == "cancelled"
    assert current_season.normalize_source_status("api_football", "NS") == "scheduled"
    assert current_season.normalize_source_status("api_football", "???") == "unknown"
    assert current_season.normalize_source_status("unknown-source", "NS") == "unknown"
    assert set(current_season.EXTENDED_STATUSES) == {
        "scheduled", "postponed", "cancelled", "abandoned",
        "live", "finished", "unknown"}


# -- acquisition: success / idempotency ----------------------------------------------

def test_acquire_success_and_idempotent_rerun(db):
    _league(db)
    _teams(db, db.query(League).filter_by(code="P18").one(), ("H1", "A1"))
    kickoff = NOW + timedelta(days=2)
    source = MockSource([_rec("H1", "A1", kickoff)])
    first = current_season.acquire_competition(db, "P18", "2026",
                                               sources=[source])
    assert first["status"] == "success"
    assert first["sources"]["mock"]["created"] == 1
    count_matches = db.query(Match).count()
    second = current_season.acquire_competition(db, "P18", "2026",
                                                sources=[source])
    assert second["sources"]["mock"]["created"] == 0
    assert db.query(Match).count() == count_matches
    runs = db.query(AcquisitionRun).filter_by(source="mock").all()
    assert len(runs) == 2
    assert all(r.status in ("success", "partial_success") for r in runs)


def test_acquire_all_statuses(db):
    _league(db, code="P18S")
    _teams(db, db.query(League).filter_by(code="P18S").one(),
           ("H", "A", "B", "C", "D", "E", "F", "G", "H2", "I", "J", "K"))
    kickoff = NOW + timedelta(days=1)
    records = [
        _rec("H", "A", kickoff, "scheduled", league="P18S", sid="s1"),
        _rec("B", "C", kickoff, "postponed", league="P18S", sid="s2"),
        _rec("D", "E", kickoff, "cancelled", league="P18S", sid="s3"),
        _rec("F", "G", kickoff - timedelta(days=40), "finished",
             league="P18S", sid="s4"),
        _rec("H2", "I", kickoff, "live", league="P18S", sid="s5"),
    ]
    result = current_season.acquire_competition(
        db, "P18S", "2026", sources=[MockSource(records)])
    assert result["status"] == "success"
    statuses = {m.provider_match_id: m.status
                for m in db.query(Match).all() if m.provider_match_id}
    assert statuses["s1"] == "SCHEDULED"
    assert statuses["s2"] == "POSTPONED"
    assert statuses["s3"] == "CANCELLED"
    assert statuses["s5"] == "LIVE"


def test_rescheduled_keeps_single_canonical_match(db):
    _league(db, code="P18R")
    _teams(db, db.query(League).filter_by(code="P18R").one(), ("H", "A"))
    kickoff = NOW + timedelta(days=3)
    source = MockSource([_rec("H", "A", kickoff, league="P18R", sid="r1")])
    current_season.acquire_competition(db, "P18R", "2026", sources=[source])
    moved = _rec("H", "A", kickoff + timedelta(hours=2), league="P18R",
                 sid="r1")
    current_season.acquire_competition(
        db, "P18R", "2026", sources=[MockSource([moved])])
    league = db.query(League).filter_by(code="P18R").one()
    rows = db.query(Match).filter_by(league_id=league.id).all()
    assert len(rows) == 1
    observations = db.query(MatchObservation).filter_by(
        match_id=rows[0].id, field="kickoff_at").all()
    assert len(observations) >= 1


def test_ambiguous_identity_quarantined_not_merged(db):
    _league(db, code="P18Q")
    _teams(db, db.query(League).filter_by(code="P18Q").one(), ("H", "A"))
    kickoff = NOW + timedelta(days=2)
    # Unknown teams must not invent canonical teams or merge.
    result = current_season.acquire_competition(
        db, "P18Q", "2026",
        sources=[MockSource([_rec("Mystery FC", "Unknown United", kickoff,
                                  league="P18Q")])])
    league = db.query(League).filter_by(code="P18Q").one()
    assert db.query(Match).filter_by(league_id=league.id).count() == 0
    assert result["status"] in ("success", "partial")


# -- partial success / failures ----------------------------------------------------------

def test_partial_success_isolation(db):
    _league(db, code="P18OK")
    _teams(db, db.query(League).filter_by(code="P18OK").one(), ("H", "A"))

    class Boom(Exception):
        pass

    good = MockSource([_rec("H", "A", NOW + timedelta(days=1),
                            league="P18OK")])
    good.name = "good"
    bad = MockSource(fail_with=Boom("down"))
    bad.name = "bad"
    report = current_season.acquire_current_season(
        db, leagues=["P18OK"], sources=[good, bad])
    assert report["status"] in ("success", "partial", "failed")
    league = db.query(League).filter_by(code="P18OK").one()
    assert db.query(Match).filter_by(league_id=league.id).count() == 1


def test_failure_classification_matrix():
    class Auth(Exception):
        status = 401

    class Forbidden(Exception):
        status = 403

    class Throttled(Exception):
        status = 429

    class Server(Exception):
        status = 503

    assert classify_failure(Auth("x")) == "authentication_failure"
    assert classify_failure(Forbidden("x")) == "authorization_failure"
    assert classify_failure(Throttled("x")) == "rate_limited"
    assert classify_failure(Server("x")) == "temporary_failure"
    assert classify_failure(TimeoutError("t")) == "temporary_failure"
    assert classify_failure(ValueError("schema changed")) == "provider_schema_error"
    # An empty *response object* is ambiguous (not proof of no fixtures);
    # only an empty record list maps to provider_empty (tested separately).
    assert classify_failure(ValueError("empty response")) == "temporary_failure"


def test_empty_response_not_proof_of_no_fixtures(db):
    _league(db)
    result = run_acquisition(db, "mock-empty", [], job="current_season")
    assert result["status"] == "empty"
    assert result["classification"] == "provider_empty"


# -- reconciliation / temporal ---------------------------------------------------------------

def test_reconciliation_runs_without_duplication(db):
    _league(db, code="P18C")
    _teams(db, db.query(League).filter_by(code="P18C").one(), ("H", "A"))
    kickoff = NOW + timedelta(days=2)
    current_season.acquire_competition(
        db, "P18C", "2026", sources=[MockSource([_rec("H", "A", kickoff,
                                                      league="P18C")])])
    from app.services.reconciliation.matches import reconcile_league

    first = reconcile_league(db, league_code="P18C", dry_run=False)
    before = db.query(Match).count()
    second = reconcile_league(db, league_code="P18C", dry_run=False)
    assert db.query(Match).count() == before
    assert first["conflicts"] == second["conflicts"]


def test_unknown_timing_never_upgraded(db):
    assert prov.classify(None, NOW) == "unknown"
    assert prov.classify(None, NOW, estimated=True,
                         anchor_before_cutoff=True) == "estimated_pre_cutoff"


# -- readiness ------------------------------------------------------------------------------------

def test_readiness_splits_not_fixture_only(db):
    _league(db, code="P18RD")
    _teams(db, db.query(League).filter_by(code="P18RD").one(), ("H", "A"))
    report = current_season.current_season_readiness(db, leagues=["P18RD"])
    league_report = report["leagues"]["P18RD"]
    assert {"fixtures", "future", "finished", "live", "postponed",
            "prediction_eligible", "prediction_ineligible"} <= set(league_report)
    kickoff = NOW + timedelta(days=2)
    current_season.acquire_competition(
        db, "P18RD", "2026", sources=[MockSource([_rec("H", "A", kickoff,
                                                       league="P18RD")])])
    report = current_season.current_season_readiness(db, leagues=["P18RD"])
    league_report = report["leagues"]["P18RD"]
    assert league_report["fixtures"] == 1
    # Fixture present but history insufficient -> explicitly ineligible.
    assert league_report["prediction_ineligible"] >= 1


# -- leakage: future/post-cutoff/market injection ----------------------------------------------------

def test_future_status_update_leaves_prediction_untouched(db):
    from app.services.intelligence.composer import PredictionComposer

    league, _teams, _ = _history_with_teams(db, code="P18L")
    target = db.query(Match).filter_by(league_id=league.id).order_by(
        Match.id.desc()).first()
    cutoff = target.kickoff_at
    before = PredictionComposer().compose(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH).model_dump()[
        "probabilities"]
    target.status = "LIVE"
    db.commit()
    after = PredictionComposer().compose(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH).model_dump()[
        "probabilities"]
    assert before == after


def test_post_match_score_leaves_prematch_untouched(db):
    from app.services.features.temporal import TemporalMode
    from app.services.intelligence.composer import PredictionComposer

    _, _, target = _history_future_target(db)
    cutoff = target.kickoff_at
    before = PredictionComposer().compose(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH).model_dump()
    target.status = "FINISHED"
    target.home_score = 4
    target.away_score = 0
    db.commit()
    after = PredictionComposer().compose(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH).model_dump()
    assert after["probabilities"] == before["probabilities"]
    assert after["core_prediction"] == before["core_prediction"]


def test_post_cutoff_odds_leave_intelligence_unchanged(db):
    from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
    from app.services.features.temporal import TemporalMode
    from app.services.intelligence_v2 import service as intel_service

    _, _unused_teams, target = _history_future_target(db, code="P18O")
    cutoff = target.kickoff_at
    before = intel_service.build_intelligence(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH,
        persist=False)["market_comparison"]
    book = Bookmaker(name="MB", provider_bookmaker_id="MB")
    db.add(book)
    db.flush()
    snap = OddsSnapshot(match_id=target.id, bookmaker_id=book.id,
                        market_type="h2h",
                        timestamp=cutoff + timedelta(hours=2),
                        source_market_id="MB:h2h")
    db.add(snap)
    db.flush()
    for selection, odds in (("home", 2.0), ("draw", 3.5), ("away", 4.0)):
        db.add(OddsSelection(snapshot_id=snap.id, selection=selection,
                             odds=odds,
                             dedup_hash=f"p18-{snap.id}-{selection}"))
    db.commit()
    after = intel_service.build_intelligence(
        db, target.id, cutoff, TemporalMode.STRICT_PREMATCH,
        persist=False)["market_comparison"]
    assert after == before


def test_provider_reorder_is_deterministic(db):
    _league(db, code="P18RO")
    _teams(db, db.query(League).filter_by(code="P18RO").one(),
           ("H", "A", "B", "C"))
    kickoff = NOW + timedelta(days=2)
    records = [_rec("H", "A", kickoff, league="P18RO", sid="s1"),
               _rec("B", "C", kickoff, league="P18RO", sid="s2")]
    first = current_season.acquire_competition(
        db, "P18RO", "2026", sources=[MockSource(records)])
    assert first["sources"]["mock"]["created"] == 2
    before = sorted(m.provider_match_id for m in db.query(Match).all()
                    if (m.provider_match_id or "").startswith("s"))
    second = current_season.acquire_competition(
        db, "P18RO", "2026", sources=[MockSource(list(reversed(records)))])
    assert second["sources"]["mock"]["created"] == 0
    after = sorted(m.provider_match_id for m in db.query(Match).all()
                   if (m.provider_match_id or "").startswith("s"))
    assert before == after


def _history_with_teams(db, code):
    league = _league(db, code=code)
    teams = _teams(db, league, ("H", "A", "B", "C"))
    base = datetime(2024, 8, 1)
    idx = 0
    for day in range(12):
        home, away = ("H", "A") if day % 2 == 0 else ("B", "C")
        db.add(Match(
            league_id=league.id, home_team_id=teams[home].id,
            away_team_id=teams[away].id,
            kickoff_at=base + timedelta(days=day), status="FINISHED",
            home_score=2 if day % 3 else 1, away_score=day % 2,
            provider="test", provider_match_id=f"p18-{code}-{idx}"))
        idx += 1
    db.commit()
    return league, teams, None


def _history_future_target(db, code="P18T"):
    league, teams, _ = _history_with_teams(db, code)
    target = Match(
        league_id=league.id, home_team_id=teams["H"].id,
        away_team_id=teams["A"].id,
        kickoff_at=datetime(2024, 9, 20, 15, 0), status="SCHEDULED",
        provider="test", provider_match_id="p18-target")
    db.add(target)
    db.commit()
    return league, teams, target


# -- historical integrity -------------------------------------------------------------------------------

def test_historical_integrity_after_acquisition(db):
    from app.db.models.predictions import Prediction
    from app.services.intelligence_v2.service import build_intelligence

    _unused_league, _unused_teams, target = _history_future_target(db, code="P18H")
    intel_before = build_intelligence(
        db, target.id, target.kickoff_at, TemporalMode.STRICT_PREMATCH,
        persist=False)
    hist_hash = intel_before["provenance"]["hash"]
    pred_count = db.query(Prediction).count()
    kickoff = NOW + timedelta(days=5)
    current_season.acquire_competition(
        db, "P18H", "2026", sources=[MockSource([_rec("H", "A", kickoff,
                                                      league="P18H")])])
    intel_after = build_intelligence(
        db, target.id, target.kickoff_at, TemporalMode.STRICT_PREMATCH,
        persist=False)
    assert intel_after["provenance"]["hash"] == hist_hash
    assert db.query(Prediction).count() == pred_count


# -- production regression ----------------------------------------------------------------------------------

def test_production_prediction_unchanged(db):
    from app.services.features.temporal import TemporalMode
    from app.services.intelligence.composer import PredictionComposer

    _, _, target = _history_future_target(db, code="P18R")
    before = PredictionComposer().compose(
        db, target.id, target.kickoff_at,
        TemporalMode.STRICT_PREMATCH).model_dump()
    current_season.acquire_current_season(db, leagues=["P18R"])
    after = PredictionComposer().compose(
        db, target.id, target.kickoff_at,
        TemporalMode.STRICT_PREMATCH).model_dump()
    assert after["probabilities"] == before["probabilities"]
    assert after["core_prediction"]["model_version"] == \
        before["core_prediction"]["model_version"]


# -- API + CLI + security --------------------------------------------------------------------------------------

def test_api_current_and_acquisition_status(client, db):
    _league(db, code="P18API")
    _teams(db, db.query(League).filter_by(code="P18API").one(), ("H", "A"))
    kickoff = NOW + timedelta(days=2)
    current_season.acquire_competition(
        db, "P18API", "2026", sources=[MockSource([_rec("H", "A", kickoff,
                                                        league="P18API")])])
    response = client.get("/api/v1/matches/current?competition=P18API")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["season"] == current_season.current_canonical_season()
    assert len(body["data"]) == 1
    assert "prediction_eligible" not in body["data"][0]
    response = client.get(
        "/api/v1/matches/current?competition=P18API&eligible=false")
    assert response.status_code == 200
    response = client.get("/api/v1/acquisition/status")
    assert response.status_code == 200
    assert "health" in response.json() and "recent_runs" in response.json()
    assert client.get("/api/v1/matches/current?competition=NOPE").status_code == 400


def test_no_secrets_or_arbitrary_urls():
    from pathlib import Path
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["grep", "-rn", "MIROFISH_API_KEY\\|ODDS_API_KEY\\|FOOTBALL_API_KEY",
         "backend/app/services/acquisition/current_season.py",
         "backend/app/api/routes/acquisition.py",
         "backend/app/api/routes/matches.py"],
        capture_output=True, text=True, cwd=repo_root)
    assert result.stdout.strip() == "", result.stdout
    # CLI source allowlist rejects arbitrary providers.
    cli = (repo_root / "backend" / "scripts" / "tacticx.py").read_text(encoding="utf-8")
    assert "unknown source" in cli

