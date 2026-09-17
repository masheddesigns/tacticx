"""Generate a stored prediction for one match (Phase 2).

    python scripts/predict.py --match-id 123 --model ensemble
    python scripts/predict.py --match-id 123 --model poisson --seed 7 --json

Models: elo, poisson, poisson-xg, montecarlo, ensemble, baseline.
Probabilities are statistical estimates with honest uncertainty — never
certainties. No betting, no staking, no guarantees anywhere in this system.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import Match  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.backtesting.service import store_full_prediction  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402
from app.services.predictions.ensemble import (  # noqa: E402
    BaselineModel,
    EnsembleModel,
)
from app.services.predictions.montecarlo import MonteCarloModel  # noqa: E402
from app.services.predictions.poisson import (  # noqa: E402
    PoissonModel,
    xg_enhanced_config,
)
from app.services.predictions.elo import EloModel  # noqa: E402


def build_model(name: str, seed=None, simulations: int = 10000):
    if name == "elo":
        return EloModel()
    if name == "poisson":
        return PoissonModel()
    if name == "poisson-xg":
        return PoissonModel(config=xg_enhanced_config())
    if name == "montecarlo":
        return MonteCarloModel(n_simulations=simulations, random_seed=seed)
    if name == "ensemble":
        return EnsembleModel()
    if name == "baseline":
        return BaselineModel()
    if name == "advanced":
        from app.services.predictions.advanced import AdvancedModel

        return AdvancedModel()
    if name == "advanced-xg":
        from app.services.predictions.advanced import AdvancedConfig, AdvancedModel

        return AdvancedModel(config=AdvancedConfig(use_xg=True))
    if name == "advanced_goal":
        from app.services.predictions.advanced import AdvancedGoalModel

        return AdvancedGoalModel()
    raise ValueError(f"unknown model: {name} "
                     "(elo|poisson|poisson-xg|montecarlo|ensemble|baseline|"
                     "advanced|advanced-xg|advanced_goal)")


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Generate a stored match prediction.")
    ap.add_argument("--match-id", type=int, required=True)
    ap.add_argument("--model", default="ensemble")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--simulations", type=int, default=10000)
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        match = db.get(Match, args.match_id)
        if match is None:
            print(f"no match with id {args.match_id}")
            return 1
        cutoff = match.kickoff_at or datetime.now()
        model = build_model(args.model, seed=args.seed, simulations=args.simulations)
        mode = TemporalMode(args.temporal_mode)
        pred = model.predict(db, args.match_id, cutoff, mode)
        row_id = None
        if not args.no_persist:
            config = getattr(getattr(model, "config", None), "as_dict", lambda: None)()
            if callable(getattr(model, "config_dict", None)):
                config = model.config_dict()
            stored = store_full_prediction(db, args.match_id, pred, model_config=config)
            row_id = stored.id
        out = pred.model_dump()
        out["prediction_id"] = row_id
        if args.as_json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"{pred.model_name} {pred.model_version} [{pred.status}] "
                  f"mode={pred.temporal_mode}")
            print(f"  1X2: H={pred.home_win_probability:.3f} "
                  f"D={pred.draw_probability:.3f} A={pred.away_win_probability:.3f}")
            if pred.expected_total_goals is not None:
                print(f"  xG: H={pred.expected_home_goals:.2f} "
                      f"A={pred.expected_away_goals:.2f} T={pred.expected_total_goals:.2f}")
            if pred.over_2_5_probability is not None:
                print(f"  O2.5={pred.over_2_5_probability:.3f} "
                      f"BTTS_yes={pred.btts_yes_probability:.3f}")
            if pred.score_probabilities:
                top = sorted(pred.score_probabilities.items(),
                             key=lambda kv: kv[1], reverse=True)[:5]
                print("  scores: " + ", ".join(f"{s}={p:.3f}" for s, p in top))
            print(f"  cutoff={pred.prediction_cutoff} xg_used={pred.xg_used}")
            for note in pred.data_quality:
                print(f"  note: {note}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
