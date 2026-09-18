"""Phase 13 tests: candidates, inventory, validation, backfill idempotency,
cross-league isolation, order invariance, regression. No live network."""
from __future__ import annotations

import pytest

from app.db.models.core import League, Match, Team
from app.services.data_expansion import (
    acquisition,
    artifacts,
    backfill,
    coverage,
    deduplication,
    inventory,
    quality,
    reconciliation,
    source_candidates,
    temporal,
    validation,
)


def _league(db, code="P13"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p13", season="2024")
    db.add(league)
    db.commit()
    return league


# -- candidates --------------------------------------------------------------------

def test_candidate_registry_statuses():
    rows = source_candidates.registry()
    assert any(r["validation_status"] == "validated" for r in rows)
    rejected = source_candidates.rejected()
    assert rejected and all(r["reason"] for r in rejected)
    assert any(r["source"] == "aggressive_scraping" for r in rejected)
    assert source_candidates.accepted()


def test_incremental_value_gate():
    current = {("EPL", "2024"): {"matches": 380, "families": ["stats"]}}
    candidate = {("EPL", "2024"): {"matches": 380, "families": ["stats"]}}
    verdict = validation.incremental_value(current, candidate)
    assert verdict["verdict"] == "reject"
    candidate2 = {("EPL", "2023"): {"matches": 380, "families": ["stats"]}}
    verdict2 = validation.incremental_value(current, candidate2)
    assert verdict2["verdict"] == "accept"
    assert verdict2["new_seasons"] == [("EPL", "2023")]


def test_row_validation_sanity():
    rows = [{"HomeTeam": "A", "AwayTeam": "B", "Date": "01/01/2020",
             "FTHG": "2", "FTAG": "1"},
            {"HomeTeam": "", "AwayTeam": "B", "Date": "x"},
            {"HomeTeam": "A", "AwayTeam": "B", "Date": "01/01/2020",
             "FTHG": "99", "FTAG": "0"}]
    report = validation.validate_rows(rows)
    assert report == {"rows": 3, "valid": 1, "invalid": 2,
                      "reasons": {"missing teams": 1,
                                  "implausible FTHG": 1}}


# -- inventory / coverage ---------------------------------------------------------------

def test_inventory_and_delta(db):
    league = _league(db)
    team_a = Team(league_id=league.id, name="A", provider="t", provider_team_id="1")
    team_b = Team(league_id=league.id, name="B", provider="t", provider_team_id="2")
    db.add_all([team_a, team_b])
    db.commit()
    from datetime import datetime

    db.add(Match(league_id=league.id, home_team_id=team_a.id,
                 away_team_id=team_b.id, kickoff_at=datetime(2024, 8, 1),
                 status="FINISHED", home_score=1, away_score=0,
                 provider="t", provider_match_id="m1"))
    db.commit()
    report = inventory.league_inventory(db, "P13")
    assert report["seasons"][0]["matches"] == 1
    assert report["totals"]["matches"] == 1
    before = coverage.snapshot_coverage(db)
    after = dict(before)
    after["matches"] += 5
    delta = coverage.delta(before, after)
    assert delta["families"]["matches"] == {"before": 1, "after": 6, "delta": 5}
    assert delta["new_matches"] == 5


# -- acquisition / dedup ------------------------------------------------------------------

def test_season_url_and_probe_validation():
    assert acquisition.season_url("EPL", "1617").endswith("/1617/E0.csv")
    with pytest.raises(ValueError):
        acquisition.season_url("NOPE", "1617")


def test_dedup_keys_tolerant_and_distinct():
    same_a = deduplication.record_key("EPL", "2024", "Arsenal", "Chelsea",
                                      "2024-08-18 12:30:00", "src", "match")
    same_b = deduplication.record_key("EPL", "2024", "Arsenal", "Chelsea",
                                      "2024-08-18 12:45:00", "src", "match")
    assert deduplication.same_observation(same_a, same_b)  # hour precision
    other = deduplication.record_key("EPL", "2024", "Arsenal", "Chelsea",
                                     "2024-08-18 12:30:00", "other", "match")
    assert not deduplication.same_observation(same_a, other)


def test_scope_difference_not_conflict():
    assert reconciliation.classify_expansion_outcome(["stats"], ["xg"]) == \
        "scope_difference"
    assert reconciliation.classify_expansion_outcome(["stats"], ["stats"]) == "overlap"


def test_temporal_hierarchy_never_promotes():
    assert temporal.level_for("football_data_co_uk")["strict"] is False
    assert temporal.level_for("unknown_source_xyz")["level"] == "E"
    assert temporal.HIERARCHY["A"]["strict"] is True


def test_artifact_delta_idempotent(tmp_path):
    path = artifacts.save_delta("test_delta", {"a": 1})
    assert artifacts.save_delta("test_delta", {"a": 1}) == path
    with pytest.raises(ValueError):
        artifacts.save_delta("test_delta", {"a": 2})


# -- backfill behavior (controlled, no network) -------------------------------------------------

def test_backfill_unavailable_probe(monkeypatch):
    import app.services.data_expansion.backfill as backfill_mod

    monkeypatch.setattr(backfill_mod.acquisition_svc, "probe",
                        lambda league, season: {"exists": False,
                                               "error": "404"})
    import datetime

    class FakeDB:
        pass

    result = backfill_mod.backfill_season(FakeDB(), "EPL", "9999",
                                          dest_dir="/tmp", dry_run=True)
    assert result["status"] == "unavailable"


def test_cross_league_rid_isolation(db):
    """Same rid prefix in two leagues must resolve separately (regression
    test for the Phase 13 cross-league rid collision)."""
    from app.services.identity.matches import MatchResolver

    league_a = _league(db, code="P13A")
    league_b = _league(db, code="P13B")
    teams_a = {name: Team(league_id=league_a.id, name=name, provider="t",
                          provider_team_id=f"a-{name}") for name in ("H", "A")}
    teams_b = {name: Team(league_id=league_b.id, name=name, provider="t",
                          provider_team_id=f"b-{name}") for name in ("H", "A")}
    db.add_all(list(teams_a.values()) + list(teams_b.values()))
    db.commit()
    from datetime import datetime

    kickoff = datetime(2024, 8, 1)
    resolver = MatchResolver(db)
    id_a, created_a = resolver.ensure("src", "fdcuk-P13A-1617-0", league_a.id,
                                      teams_a["H"].id, teams_a["A"].id, kickoff)
    id_b, created_b = resolver.ensure("src", "fdcuk-P13B-1617-0", league_b.id,
                                      teams_b["H"].id, teams_b["A"].id, kickoff)
    assert created_a and created_b and id_a != id_b
    # Same rid re-resolution returns the same match (idempotent).
    id_a2, created_a2 = resolver.ensure("src", "fdcuk-P13A-1617-0", league_a.id,
                                        teams_a["H"].id, teams_a["A"].id, kickoff)
    assert id_a2 == id_a and not created_a2


# -- regression: models untouched --------------------------------------------------------------------

def test_phase13_production_files_untouched():
    import subprocess

    result = subprocess.run(
        ["git", "status", "--porcelain",
         "backend/app/services/predictions/",
         "backend/app/services/intelligence/",
         "backend/app/services/evaluation/",
         "backend/app/services/backtesting/",
         "backend/app/services/features/",
         "backend/app/services/player_intelligence/",
         "backend/app/services/lifecycle/",
         "backend/app/services/reconciliation/",
         "backend/app/services/freshness/",
         "backend/app/services/acquisition/",
         "backend/app/services/model_research/"],
        capture_output=True, text=True, cwd="/Users/sivek/Documents/Bet Predictor")
    allowed = [line for line in result.stdout.strip().splitlines() if line.strip()]
    # Only the intended Phase 13 pipeline idempotency fix may touch sources;
    # Phase 14 research-framework evolution may touch model_research.
    for line in allowed:
        assert "sources/pipeline.py" in line or "data_expansion" in line or \
            "test_phase13" in line or "tacticx.py" in line or \
            "model_research" in line or "test_phase14" in line, line


def test_ingestion_order_invariance(db):
    """Reversed row order yields identical canonical results (only observation
    ordering metadata may differ)."""
    from app.services.sources.historical.csv_source import import_rows

    league = _league(db, code="P13O")
    rows = [
        {"HomeTeam": "H1", "AwayTeam": "A1", "Date": "01/08/2024",
         "FTHG": "2", "FTAG": "0", "Div": "P13O"},
        {"HomeTeam": "H2", "AwayTeam": "A2", "Date": "02/08/2024",
         "FTHG": "1", "FTAG": "1", "Div": "P13O"},
        {"HomeTeam": "H1", "AwayTeam": "A2", "Date": "03/08/2024",
         "FTHG": "0", "FTAG": "3", "Div": "P13O"},
    ]
    first = import_rows(db, "order_test", list(rows), "P13O", "2024",
                        rid_prefix="ord-a-")
    assert first["invalid"] == 0
    second = import_rows(db, "order_test", list(reversed(rows)), "P13O",
                         "2024", rid_prefix="ord-b-")
    # Different rids -> matches resolve to the same canonical rows by tuple.
    from app.db.models.core import Match

    matches = db.query(Match).filter_by(league_id=league.id).all()
    assert len(matches) == 3
    scores = sorted((m.home_score, m.away_score) for m in matches)
    assert scores == [(0, 3), (1, 1), (2, 0)]
    assert second["invalid"] == 0
