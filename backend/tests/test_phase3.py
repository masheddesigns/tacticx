"""Phase 3 tests: market math, consensus, timelines, reconstruction, model
comparison, market API, market backtesting. Deterministic fixtures only —
no live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _utcnow():
    """Aware UTC now — naive local wall-clock would corrupt temporal tests
    on machines whose local timezone is not UTC."""
    return datetime.now(timezone.utc)

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
from app.services.market.compare import agreement_label, compare
from app.services.market.consensus import aggregate, consensus, price_summary
from app.services.market.probabilities import (
    MARKET_PROBABILITY_V1,
    implied_probability,
    market_completeness,
    no_vig_probabilities,
    overround,
    validate_price,
)
from app.services.market.repository import closing_state, get_market_state
from app.services.market.timeline import (
    MOVEMENT_V1,
    dedupe_observations,
    opening_status,
    timeline,
    velocity,
)

BASE = datetime(2024, 9, 15, 10, 0, 0)


def _league(db, code="MKT"):
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="9", season="2024")
    db.add(league)
    db.commit()
    return league


_team_counter = {"n": 0}


def _match(db, league, kickoff=None):
    _team_counter["n"] += 1
    suffix = _team_counter["n"]
    home = Team(league_id=league.id, name="Home FC", provider="test",
                provider_team_id=f"h{suffix}")
    away = Team(league_id=league.id, name="Away FC", provider="test",
                provider_team_id=f"a{suffix}")
    db.add_all([home, away])
    db.flush()
    match = Match(league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                  kickoff_at=kickoff or datetime(2024, 9, 15, 19, 30),
                  status="SCHEDULED", home_score=None, away_score=None,
                  provider="test", provider_match_id=f"m{suffix}")
    db.add(match)
    db.commit()
    return match


def _bookmaker(db, name, key):
    bookmaker = Bookmaker(name=name, provider="test", provider_bookmaker_id=key)
    db.add(bookmaker)
    db.commit()
    return bookmaker


def _snapshot(db, match, bookmaker, market, timestamp, selections,
              source="test", market_id=""):
    snap = OddsSnapshot(match_id=match.id,
                        bookmaker_id=bookmaker.id if bookmaker else None,
                        market_type=market, timestamp=timestamp, source=source,
                        is_live=False, source_event_id="e1",
                        source_market_id=market_id or None)
    db.add(snap)
    db.flush()
    for selection, price in selections.items():
        assert price > 1.0
        db.add(OddsSelection(
            snapshot_id=snap.id, selection=selection, odds=price, point=None,
            dedup_hash=f"{snap.id}-{selection}-{price}"))
    db.commit()
    return snap


def _h2h_match(db):
    league = _league(db)
    match = _match(db, league)
    book_a = _bookmaker(db, "Bookmaker A", "a")
    book_b = _bookmaker(db, "Bookmaker B", "b")
    # Bookmaker A: two polls, price drifting down.
    _snapshot(db, match, book_a, "h2h", BASE,
              {"home": 1.82, "draw": 3.60, "away": 4.50}, market_id="a:h2h")
    _snapshot(db, match, book_a, "h2h", BASE + timedelta(hours=4),
              {"home": 1.75, "draw": 3.70, "away": 4.80}, market_id="a:h2h")
    # Bookmaker B: single poll.
    _snapshot(db, match, book_b, "h2h", BASE + timedelta(hours=2),
              {"home": 1.80, "draw": 3.75, "away": 4.60}, market_id="b:h2h")
    return match, book_a, book_b


# ------------------------------------------------------------------ implied

def test_implied_probability():
    assert implied_probability(2.00) == pytest.approx(0.50)
    assert implied_probability(4.00) == pytest.approx(0.25)


def test_validate_price_rejects():
    assert validate_price(1.80) == (True, "")
    ok, reason = validate_price(1.0)
    assert not ok and reason
    ok, _ = validate_price(0.5)
    assert not ok
    ok, _ = validate_price("abc")
    assert not ok
    ok, _ = validate_price(float("nan"))
    assert not ok
    # Never silently repaired: invalid input stays invalid.
    assert validate_price(None)[0] is False


# ------------------------------------------------------------------ overround

def test_overround_complete_market():
    total, pct, version = overround({"home": 2.00, "draw": 3.50, "away": 4.00})
    assert total == pytest.approx(1.0357, abs=1e-4)
    assert pct == pytest.approx(3.57, abs=1e-2)
    assert version == MARKET_PROBABILITY_V1


def test_overround_empty():
    total, pct, _ = overround({})
    assert total is None and pct is None


# ------------------------------------------------------------------ no-vig

def test_no_vig_normalization():
    probs, version = no_vig_probabilities({"home": 2.00, "draw": 3.50, "away": 4.00})
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert probs["home"] == pytest.approx(0.50 / 1.0357, abs=1e-3)
    assert probs["draw"] == pytest.approx(0.2857 / 1.0357, abs=1e-3)
    assert probs["away"] == pytest.approx(0.25 / 1.0357, abs=1e-3)
    assert version == MARKET_PROBABILITY_V1


def test_no_vig_incomplete_market_handling():
    # Partial markets still normalize over what exists (caller gates
    # overround/consensus on completeness separately).
    probs, _ = no_vig_probabilities({"home": 1.80, "away": 4.50})
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    empty, _ = no_vig_probabilities({})
    assert empty == {}


# ------------------------------------------------------------------ completeness

def test_market_completeness():
    assert market_completeness("h2h", ["home", "draw", "away"]) == "complete"
    assert market_completeness("h2h", ["home", "away"]) == "partial"
    assert market_completeness("h2h", ["home"]) == "partial"
    assert market_completeness("h2h", []) == "insufficient"
    assert market_completeness("totals", ["over_2.5", "under_2.5"]) == "complete"
    assert market_completeness("totals", ["over_2.5"]) == "partial"
    assert market_completeness("corners", ["over_9.5"]) == "unknown"


# ------------------------------------------------------------------ consensus

def test_consensus_median_default():
    result = consensus({
        "A": {"home": 0.50, "draw": 0.28, "away": 0.22},
        "B": {"home": 0.48, "draw": 0.29, "away": 0.23},
        "C": {"home": 0.49, "draw": 0.27, "away": 0.24},
    })
    assert result["values"]["home"] == pytest.approx(0.49)
    assert result["method"] == "median"
    assert result["bookmakers_used"] == 3
    assert "market_consensus_v1" in result["calculation_version"]


def test_consensus_mean_and_trimmed():
    vectors = {
        "A": {"home": 0.50}, "B": {"home": 0.48},
        "C": {"home": 0.90}, "D": {"home": 0.49},
    }
    mean = consensus(vectors, method="mean", min_bookmakers=1)
    assert mean["values"]["home"] == pytest.approx((0.50 + 0.48 + 0.90 + 0.49) / 4)
    trimmed = consensus(vectors, method="trimmed_mean", min_bookmakers=1)
    # Outlier 0.90 dropped with n>=4: median of the middle two.
    assert trimmed["values"]["home"] == pytest.approx((0.49 + 0.50) / 2)
    small = consensus({"A": {"home": 0.5}, "B": {"home": 0.9}},
                      method="trimmed_mean", min_bookmakers=1)
    assert small["values"]["home"] == pytest.approx(0.7)  # falls back to median


def test_consensus_missing_bookmaker_and_minimum():
    result = consensus({"A": {"home": 0.5, "draw": 0.3}}, min_bookmakers=2)
    assert result["values"] == {}
    result = consensus({"A": {"home": 0.5}, "B": {}}, min_bookmakers=1)
    assert result["values"] == {"home": 0.5}
    assert aggregate([], method="mean") is None


def test_price_summary():
    summary = price_summary([1.82, 1.80, 1.85, 1.81])
    assert summary["best"] == 1.85
    assert summary["worst"] == 1.80
    assert summary["median"] == pytest.approx(1.815)
    assert summary["count"] == 4
    assert price_summary([])["count"] == 0


# ------------------------------------------------------------------ movement

def test_movement_directions():
    down = timeline([(BASE, 1.80), (BASE + timedelta(hours=2), 1.70)])
    assert down["direction"] == "down"
    assert down["percentage_movement"] == pytest.approx(-5.56, abs=1e-2)
    assert down["absolute_movement"] == pytest.approx(-0.10)
    up = timeline([(BASE, 1.70), (BASE + timedelta(hours=1), 1.80)])
    assert up["direction"] == "up"
    flat = timeline([(BASE, 1.80), (BASE + timedelta(hours=1), 1.80)])
    assert flat["direction"] == "flat"
    assert flat["number_of_movements"] == 0
    assert flat["calculation_version"] == MOVEMENT_V1


def test_movement_velocity_unit():
    # 1.80 -> 1.70 over 2h: -5.555... percentage points per hour ~= -2.7778.
    result = timeline([(BASE, 1.80), (BASE + timedelta(hours=2), 1.70)])
    assert result["movement_velocity_per_hour"] == pytest.approx(-2.7778, abs=1e-3)
    assert result["time_to_close_hours"] == pytest.approx(2.0)


def test_velocity_zero_interval():
    assert velocity(1.0, 0.0) is None
    assert velocity(1.0, None) is None
    assert velocity(-5.0, 2.0) == pytest.approx(-2.5)
    zero = timeline([(BASE, 1.80), (BASE, 1.70)])
    assert zero["movements"][0]["velocity_per_hour"] is None
    # Sub-minute intervals (bulk-import batch stamps) record the movement
    # but refuse to annualize it into a nonsense velocity.
    tiny = timeline([(BASE, 1.80), (BASE + timedelta(milliseconds=9), 1.70)])
    assert tiny["number_of_movements"] == 1
    assert tiny["movements"][0]["velocity_per_hour"] is None
    assert tiny["movement_velocity_per_hour"] is None


def test_dedupe_and_out_of_order():
    points = [(BASE + timedelta(hours=2), 1.70), (BASE, 1.80),
              (BASE + timedelta(hours=1), 1.80)]
    distinct = dedupe_observations(points)
    assert [p for _, p in distinct] == [1.80, 1.70]
    dup = dedupe_observations([(BASE, 1.80), (BASE, 1.75)])
    assert len(dup) == 2  # same timestamp kept, movement still computed
    assert timeline([])["observations"] == 0


def test_opening_status():
    assert opening_status(True, True) == "source_verified"
    assert opening_status(False, True) == "first_observed"
    assert opening_status(False, False) == "unknown"


# ------------------------------------------------------------------ reconstruction

def test_cutoff_selects_latest_valid(db):
    match, _, _ = _h2h_match(db)
    cutoff = BASE + timedelta(hours=3)
    state = get_market_state(db, match.id, cutoff, "h2h")
    assert state["bookmakers_available"] == 2
    assert state["market_completeness"] == "complete"
    assert state["timestamp_quality"] in ("simultaneous", "spread")
    # Bookmaker A's state is the 10:00 poll, not the 14:00 one.
    book_a = next(b for b in state["bookmakers"] if b["bookmaker"] == "Bookmaker A")
    assert book_a["selections"]["home"]["price"] == 1.82


def test_future_odds_excluded(db):
    match, _, _ = _h2h_match(db)
    state = get_market_state(db, match.id, BASE + timedelta(minutes=30), "h2h")
    assert state["bookmakers_available"] == 1
    assert state["bookmakers"][0]["bookmaker"] == "Bookmaker A"
    # Before anything exists: insufficient, never an error-shaped guess.
    empty = get_market_state(db, match.id, BASE - timedelta(hours=1), "h2h")
    assert empty["bookmakers_available"] == 0
    assert empty["market_completeness"] == "insufficient"


def test_missing_match_reconstruction(db):
    state = get_market_state(db, 999999, BASE, "h2h")
    assert state["error"] == "match not found"


# ------------------------------------------------------------------ comparison

def test_probability_differences():
    result = compare({"home": 0.55, "draw": 0.25, "away": 0.20},
                     {"home": 0.49, "draw": 0.28, "away": 0.23})
    assert result["differences"]["home"]["absolute_difference"] == pytest.approx(0.06)
    assert result["differences"]["home"]["relative_difference"] == pytest.approx(
        0.06 / 0.49)
    assert "calculation_version" in result
    lowered = str(result).lower()
    for phrase in ("bet this", "best bet", "value bet", "stake", "sure win", "lock"):
        assert phrase not in lowered


def test_agreement_labels():
    same = {"home": 0.55, "draw": 0.25, "away": 0.20}
    close = {"home": 0.54, "draw": 0.26, "away": 0.20}
    assert agreement_label({}, same, close) == "neutral"  # no overlap to compare
    assert compare(same, close)["agreement"] == "strong_agreement"
    mild = {"home": 0.50, "draw": 0.28, "away": 0.22}
    assert compare(same, mild)["agreement"] == "moderate_agreement"
    flipped = {"home": 0.20, "draw": 0.25, "away": 0.55}
    assert compare(same, flipped)["agreement"] == "strong_disagreement"
    other_winner_close = {"home": 0.33, "draw": 0.35, "away": 0.32}
    label = compare({"home": 0.34, "draw": 0.33, "away": 0.33},
                    other_winner_close)["agreement"]
    assert label == "neutral"  # different winners, tiny spread


# ------------------------------------------------------------------ closing

def test_closing_identified_and_benchmark_only(db):
    league = _league(db)
    match = _match(db, league)
    book = _bookmaker(db, "Closer", "c")
    _snapshot(db, match, book, "h2h", BASE, {"home": 1.90, "draw": 3.40, "away": 4.20},
              market_id="c:h2h")
    _snapshot(db, match, book, "h2h", BASE + timedelta(hours=8),
              {"home": 1.75, "draw": 3.60, "away": 4.50}, market_id="cC:h2h")
    state = closing_state(db, match.id, "h2h")
    assert state["available"] is True
    assert state["bookmakers"][0]["selections"]["home"]["price"] == 1.75
    # A pre-closing cutoff must NOT see the closing snapshot.
    early = get_market_state(db, match.id, BASE + timedelta(hours=1), "h2h")
    assert early["bookmakers"][0]["selections"]["home"]["price"] == 1.90
    # No closing data at all: honest unavailability.
    league2 = _league(db, code="MKT2")
    match2 = _match(db, league2)
    assert closing_state(db, match2.id, "h2h")["available"] is False


# ------------------------------------------------------------------ quality

def test_incomplete_and_conflicting(db):
    league = _league(db)
    match = _match(db, league)
    book = _bookmaker(db, "Thin", "t")
    _snapshot(db, match, book, "h2h", BASE, {"home": 1.80, "away": 4.50},
              market_id="t:h2h")
    state = get_market_state(db, match.id, BASE + timedelta(hours=1), "h2h")
    assert state["market_completeness"] == "partial"
    assert state["bookmakers"][0]["completeness"] == "partial"


# ------------------------------------------------------------------ API

def test_markets_endpoints(client, db, sample_match):
    league = db.query(League).filter_by(code="EPL").one()
    match = db.query(Match).filter_by(provider_match_id="12345").one()
    book = _bookmaker(db, "API Book", "api")
    book2 = _bookmaker(db, "API Book 2", "api2")
    _snapshot(db, match, book, "h2h", _utcnow() - timedelta(minutes=4),
              {"home": 2.00, "draw": 3.50, "away": 4.00}, market_id="api:h2h")
    _snapshot(db, match, book2, "h2h", _utcnow() - timedelta(minutes=2),
              {"home": 2.10, "draw": 3.40, "away": 4.00}, market_id="api2:h2h")
    state = client.get(f"/api/v1/markets/{match.id}").json()
    assert state["market_completeness"] == "complete"
    assert state["consensus"]["bookmakers_used"] == 2
    home_consensus = state["consensus"]["values"]["home"]
    assert 0.46 < home_consensus < 0.49  # median of the two books' no-vig
    assert abs(sum(state["consensus"]["values"].values()) - 1.0) < 1e-6
    assert state["best_prices"]["home"]["best"] == 2.10  # highest decimal wins
    assert state["best_prices"]["home"]["worst"] == 2.00
    history = client.get(f"/api/v1/markets/{match.id}/history").json()
    assert history["series"][0]["opening_status"] == "first_observed"
    movement = client.get(f"/api/v1/markets/{match.id}/movement").json()
    home_move = next(m for m in movement["movements"] if m["selection"] == "home")
    assert home_move["opening"] == 2.00
    assert home_move["direction"] == "flat"  # single observation per book
    consensus = client.get(f"/api/v1/markets/{match.id}/consensus").json()
    assert consensus["consensus"]["method"] == "median"
    comparison = client.get(
        f"/api/v1/markets/{match.id}/comparison?model=ensemble").json()
    assert "error" in comparison["comparison"]  # no stored prediction yet
    assert client.get("/api/v1/markets/999999").status_code == 404
    assert client.get(f"/api/v1/markets/{match.id}?cutoff=not-a-date").status_code == 400


# ------------------------------------------------------------------ backtest market analysis

def test_market_analysis_comparison(db):
    from app.db.models.predictions import Prediction
    from app.services.backtesting.market_analysis import compare_with_market

    match, _, _ = _h2h_match(db)
    match.status = "FINISHED"
    match.home_score = 1
    match.away_score = 0
    db.commit()
    db.add(Prediction(
        match_id=match.id, model_version="ensemble_v1", prediction_type="1x2",
        predicted_probability=0.55,
        probabilities={"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
        confidence=0.3, model_name="ensemble",
        prediction_cutoff=BASE + timedelta(hours=5),
        temporal_mode="strict_prematch", status="valid"))
    db.commit()
    report = compare_with_market(db, "ensemble")
    assert report["sample_size"] == 1
    assert report["skipped_no_market"] == 0
    assert report["model"]["accuracy"] == 1.0
    assert report["market"]["accuracy"] in (0.0, 1.0)
    assert report["closing"]["sample_size"] == 0  # no closing lines in fixture
    assert len(report["examples"]) == 1
    assert report["examples"][0]["actual"] == "home"
    empty = compare_with_market(db, "no-such-model")
    assert empty["sample_size"] == 0
    assert empty["skipped_no_prediction"] == 1
