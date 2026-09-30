"""Phase 16 tests: MiroFish contract, determinism, validation, leakage,
isolation, mock provider, API/CLI. No live network calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, MatchEvent, Team
from app.db.models.mirofish import MiroFishScenarioRun
from app.db.models.odds import Bookmaker, OddsSnapshot
from app.services.features.temporal import TemporalMode
from app.services.mirofish import (
    adapter,
    contracts,
    request_builder,
    response_parser,
    scenario_builder,
    service,
    validation,
)

STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P16"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p16", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p16-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _history(db, code="P16H", start_day=1, rounds=8, teams=("A", "B", "C", "D")):
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
                provider_match_id=f"p16-{code}-{idx}"))
            day += 1
    db.commit()
    target = Match(
        league_id=league.id, home_team_id=team_map[names[0]].id,
        away_team_id=team_map[names[1]].id,
        kickoff_at=datetime(2024, 9, 20, 15, 0), status="SCHEDULED",
        provider="test", provider_match_id="p16-target")
    db.add(target)
    db.commit()
    return league, team_map, target


def _composed(db, target):
    from app.services.intelligence.composer import PredictionComposer

    return PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()


class FakeProvider(adapter.MiroFishProvider):
    name = "fake"

    def __init__(self, responder):
        self._responder = responder
        self.calls = 0

    async def run_scenario(self, request_json):
        self.calls += 1
        return self._responder(json.loads(request_json))


def _good_response(request):
    return {
        "contract_version": "mirofish_contract_v1",
        "match_id": request["match_id"], "cutoff": request["cutoff"],
        "scenario_id": request["scenario"]["scenario_id"],
        "scenario_hash": request["scenario"]["scenario_hash"],
        "baseline_prediction_hash": request["baseline_hashes"]["baseline_prediction"],
        "intelligence_snapshot_hash": request["baseline_hashes"]["intelligence_snapshot"],
        "provider": "fake",
        "structured_observations": [
            {"kind": "sensitivity",
             "statement": "under this scenario, the simulated environment "
                          "produced wider margins",
             "detail": {}}],
        "narrative": "Under this scenario, the simulation indicates variance.",
        "warnings": [], "provenance": {},
    }


# -- contract ----------------------------------------------------------------------------------

def test_whitelisted_fields_only(db):
    _, _, target = _history(db)
    composed = _composed(db, target)
    composed["evil"] = "drop me"
    composed["probabilities"]["actual_result"] = "home"
    definition = scenario_builder.build_definition(
        {k: composed["probabilities"][k] for k in ("home", "draw", "away")},
        composed["goals"]["home_lambda"], composed["goals"]["away_lambda"],
        "baseline", "basehash")
    request = request_builder.build_request(composed, definition,
                                            "mirofish_contract_v1", {})
    dumped = request.model_dump()
    assert set(dumped) <= set(contracts.REQUEST_FIELDS)
    assert "evil" not in dumped["uncertainty"]
    assert "actual_result" not in dumped["core_prediction"]
    with pytest.raises(ValueError):
        scenario_builder.build_definition(
            {"home": 0.5, "draw": 0.3, "away": 0.2}, 1.5, 1.0, "nope", "h")


def test_allowed_scenario_ids_match_phase15():
    from app.services.intelligence import scenarios as scenario_engine

    assert scenario_builder.allowed_scenario_ids() == sorted(scenario_engine.SCENARIOS)
    assert set(scenario_builder.allowed_scenario_ids()) >= {
        "baseline", "home_strength_up", "home_strength_down",
        "away_strength_up", "away_strength_down", "high_scoring", "low_scoring"}


def test_request_determinism_and_sensitivity(db):
    _, _, target = _history(db)
    composed = _composed(db, target)
    kwargs = dict(
        baseline_1x2={k: composed["probabilities"][k]
                      for k in ("home", "draw", "away")},
        lambda_home=composed["goals"]["home_lambda"],
        lambda_away=composed["goals"]["away_lambda"],
        baseline_hash="basehash")
    definition = scenario_builder.build_definition(**kwargs, scenario_id="baseline")
    first = request_builder.build_request(composed, definition,
                                          "mirofish_contract_v1", {})
    second = request_builder.build_request(composed, definition,
                                           "mirofish_contract_v1", {})
    assert request_builder.request_hash(first) == request_builder.request_hash(second)
    other = scenario_builder.build_definition(**kwargs, scenario_id="high_scoring")
    third = request_builder.build_request(composed, other,
                                          "mirofish_contract_v1", {})
    assert request_builder.request_hash(third) != request_builder.request_hash(first)


# -- validation -------------------------------------------------------------------------------------

def test_response_validation_rules():
    base = {"contract_version": "mirofish_contract_v1", "match_id": 1,
            "cutoff": "2024-01-01", "scenario_id": "baseline",
            "scenario_hash": "s", "baseline_prediction_hash": "b",
            "intelligence_snapshot_hash": "i", "provider": "fake"}
    expected = dict(base)
    assert validation.validate_response(dict(base), expected, 65536)["valid"]
    bad_contract = dict(base, contract_version="v0")
    assert not validation.validate_response(bad_contract, expected, 65536)["valid"]
    cross_match = dict(base, match_id=2)
    result = validation.validate_response(cross_match, expected, 65536)
    assert not result["valid"] and any("match_id" in e for e in result["errors"])
    for probs in ({"home": -0.1, "draw": 0.5, "away": 0.6},
                  {"home": 0.9, "draw": 0.9, "away": 0.9},
                  {"home": float("nan"), "draw": 0.5, "away": 0.5},
                  {"home": float("inf"), "draw": 0.5, "away": -0.5 + 0.0}):
        payload = dict(base, scenario_probabilities=probs)
        assert not validation.validate_response(payload, expected, 65536)["valid"]
    assert validation.validate_response(
        dict(base, scenario_probabilities={"home": 0.5}), expected, 65536)["valid"]
    assert not validation.validate_response(dict(base), expected, 10)["valid"]


def test_narrative_safety_flags_not_rewrites():
    scan = response_parser.scan_narrative("This team will happen to win, guaranteed lock.")
    assert scan["certainty_phrases"]
    assert scan["label"].startswith("simulated")
    clean = response_parser.scan_narrative(
        "Under this scenario, the simulation indicates variance.")
    assert not clean["certainty_phrases"] and clean["scenario_framed"]


# -- service behavior ----------------------------------------------------------------------------------

def test_unavailable_by_default_and_persisted(db):
    _, _, target = _history(db)
    result = service.run_mirofish_scenario(db, target.id, target.kickoff_at,
                                           "baseline")
    assert result["status"] == "unavailable"
    assert result["error_code"] == "provider_not_configured"
    assert result["provenance"]["scenario_id"] == "baseline"
    rows = db.query(MiroFishScenarioRun).filter_by(match_id=target.id).all()
    assert len(rows) == 1 and rows[0].status == "unavailable"


def test_mock_provider_ok_path_and_provenance(db):
    _, _, target = _history(db)
    result = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "high_scoring",
        provider=FakeProvider(_good_response))
    assert result["status"] == "ok"
    assert result["contract_version"] == "mirofish_contract_v1"
    assert result["provenance"]["scenario_id"] == "high_scoring"
    assert result["provenance"]["provider"] == "fake"
    assert result["provenance"]["request_hash"]
    assert result["response_hash"]
    assert result["narrative_safety"]["label"].startswith("simulated")


def test_batch_bounded_partial_and_dedup(db):
    _, _, target = _history(db)
    fake = FakeProvider(_good_response)
    batch = service.run_mirofish_batch(
        db, target.id, target.kickoff_at, ["baseline", "high_scoring", "baseline"],
        provider=fake)
    assert batch["status"] == "ok" and batch["succeeded"] == 2
    assert [r["scenario_id"] for r in batch["scenarios"]] == ["baseline", "high_scoring"]
    import app.services.mirofish.config as batch_config_mod

    real_loader = batch_config_mod.load_config

    def tiny_max():
        config = real_loader()
        import dataclasses

        return dataclasses.replace(config, max_scenarios=1)

    batch_config_mod.load_config = tiny_max  # type: ignore
    try:
        with pytest.raises(ValueError):
            service.run_mirofish_batch(db, target.id, target.kickoff_at,
                                       ["baseline", "high_scoring"],
                                       provider=fake)
    finally:
        batch_config_mod.load_config = real_loader


def test_provider_failure_modes(db):
    _, _, target = _history(db)

    class Slow(adapter.MiroFishProvider):
        name = "slow"

        async def run_scenario(self, request_json):
            import asyncio as _asyncio

            await _asyncio.sleep(30)
            raise AssertionError("must time out first")

    import app.services.mirofish.config as timeout_config_mod

    original = timeout_config_mod.load_config

    class TinyTimeout:
        def __getattr__(self, name):
            inner = original()
            if name == "timeout_seconds":
                return 0.05
            return getattr(inner, name)

    timeout_config_mod.load_config = TinyTimeout  # type: ignore
    try:
        result = service.run_mirofish_scenario(db, target.id, target.kickoff_at,
                                               "baseline", provider=Slow())
    finally:
        timeout_config_mod.load_config = original
    assert result["status"] == "unavailable"
    assert result["error_code"] == "provider_timeout"

    class Bad(adapter.MiroFishProvider):
        name = "bad"

        async def run_scenario(self, request_json):
            return {"contract_version": "wrong", "narrative": "x"}

    result = service.run_mirofish_scenario(db, target.id, target.kickoff_at,
                                           "baseline", provider=Bad())
    assert result["status"] == "unavailable"
    assert result["error_code"] == "contract_mismatch"


def test_production_isolation(db):
    from app.db.models.core import Match as MatchModel
    from app.db.models.odds import OddsSnapshot as OddsSnapshotModel
    from app.db.models.predictions import Prediction as PredictionModel

    _, _, target = _history(db, code="P16I")
    before_pred = [(p.id, p.probabilities) for p in
                   db.query(PredictionModel).all()]
    before_matches = [(m.id, m.home_score, m.away_score) for m in
                      db.query(MatchModel).all()]
    before_odds = db.query(OddsSnapshotModel).count()
    service.run_mirofish_scenario(db, target.id, target.kickoff_at, "baseline",
                                  provider=FakeProvider(_good_response))
    after_pred = [(p.id, p.probabilities) for p in
                  db.query(PredictionModel).all()]
    after_matches = [(m.id, m.home_score, m.away_score) for m in
                     db.query(MatchModel).all()]
    assert before_pred == after_pred
    assert before_matches == after_matches
    assert db.query(OddsSnapshotModel).count() == before_odds
    assert db.query(MiroFishScenarioRun).filter_by(match_id=target.id).count() == 1


# -- leakage ----------------------------------------------------------------------------------------------

def _market(db, target, after=False, closing=False):
    book = db.query(Bookmaker).filter_by(name="MB").first()
    if book is None:
        book = Bookmaker(name="MB", provider_bookmaker_id="MB")
        db.add(book)
        db.flush()
    from app.db.models.odds import OddsSelection

    stamp = target.kickoff_at + timedelta(hours=2 if after else -1)
    snap = OddsSnapshot(match_id=target.id, bookmaker_id=book.id,
                        market_type="h2h", timestamp=stamp,
                        source_market_id="MBC:h2h" if closing else "MB:h2h")
    db.add(snap)
    db.flush()
    for selection, odds in (("home", 2.0), ("draw", 3.5), ("away", 4.0)):
        db.add(OddsSelection(snapshot_id=snap.id, selection=selection,
                             odds=odds,
                             dedup_hash=f"p16-{snap.id}-{selection}"))
    db.commit()


def _request_hash_for(db, target):
    composed = _composed(db, target)
    definition = scenario_builder.build_definition(
        {k: composed["probabilities"][k] for k in ("home", "draw", "away")},
        composed["goals"]["home_lambda"], composed["goals"]["away_lambda"],
        "baseline", "basehash")
    return request_builder.request_hash(request_builder.build_request(
        composed, definition, "mirofish_contract_v1", {}))


def test_future_data_leaves_request_identical(db):
    _, _, target = _history(db, code="P16L")
    before = _request_hash_for(db, target)
    db.add(MatchEvent(match_id=target.id, minute=10, event_type="goal",
                      team="home", player_name="X", provider="t",
                      provider_event_id="t-post", source="t"))
    future = Match(
        league_id=target.league_id, home_team_id=target.home_team_id,
        away_team_id=target.away_team_id,
        kickoff_at=target.kickoff_at + timedelta(days=30),
        status="FINISHED", home_score=9, away_score=0, provider="test",
        provider_match_id="p16-future")
    db.add(future)
    db.commit()
    assert _request_hash_for(db, target) == before


def test_future_market_leaves_request_identical(db):
    _, _, target = _history(db, code="P16M")
    _market(db, target)
    before = _request_hash_for(db, target)
    _market(db, target, after=True)
    _market(db, target, closing=True)
    assert _request_hash_for(db, target) == before


def test_scenario_mutation_rejected(db):
    _, _, target = _history(db)
    first = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline",
        provider=FakeProvider(_good_response))
    assert first["status"] == "ok"

    def tampered(request):
        response = _good_response(request)
        response["scenario_hash"] = "forged"
        return response

    result2 = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline",
        provider=FakeProvider(tampered))
    assert result2["status"] == "unavailable"


def test_cross_match_and_cross_scenario_rejected(db):
    _, _, target = _history(db)

    def wrong_match(request):
        response = _good_response(request)
        response["match_id"] = 999999
        return response

    result = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline",
        provider=FakeProvider(wrong_match))
    assert result["status"] == "unavailable"

    def wrong_scenario(request):
        response = _good_response(request)
        response["scenario_id"] = "high_scoring"
        return response

    result = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline",
        provider=FakeProvider(wrong_scenario))
    assert result["status"] == "unavailable"


def test_narrative_certainty_never_moves_probability(db):
    _, _, target = _history(db)

    def certain(request):
        response = _good_response(request)
        response["narrative"] = "This is guaranteed lock, a sure win, confirmed result."
        return response

    result = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline",
        provider=FakeProvider(certain))
    assert result["status"] == "ok"
    assert result["narrative_safety"]["certainty_phrases"]
    # Narrative never becomes probabilities: the result carries no
    # statistical probability fields of its own.
    assert "home" not in result


# -- API + CLI -----------------------------------------------------------------------------------------------

def test_api_mirofish_endpoints(client, db):
    _, _, target = _history(db, code="P16API")
    response = client.get(f"/api/v1/intelligence/{target.id}/mirofish")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    response = client.post(f"/api/v1/intelligence/{target.id}/mirofish",
                           json={"scenario_id": "baseline"})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["error_code"] == "provider_not_configured"
    response = client.get(
        f"/api/v1/intelligence/{target.id}/mirofish/high_scoring")
    assert response.status_code == 200
    response = client.post(f"/api/v1/intelligence/{target.id}/mirofish/batch",
                           json={"scenario_ids": ["baseline", "high_scoring"]})
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "partial", "unavailable")
    response = client.post(f"/api/v1/intelligence/{target.id}/mirofish",
                           json={"scenario_id": "nope"})
    assert response.status_code == 400
    assert client.get("/api/v1/intelligence/999999/mirofish").status_code == 404


def test_cli_mirofish_reports_status(db, capsys):
    import asyncio as _asyncio  # noqa: F401 (documents async boundary)

    _, _, target = _history(db, code="P16CLI")
    from app.services.mirofish import service as service_mod

    result = service_mod.run_mirofish_scenario(db, target.id,
                                               target.kickoff_at, "baseline")
    assert result["status"] == "unavailable"
    assert "provider" in result["provenance"]


def test_local_simulation_provider(db):
    _, _, target = _history(db, code="P16LOC")
    local_prov = adapter.LocalSimulationProvider()
    result = service.run_mirofish_scenario(
        db, target.id, target.kickoff_at, "baseline", provider=local_prov)
    assert result["status"] == "ok"
    assert result["contract_version"] == "mirofish_contract_v1"
    assert result["provider"] == "local"
    assert len(result["structured_observations"]) >= 2
    assert result["narrative_safety"]["label"].startswith("simulated")
    assert result["narrative_safety"]["scenario_framed"] is True
    assert not result["narrative_safety"]["certainty_phrases"]

