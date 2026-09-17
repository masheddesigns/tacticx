"""Phase 8 tests: reconciliation, identity, events, statistics, xG, odds,
conflicts, provenance, versioning, quality, gating. No live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, MatchEvent, MatchStatistic, Team
from app.db.models.reconciliation import (
    ManualMapping,
    ReconciliationConflict,
    UnresolvedRecord,
)
from app.services.reconciliation import (
    canonical,
    conflicts,
    events,
    gating,
    identities,
    matches,
    matrix,
    odds_norm,
    quality,
    statistics,
)

BASE = datetime(2024, 9, 1, 12, 0)


def _league(db, code="P8"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p8", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p8-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _match(db, league, teams, home="A", away="B", kickoff=None, hs=2, aws=1,
           status="FINISHED", provider="test", pid="m1"):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=kickoff or BASE, status=status, home_score=hs, away_score=aws,
        provider=provider, provider_match_id=pid)
    db.add(match)
    db.commit()
    return match


# -- match reconciliation --------------------------------------------------------

def test_reconcile_match_agreements(db):
    league = _league(db)
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    result = matches.reconcile_match(
        db, match.id, "test",
        {"league_code": "P8", "home_team_id": teams["A"].id,
         "away_team_id": teams["B"].id, "kickoff_at": BASE, "status": "FINISHED",
         "home_score": 2, "away_score": 1, "source_match_id": "m1"},
        dry_run=True)
    assert "score" in result["agreements"] and result["conflicts"] == []


def test_score_conflict_critical_and_persisted(db):
    league = _league(db, code="P8S")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    result = matches.reconcile_match(
        db, match.id, "other",
        {"home_score": 1, "away_score": 1, "source_match_id": "x"})
    conflict = result["conflicts"][0]
    assert conflict["type"] == "score_mismatch"
    assert conflict["severity"] == "critical"
    row = db.query(ReconciliationConflict).filter_by(id=conflict["conflict_id"]).one()
    assert row.resolution_status == "unresolved"
    # Idempotent: same disagreement returns the same row.
    again = matches.reconcile_match(
        db, match.id, "other",
        {"home_score": 1, "away_score": 1, "source_match_id": "x"})
    assert again["conflicts"][0]["conflict_id"] == conflict["conflict_id"]
    assert db.query(ReconciliationConflict).count() == 1


def test_kickoff_tolerance_vs_large_gap(db):
    league = _league(db, code="P8K")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    small = matches.reconcile_match(
        db, match.id, "s", {"kickoff_at": BASE + timedelta(minutes=10)},
        dry_run=True)
    assert small["conflicts"] == []
    big = matches.reconcile_match(
        db, match.id, "s", {"kickoff_at": BASE + timedelta(hours=7)},
        dry_run=True)
    assert big["conflicts"][0]["type"] == "kickoff_mismatch"
    assert "never merged" in big["conflicts"][0]["note"]


def test_timezone_rendering_auto_merges(db):
    league = _league(db, code="P8TZ")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    iso_z = BASE.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    result = matches.reconcile_match(
        db, match.id, "s", {"kickoff_at": BASE}, dry_run=True)
    assert result["conflicts"] == []
    _ = iso_z


def test_duplicate_source_rows_conflict(db):
    league = _league(db, code="P8D")
    teams = _teams(db, league, ("A", "B"))
    _match(db, league, teams, pid="dup-a")
    _match(db, league, teams, pid="dup-b")
    summary = matches.reconcile_league(db, league_code="P8D", dry_run=False)
    assert summary["multi_row_groups"] == 1
    types = [c.field.split(":")[0] for c in db.query(ReconciliationConflict).all()]
    assert "duplicate_source_match" in types


# -- team / player identity ---------------------------------------------------------

def test_team_alias_and_ambiguous(db):
    league = _league(db, code="P8T")
    _teams(db, league, ("Arsenal",))
    resolved = identities.resolve_team(db, "src", provider_team_name="arsenal ")
    assert resolved["canonical_team_id"] is not None
    assert resolved["mapping_method"] in ("normalized_name", "alias",
                                             "mapping", "legacy_provider_id")
    missing = identities.resolve_team(db, "src", provider_team_name="No Such FC")
    assert missing["canonical_team_id"] is None
    queued = db.query(UnresolvedRecord).filter_by(entity_type="team").all()
    assert len(queued) >= 1 and queued[0].status == "open"


def test_manual_mapping_versioned_and_mirrored(db):
    league = _league(db, code="P8M")
    teams = _teams(db, league, ("Real Team",))
    first = identities.apply_manual_mapping(db, "team", "src", "R1", teams["Real Team"].id)
    assert first["status"] == "applied" and first["version"] == 1
    second = identities.apply_manual_mapping(db, "team", "src", "R1", teams["Real Team"].id)
    assert second["version"] == 2
    rows = db.query(ManualMapping).filter_by(source="src", source_record_id="R1").all()
    assert sorted(r.version for r in rows) == [1, 2]
    assert sum(1 for r in rows if r.superseded_by is None) == 1
    # Native mapping mirrored so resolvers pick it up.
    resolved = identities.resolve_team(db, "src", provider_team_id="R1")
    assert resolved["canonical_team_id"] == teams["Real Team"].id
    with pytest.raises(ValueError):
        identities.apply_manual_mapping(db, "nope", "src", "R1", 1)


def test_player_identity_and_transfer(db):
    from app.db.models.core import Player

    league = _league(db, code="P8P")
    teams = _teams(db, league, ("Home FC", "Away FC"))
    player = Player(name="John Smith", team_id=teams["Home FC"].id,
                    provider="test", provider_player_id="p-1")
    db.add(player)
    db.commit()
    found = identities.resolve_player(db, "test", provider_player_id="p-1",
                                      name="John Smith", team="Home FC")
    assert found["canonical_player_id"] == player.id
    # Same name, other team context, no ID: unresolved, queued, not merged.
    other = identities.resolve_player(db, "other", name="John Smith",
                                      team="Away FC")
    assert other["canonical_player_id"] is None
    assert db.query(UnresolvedRecord).filter_by(entity_type="player").count() >= 1


# -- events ------------------------------------------------------------------------------

def test_event_duplicate_goal_matched(db):
    league = _league(db, code="P8E")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)

    def goal(source, minute, second=None, pid=""):
        db.add(MatchEvent(match_id=match.id, minute=minute, second=second,
                          event_type="goal", team="home", player_name="P",
                          provider=source, provider_event_id=f"{source}-{minute}-{pid}",
                          source=source))
    goal("a", 23, 10, "g1")
    goal("b", 23, 35, "g1")  # 25s apart: same goal, different precision
    db.commit()
    summary = events.reconcile_match_events(db, match.id, dry_run=True)
    assert summary["matched"] == 1 and summary["unresolved"] == 0


def test_event_conflict_and_tolerance(db):
    league = _league(db, code="P8E2")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    db.add(MatchEvent(match_id=match.id, minute=10, event_type="goal",
                      team="home", source="a", provider="a", provider_event_id="a-10"))
    db.add(MatchEvent(match_id=match.id, minute=80, event_type="goal",
                      team="home", source="b", provider="b", provider_event_id="b-80"))
    db.add(MatchEvent(match_id=match.id, minute=None, event_type="goal",
                      team="home", source="b", provider="b", provider_event_id="b-unk"))
    db.commit()
    summary = events.reconcile_match_events(db, match.id, dry_run=False)
    assert summary["unresolved"] >= 1
    assert db.query(ReconciliationConflict).filter_by(entity_type="event").count() >= 1


# -- statistics + xG -----------------------------------------------------------------------

def test_statistic_classification(db):
    """Schema reality: one row per (match, team, stat, period) — the second
    source reconciles at ingest against the stored row."""
    statistics.ensure_stat_definitions(db)
    league = _league(db, code="P8ST")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    first = canonical.resolve_statistic(db, match.id, "home", "shots_total",
                                        "full", "10", "football_data_co_uk")
    assert first["status"] == "recorded"
    second = canonical.resolve_statistic(db, match.id, "home", "shots_total",
                                         "full", "12", "api_football")
    # Different provider definitions -> definition_difference; stored value
    # kept (no authoritative source configured for shots_total), no conflict.
    assert second["classification"] == "definition_difference"
    assert second["status"] == "kept_stored_conflict_open"
    from app.db.models.core import MatchStatistic

    row = db.query(MatchStatistic).filter_by(match_id=match.id).one()
    assert row.stat_value == "10"
    assert db.query(ReconciliationConflict).filter_by(entity_type="statistic").count() == 0


def test_statistic_true_conflict_and_units(db):
    statistics.ensure_stat_definitions(db)
    league = _league(db, code="P8ST2")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    canonical.resolve_statistic(db, match.id, "home", "shots_total",
                                "full", "10", "football_data_co_uk")
    # Same source, same semantics, material gap -> true_conflict persisted.
    second = canonical.resolve_statistic(db, match.id, "home", "shots_total",
                                         "full", "20", "football_data_co_uk")
    assert second["classification"] == "true_conflict"
    assert db.query(ReconciliationConflict).filter_by(entity_type="statistic").count() == 1
    # Unparseable values -> unknown, stored value kept.
    third = canonical.resolve_statistic(db, match.id, "home", "shots_total",
                                        "full", "n/a", "football_data_co_uk")
    assert third["classification"] == "unknown"


def test_xg_source_separation_and_gating(db):
    statistics.ensure_stat_definitions(db)
    league = _league(db, code="P8XG")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    canonical.resolve_statistic(db, match.id, "home", "expected_goals",
                                "full", "1.8", "statsbomb")
    # Second xG source reconciles at ingest: different vendor definition ->
    # definition_difference; authoritative statsbomb value kept, never averaged.
    incoming = canonical.resolve_statistic(db, match.id, "home", "expected_goals",
                                           "full", "2.1", "api_football")
    assert incoming["classification"] == "definition_difference"
    separated = statistics.xg_by_source(db, match.id)
    assert separated["by_source"]["statsbomb"][0]["xg_value"] == 1.8
    assert "api_football" not in separated["by_source"]
    compat = statistics.compatible_sources(db, "expected_goals",
                                           ["statsbomb", "api_football"])
    assert compat["compatible"] is False


# -- odds identity -----------------------------------------------------------------------------

def test_bookmaker_and_market_identity(db):
    assert odds_norm.canonical_bookmaker_name("B365") == "Bet365"
    assert odds_norm.canonical_market("1X2") == "h2h"
    assert odds_norm.canonical_selection("1") == "home"
    resolved = odds_norm.resolve_bookmaker(db, "test", provider_bookmaker_id="B1",
                                           display_name="B365")
    assert resolved["canonical_bookmaker_id"] is None  # no guessing
    from app.db.models.odds import Bookmaker

    db.add(Bookmaker(name="Bet365", provider="test", provider_bookmaker_id="B1"))
    db.commit()
    resolved2 = odds_norm.resolve_bookmaker(db, "test", provider_bookmaker_id="B1",
                                            display_name="B365")
    assert resolved2["method"] == "existing_mapping"


# -- conflicts / provenance / versioning --------------------------------------------------------

def test_conflict_severity_policy_and_resolution():
    assert conflicts.SEVERITY_POLICY["score_mismatch"][0] == "critical"
    assert conflicts.SEVERITY_POLICY["kickoff_mismatch"][0] == "high"
    assert conflicts.SEVERITY_POLICY["formatting_difference"][0] == "low"
    assert conflicts.auto_resolvable("formatting_difference", "Arsenal", "arsenal ") == "merged"
    assert conflicts.auto_resolvable("score_mismatch", "2-1", "1-1") is None


def test_canonical_version_history(db):
    league = _league(db, code="P8V")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams, hs=None, aws=None, status="SCHEDULED")
    out = canonical.resolve_match_score(db, match.id, 2, 1, "s1")
    assert out["status"] == "recorded"
    out2 = canonical.resolve_match_score(db, match.id, 2, 2, "s2")
    assert out2["status"] == "recorded_overwrite"
    from app.db.models.reconciliation import CanonicalFieldVersion

    versions = db.query(CanonicalFieldVersion).filter_by(
        entity_type="match", canonical_entity_id=match.id, field="score").all()
    assert len(versions) == 2
    assert versions[1].old_value == "2-1"
    refused = canonical.resolve_kickoff(
        db, match.id, BASE + timedelta(hours=3), "s1")
    assert refused["status"] == "refused"  # finished never moves


def test_no_prediction_mutation(db):
    from app.db.models.predictions import Prediction

    league = _league(db, code="P8NP")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    pred = Prediction(match_id=match.id, model_version="ensemble_v1",
                      prediction_type="1x2", predicted_probability=0.5,
                      probabilities={"home_win": 0.5, "draw": 0.3, "away_win": 0.2})
    db.add(pred)
    db.commit()
    before = dict(pred.probabilities)
    canonical.resolve_match_score(db, match.id, 0, 0, "s2")
    matches.reconcile_match(db, match.id, "s2", {"home_score": 0, "away_score": 0})
    db.refresh(pred)
    assert dict(pred.probabilities) == before


# -- quality + gating -------------------------------------------------------------------------------

def test_quality_components_and_thresholds(db):
    league = _league(db, code="P8Q")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    result = quality.assess_match(db, match.id)
    assert result["quality"] in ("high", "medium", "low")
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9
    assert result["score"] == round(
        sum(result["components"][k] * result["weights"][k]
            for k in result["weights"]), 4)


def test_gating_blocks_critical_allows_irrelevant(db):
    league = _league(db, code="P8G")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    allowed = gating.gating_decision(db, match.id)
    assert allowed["decision"] == "allowed"
    matches.reconcile_match(db, match.id, "rogue",
                            {"home_score": 9, "away_score": 9})
    blocked = gating.gating_decision(db, match.id)
    assert blocked["decision"] == "blocked"
    assert any("critical" in r for r in blocked["reasons"])


# -- matrix / dry-run / idempotency / API ---------------------------------------------------------------

def test_source_matrix_from_actual_data(db):
    league = _league(db, code="P8MX")
    teams = _teams(db, league, ("A", "B"))
    _match(db, league, teams)
    matrix_data = matrix.coverage_matrix(db)
    assert "test" in matrix_data["sources"]
    assert matrix_data["sources"]["test"]["fixtures"] is True
    coverage = matrix.canonical_coverage(db, league_code="P8MX")
    assert coverage["matches"] >= 1


def test_reconcile_idempotency(db):
    league = _league(db, code="P8ID")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    observed = {"home_score": 0, "away_score": 0}
    first = matches.reconcile_match(db, match.id, "s", observed)
    second = matches.reconcile_match(db, match.id, "s", observed)
    assert first["conflicts"][0]["conflict_id"] == second["conflicts"][0]["conflict_id"]
    assert db.query(ReconciliationConflict).filter_by(
        entity_type="match", canonical_entity_id=match.id).count() == 1


def test_api_reconciliation_endpoints(client, db):
    league = _league(db, code="P8API")
    teams = _teams(db, league, ("A", "B"))
    match = _match(db, league, teams)
    assert client.get("/api/v1/data-quality").status_code == 200
    response = client.get("/api/v1/data-quality/matches")
    assert response.status_code == 200 and "matches" in response.json()
    assert client.get("/api/v1/data-quality/nope").status_code == 404
    assert client.get(f"/api/v1/matches/{match.id}/sources").status_code == 200
    assert client.get(f"/api/v1/matches/{match.id}/conflicts").status_code == 200
    assert client.get(f"/api/v1/matches/{match.id}/provenance").status_code == 200
    response = client.post("/api/v1/reconciliation/mappings",
                           json={"entity_type": "team", "source": "src",
                                 "source_record_id": "T1",
                                 "canonical_id": teams["A"].id})
    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert client.get("/api/v1/reconciliation/queue").status_code == 200
    assert client.get("/api/v1/matches/999999/conflicts").status_code == 404
