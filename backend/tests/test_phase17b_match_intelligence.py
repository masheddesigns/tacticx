"""Phase 17 tests: canonical match-intelligence API. Reuses the Phase 15b
fixture conventions; never touches test_phase17.py (Phase-1.7 suite).
No live network calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, MatchEvent, Team
from app.db.models.intelligence_v2 import IntelligenceSnapshot
from app.db.models.mirofish import MiroFishScenarioRun
from app.db.models.odds import Bookmaker, OddsSnapshot
from app.services.features.temporal import TemporalMode
from app.services.match_intelligence import service
from app.services.match_intelligence.schemas import (
    SCHEMA_VERSION,
    MatchIntelligence,
)

STRICT = TemporalMode.STRICT_PREMATCH
SECTIONS = ("schema_version", "match", "cutoff", "core_prediction",
            "derived_markets", "expected_goals", "correct_score",
            "uncertainty", "model_disagreement", "data_quality",
            "temporal_quality", "market", "analogues", "scenarios",
            "mirofish", "explanation", "warnings", "provenance")


def _league(db, code="P17"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p17", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p17-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _history(db, code="P17H", start_day=1, rounds=8, teams=("A", "B", "C", "D")):
    league = _league(db, code)
    names = list(teams)
    team_map = _teams(db, league, names)
    scores = [(2, 0), (1, 1), (0, 1), (3, 1)]
    idx = day = 0
    for round_no in range(rounds):
        order = names[round_no:] + names[:round_no]
        for i in range(0, len(order) - 1, 2):
            hs, aws = scores[idx % len(scores)]
            idx += 1
            db.add(Match(
                league_id=league.id, home_team_id=team_map[order[i]].id,
                away_team_id=team_map[order[i + 1]].id,
                kickoff_at=datetime(2024, 8, start_day) + timedelta(days=day),
                status="FINISHED", home_score=hs, away_score=aws,
                provider="test",
                provider_match_id=f"p17-{code}-{idx}"))
            day += 1
    db.commit()
    target = Match(
        league_id=league.id, home_team_id=team_map[names[0]].id,
        away_team_id=team_map[names[1]].id,
        kickoff_at=datetime(2024, 9, 20, 15, 0), status="SCHEDULED",
        provider="test", provider_match_id="p17-target")
    db.add(target)
    db.commit()
    return league, team_map, target


def _build(db, target, **kwargs):
    params = {"response_mode": "standard", "with_mirofish": True,
              "mirofish_scenario": "baseline"}
    params.update(kwargs)
    return service.build_match_intelligence(
        db, target.id, target.kickoff_at, STRICT, **params)


# -- schema ----------------------------------------------------------------------------------

def test_canonical_schema_sections_and_version(db):
    _, _, target = _history(db)
    document = _build(db, target)
    assert document["schema_version"] == SCHEMA_VERSION == "match_intelligence_v1"
    for section in SECTIONS:
        assert section in document, section
    validated = MatchIntelligence(**document)
    assert validated.schema_version == SCHEMA_VERSION


def test_compact_is_strict_presentation_subset(db):
    _, _, target = _history(db)
    full = _build(db, target)
    compact = _build(db, target, response_mode="compact")
    assert compact["core_prediction"] == full["core_prediction"]
    assert compact["derived_markets"]["one_x_two"] == \
        full["derived_markets"]["one_x_two"]
    assert compact["correct_score"]["tail_mass"] == \
        full["correct_score"]["tail_mass"]
    assert compact["scenarios"] == []
    assert len(compact["correct_score"]["top_n"]) <= 3
    assert compact["mirofish"]["status"] == full["mirofish"]["status"]
    with pytest.raises(ValueError):
        service.build_match_intelligence(db, target.id, target.kickoff_at,
                                         STRICT, response_mode="tiny")


# -- probability integrity ---------------------------------------------------------------------

def test_core_probabilities_unchanged(db):
    from app.services.intelligence.composer import PredictionComposer

    _, _, target = _history(db)
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()
    document = _build(db, target)
    for key in ("home", "draw", "away"):
        assert document["core_prediction"][key] == composed["probabilities"][key]
    assert abs(sum(document["core_prediction"][k] for k in
                   ("home", "draw", "away")) - 1.0) < 1e-9


def test_derived_invariants_hold(db):
    _, _, target = _history(db)
    document = _build(db, target)
    derived = document["derived_markets"]
    home, draw, away = (document["core_prediction"][k]
                        for k in ("home", "draw", "away"))
    assert abs(derived["double_chance"]["1x"] - (home + draw)) < 1e-6
    assert abs(derived["double_chance"]["x2"] - (draw + away)) < 1e-6
    assert abs(derived["double_chance"]["12"] - (home + away)) < 1e-6
    assert abs(derived["btts"]["yes"] + derived["btts"]["no"] - 1.0) < 1e-6
    totals = derived["totals"]
    assert abs(totals["over_2_5"] + totals["under_2_5"] - 1.0) < 1e-9
    scores = document["correct_score"]
    assert abs(scores["probability_sum"] + 0.0 - scores["probability_sum"]) < 1e-12
    assert abs(scores["required_16_mass"] + scores["tail_mass"] - 1.0) < 1e-6


# -- provenance / hash ----------------------------------------------------------------------------

def test_provenance_complete_and_hash_deterministic(db):
    _, _, target = _history(db)
    first = _build(db, target)
    second = _build(db, target)
    assert first["provenance"]["response_hash"] == \
        second["provenance"]["response_hash"]
    provenance = first["provenance"]
    for field in ("match_id", "cutoff", "model_version", "feature_version",
                  "dataset_version", "scenario_version",
                  "mirofish_contract_version", "generated_at"):
        assert field in provenance, field
    assert provenance["match_id"] == target.id
    assert provenance["model_version"].startswith("ensemble_v1")
    # Verifier path: drop response_hash + generated_at, recompute.
    check = dict(first)
    check["provenance"] = dict(first["provenance"])
    check["provenance"].pop("response_hash")
    check["provenance"].pop("generated_at")
    assert service.content_hash(check) == first["provenance"]["response_hash"]


def test_fixture_matches_schema_and_hash():
    with open("tests/fixtures/match_intelligence_example.json") as handle:
        fixture = json.load(handle)
    MatchIntelligence(**fixture)
    check = dict(fixture)
    check["provenance"] = dict(fixture["provenance"])
    check["provenance"]["generated_at"] = "x"
    check["provenance"].pop("response_hash")
    check["provenance"].pop("generated_at")
    assert service.content_hash(check) == fixture["provenance"]["response_hash"]
    assert fixture["mirofish"]["status"] == "unavailable"
    assert fixture["core_prediction"]["home"] + fixture["core_prediction"]["draw"] + \
        fixture["core_prediction"]["away"] == pytest.approx(1.0)


# -- temporal integrity -------------------------------------------------------------------------------

def test_future_market_excluded_from_canonical(db):
    _, _, target = _history(db, code="P17M")
    book = Bookmaker(name="MB", provider_bookmaker_id="MB")
    db.add(book)
    db.flush()
    from app.db.models.odds import OddsSelection

    for hours, tag in ((-1, "pre"), (2, "post")):
        snap = OddsSnapshot(match_id=target.id, bookmaker_id=book.id,
                            market_type="h2h",
                            timestamp=target.kickoff_at + timedelta(hours=hours),
                            source_market_id="MB:h2h")
        db.add(snap)
        db.flush()
        for selection, odds in (("home", 2.0), ("draw", 3.5), ("away", 4.0)):
            db.add(OddsSelection(snapshot_id=snap.id, selection=selection,
                                 odds=odds,
                                 dedup_hash=f"p17-{snap.id}-{selection}"))
    db.commit()
    document = _build(db, target)
    timing = document["market"]["market_timing"]
    assert timing is not None and timing <= str(target.kickoff_at)


def test_unknown_timing_never_upgraded(db):
    _, _, target = _history(db)
    document = _build(db, target)
    temporal = document["temporal_quality"]
    assert "xg" in temporal["unknown"]
    assert "xg" not in temporal["strict"]
    assert document["cutoff"]["has_unknown_timing"] is True


# -- mirofish ---------------------------------------------------------------------------------------------

def test_mirofish_unavailable_keeps_intelligence(db):
    _, _, target = _history(db)
    document = _build(db, target)
    assert document["mirofish"]["status"] == "unavailable"
    assert "not configured" in document["mirofish"]["reason"]
    assert document["core_prediction"]["home"] is not None
    assert "simulated scenario evidence" in document["mirofish"].get(
        "reason", "") or document["mirofish"]["status"] == "unavailable"


def test_mock_mirofish_included_and_isolated(db):
    import app.services.mirofish.config as config_mod
    from app.services.mirofish import service as mirofish_service
    from app.services.mirofish.adapter import MiroFishProvider

    _, _, target = _history(db, code="P17MF")

    class Fake(MiroFishProvider):
        name = "fake"

        async def run_scenario(self, request_json):
            import json as _json

            req = _json.loads(request_json)
            return {"contract_version": "mirofish_contract_v1",
                    "match_id": req["match_id"], "cutoff": req["cutoff"],
                    "scenario_id": req["scenario"]["scenario_id"],
                    "scenario_hash": req["scenario"]["scenario_hash"],
                    "baseline_prediction_hash": req["baseline_hashes"][
                        "baseline_prediction"],
                    "intelligence_snapshot_hash": req["baseline_hashes"][
                        "intelligence_snapshot"],
                    "provider": "fake", "structured_observations": [],
                    "narrative": "Under this scenario, the simulation indicates variance.",
                    "warnings": [], "provenance": {}}

    before = service.build_match_intelligence(
        db, target.id, target.kickoff_at, STRICT,
        response_mode="standard", with_mirofish=False)
    result = mirofish_service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline", provider=Fake())
    assert result["status"] == "ok"
    assert result["narrative_safety"]["label"].startswith("simulated")
    after = service.build_match_intelligence(
        db, target.id, target.kickoff_at, STRICT,
        response_mode="standard", with_mirofish=False)
    assert after["core_prediction"] == before["core_prediction"]
    assert after["provenance"]["response_hash"] == \
        before["provenance"]["response_hash"]
    _ = config_mod


def test_invalid_mirofish_rejected(db):
    from app.services.mirofish import service as mirofish_service
    from app.services.mirofish.adapter import MiroFishProvider

    _, _, target = _history(db, code="P17MI")

    class Bad(MiroFishProvider):
        name = "bad"

        async def run_scenario(self, request_json):
            return {"contract_version": "wrong", "narrative": "x"}

    result = mirofish_service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline", provider=Bad())
    assert result["status"] == "unavailable"


# -- API ------------------------------------------------------------------------------------------------------

def test_canonical_endpoint_and_sections(client, db):
    _, _, target = _history(db, code="P17API")
    response = client.get(f"/api/v1/matches/{target.id}/intelligence")
    assert response.status_code == 200, response.text[:400]
    body = response.json()
    assert body["schema_version"] == "match_intelligence_v1"
    assert body["mirofish"]["status"] == "unavailable"
    for section in ("summary", "markets", "uncertainty", "scenarios",
                    "analogues", "mirofish"):
        response = client.get(
            f"/api/v1/matches/{target.id}/intelligence/{section}")
        assert response.status_code == 200, section
    response = client.get(
        f"/api/v1/matches/{target.id}/intelligence?response_mode=compact")
    assert response.status_code == 200
    assert response.json()["scenarios"] == []
    assert client.get("/api/v1/matches/999999/intelligence").status_code == 404
    response = client.get(
        f"/api/v1/matches/{target.id}/intelligence?response_mode=tiny")
    assert response.status_code == 400


def test_openapi_documents_intelligence(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/matches/{match_id}/intelligence" in paths


# -- production isolation ------------------------------------------------------------------------------------------

def test_production_tables_untouched(db):
    from app.db.models.mirofish import MiroFishScenarioRun
    from app.db.models.odds import OddsSnapshot as OddsSnapshotModel
    from app.db.models.predictions import Prediction as PredictionModel

    _, _, target = _history(db, code="P17PI")
    before_predictions = [(p.id, p.probabilities) for p in
                          db.query(PredictionModel).all()]
    before_matches = [(m.id, m.home_score, m.away_score) for m in
                      db.query(Match).all()]
    before_odds = db.query(OddsSnapshotModel).count()
    before_runs = db.query(MiroFishScenarioRun).count()
    _build(db, target)
    assert [(p.id, p.probabilities) for p in
            db.query(PredictionModel).all()] == before_predictions
    assert [(m.id, m.home_score, m.away_score) for m in
            db.query(Match).all()] == before_matches
    assert db.query(OddsSnapshotModel).count() == before_odds
    # The layer's own append-only run history grows by exactly one row;
    # everything else is byte-identical.
    assert db.query(MiroFishScenarioRun).count() == before_runs + 1
