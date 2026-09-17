"""Phase 5 deep-dive: detail-rich scopes + distribution/drift/ML-xg audits.

Re-runs small scoped backtests WITH extended detail rows (goals, scores,
grids) and computes: draw calibration, goal-distribution audit, correct-score
audit, train/test drift diagnostics, Poisson truncation audit over observed
lambdas, and the same-season advanced vs advanced-xg experiment. Everything
is saved under backend/data/phase5/<run_id>/deepdive_report.json.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.backtesting.runner import run_backtest, scope_matches  # noqa: E402
from app.services.evaluation import (  # noqa: E402
    artifacts,
    compare,
    sensitivity,
    subgroups,
)
from app.services.features.temporal import TemporalMode  # noqa: E402
from scripts.predict import build_model  # noqa: E402


def _run(db, name, league, season, mode, seed, date_from=None, date_to=None):
    model = build_model(name, seed=seed)
    res = run_backtest(db, model, league, season, date_from, date_to, mode,
                       persist=False, seed=seed, return_details=True)
    details = res.pop("details", [])
    return res, details


def _same_season_ml_experiment(db, mode, seed):
    """advanced vs advanced-xg, first-half fit, second-half test, LA_LIGA 2015."""
    from app.services.predictions.advanced import AdvancedConfig, AdvancedModel

    matches = sorted(scope_matches(db, league_code="LA_LIGA", season="2015"),
                     key=lambda m: (m.kickoff_at, m.id))
    cut = len(matches) // 2
    train, test = matches[:cut], matches[cut:]
    experiment = {"league": "LA_LIGA", "season": "2015",
                  "train_n": len(train), "test_n": len(test),
                  "cut_kickoff": str(test[0].kickoff_at)}
    details = {}
    for tag, use_xg in (("advanced", False), ("advanced-xg", True)):
        model = AdvancedModel(config=AdvancedConfig(use_xg=use_xg))
        try:
            meta = model.fit(db, train, mode)
        except Exception as exc:
            experiment[tag] = {"status": "failed", "error": str(exc)}
            continue
        res = run_backtest(db, model, "LA_LIGA", None,
                           test[0].kickoff_at, test[-1].kickoff_at,
                           mode, persist=False, seed=seed, return_details=True)
        details[tag] = res.pop("details", [])
        experiment[tag] = {"status": "ok", "train_rows": meta.get("rows"),
                           "train_dropped": meta.get("dropped"),
                           "metrics": res["metrics"], "sample_size": res["sample_size"]}
    if "advanced" in details and "advanced-xg" in details:
        experiment["paired"] = compare.compare_pair(
            details["advanced"], details["advanced-xg"], "advanced_v1", "advanced_v1-xg")
    return experiment


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Phase 5 deep-dive audits.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--label", default="deepdive")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        fingerprint = artifacts.dataset_fingerprint()
        rid = artifacts.run_id("deepdive", fingerprint, args.label)
        strict = TemporalMode.STRICT_PREMATCH
        estimated = TemporalMode.HISTORICAL_ESTIMATED
        payload = {"run_id": rid,
                   "metadata": artifacts.environment_metadata(
                       {"dataset_fingerprint": fingerprint, "seed": args.seed})}

        # -- detail-rich strict scope (EPL 2024) -------------------------
        strict_details, strict_runs = {}, {}
        for name in ("elo", "poisson", "ensemble"):
            res, det = _run(db, name, "EPL", "2024", strict, args.seed)
            strict_runs[name] = {"metrics": res["metrics"],
                                 "sample_size": res["sample_size"]}
            strict_details[name] = det
        payload["strict_scope"] = {"league": "EPL", "season": "2024",
                                   "mode": strict.value, "runs": strict_runs}

        ens = strict_details["ensemble"]
        payload["draw_calibration_strict"] = subgroups.draw_calibration(
            ens, league_draw_baseline=0.25)
        payload["goal_distribution_strict"] = subgroups.goal_distribution_audit(
            [r for r in strict_details["poisson"] if r.get("expected_home_goals") is not None])
        payload["score_distribution_strict"] = subgroups.score_distribution_audit(
            [r for r in strict_details["poisson"] if r.get("score_probabilities")])
        payload["subgroups_strict"] = subgroups.subgroup_analysis(ens)
        payload["extremes_strict"] = subgroups.extreme_probability_audit(ens)

        # -- drift: EPL 2023 (train-era) vs EPL 2024 (test-era) -----------
        _, train_det = _run(db, "ensemble", "EPL", "2023", strict, args.seed)
        payload["drift"] = subgroups.drift_diagnostics(train_det, ens)

        # -- truncation over observed lambdas ----------------------------
        lambdas = [(r["expected_home_goals"], r["expected_away_goals"])
                   for r in strict_details["poisson"]
                   if r.get("expected_home_goals") is not None
                   and r.get("expected_away_goals") is not None]
        payload["truncation"] = sensitivity.truncation_audit(lambdas, max_goals=10)

        # -- detail-rich estimated scope (LA_LIGA 2015, xG active) --------
        est_details, est_runs = {}, {}
        for name in ("poisson", "poisson-xg", "ensemble"):
            res, det = _run(db, name, "LA_LIGA", "2015", estimated, args.seed)
            est_runs[name] = {"metrics": res["metrics"],
                              "sample_size": res["sample_size"]}
            est_details[name] = det
        payload["estimated_scope"] = {"league": "LA_LIGA", "season": "2015",
                                      "mode": estimated.value, "runs": est_runs}
        payload["xg_ablation_estimated"] = compare.compare_pair(
            est_details["poisson"], est_details["poisson-xg"],
            "poisson_v1", "poisson_v1-xg")
        payload["draw_calibration_estimated"] = subgroups.draw_calibration(
            est_details["poisson-xg"], league_draw_baseline=0.25)
        payload["goal_distribution_estimated"] = subgroups.goal_distribution_audit(
            [r for r in est_details["poisson-xg"]
             if r.get("expected_home_goals") is not None])

        # -- same-season ML xG experiment --------------------------------
        payload["ml_xg_experiment"] = _same_season_ml_experiment(db, estimated, args.seed)

        path = artifacts.save_artifact(rid, "deepdive_report", payload)
        print(json.dumps({"run_id": rid, "artifact": path}, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
