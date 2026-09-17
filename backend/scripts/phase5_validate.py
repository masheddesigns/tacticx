"""Phase 5 robustness + cross-league validation CLI.

Produces deterministic run artifacts under backend/data/phase5/<run_id>/:

    python scripts/phase5_validate.py --analysis baseline --scope "EPL:2024"
    python scripts/phase5_validate.py --analysis all --scope "EPL:2024,La Liga:2015"
    python scripts/phase5_validate.py --analysis sensitivity --scope "EPL:2024"
    python scripts/phase5_validate.py --analysis mc --scope "EPL:2024" --seed 7

Scope format is "LEAGUE:SEASON" (repeatable, comma-separated). Every analysis
is chronological (expanding windows via run_backtest) and never persists
unless --persist is passed. Populations are intersected before any comparison.
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
from app.services.backtesting.runner import dataset_summary, run_backtest  # noqa: E402
from app.services.evaluation import (  # noqa: E402
    artifacts,
    calibration,
    compare,
    sensitivity as sens,
    subgroups,
    uncertainty,
)
from app.services.features.temporal import TemporalMode  # noqa: E402
from scripts.predict import build_model  # noqa: E402

BASELINE_MODELS = ["baseline", "elo", "poisson", "poisson-xg", "montecarlo", "ensemble"]
REFERENCE = "ensemble"


def _parse_scopes(raw: str):
    scopes = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        league, season = part.split(":", 1)
        scopes.append((league.strip(), season.strip()))
    return scopes


def _run_model(db, name: str, league, season, mode, seed, persist, **build_kwargs):
    model = build_model(name, seed=seed,
                        simulations=build_kwargs.get("simulations", 1000))
    return run_backtest(db, model, league, season, None, None, mode,
                        persist=persist, seed=seed, return_details=True)


def _scope_label(league, season) -> str:
    return f"{league or 'ALL'}_{season or 'ALL'}"


def _analysis_baseline(db, scopes, models, mode, seed, persist, with_market):
    from app.services.backtesting.market_analysis import compare_with_market

    report = {"scopes": {}, "reference": REFERENCE}
    for league, season in scopes:
        label = _scope_label(league, season)
        scope_entry = {"dataset": dataset_summary(db, league, season, None, None),
                       "runs": {}}
        details_by_model = {}
        for name in models:
            try:
                result = _run_model(db, name, league, season, mode, seed, persist)
            except Exception as exc:  # never fabricate; record and continue
                scope_entry["runs"][name] = {"status": "failed", "error": str(exc)}
                continue
            details = result.pop("details", [])
            details_by_model[name] = details
            entry = {"status": "ok", "metrics": result["metrics"],
                     "sample_size": result["sample_size"],
                     "excluded_insufficient": result["excluded_insufficient"],
                     "excluded_temporal": result["excluded_temporal"],
                     "model_version": result.get("model_version"),
                     "calibration": calibration.calibration_summary(details)}
            if name in ("ensemble", "elo", "poisson"):
                entry["subgroups"] = subgroups.subgroup_analysis(details)
                entry["extremes"] = subgroups.extreme_probability_audit(details)
            if with_market:
                entry["market"] = compare_with_market(db, name, league, season,
                                                      None, None)
            scope_entry["runs"][name] = entry
        pairs = {}
        if REFERENCE in details_by_model:
            for name, rows in details_by_model.items():
                if name == REFERENCE:
                    continue
                pairs[f"{name}_vs_{REFERENCE}"] = compare.compare_pair(
                    rows, details_by_model[REFERENCE], name, REFERENCE)
        scope_entry["paired_vs_reference"] = pairs
        scope_entry["details"] = details_by_model
        if "poisson" in details_by_model and "poisson-xg" in details_by_model:
            scope_entry["xg_ablation"] = compare.compare_pair(
                details_by_model["poisson"], details_by_model["poisson-xg"],
                "poisson_v1", "poisson_v1-xg")
        report["scopes"][label] = scope_entry
    return report


def _analysis_sensitivity(db, league, season, mode, seed, persist):
    from app.services.predictions.elo import EloConfig, EloModel
    from app.services.predictions.poisson import PoissonConfig, PoissonModel

    base_elo = run_backtest(db, EloModel(), league, season, None, None, mode,
                            persist=persist, seed=seed, return_details=True)
    base_details = base_elo.pop("details", [])
    runs = [{"label": "elo_baseline", "metrics": base_elo["metrics"],
             "sample_size": base_elo["sample_size"]}]
    for variant in sens.sensitivity_runs()["elo"][1:]:
        cfg = EloConfig(k_factor=variant["k_factor"],
                        home_advantage=variant["home_advantage"])
        res = run_backtest(db, EloModel(config=cfg), league, season, None, None,
                           mode, persist=persist, seed=seed, return_details=True)
        det = res.pop("details", [])
        runs.append({"label": variant["label"], "metrics": res["metrics"],
                     "sample_size": res["sample_size"],
                     "max_prob_change": sens.max_probability_change(base_details, det)})
    elo = sens.summarize_sensitivity(base_elo["metrics"], runs)

    base_p = run_backtest(db, PoissonModel(), league, season, None, None, mode,
                          persist=persist, seed=seed, return_details=True)
    base_p_details = base_p.pop("details", [])
    p_runs = [{"label": "poisson_baseline", "metrics": base_p["metrics"],
               "sample_size": base_p["sample_size"]}]
    for half_life in sens.sensitivity_runs()["poisson_half_life_days"]:
        import math as _math

        decay = _math.log(2) / half_life
        res = run_backtest(db, PoissonModel(config=PoissonConfig(recency_decay=decay)),
                           league, season, None, None, mode,
                           persist=persist, seed=seed, return_details=True)
        det = res.pop("details", [])
        p_runs.append({"label": f"half_life_{half_life}d", "metrics": res["metrics"],
                       "sample_size": res["sample_size"],
                       "max_prob_change": sens.max_probability_change(base_p_details, det)})
    poisson = sens.summarize_sensitivity(base_p["metrics"], p_runs)
    return {"scope": _scope_label(league, season), "elo": elo, "poisson": poisson,
            "note": sens.sensitivity_runs().__doc__ or
            "Sensitivity analysis is not hyperparameter tuning."}


def _analysis_mc(db, league, season, mode, seed, persist):
    from scripts.predict import build_model as _build

    grids = {}
    for count in sens.sensitivity_runs()["montecarlo_simulations"]:
        model = _build("montecarlo", seed=seed, simulations=count)
        res = run_backtest(db, model, league, season, None, None, mode,
                           persist=persist, seed=seed, return_details=True)
        grids[count] = res.pop("details", [])
    return {"scope": _scope_label(league, season), "seed": seed,
            "convergence": sens.mc_convergence_stats(grids)}


def _analysis_advanced(db, league, train_seasons, validate_season, test_seasons,
                       mode, seed, persist, use_xg: bool = False):
    """Walk-forward ML protocol with details kept for paired ablations.

    Train (fit advanced) strictly before validate (weights + temperature)
    strictly before test. Advanced ablations: with/without temperature,
    ensemble_v1 (equal) vs ensemble_v2 (learned), v1 members vs advanced.
    """
    from app.services.backtesting.runner import scope_matches
    from app.services.backtesting.walkforward import _member_probs_for
    from app.services.backtesting.weights import blend_probabilities, learn_weights
    from app.services.predictions.advanced import (
        AdvancedConfig,
        AdvancedModel,
        CalibratedModel,
        fit_temperature,
    )
    from app.services.predictions.elo import EloModel
    from app.services.predictions.ensemble import EnsembleModel
    from app.services.predictions.poisson import PoissonModel

    def season_of(match):
        from app.services.backtesting.runner import _season_label

        return _season_label(match.kickoff_at)

    all_matches = scope_matches(db, league_code=league)
    train = [m for m in all_matches if season_of(m) in train_seasons]
    validate = [m for m in all_matches if season_of(m) == validate_season]
    test = [m for m in all_matches if season_of(m) in test_seasons]
    if not train or not validate or not test:
        return {"status": "skipped",
                "reason": f"need non-empty train/validate/test "
                          f"(got {len(train)}/{len(validate)}/{len(test)})"}
    try:
        advanced = AdvancedModel(config=AdvancedConfig(use_xg=use_xg))
        train_meta = advanced.fit(db, train, mode)
    except Exception as exc:
        return {"status": "skipped", "reason": f"advanced fit failed: {exc}"}

    members = {"elo": EloModel(), "poisson": PoissonModel(), "advanced": advanced}
    chosen = list(members)
    try:
        val_maps = {n: _member_probs_for(members[n], db, validate, mode, seed=seed)
                    for n in chosen}
        common = sorted(set.intersection(*(set(v) for v in val_maps.values())))
        if not common:
            return {"status": "skipped", "reason": "no validation match covered by all members"}
        ordered = [[val_maps[n][mid][0] for mid in common] for n in chosen]
        val_actual = [val_maps[chosen[0]][mid][1] for mid in common]
        weights, weight_diag = learn_weights(ordered, val_actual)
        temperature = fit_temperature(blend_probabilities(ordered, weights), val_actual)
    except Exception as exc:
        return {"status": "skipped", "reason": f"validation step failed: {exc}"}
    weight_map = dict(zip(chosen, weights))

    test_from = min(m.kickoff_at for m in test)
    test_to = max(m.kickoff_at for m in test)
    tag = "advanced-xg" if use_xg else "advanced"
    eval_models = {
        "elo": members["elo"],
        "poisson": members["poisson"],
        tag: advanced,
        f"{tag}+cal": CalibratedModel(advanced, temperature,
                                      train_window=f"validate:{validate_season}"),
        "ensemble_v1": EnsembleModel.from_names(["elo", "poisson"]),
        "ensemble_v2": EnsembleModel(
            members=[members[n] for n in chosen],
            weights=[weight_map[n] for n in chosen]),
    }
    test_runs, details_by_model = {}, {}
    for name, model in eval_models.items():
        try:
            res = run_backtest(db, model, league, None, test_from, test_to, mode,
                               persist=persist, seed=seed, return_details=True)
        except Exception as exc:
            test_runs[name] = {"status": "failed", "error": str(exc)}
            continue
        details_by_model[name] = res.pop("details", [])
        test_runs[name] = {"status": "ok", "metrics": res["metrics"],
                           "sample_size": res["sample_size"],
                           "excluded_insufficient": res["excluded_insufficient"],
                           "model_version": res.get("model_version")}
    ablations = {}
    if tag in details_by_model and f"{tag}+cal" in details_by_model:
        ablations["temperature"] = compare.compare_pair(
            details_by_model[tag], details_by_model[f"{tag}+cal"],
            tag, f"{tag}+cal")
    if "ensemble_v1" in details_by_model and "ensemble_v2" in details_by_model:
        ablations["learned_vs_equal_weights"] = compare.compare_pair(
            details_by_model["ensemble_v1"], details_by_model["ensemble_v2"],
            "ensemble_v1", "ensemble_v2")
    if tag in details_by_model and "elo" in details_by_model:
        ablations["advanced_vs_elo"] = compare.compare_pair(
            details_by_model[tag], details_by_model["elo"], tag, "elo_v1")
    return {"status": "ok", "league": league, "train_seasons": train_seasons,
            "validate_season": validate_season, "test_seasons": test_seasons,
            "train_rows": train_meta.get("rows"), "train_dropped": train_meta.get("dropped"),
            "validate_n": len(common), "weights": weight_map,
            "weight_diagnostics": weight_diag, "temperature": temperature,
            "use_xg": use_xg, "test_runs": test_runs, "ablations": ablations,
            "details": details_by_model}


def _analysis_weights(db, league, season, mode, seed, persist):
    from app.services.predictions.elo import EloModel
    from app.services.predictions.ensemble import EnsembleModel
    from app.services.predictions.poisson import PoissonModel

    base = run_backtest(db, EnsembleModel(), league, season, None, None, mode,
                        persist=persist, seed=seed, return_details=True)
    base_details = base.pop("details", [])
    variants = {
        "equal_weights": [0.5, 0.5],
        "elo_heavy": [0.75, 0.25],
        "poisson_heavy": [0.25, 0.75],
        "elo_only": [1.0, 0.0],
        "poisson_only": [0.0, 1.0],
    }
    member_detail_map = {}
    out = {}
    for label, weights in variants.items():
        model = EnsembleModel(members=[EloModel(), PoissonModel()], weights=weights)
        res = run_backtest(db, model, league, season, None, None, mode,
                           persist=persist, seed=seed, return_details=True)
        det = res.pop("details", [])
        out[label] = {"metrics": res["metrics"], "sample_size": res["sample_size"],
                      "paired_vs_equal": compare.compare_pair(
                          det, base_details, label, "ensemble_v1_equal")}
        if label in ("elo_only", "poisson_only"):
            member_detail_map[label] = det
    out["member_disagreement"] = uncertainty.ensemble_disagreement(
        {"elo_v1": member_detail_map.get("elo_only", []),
         "poisson_v1": member_detail_map.get("poisson_only", [])})
    return {"scope": _scope_label(league, season), "variants": out}


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Phase 5 validation runs.")
    ap.add_argument("--analysis", default="baseline",
                    choices=["baseline", "sensitivity", "mc", "weights", "advanced", "all"])
    ap.add_argument("--train-seasons", default="2022",
                    help="comma-separated train seasons (advanced analysis)")
    ap.add_argument("--validate-season", default="2023",
                    help="validation season (advanced analysis)")
    ap.add_argument("--test-seasons", default="2024",
                    help="comma-separated test seasons (advanced analysis)")
    ap.add_argument("--use-xg", action="store_true",
                    help="fit advanced-xg (requires estimated mode for xG rows)")
    ap.add_argument("--scope", default="EPL:2024",
                    help='comma-separated "LEAGUE:SEASON" scopes')
    ap.add_argument("--models", default=",".join(BASELINE_MODELS))
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--persist", action="store_true")
    ap.add_argument("--with-market", action="store_true")
    ap.add_argument("--label", default="validation")
    args = ap.parse_args()

    scopes = _parse_scopes(args.scope)
    if not scopes:
        print("no valid scopes (expected LEAGUE:SEASON, ...) ")
        return 1
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        fingerprint = artifacts.dataset_fingerprint()
        rid = artifacts.run_id(args.analysis, fingerprint, args.label)
        mode = TemporalMode(args.temporal_mode)
        payload = {"run_id": rid, "analysis": args.analysis,
                   "scopes": args.scope, "models": models,
                   "metadata": artifacts.environment_metadata(
                       {"dataset_fingerprint": fingerprint,
                        "temporal_mode": args.temporal_mode, "seed": args.seed})}
        analyses = (["baseline", "sensitivity", "mc", "weights", "advanced"]
                    if args.analysis == "all" else [args.analysis])
        for kind in analyses:
            if kind == "baseline":
                payload["baseline"] = _analysis_baseline(
                    db, scopes, models, mode, args.seed, args.persist, args.with_market)
            elif kind == "advanced":
                league, _ = scopes[0]
                payload["advanced"] = _analysis_advanced(
                    db, league, [s.strip() for s in args.train_seasons.split(",") if s.strip()],
                    args.validate_season,
                    [s.strip() for s in args.test_seasons.split(",") if s.strip()],
                    mode, args.seed, args.persist, use_xg=args.use_xg)
            elif kind == "sensitivity":
                league, season = scopes[0]
                payload["sensitivity"] = _analysis_sensitivity(
                    db, league, season, mode, args.seed, args.persist)
            elif kind == "mc":
                league, season = scopes[0]
                payload["mc"] = _analysis_mc(db, league, season, mode, args.seed,
                                             args.persist)
            elif kind == "weights":
                league, season = scopes[0]
                payload["weights"] = _analysis_weights(
                    db, league, season, mode, args.seed, args.persist)
        path = artifacts.save_artifact(rid, f"{args.analysis}_report", payload)
        print(json.dumps({"run_id": rid, "artifact": path,
                          "scopes": list((payload.get("baseline") or {}).get("scopes", {}))},
                         indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
