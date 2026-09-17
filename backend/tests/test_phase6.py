"""Phase 6 tests: composer, derived markets, explanation, analogues,
scenarios, MiroFish adapter, temporal safety, API. No live network calls."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
from app.services.features.temporal import TemporalMode
from app.services.intelligence import analogues, derived, scenarios
from app.services.intelligence.composer import PredictionComposer
from app.services.intelligence.explanation import explain
from app.services.intelligence.mirofish_adapter import (
    DisabledMirofishService,
    build_context,
    run_mirofish,
    validate_output,
)
from app.services.predictions.mirofish import MiroFishInput, MiroFishOutput

STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P6"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p6", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for i, name in enumerate(names):
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p6-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _add(db, league, teams, home, away, kickoff, hs, aws, status="FINISHED"):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=kickoff, status=status, home_score=hs, away_score=aws,
        provider="test", provider_match_id=f"p6-{home}-{away}-{kickoff.isoformat()}")
    db.add(match)
    db.commit()
    return match


def _round_robin(db, code="P6", teams=("A", "B", "C", "D", "E", "F"), start_day=1,
                 rounds=5):
    """Enough history for poisson sufficiency + analogue candidates."""
    league = _league(db, code)
    names = list(teams)
    team_map = _teams(db, league, names)
    base = datetime(2024, 8, start_day)
    day = 0
    rng_scores = [(2, 0), (1, 1), (0, 1), (3, 1), (1, 0), (2, 2), (0, 2), (1, 2)]
    idx = 0
    for round_no in range(rounds):
        order = names[round_no:] + names[:round_no]
        for i in range(0, len(order) - 1, 2):
            hs, aws = rng_scores[idx % len(rng_scores)]
            idx += 1
            _add(db, league, team_map, order[i], order[i + 1],
                 base + timedelta(days=day), hs, aws)
            day += 1
    target = _add(db, league, team_map, names[0], names[1],
                  base + timedelta(days=day + 1), None, None, status="SCHEDULED")
    return league, team_map, target


# -- derived math (no DB) ------------------------------------------------

def test_validate_1x2_accepts_and_rejects():
    ok = derived.validate_1x2(0.5, 0.3, 0.2)
    assert ok["valid"] and ok["errors"] == []
    bad = derived.validate_1x2(0.5, 0.3, 0.3)
    assert not bad["valid"] and any("sums" in e for e in bad["errors"])
    bad2 = derived.validate_1x2(1.2, -0.1, -0.1)
    assert not bad2["valid"] and len(bad2["errors"]) == 3


def test_goal_distributions_normalize_and_expose_tail():
    dist = derived.goal_distributions(1.6, 1.1)
    assert dist["status"] == "ok"
    assert abs(sum(dist["joint"].values()) - 1.0) < 1e-6
    assert dist["tail_mass"] >= 0.0
    assert dist["total_lambda"] == round(1.6 + 1.1, 4)
    wide = derived.goal_distributions(5.7, 0.9)
    assert wide["tail_mass"] > dist["tail_mass"]


def test_totals_over_under_consistent():
    dist = derived.goal_distributions(1.6, 1.1)
    totals = derived.totals_from_joint(dist["joint"])
    assert totals["consistent"]
    for line in ("0_5", "1_5", "2_5", "3_5"):
        assert abs(totals["probabilities"][f"over_{line}"]
                   + totals["probabilities"][f"under_{line}"] - 1.0) < 1e-9


def test_btts_joint_matches_closed_form():
    dist = derived.goal_distributions(1.6, 1.1)
    joint = derived.btts_from_joint(dist["joint"])
    closed = derived.btts_closed_form(dist["home_marginal"]["0"],
                                      dist["away_marginal"]["0"])
    assert abs(joint["yes"] - closed["yes"]) < 1e-6
    assert abs(joint["yes"] + joint["no"] - 1.0) < 1e-9


def test_mc_crosscheck_flags_divergence():
    analytic = {"over_2_5": 0.5, "btts": 0.5}
    close = derived.mc_crosscheck(analytic, {"over_2_5": 0.505, "btts": 0.498})
    assert close["consistent"]
    far = derived.mc_crosscheck(analytic, {"over_2_5": 0.60, "btts": 0.498})
    assert not far["consistent"]


def test_double_chance_identities():
    dc = derived.double_chance(0.5, 0.3, 0.2)
    assert dc["consistent"]
    assert dc["probabilities"] == {"1x": 0.8, "x2": 0.5, "12": 0.7}


def test_team_totals_monotone():
    team = derived.team_totals(1.6, 1.1)
    assert team["status"] == "ok"
    home = team["home"]
    assert home["over_0_5"] > home["over_1_5"] > home["over_2_5"]


def test_correct_scores_top_and_coverage():
    dist = derived.goal_distributions(1.6, 1.1)
    scores = derived.correct_scores(dist["joint"], top_n=5)
    assert len(scores["top"]) == 5
    assert scores["top"][0]["probability"] >= scores["top"][-1]["probability"]
    assert abs(scores["required_16_mass"] + scores["tail_mass"] - 1.0) < 1e-6
    assert "never a certain outcome" in scores["note"]


# -- scenarios (no DB) ----------------------------------------------------

def test_scenarios_deterministic_and_baseline_preserving():
    base = {"home": 0.5, "draw": 0.3, "away": 0.2}
    first = scenarios.run_all(base, 1.6, 1.1)
    second = scenarios.run_all(base, 1.6, 1.1)
    assert [o.model_dump() for o in first] == [o.model_dump() for o in second]
    names = [o.name for o in first]
    assert names[0] == "baseline" and "high_scoring" in names


def test_scenario_differences_direction():
    base = {"home": 0.5, "draw": 0.3, "away": 0.2}
    high = scenarios.run_scenario(base, 1.6, 1.1, "high_scoring")
    low = scenarios.run_scenario(base, 1.6, 1.1, "low_scoring")
    assert high.markets["over_2_5"] > low.markets["over_2_5"]
    assert high.markets["btts"] > low.markets["btts"]
    assert "not a prediction" in high.label


def test_scenario_param_validation_rejects():
    base = {"home": 0.5, "draw": 0.3, "away": 0.2}
    with pytest.raises(ValueError):
        scenarios.run_scenario(base, 1.6, 1.1, "nope")
    with pytest.raises(ValueError):
        scenarios.run_scenario(base, 1.6, 1.1, "high_scoring",
                               custom_params={"home_mult": 99.0})
    check = scenarios.validate_scenario_params("lambda", {"home_mult": 1.1})
    assert not check["valid"]  # away_mult missing


# -- composer + explanation (DB) -------------------------------------------

def test_composer_complete_prediction(db):
    _, _, target = _round_robin(db)
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()
    assert composed["status"] in ("complete", "partial")
    assert composed["model"]["version"].startswith("ensemble_v1")
    assert composed["probabilities"]["validation"]["valid"]
    assert composed["markets"]["totals"]["consistent"]
    assert composed["markets"]["double_chance"]["consistent"]
    assert composed["uncertainty"]["predictive_entropy"] > 0
    assert composed["data_quality"]["strict_mode"] is True
    assert "will win because" not in composed["explanation"]["headline"]
    assert composed["explanation"]["xg"]["xg_status"] in ("used", "unavailable")


def test_composer_insufficient_data_path(db):
    league = _league(db, code="P6EMPTY")
    teams = _teams(db, league, ("X", "Y"))
    target = _add(db, league, teams, "X", "Y", datetime(2024, 8, 1),
                  None, None, status="SCHEDULED")
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()
    assert composed["status"] == "insufficient_data"
    assert composed["probabilities"]["validation"]["valid"]


def test_composer_unknown_match_rejected(db):
    with pytest.raises(ValueError):
        PredictionComposer().compose(db, 999999, datetime(2024, 8, 1), STRICT)


def test_composer_estimated_mode_labels(db):
    _, _, target = _round_robin(db, code="P6EST")
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at,
        TemporalMode.HISTORICAL_ESTIMATED).model_dump()
    assert composed["data_quality"]["strict_mode"] is False
    assert composed["provenance"]["temporal_mode"] == "historical_estimated"


def test_disagreement_identical_divergent_missing(db):
    _, _, target = _round_robin(db, code="P6DIS")
    composer = PredictionComposer()
    full = composer.disagreement(db, target.id, target.kickoff_at, STRICT)
    assert full.per_outcome["home"]["n_members"] >= 2
    partial = composer.disagreement(
        db, target.id, target.kickoff_at, STRICT, members=("elo", "nope"))
    assert partial.members["nope"]["status"] == "unknown_model"
    assert partial.per_outcome["home"]["n_members"] >= 1


def test_explanation_provenance_and_xg(db):
    from app.services.predictions.outputs import FullPrediction

    _, _, target = _round_robin(db, code="P6EXP")
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT)
    expl = explain(db, target.id, target.kickoff_at, STRICT,
                   FullPrediction(**composed.core_prediction),
                   {}, composed.model_disagreement).model_dump()
    assert expl["provenance"]["model_version"].startswith("ensemble_v1")
    assert expl["elo"]["status"] == "ok"
    assert "home_elo" in expl["elo"] and "away_elo" in expl["elo"]
    assert expl["xg"]["xg_status"] == "unavailable"
    assert expl["xg"]["home_xg_history"] == 0


# -- analogues (DB) ----------------------------------------------------------

def test_analogues_cutoff_safe_and_deterministic(db):
    _, _, target = _round_robin(
        db, code="P6ANA",
        teams=("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"), rounds=9)
    first = analogues.find_analogues(db, target.id, target.kickoff_at, STRICT,
                                     top_k=5)
    second = analogues.find_analogues(db, target.id, target.kickoff_at, STRICT,
                                      top_k=5)
    assert first.status == "ok"
    assert [a["match_id"] for a in first.analogues] == \
        [a["match_id"] for a in second.analogues]
    assert target.id not in [a["match_id"] for a in first.analogues]
    for a in first.analogues:
        assert a["kickoff_at"] < str(target.kickoff_at)
    dist = first.outcome_distribution
    assert abs(dist["home"] + dist["draw"] + dist["away"] - 1.0) < 1e-3


def test_analogues_insufficient_sample(db):
    league = _league(db, code="P6ANA2")
    teams = _teams(db, league, ("X", "Y"))
    _add(db, league, teams, "X", "Y", datetime(2024, 8, 1), 1, 0)
    target = _add(db, league, teams, "X", "Y", datetime(2024, 8, 8),
                  None, None, status="SCHEDULED")
    result = analogues.find_analogues(db, target.id, target.kickoff_at, STRICT)
    assert result.status == "insufficient_sample"
    assert result.outcome_distribution == {}


# -- MiroFish (no DB needed except context) -----------------------------------

class _StubSuccess:
    async def analyze(self, payload: MiroFishInput) -> MiroFishOutput:
        return MiroFishOutput(
            scenario_analysis="stub analysis",
            scenario_probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
            summary="stub")


class _StubInvalid:
    async def analyze(self, payload: MiroFishInput) -> MiroFishOutput:
        return MiroFishOutput(scenario_probabilities={"home": 0.9, "draw": 0.9,
                                                      "away": 0.9})


class _StubSlow:
    async def analyze(self, payload: MiroFishInput) -> MiroFishOutput:
        await asyncio.sleep(5)
        return MiroFishOutput()


def _composed_stub():
    from app.services.intelligence.schemas import ComposedPrediction

    return ComposedPrediction(
        match={"match_id": 1, "kickoff_at": "2024-09-01 15:00:00"},
        cutoff="2024-09-01 15:00:00",
        probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
        goals={"home_lambda": 1.5, "away_lambda": 1.0})


def test_mirofish_success_validated():
    result = asyncio.run(run_mirofish(_composed_stub(), service=_StubSuccess(),
                                      version="stub-v1"))
    assert result.status == "ok"
    assert result.version == "stub-v1"
    assert result.input_reference.startswith("mirofish_ctx_")


def test_mirofish_disabled_reports_unavailable():
    result = asyncio.run(run_mirofish(_composed_stub()))
    assert result.status == "unavailable"
    assert "not configured" in result.output["error"]


def test_mirofish_timeout_and_invalid():
    slow = asyncio.run(run_mirofish(_composed_stub(), service=_StubSlow(),
                                    timeout_seconds=0.05))
    assert slow.status == "unavailable" and "timed out" in slow.output["error"]
    bad = asyncio.run(run_mirofish(_composed_stub(), service=_StubInvalid()))
    assert bad.status == "unavailable"
    assert "validation" in bad.output["error"]


def test_mirofish_output_validation_rules():
    assert validate_output(MiroFishOutput(
        scenario_probabilities={"home": 0.5, "draw": 0.3, "away": 0.2}))["valid"]
    assert not validate_output(MiroFishOutput(
        scenario_probabilities={"home": 0.5, "draw": 0.5, "away": 0.5}))["valid"]
    assert not validate_output(MiroFishOutput(
        scenario_probabilities={"home": -0.1, "draw": 0.3, "away": 0.8}))["valid"]


def test_mirofish_context_labels_and_cutoff_guard():
    ctx = build_context(_composed_stub(), "high_scoring", {"home_mult": 1.1})
    assert ctx.prediction["probabilities_1x2"].kind == "derived"
    assert ctx.scenario["name"].kind == "scenario"
    assert ctx.match["match_id"].kind == "observed"
    with pytest.raises(ValueError):
        ctx.assert_no_future("2024-01-01 00:00:00")


def test_core_prediction_untouched_by_mirofish(db):
    _, _, target = _round_robin(db, code="P6MF")
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT,
        with_disagreement=False, with_market=False)
    before = dict(composed.probabilities)
    asyncio.run(run_mirofish(composed, service=_StubSuccess()))
    assert dict(composed.probabilities) == before


# -- temporal safety (DB) -------------------------------------------------------

def _market_rows(db, match_id, kickoff, closing=False, after=False, book="TestBook"):
    row = db.query(Bookmaker).filter_by(name=book).first()
    if row is None:
        row = Bookmaker(name=book, provider_bookmaker_id="TB" if book == "TestBook" else "TB2")
        db.add(row)
        db.flush()
    stamp = kickoff + timedelta(hours=2 if after else -1)
    source = f"{'TBC' if closing else 'TB'}:h2h"
    snap = OddsSnapshot(match_id=match_id, bookmaker_id=row.id, market_type="h2h",
                        timestamp=stamp, source_market_id=source)
    db.add(snap)
    db.flush()
    for selection, odds in (("home", 2.0), ("draw", 3.5), ("away", 4.0)):
        db.add(OddsSelection(snapshot_id=snap.id, selection=selection, odds=odds,
                             dedup_hash=f"p6-{snap.id}-{selection}"))
    db.commit()
    return snap


def test_closing_and_post_cutoff_excluded(db):
    league = _league(db, code="P6MKT")
    teams = _teams(db, league, ("H", "A"))
    for i in range(6):
        _add(db, league, teams, "H" if i % 2 == 0 else "A",
             "A" if i % 2 == 0 else "H", datetime(2024, 8, 1 + i), 2, 1)
    target = _add(db, league, teams, "H", "A", datetime(2024, 8, 20),
                  None, None, status="SCHEDULED")
    _market_rows(db, target.id, target.kickoff_at, closing=False, after=False)
    _market_rows(db, target.id, target.kickoff_at, closing=False, after=False,
                 book="TestBook2")
    _market_rows(db, target.id, target.kickoff_at, closing=True, after=False)
    _market_rows(db, target.id, target.kickoff_at, closing=False, after=True)
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()
    assert composed["market"]["status"] == "ok"
    assert composed["market"]["consensus"]["closing_snapshots_excluded"] is True
    values = composed["market"]["consensus"]["values"]
    # Regular pre-cutoff prices 2.0/3.5/4.0 -> no-vig normalized.
    total = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert abs(values["home"] - (1 / 2.0) / total) < 1e-5


def test_only_closing_available_reports_unavailable(db):
    league = _league(db, code="P6MKT2")
    teams = _teams(db, league, ("H", "A"))
    for i in range(6):
        _add(db, league, teams, "H" if i % 2 == 0 else "A",
             "A" if i % 2 == 0 else "H", datetime(2024, 8, 1 + i), 2, 1)
    target = _add(db, league, teams, "H", "A", datetime(2024, 8, 20),
                  None, None, status="SCHEDULED")
    _market_rows(db, target.id, target.kickoff_at, closing=True, after=False)
    composed = PredictionComposer().compose(
        db, target.id, target.kickoff_at, STRICT).model_dump()
    assert composed["market"]["status"] == "unavailable"
    assert composed["probabilities"]["validation"]["valid"]


# -- API (client) -----------------------------------------------------------------

def test_api_full_and_sub_endpoints(client, db):
    _, _, target = _round_robin(db, code="P6API")
    response = client.get(f"/api/v1/predictions/{target.id}/full")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["probabilities"]["validation"]["valid"]
    response = client.get(f"/api/v1/predictions/{target.id}/explanation")
    assert response.status_code == 200
    assert "headline" in response.json()
    response = client.get(f"/api/v1/predictions/{target.id}/distribution")
    assert response.status_code == 200
    assert "goal_distributions" in response.json()["markets"]
    response = client.get(f"/api/v1/predictions/{target.id}/models")
    assert response.status_code == 200
    assert "per_outcome" in response.json()
    response = client.get(f"/api/v1/predictions/{target.id}/scenarios")
    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "baseline"


def test_api_post_scenarios_and_mirofish_do_not_touch_core(client, db):
    _, _, target = _round_robin(db, code="P6API2")
    before = client.get(f"/api/v1/predictions/{target.id}/full").json()
    response = client.post(f"/api/v1/predictions/{target.id}/scenarios",
                           json={"names": ["baseline", "high_scoring"]})
    assert response.status_code == 200
    assert response.json()["data"][1]["name"] == "high_scoring"
    response = client.post(f"/api/v1/predictions/{target.id}/mirofish",
                           json={"scenario": "baseline"})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    after = client.get(f"/api/v1/predictions/{target.id}/full").json()
    assert after["probabilities"] == before["probabilities"]
    assert after["core_prediction"]["home_win_probability"] == \
        before["core_prediction"]["home_win_probability"]


def test_api_analogues_and_404s(client, db):
    _, _, target = _round_robin(db, code="P6API3")
    response = client.get(f"/api/v1/predictions/{target.id}/analogues?top_k=3")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "insufficient_sample")
    assert client.get("/api/v1/predictions/999999/full").status_code == 404
    response = client.get(f"/api/v1/predictions/{target.id}/full?model=nope")
    assert response.status_code == 400
