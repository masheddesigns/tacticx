"""Chronological backtesting CLI (Phase 2).

Walk-forward only — never a random split:

    python scripts/backtest.py --league EPL --season 2024
    python scripts/backtest.py --league EPL --season 2024 --model poisson
    python scripts/backtest.py --model ensemble --temporal-mode strict_prematch
    python scripts/backtest.py --league EPL --from-date 2024-01-01 --to-date 2024-05-31 --json

A dataset summary (from the database, never fabricated) prints first, then
one backtest per requested model. Strict-prematch shortfalls are reported as
sample-size facts, never worked around by weakening the methodology.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.backtesting.runner import dataset_summary, run_backtest  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402
from scripts.predict import build_model  # noqa: E402

MODELS = ["baseline", "elo", "poisson", "poisson-xg", "montecarlo", "ensemble"]


def _parse_date(value: str):
    if not value:
        return None
    return datetime.fromisoformat(value)


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Chronological model backtesting.")
    ap.add_argument("--league", default="")
    ap.add_argument("--season", default="")
    ap.add_argument("--model", default="", help=f"one of {MODELS} (default: all)")
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--from-date", default="")
    ap.add_argument("--to-date", default="")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--simulations", type=int, default=1000,
                    help="Monte Carlo draws per match (backtests default lower for speed)")
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--with-market", action="store_true",
                    help="Append model-vs-market comparison (cutoff-safe, closing as benchmark only)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    requested = [args.model] if args.model else MODELS
    for name in requested:
        if name not in MODELS:
            print(f"unknown model: {name} (choose from {MODELS})")
            return 1

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        date_from = _parse_date(args.from_date)
        date_to = _parse_date(args.to_date)
        mode = TemporalMode(args.temporal_mode)
        summary = dataset_summary(db, args.league or None, args.season or None,
                                  date_from, date_to)
        results = []
        for name in requested:
            if name == "montecarlo":
                model = build_model(name, seed=args.seed, simulations=args.simulations)
            else:
                model = build_model(name)
            results.append(run_backtest(
                db, model, args.league or None, args.season or None,
                date_from, date_to, mode,
                persist=not args.no_persist, seed=args.seed))
        output = {"dataset": summary, "results": results}
        if args.with_market:
            from app.services.backtesting.market_analysis import compare_with_market

            output["market_comparison"] = {
                name: compare_with_market(db, name, args.league or None,
                                          args.season or None, date_from, date_to)
                for name in requested
            }
        if args.as_json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"dataset: total={summary['total_matches']} "
                  f"strict_eligible={summary['strict_prematch_eligible']} "
                  f"insufficient={summary['insufficient_history']}")
            header = (f"{'model':<14}{'n':>6}{'acc':>8}{'logloss':>9}"
                      f"{'brier':>8}{'ece':>8}{'maeH':>8}{'rmseH':>8}")
            print(header)
            for result in results:
                metrics = result["metrics"]
                print(f"{result['model_version']:<14}{result['sample_size']:>6}"
                      f"{_fmt(metrics.get('accuracy_1x2')):>8}"
                      f"{_fmt(metrics.get('log_loss_1x2')):>9}"
                      f"{_fmt(metrics.get('brier_1x2')):>8}"
                      f"{_fmt(metrics.get('ece_home_win')):>8}"
                      f"{_fmt(metrics.get('mae_home_goals')):>8}"
                      f"{_fmt(metrics.get('rmse_home_goals')):>8}")
            for result in results:
                if result["excluded_insufficient"] or result["excluded_temporal"]:
                    print(f"{result['model_version']}: excluded "
                          f"insufficient={result['excluded_insufficient']} "
                          f"temporal={result['excluded_temporal']}")
            if args.with_market:
                for name in requested:
                    _print_market_comparison(name, output["market_comparison"][name])
        return 0
    finally:
        db.close()


def _fmt(value) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"


def _print_market_comparison(name: str, comparison: dict) -> None:
    print(f"market comparison [{name}]: sample={comparison.get('sample_size')} "
          f"skipped_no_market={comparison.get('skipped_no_market')} "
          f"skipped_no_prediction={comparison.get('skipped_no_prediction')}")
    for side in ("model", "market"):
        metrics = (comparison.get(side) or {})
        print(f"  {side:<6} acc={_fmt(metrics.get('accuracy'))} "
              f"logloss={_fmt(metrics.get('log_loss'))} brier={_fmt(metrics.get('brier'))}")
    closing = comparison.get("closing") or {}
    if closing.get("sample_size"):
        print(f"  closing benchmark (NOT an input): n={closing['sample_size']} "
              f"logloss={_fmt(closing.get('log_loss'))} brier={_fmt(closing.get('brier'))}")


if __name__ == "__main__":
    raise SystemExit(main())
