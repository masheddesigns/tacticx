"""Walk-forward validation orchestration (Phase 4).

Expanding windows only — never random splits, never shuffle:

    train    : seasons strictly before the validation season
    validate : one season (weight learning + calibration fitting)
    test     : one or more later seasons (final evaluation)

Example: train=[2022] (or [2015, 2022]), validate=2023, test=[2024].

Only fitted artifacts (ML coefficients, calibrator temperature, ensemble
weights) cross from train/validate into test — each test prediction still
uses its own kickoff as cutoff for all feature queries. Test-period outcomes
never influence training, calibration, or weights (enforced by construction
and tested).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.predictions import ModelEvaluation, ModelTrainingRun
from app.services.backtesting import metrics as met
from app.services.backtesting.runner import INDEX, actual_outcome, run_backtest, scope_matches
from app.services.backtesting.weights import blend_probabilities, learn_weights
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.advanced import (
    AdvancedConfig,
    AdvancedModel,
    CalibratedModel,
    fit_temperature,
)
from app.services.predictions.ensemble import EnsembleModel
from app.services.predictions.outputs import FullPrediction


def _bootstrap_cis(details) -> Dict:
    """Seeded bootstrap CIs over the test population (descriptive only)."""
    from app.config import get_settings
    from app.services.backtesting import metrics as met

    if not details:
        return {}
    settings = get_settings()
    probs = [d["probs"] for d in details]
    actual = [d["actual"] for d in details]
    out = {}
    boot = lambda fn: met.bootstrap_ci(
        fn, probs, actual,
        n_boot=settings.BOOTSTRAP_SAMPLES, seed=settings.BOOTSTRAP_SEED)
    out["accuracy"] = boot(lambda p, a: met.accuracy_from_probs(p, a))
    out["log_loss"] = boot(lambda p, a: met.multiclass_log_loss(p, a))
    out["brier"] = boot(lambda p, a: met.multiclass_brier(p, a))
    return out


def seasons_in_scope(db: Session, league_code: Optional[str] = None) -> List[str]:
    """Distinct season labels present, sorted chronologically."""
    from app.services.backtesting.runner import _season_label

    seasons = set()
    for match in scope_matches(db, league_code=league_code):
        seasons.add(_season_label(match.kickoff_at))
    return sorted(s for s in seasons if s != "unknown")


def fit_advanced_for_scope(db: Session, model, league_code: Optional[str],
                           scope_start, mode: TemporalMode,
                           persist: bool = True) -> Optional[int]:
    """Fit an AdvancedModel on finished matches strictly before the scope
    window (train strictly before test). Returns the training run id."""
    from app.services.features.temporal import as_naive_utc as _naive

    start = _naive(scope_start)
    train_matches = [m for m in scope_matches(db, league_code=league_code)
                     if _naive(m.kickoff_at) is not None and start is not None
                     and _naive(m.kickoff_at) < start]
    meta = model.fit(db, train_matches, mode)
    if not persist:
        return None
    row = ModelTrainingRun(
        model_name=model.model_name, model_version=model.model_version,
        feature_version="features_v1", league=league_code or "",
        train_from=min((m.kickoff_at for m in train_matches), default=None),
        train_to=max((m.kickoff_at for m in train_matches), default=None),
        train_sample=meta.get("rows", 0), train_dropped=meta.get("dropped", 0),
        temporal_mode=mode.value, config=model.config_dict(),
        metrics={"train_loss": meta.get("train_loss")},
        params={"coef": meta.get("coef"), "scaler_mean": meta.get("scaler_mean"),
                "scaler_scale": meta.get("scaler_scale")})
    db.add(row)
    db.commit()
    return row.id


def _member_probs_for(model, db: Session, matches, mode: TemporalMode,
                      seed: Optional[int] = None):
    """Generate {match_id: (1X2 vector, actual index)} with cutoff = kickoff."""
    import inspect

    out = {}
    for match in matches:
        cutoff = as_naive_utc(match.kickoff_at)
        try:
            params = inspect.signature(model.predict).parameters
            if "seed" in params:
                pred = model.predict(db, match.id, cutoff, mode, seed=seed)
            else:
                pred = model.predict(db, match.id, cutoff, mode)
        except Exception:
            continue
        if not isinstance(pred, FullPrediction) or pred.status != "valid":
            continue
        outcome = actual_outcome(match)
        if outcome is None:
            continue
        out[match.id] = ([pred.home_win_probability, pred.draw_probability,
                          pred.away_win_probability], INDEX[outcome])
    return out


def run_walkforward(db: Session, league_code: str,
                    train_seasons: List[str], validate_season: str,
                    test_seasons: List[str],
                    member_names: Optional[List[str]] = None,
                    mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                    use_xg: bool = False, seed: Optional[int] = None,
                    persist: bool = True) -> Dict:
    """Full walk-forward protocol. Returns per-model test metrics + weights."""
    from app.services.predictions.elo import EloModel
    from app.services.predictions.poisson import PoissonModel, xg_enhanced_config

    member_names = member_names or ["elo", "poisson", "advanced"]
    train_matches, validate_matches, test_matches = [], [], []
    for match in scope_matches(db, league_code=league_code):
        from app.services.backtesting.runner import _season_label

        label = _season_label(match.kickoff_at)
        if label in train_seasons:
            train_matches.append(match)
        elif label == validate_season:
            validate_matches.append(match)
        elif label in test_seasons:
            test_matches.append(match)
    if not train_matches:
        raise ValueError("empty training window")
    if not validate_matches:
        raise ValueError("empty validation window")
    if not test_matches:
        raise ValueError("empty test window")

    # -- fit advanced ML on TRAIN only ---------------------------------
    advanced = AdvancedModel(config=AdvancedConfig(
        use_xg=use_xg,
        minimum_xg_matches=5 if use_xg else 3))
    train_meta = advanced.fit(db, train_matches, mode)
    train_meta.update({"train_seasons": train_seasons, "league": league_code})
    training_row_id = None
    if persist:
        row = ModelTrainingRun(
            model_name=advanced.model_name, model_version=advanced.model_version,
            feature_version="features_v1", league=league_code,
            train_from=min(m.kickoff_at for m in train_matches),
            train_to=max(m.kickoff_at for m in train_matches),
            train_sample=train_meta.get("rows", 0),
            train_dropped=train_meta.get("dropped", 0),
            temporal_mode=mode.value, config=advanced.config_dict(),
            metrics={"train_loss": train_meta.get("train_loss")},
            params={"coef": train_meta.get("coef"),
                    "scaler_mean": train_meta.get("scaler_mean"),
                    "scaler_scale": train_meta.get("scaler_scale")})
        db.add(row)
        db.commit()
        training_row_id = row.id

    # -- member predictions on VALIDATE (for weights + calibration) -----
    # Populations are intersected by match id so every comparison is fair.
    members = {"elo": EloModel(), "poisson": PoissonModel(), "advanced": advanced}
    chosen = [m for m in member_names if m in members]
    if not chosen:
        raise ValueError(f"no known members in {member_names}")
    val_maps = {name: _member_probs_for(members[name], db, validate_matches, mode,
                                        seed=seed)
                for name in chosen}
    common_ids = sorted(set.intersection(
        *(set(val_maps[name]) for name in chosen))) if chosen else []
    if not common_ids:
        raise ValueError("no validation match covered by all members")
    ordered = [[val_maps[name][mid][0] for mid in common_ids] for name in chosen]
    val_actual = [val_maps[chosen[0]][mid][1] for mid in common_ids]
    weights, weight_diag = learn_weights(ordered, val_actual)
    weight_map = dict(zip(chosen, weights))

    # -- calibration on VALIDATE ensemble -------------------------------
    blended_val = blend_probabilities(ordered, weights)
    temperature = fit_temperature(blended_val, val_actual)
    calibrated_members = {n: CalibratedModel(members[n], temperature,
                                             train_window=f"validate:{validate_season}")
                          for n in chosen}

    # -- evaluate on TEST ------------------------------------------------
    # Date bounds restrict run_backtest to the test window exactly.
    test_kickoffs = sorted(m.kickoff_at for m in test_matches)
    test_from, test_to = test_kickoffs[0], test_kickoffs[-1]
    results: Dict = {"weights": weight_map, "weight_diagnostics": weight_diag,
                     "temperature": temperature, "training_run_id": training_row_id,
                     "models": {}}
    eval_models = {}
    for name in chosen:
        eval_models[name] = members[name]
        eval_models[f"{name}+cal"] = calibrated_members[name]
    base_pair = [n for n in ("elo", "poisson") if n in chosen]
    if base_pair:
        eval_models["ensemble_v1"] = EnsembleModel.from_names(base_pair)
    eval_models["ensemble_v2"] = EnsembleModel(
        members=[members[n] for n in chosen],
        weights=[weight_map[n] for n in chosen])
    for name, model in eval_models.items():
        result = run_backtest(
            db, model, league_code, None, test_from, test_to, mode,
            persist=persist, seed=seed, return_details=True)
        result["test_seasons"] = test_seasons
        result["metrics_ci"] = _bootstrap_cis(result.pop("details", []))
        results["models"][name] = result
        if persist:
            db.add(ModelEvaluation(
                training_run_id=training_row_id, model_name=name,
                model_version=getattr(model, "model_version", "?"),
                league=league_code, season=",".join(test_seasons),
                temporal_mode=mode.value, sample_size=result["sample_size"],
                metrics=result["metrics"]))
    if persist:
        db.commit()
    results["train_sample"] = len(train_matches)
    results["validate_sample"] = len(common_ids)
    return results
