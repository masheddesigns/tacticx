"""Walk-forward validation CLI (Phase 4).

Expanding windows only — never random splits, never shuffle:

    python scripts/walkforward.py --league EPL --train 2015,2022 --validate 2023 --test 2024
    python scripts/walkforward.py --league EPL --train 2015,2022 --validate 2023 --test 2024 --use-xg --json

Trains the ML model on train seasons, learns ensemble weights + calibration
temperature on the validate season, evaluates everything on the test seasons.
Test-period outcomes never influence training, calibration, or weights.
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
from app.services.backtesting.walkforward import run_walkforward, seasons_in_scope  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402


def _parse_list(value: str):
    return [v.strip() for v in value.split(",") if v.strip()]


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Walk-forward model validation.")
    ap.add_argument("--league", default="EPL")
    ap.add_argument("--train", default="", help="Comma-separated train seasons, e.g. 2015,2022")
    ap.add_argument("--validate", default="", help="Validation season, e.g. 2023")
    ap.add_argument("--test", default="", help="Comma-separated test seasons, e.g. 2024")
    ap.add_argument("--members", default="elo,poisson,advanced",
                    help="Comma-separated member models for ensemble_v2")
    ap.add_argument("--use-xg", action="store_true",
                    help="Train the xG variant of the advanced model")
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        if not args.train or not args.validate or not args.test:
            available = seasons_in_scope(db, args.league or None)
            print(f"pass --train/--validate/--test season lists (available: {available})")
            return 1
        result = run_walkforward(
            db, args.league, _parse_list(args.train), args.validate,
            _parse_list(args.test),
            member_names=_parse_list(args.members),
            mode=TemporalMode(args.temporal_mode), use_xg=args.use_xg,
            seed=args.seed, persist=not args.no_persist)
        if args.as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"train_sample={result['train_sample']} "
                  f"validate_sample={result['validate_sample']}")
            print(f"weights={result['weights']} temperature={result['temperature']}")
            header = (f"{'model':<16}{'n':>6}{'acc':>8}{'logloss':>9}"
                      f"{'brier':>8}{'ece':>8}")
            print(header)
            for name, res in result["models"].items():
                metrics = res["metrics"]
                print(f"{name:<16}{res['sample_size']:>6}"
                      f"{_fmt(metrics.get('accuracy_1x2')):>8}"
                      f"{_fmt(metrics.get('log_loss_1x2')):>9}"
                      f"{_fmt(metrics.get('brier_1x2')):>8}"
                      f"{_fmt(metrics.get('ece_home_win')):>8}")
        return 0
    except ValueError as exc:
        print(f"WALKFORWARD FAILED: {exc}")
        return 1
    finally:
        db.close()


def _fmt(value) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
