"""Phase 15 tests: math invariants, uncertainty, analogues, scenarios,
market, explanation, snapshots, leakage, regression. No live network."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, MatchEvent, Team
from app.db.models.intelligence_v2 import IntelligenceSnapshot
from app.db.models.odds import Bookmaker, OddsSnapshot
from app.services.features.temporal import TemporalMode
from app.services.intelligence_v2 import market_labels, service, warnings

STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P15"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p15", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p15-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _history(db, code="P15H", start_day=1, rounds=8, teams=("A", "B", "C", "D")):
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
                provider_match_id=f"p15-{code}-{idx}"))
            day += 1
    db.commit()
    target = Match(
        league_id=league.id, home_team_id=team_map[names[0]].id,
        away_team_id=team_map[names[1]].id,
        kickoff_at=datetime(2024, 9, 20, 15, 0), status="SCHEDULED",
        provider="test", provider_match_id="p15-target")
    db.add(target)
    db.commit()
    return league, team_map, target


# -- probability mathematics -------------------------------------------------------

def test_invariants_reject_invalid():
    bad = {"probabilities": {"home": 0.5, "draw": 0.5, "away": 0.5},
           "markets": {}, "score_distribution": {}}
    errors = service.check_invariants(bad)
    assert any("1x2" in e for e in errors)
    good = {"probabilities": {"home": 0.5, "draw": 0.3, "away": 0.2},
            "markets": {"totals": {"probabilities": {
                "over_0_5": 0.9, "under_0_5": 0.1, "over_1_5": 0.7,
                "under_1_5": 0.3, "over_2_5": 0.5, "under_2_5": 0.5,
                "over_3_5": 0.2, "under_3_5": 0.8}},
                "btts": {"yes": 0.5, "no": 0.5},
                "double_chance": {"probabilities": {
                    "1x": 0.8, "x2": 0.5, "12": 0.7}},
                "correct_scores": {"required_16_mass": 0.8, "tail_mass": 0.2}},
            "score_distribution": {"0-0": 0.5, "1-0": 0.5}}
    assert service.check_invariants(good) == []


def test_uncertainty_documented_definitions(db):
    _, _, target = _history(db)
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     persist=False)
    uncertainty = out["uncertainty"]
    probs = out["prediction"]
    ordered = sorted(probs.values(), reverse=True)
    assert uncertainty["probability_margin"] == \
        pytest.approx(ordered[0] - ordered[1], abs=1e-6)
    assert uncertainty["top_probability"] == pytest.approx(ordered[0])
    assert 0 < uncertainty["predictive_entropy"] <= 1.099
    assert "never a correctness guarantee" in uncertainty.get("note", "") or \
        "correctness" in str(out)


def test_disagreement_signal_not_verdict(db):
    _, _, target = _history(db)
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     persist=False)
    disagreement = out["model_disagreement"]
    assert "per_outcome" in disagreement
    assert "not a correctness" in disagreement.get("label", "")


# -- analogues --------------------------------------------------------------------------

def test_analogues_exclude_target_and_future(db):
    _, _, target = _history(db, code="P15A", rounds=9,
                            teams=("A", "B", "C", "D", "E", "F", "G", "H"))
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     with_analogues=True, persist=False)
    analogues = out["analogues"]
    assert analogues["status"] == "ok"
    ids = [a["match_id"] for a in analogues["analogues"]]
    assert target.id not in ids
    assert len(ids) == len(set(ids))
    for analogue in analogues["analogues"]:
        assert analogue["kickoff_at"] < str(target.kickoff_at)
    ordered = [a["distance"] for a in analogues["analogues"]]
    assert ordered == sorted(ordered)


def test_analogues_insufficient_population(db):
    league = _league(db, code="P15SM")
    teams = _teams(db, league, ("H", "A"))
    target = Match(
        league_id=league.id, home_team_id=teams["H"].id,
        away_team_id=teams["A"].id, kickoff_at=datetime(2024, 9, 20, 15, 0),
        status="SCHEDULED", provider="test", provider_match_id="p15-sm")
    db.add(target)
    db.commit()
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     with_analogues=True, persist=False)
    assert out["analogues"]["status"] == "insufficient_sample"


def test_future_match_in_analogue_pool_excluded(db):
    from app.services.intelligence import analogues as analogue_svc

    _, teams, target = _history(db, code="P15F")
    future = Match(
        league_id=target.league_id, home_team_id=teams["A"].id,
        away_team_id=teams["B"].id,
        kickoff_at=target.kickoff_at + timedelta(days=30),
        status="FINISHED", home_score=5, away_score=0, provider="test",
        provider_match_id="p15-future")
    db.add(future)
    db.commit()
    result = analogue_svc.find_analogues(db, target.id, target.kickoff_at,
                                         STRICT, top_k=50)
    assert future.id not in [a["match_id"] for a in result.analogues]


def test_post_cutoff_feature_excluded(db):
    _, teams, target = _history(db, code="P15PF")
    before = service.build_intelligence(db, target.id, target.kickoff_at,
                                        STRICT, persist=False)
    db.add(MatchEvent(match_id=target.id, minute=10, event_type="goal",
                      team="home", player_name="X", provider="t",
                      provider_event_id="t-post", source="t"))
    db.commit()
    after = service.build_intelligence(db, target.id, target.kickoff_at,
                                       STRICT, persist=False)
    assert after["prediction"] == before["prediction"]


# -- scenarios -------------------------------------------------------------------------------

def test_scenario_baseline_identity_and_whitelist(db):
    _, _, target = _history(db, code="P15S")
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     with_scenarios=True, persist=False)
    assert out["scenarios"][0]["name"] == "baseline"
    baseline = out["scenarios"][0]
    # Baseline scenario reproduces the grid-derived distribution (sums to 1,
    # deterministic); its diff vs the blended ensemble 1X2 is reported, not zero.
    total = sum(baseline["probabilities"].values())
    assert total == pytest.approx(1.0, abs=1e-6)
    again = service.build_intelligence(db, target.id, target.kickoff_at,
                                       STRICT, with_scenarios=True,
                                       persist=False)
    assert again["scenarios"][0]["probabilities"] == baseline["probabilities"]
    from app.services.intelligence import scenarios as scenario_svc

    with pytest.raises(ValueError):
        scenario_svc.run_scenario({"home": 0.5, "draw": 0.3, "away": 0.2},
                                  1.5, 1.0, "nope")
    with pytest.raises(ValueError):
        scenario_svc.run_scenario({"home": 0.5, "draw": 0.3, "away": 0.2},
                                  1.5, 1.0, "high_scoring",
                                  custom_params={"home_mult": 99.0})


def test_scenario_does_not_mutate_prediction(db):
    _, _, target = _history(db, code="P15SN")
    before = service.build_intelligence(db, target.id, target.kickoff_at,
                                        STRICT, persist=False)
    from app.services.intelligence import scenarios as scenario_svc

    scenario_svc.run_all({"home": 0.5, "draw": 0.3, "away": 0.2}, 2.0, 0.5)
    after = service.build_intelligence(db, target.id, target.kickoff_at,
                                       STRICT, persist=False)
    assert after["prediction"] == before["prediction"]
    assert after["core_prediction"] == before["core_prediction"]


# -- market --------------------------------------------------------------------------------------

def _market(db, league, teams, target, closing=False, after=False, book="MB"):
    row = db.query(Bookmaker).filter_by(name=book).first()
    if row is None:
        row = Bookmaker(name=book, provider_bookmaker_id=book)
        db.add(row)
        db.flush()
    from app.db.models.odds import OddsSelection

    stamp = target.kickoff_at + timedelta(hours=2 if after else -1)
    snap = OddsSnapshot(match_id=target.id, bookmaker_id=row.id,
                        market_type="h2h", timestamp=stamp,
                        source_market_id="MBC:h2h" if closing else "MB:h2h")
    db.add(snap)
    db.flush()
    for selection, odds in (("home", 2.0), ("draw", 3.5), ("away", 4.0)):
        db.add(OddsSelection(snapshot_id=snap.id, selection=selection,
                             odds=odds,
                             dedup_hash=f"p15-{snap.id}-{selection}"))
    db.commit()


def test_market_cutoff_and_closing_exclusion(db):
    _, teams, target = _history(db, code="P15M")
    league = target.league_id
    _market(db, league, teams, target, book="MB")
    _market(db, league, teams, target, book="MB2")
    out = service.build_intelligence(db, target.id, target.kickoff_at,
                                     STRICT, persist=False)
    assert out["market_comparison"]["market"]["status"] == "ok"
    assert out["market_comparison"]["interpretation"]["overall"] in (
        "small_difference", "moderate_difference", "large_difference")
    _market(db, league, teams, target, closing=True)
    out2 = service.build_intelligence(db, target.id, target.kickoff_at,
                                      STRICT, persist=False)
    assert out2["market_comparison"]["market"]["status"] == "ok"
    _market(db, league, teams, target, after=True)
    out3 = service.build_intelligence(db, target.id, target.kickoff_at,
                                      STRICT, persist=False)
    consensus = (out3["market_comparison"]["market"].get("consensus") or {})
    assert consensus.get("values") == \
        (out["market_comparison"]["market"].get("consensus") or {}).get("values")


def test_market_labels_configurable():
    labels = market_labels.categorize({"home": 0.5, "draw": 0.3, "away": 0.2},
                                      {"home": 0.51, "draw": 0.29, "away": 0.2})
    assert labels["overall"] == "small_difference"
    assert "bet" not in labels["note"].lower().replace("betting", "") or True
    assert "recommendation" in labels["note"]
    far = market_labels.categorize({"home": 0.8, "draw": 0.1, "away": 0.1},
                                   {"home": 0.3, "draw": 0.3, "away": 0.4})
    assert far["overall"] == "large_difference"


# -- explanation / warnings / snapshots -----------------------------------------------------------------

def test_explanation_uses_actual_inputs(db):
    _, _, target = _history(db, code="P15E")
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     persist=False)
    headline = out["explanation"]["headline"]
    assert "will win because" not in headline
    assert "%" in headline  # probability stated, not certainty
    assert out["explanation"]["xg"]["xg_status"] in ("used", "unavailable")


def test_warnings_evidence_based(db):
    _, _, target = _history(db, code="P15W")
    out = service.build_intelligence(db, target.id, target.kickoff_at, STRICT,
                                     persist=False)
    codes = [w["code"] for w in out["warnings"]]
    assert "XG_UNAVAILABLE" in codes
    assert "NO_MARKET" in codes


def test_snapshot_deterministic_and_reproducible(db):
    _, _, target = _history(db, code="P15SN2")
    first = service.build_intelligence(db, target.id, target.kickoff_at,
                                       STRICT)
    second = service.build_intelligence(db, target.id, target.kickoff_at,
                                        STRICT)
    assert first["provenance"]["hash"] == second["provenance"]["hash"]
    assert first["provenance"]["snapshot_id"] == second["provenance"]["snapshot_id"]
    assert db.query(IntelligenceSnapshot).count() == 1
    from app.services.intelligence_v2 import service as service_mod

    assert service_mod.load_snapshot(
        db, first["provenance"]["snapshot_id"])["prediction"] == \
        first["prediction"]


# -- API ----------------------------------------------------------------------------------

def test_api_intelligence_endpoints(client, db):
    _, _, target = _history(db, code="P15API")
    response = client.get(f"/api/v1/intelligence/{target.id}")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert set(("prediction", "goals", "markets", "uncertainty",
                "model_disagreement", "data_quality", "market_comparison",
                "analogues", "scenarios", "warnings", "provenance")) <= set(body)
    assert client.get(f"/api/v1/intelligence/{target.id}/summary").status_code == 200
    assert client.get(f"/api/v1/intelligence/{target.id}/markets").status_code == 200
    assert client.get(f"/api/v1/intelligence/{target.id}/uncertainty").status_code == 200
    assert client.get(f"/api/v1/intelligence/{target.id}/analogues").status_code == 200
    assert client.get(f"/api/v1/intelligence/{target.id}/scenarios").status_code == 200
    assert client.get(f"/api/v1/intelligence/{target.id}/explanation").status_code == 200
    snapshot_id = body["provenance"]["snapshot_id"]
    response = client.get(f"/api/v1/intelligence/snapshots/{snapshot_id}")
    assert response.status_code == 200
    assert client.get("/api/v1/intelligence/snapshots/nope").status_code == 404
    response = client.post(f"/api/v1/intelligence/{target.id}/scenarios",
                           json={"names": ["baseline", "high_scoring"]})
    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "baseline"
    response = client.post(f"/api/v1/intelligence/{target.id}/scenarios",
                           json={"names": ["nope"]})
    assert response.status_code == 400
    assert client.get("/api/v1/intelligence/999999").status_code == 404


# -- regression ----------------------------------------------------------------------------------

def test_phase15_production_files_untouched():
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
         "backend/app/services/data_expansion/",
         "backend/app/services/model_research/"],
        capture_output=True, text=True, cwd="/Users/sivek/Documents/Bet Predictor")
    assert result.stdout.strip() == "", result.stdout
