"""Offline player-feature experiment (Phase 9, descriptive only).

Compares baseline ensemble_v1 against an EXPERIMENTAL variant that adjusts
ensemble log-odds with one transparent player feature (home/away starter
continuity differential, logistic weight fit on a train window). The
experimental model is versioned experimental_ensemble_player_v0, evaluated
chronologically (train strictly before test), and NEVER promoted: this
script writes no production rows and changes no model versions.

Reports population, availability, strict/estimated, league/season, N,
missingness, Brier/log-loss/accuracy/calibration, paired differences with
bootstrap CIs. Insufficient sample -> NOT ENOUGH DATA.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import Match  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.evaluation.compare import compare_pair  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402
from app.services.intelligence.composer import build_core_model  # noqa: E402
from app.services.player_intelligence import feature_snapshot  # noqa: E402

EXPERIMENT_VERSION = "experimental_ensemble_player_v0"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _continuity_diff(snapshot: dict) -> float | None:
    try:
        home = snapshot["home"]["team"]["regular_starter_continuity"]["value"]
        away = snapshot["away"]["team"]["regular_starter_continuity"]["value"]
    except (KeyError, TypeError):
        return None
    if home is None or away is None:
        return None
    return home - away


def _fit_weight(train_rows):
    """Single logistic weight on the continuity differential (deterministic
    grid search on train NLL; train outcomes only)."""
    best_w, best_nll = 0.0, float("inf")
    for w in [i / 10.0 for i in range(-20, 21)]:
        nll = 0.0
        for probs, diff, actual in train_rows:
            logits = [math.log(max(p, 1e-9)) for p in probs]
            logits[0] += w * diff
            logits[2] -= w * diff
            total = sum(math.exp(v) for v in logits)
            adjusted = [math.exp(v) / total for v in logits]
            nll -= math.log(max(adjusted[actual], 1e-12))
        if nll < best_nll:
            best_nll, best_w = nll, w
    return best_w


def _adjust(probs, diff, weight):
    logits = [math.log(max(p, 1e-9)) for p in probs]
    logits[0] += weight * diff
    logits[2] -= weight * diff
    total = sum(math.exp(v) for v in logits)
    return [math.exp(v) / total for v in logits]


def run_experiment(db, league_code: str, split_iso: str,
                   mode: TemporalMode) -> dict:
    from app.db.models.core import League

    league = db.query(League).filter_by(code=league_code).first()
    if league is None:
        return {"league": league_code, "status": "unknown_league"}
    split = datetime.fromisoformat(split_iso)
    matches = db.query(Match).filter(
        Match.league_id == league.id, Match.status == "FINISHED",
        Match.home_score.is_not(None), Match.kickoff_at.is_not(None)).order_by(
            Match.kickoff_at.asc()).all()
    ensemble = build_core_model("ensemble")
    train_rows, test_detail_base, test_detail_exp, tested = [], [], [], []
    for match in matches:
        cutoff = match.kickoff_at
        try:
            snapshot = feature_snapshot.build_snapshot(
                db, match.id, cutoff, mode, persist=False)
        except ValueError:
            continue
        if snapshot["home"].get("status") != "ok" or \
                snapshot["away"].get("status") != "ok":
            continue
        diff = _continuity_diff(snapshot)
        if diff is None:
            continue
        try:
            pred = ensemble.predict(db, match.id, cutoff, mode)
        except Exception:
            continue
        if pred.status != "valid":
            continue
        probs = [pred.home_win_probability, pred.draw_probability,
                 pred.away_win_probability]
        actual = 0 if (match.home_score or 0) > (match.away_score or 0) else (
            1 if match.home_score == match.away_score else 2)
        row = (probs, diff, actual)
        if cutoff < split:
            train_rows.append(row)
        else:
            tested.append({"match_id": match.id, "row": row})
    report = {"experiment": EXPERIMENT_VERSION, "league": league_code,
              "mode": mode.value, "split": split_iso,
              "train_n": len(train_rows), "test_n": len(tested)}
    if len(train_rows) < 30 or len(tested) < 30:
        report["status"] = "NOT ENOUGH DATA"
        return report
    weight = _fit_weight(train_rows)
    for item in tested:
        probs, diff, actual = item["row"]
        test_detail_base.append({"match_id": item["match_id"], "probs": probs,
                                 "actual": actual})
        test_detail_exp.append({"match_id": item["match_id"],
                                "probs": _adjust(probs, diff, weight),
                                "actual": actual})
    report["status"] = "complete"
    report["fitted_weight"] = weight
    report["paired"] = compare_pair(test_detail_base, test_detail_exp,
                                    "ensemble_v1", EXPERIMENT_VERSION)
    return report


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Offline player-feature experiment.")
    ap.add_argument("--league", default="LA_LIGA")
    ap.add_argument("--split", default="2016-01-01T00:00:00")
    ap.add_argument("--temporal-mode", default="historical_estimated",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        report = run_experiment(db, args.league, args.split,
                                TemporalMode(args.temporal_mode))
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(f"{report['experiment']} [{report.get('status')}] "
                  f"train={report['train_n']} test={report['test_n']}")
            if report.get("paired"):
                print(json.dumps(report["paired"], indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
