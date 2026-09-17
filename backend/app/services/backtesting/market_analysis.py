"""Market comparison over stored backtest predictions (Phase 3).

Reads predictions the models already stored, reconstructs the market state
at each prediction's own cutoff (never future odds), and compares both
probability sources against actual outcomes. Closing lines are a benchmark
only — never an input (enforced: market-at-cutoff comes from the cutoff
repository; closing is fetched separately for display).

No superiority is claimed without adequate sample size; the report carries
sample counts alongside every metric.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.predictions import Prediction
from app.services.backtesting import metrics as met
from app.services.backtesting.runner import INDEX, actual_outcome, scope_matches
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.market.compare import compare
from app.services.market.consensus import consensus
from app.services.market.probabilities import (
    MARKET_PROBABILITY_V1,
    market_completeness,
    no_vig_probabilities,
)
from app.services.market.repository import closing_state, get_market_state

OUTCOMES = ("home", "draw", "away")


def _latest_predictions(db: Session, model_name: str, match_ids: List[int]):
    """Latest stored prediction per match for one model (no double counting
    across repeated backtest runs)."""
    rows = (db.query(Prediction)
            .filter(Prediction.model_name == model_name,
                    Prediction.match_id.in_(match_ids),
                    Prediction.status == "valid")
            .order_by(Prediction.prediction_timestamp.desc()).all()) if match_ids else []
    latest: Dict[int, Prediction] = {}
    for row in rows:
        latest.setdefault(row.match_id, row)
    return latest


def _market_no_vig(db: Session, match_id: int, cutoff, market: str = "h2h"):
    """Consensus no-vig probabilities at cutoff, or (None, reason)."""
    state = get_market_state(db, match_id, cutoff, market)
    if state.get("error"):
        return None, "no match"
    vectors = {}
    for book in state["bookmakers"]:
        if book["completeness"] != "complete":
            continue
        prices = {sel: info["price"] for sel, info in book["selections"].items()}
        probs, _ = no_vig_probabilities(prices)
        if probs:
            vectors[book["bookmaker"] or f"book_{len(vectors)}"] = probs
    if not vectors:
        return None, f"no complete {market} market at cutoff"
    result = consensus(vectors)
    if not result["values"]:
        return None, "consensus below bookmaker minimum"
    return result["values"], None


def compare_with_market(db: Session, model_name: str,
                        league_code: Optional[str] = None,
                        season: Optional[str] = None,
                        date_from=None, date_to=None,
                        market: str = "h2h") -> Dict:
    """Model vs market over stored predictions. Returns aggregates + examples."""
    matches = scope_matches(db, league_code, season, date_from, date_to)
    match_ids = [m.id for m in matches]
    stored = _latest_predictions(db, model_name, match_ids)
    model_probs: List[List[float]] = []
    market_probs: List[List[float]] = []
    closing_probs: List[List[float]] = []
    actual: List[int] = []
    skipped_no_market = 0
    skipped_no_prediction = 0
    examples = []
    for match in matches:
        row = stored.get(match.id)
        if row is None or not row.probabilities:
            skipped_no_prediction += 1
            continue
        probs = row.probabilities
        model_vec = [probs.get("home_win"), probs.get("draw"), probs.get("away_win")]
        if any(v is None for v in model_vec):
            skipped_no_prediction += 1
            continue
        cutoff = row.prediction_cutoff or match.kickoff_at
        market_vec, reason = _market_no_vig(db, match.id, cutoff, market)
        if market_vec is None:
            skipped_no_market += 1
            continue
        ordered = [market_vec.get(o) for o in OUTCOMES]
        if any(v is None for v in ordered):
            skipped_no_market += 1
            continue
        outcome = actual_outcome(match)
        if outcome is None:
            continue
        model_probs.append(model_vec)
        market_probs.append(ordered)
        actual.append(INDEX[outcome])
        closing = closing_state(db, match.id, market)
        closing_vec = None
        if closing.get("available"):
            vectors = {}
            for book in closing["bookmakers"]:
                if market_completeness(market, list(book["selections"])) != "complete":
                    continue
                prices = {sel: info["price"] for sel, info in book["selections"].items()}
                probs_c, _ = no_vig_probabilities(prices)
                if probs_c:
                    vectors[book["bookmaker"] or f"book_{len(vectors)}"] = probs_c
            if vectors:
                consensus_c = consensus(vectors)["values"]
                ordered_c = [consensus_c.get(o) for o in OUTCOMES]
                if all(v is not None for v in ordered_c):
                    closing_vec = ordered_c
        if closing_vec is not None:
            closing_probs.append(closing_vec)
        if len(examples) < 5:
            examples.append({
                "match_id": match.id,
                "model": [round(v, 4) for v in model_vec],
                "market": [round(v, 4) for v in ordered],
                "closing": [round(v, 4) for v in closing_vec] if closing_vec else None,
                "actual": outcome,
                "comparison": compare(
                    dict(zip(OUTCOMES, model_vec)), dict(zip(OUTCOMES, ordered))),
            })
    report: Dict = {
        "model": model_name,
        "market": market,
        "sample_size": len(actual),
        "skipped_no_prediction": skipped_no_prediction,
        "skipped_no_market": skipped_no_market,
        "calculation_version": MARKET_PROBABILITY_V1,
    }
    if actual:
        model_pred = met.argmax_labels(model_probs)
        market_pred = met.argmax_labels(market_probs)
        report["model"] = {
            "accuracy": round(met.accuracy_from_probs(model_probs, actual), 4),
            "log_loss": round(met.multiclass_log_loss(model_probs, actual), 4),
            "brier": round(met.multiclass_brier(model_probs, actual), 4),
            "ece_home": met.expected_calibration_error(
                [p[0] for p in model_probs], [1 if a == 0 else 0 for a in actual]),
        }
        report["market"] = {
            "accuracy": round(met.accuracy_from_probs(market_probs, actual), 4),
            "log_loss": round(met.multiclass_log_loss(market_probs, actual), 4),
            "brier": round(met.multiclass_brier(market_probs, actual), 4),
            "ece_home": met.expected_calibration_error(
                [p[0] for p in market_probs], [1 if a == 0 else 0 for a in actual]),
        }
        if closing_probs and len(closing_probs) == len(actual):
            report["closing"] = {
                "sample_size": len(closing_probs),
                "log_loss": round(met.multiclass_log_loss(closing_probs, actual), 4),
                "brier": round(met.multiclass_brier(closing_probs, actual), 4),
            }
        else:
            report["closing"] = {"sample_size": 0, "note": "insufficient closing coverage"}
    else:
        report["model"] = {}
        report["market"] = {}
        report["closing"] = {"sample_size": 0, "note": "no comparable sample"}
    report["examples"] = examples
    report["note"] = ("Closing lines are a benchmark, never a prediction input. "
                      "No superiority claimed without adequate sample size.")
    return report
