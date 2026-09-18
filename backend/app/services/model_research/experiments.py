"""Experiment runner: walk-forward + folds + baselines + registry (Phase 12).

Reads baseline probabilities from stored production predictions where they
exist (matching model_version + cutoff); computes live only for gaps
(counted). Candidates train inside their windows; calibration fits on
validation; test labels never enter training, scaling, selection or
calibration. Every run registers (dataset/model/seed/artifact hash) and
saves hashed artifacts. Nothing here writes production tables.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.predictions import Prediction
from app.services.backtesting.runner import _season_label
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.model_research import artifacts as artifact_svc
from app.services.model_research import calibration as calibration_svc
from app.services.model_research import candidates as candidate_svc
from app.services.model_research import datasets as dataset_svc
from app.services.model_research import evaluation as evaluation_svc
from app.services.model_research import features as feature_svc
from app.services.model_research import promotion as promotion_svc
from app.services.model_research import significance as significance_svc
from app.services.model_research import splits as splits_svc
from app.services.model_research import training as training_svc

BASELINE_VERSIONS = {"baseline_ensemble": "ensemble_v1-elo+poisson",
                     "baseline_elo": "elo_v1",
                     "baseline_poisson": "poisson_v1"}


def stored_baseline_probs(db: Session, match_ids: List[int],
                          model_version: str) -> Dict[int, List[float]]:
    """Latest stored production probabilities per match (never refit)."""
    out = {}
    if not match_ids:
        return out
    rows = db.query(Prediction).filter(
        Prediction.match_id.in_(match_ids),
        Prediction.model_version == model_version,
        Prediction.status == "valid").order_by(Prediction.id.asc()).all()
    for row in rows:
        probs = row.probabilities or {}
        vec = [probs.get("home_win"), probs.get("draw"), probs.get("away_win")]
        if all(isinstance(v, (int, float)) for v in vec):
            out[row.match_id] = [float(vec[0]), float(vec[1]), float(vec[2])]
    return out


def live_baseline_probs(db: Session, match_id: int, cutoff,
                        mode: TemporalMode, candidate: str) -> Optional[List[float]]:
    from app.services.intelligence.composer import build_core_model

    name = {"baseline_ensemble": "ensemble", "baseline_elo": "elo",
            "baseline_poisson": "poisson"}[candidate]
    try:
        pred = build_core_model(name).predict(db, match_id, cutoff, mode)
    except Exception:
        return None
    if pred.status != "valid":
        return None
    return [pred.home_win_probability, pred.draw_probability,
            pred.away_win_probability]


def run_season_experiment(db: Session, league_code: str, candidate: str,
                          train_seasons: List[str], validate_season: str,
                          test_seasons: List[str],
                          mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                          seed: int = 7, hypothesis: str = "exploratory",
                          persist_artifacts: bool = True,
                          split_date: Optional[str] = None) -> Dict:
    """Train/validate/test split experiment for one candidate + league.

    split_date (ISO, optional): within-season chronological firewall — when
    validate and test share a season, validate rows must predate split_date
    and test rows must follow it. Without it, same-season validate/test
    would contaminate calibration.
    """
    """Train/validate/test split experiment for one candidate + league."""
    started = time.monotonic()
    spec = candidate_svc.describe(candidate)
    families = spec.get("families", [])
    dataset = dataset_svc.build_dataset(db, league_code, seasons=None,
                                        families=families or ["team"], mode=mode)
    season_of = lambda r: _season_label(datetime.fromisoformat(r["kickoff"]))
    if set([validate_season]) & set(test_seasons) and split_date is None:
        raise ValueError("validate and test share seasons without split_date: "
                         "calibration contamination risk refused")
    parts = splits_svc.season_splits(dataset["rows"], train_seasons,
                                     validate_season, test_seasons, season_of)
    if split_date is not None:
        cut = datetime.fromisoformat(split_date)
        before = [r for r in parts["validate"]
                  if datetime.fromisoformat(r["kickoff"]) < cut]
        after = [r for r in parts["test"]
                 if datetime.fromisoformat(r["kickoff"]) >= cut]
        if not before:
            raise ValueError("split_date leaves validation empty")
        if not after:
            raise ValueError("split_date leaves test empty")
        parts["validate"], parts["test"] = before, after
    live_computed = 0

    def probs_for(rows: List[Dict], window: str):
        nonlocal live_computed
        if candidate.startswith("baseline_"):
            version = BASELINE_VERSIONS[candidate]
            stored = stored_baseline_probs(
                db, [r["match_id"] for r in rows], version)
            out_probs, out_actual, out_ids = [], [], []
            for row in rows:
                vec = stored.get(row["match_id"])
                if vec is None:
                    vec = live_baseline_probs(db, row["match_id"],
                                              datetime.fromisoformat(row["kickoff"]),
                                              mode, candidate)
                    if vec is None:
                        continue
                    live_computed += 1
                out_probs.append(vec)
                out_actual.append(row["actual"])
                out_ids.append(row["match_id"])
            return {"probs": out_probs, "actual": out_actual,
                    "match_ids": out_ids, "live_computed": live_computed}
        selected = feature_svc.select_features(rows, families)
        if selected["kept"] < 30:
            raise ValueError(f"insufficient training rows: {selected['kept']}")
        X = np.asarray(selected["X"], dtype=float)
        y = np.asarray(selected["labels"], dtype=int)
        mean, scale = training_svc.standardize_fit(X)
        trained = training_svc.train_logreg(
            training_svc.standardize_apply(X, mean, scale), y)
        trained.update({"feature_names": selected["feature_names"],
                        "mean": mean.tolist(), "scale": scale.tolist()})
        return {"trained": trained, "selected": selected}

    if candidate.startswith("baseline_"):
        test = probs_for(parts["test"], "test")
        candidate_probs, actual = test["probs"], test["actual"]
        trained_info = {"kind": "production_baseline"}
        missing = {"eligible_rows": len(candidate_probs),
                   "missing_rows": len(parts["test"]) - len(candidate_probs)}
    else:
        train = probs_for(parts["train"], "train")
        trained = train["trained"]
        val_selected = feature_svc.select_features(parts["validate"], families)
        X_val = training_svc.standardize_apply(
            np.asarray(val_selected["X"], dtype=float),
            np.asarray(train["trained"]["mean"], dtype=float),
            np.asarray(train["trained"]["scale"], dtype=float))
        val_probs = training_svc.predict_logreg(train["trained"], X_val).tolist()
        test_selected = feature_svc.select_features(parts["test"], families)
        X_test = training_svc.standardize_apply(
            np.asarray(test_selected["X"], dtype=float),
            np.asarray(train["trained"]["mean"], dtype=float),
            np.asarray(train["trained"]["scale"], dtype=float))
        candidate_probs = training_svc.predict_logreg(train["trained"], X_test).tolist()
        actual = test_selected["labels"]
        trained_info = {"kind": "multinomial_logistic",
                        "features": train["trained"]["feature_names"],
                        "hyperparameters": train["trained"].get("hyperparameters"),
                        "train_kept": train["selected"]["kept"],
                        "train_dropped": train["selected"]["dropped"]}
        missing = {"eligible_rows": len(candidate_probs),
                   "missing_rows": test_selected["dropped"]}
        calibration = calibration_svc.evaluate_calibration(
            val_probs, val_selected["labels"], candidate_probs, actual)
    # Baseline on the IDENTICAL test population (intersection by match id;
    # live fill counted, actuals always from the candidate's own rows).
    actual_by_id = {r["match_id"]: r["actual"] for r in parts["test"]}
    if candidate.startswith("baseline_"):
        cand_ids = test["match_ids"]
        cand_by_id = dict(zip(cand_ids, zip(candidate_probs, actual)))
    else:
        cand_ids = test_selected["match_ids"]
        cand_by_id = dict(zip(cand_ids, zip(candidate_probs, actual)))
    base_by_id = dict(stored_baseline_probs(
        db, [r["match_id"] for r in parts["test"]],
        BASELINE_VERSIONS["baseline_ensemble"]))
    live_computed = 0
    for mid in cand_ids:
        if mid not in base_by_id:
            row = next((r for r in parts["test"] if r["match_id"] == mid), None)
            if row is None:
                continue
            vec = live_baseline_probs(db, mid,
                                      datetime.fromisoformat(row["kickoff"]),
                                      mode, "baseline_ensemble")
            if vec is None:
                continue
            base_by_id[mid] = vec
            live_computed += 1
    keep_ids = [mid for mid in cand_ids if mid in base_by_id]
    cand_probs = [cand_by_id[mid][0] for mid in keep_ids]
    cand_actual = [cand_by_id[mid][1] for mid in keep_ids]
    base_probs = [base_by_id[mid] for mid in keep_ids]
    base_actual = [actual_by_id[mid] for mid in keep_ids]
    metrics = evaluation_svc.score_1x2(cand_probs, cand_actual)
    baseline_metrics = evaluation_svc.score_1x2(base_probs, base_actual)
    deltas = significance_svc.paired_deltas(cand_probs, base_probs, cand_actual,
                                            seed=seed)
    report = {
        "candidate": candidate, "league": league_code, "mode": mode.value,
        "hypothesis": hypothesis, "seed": seed,
        "dataset_version": dataset["dataset_version"],
        "train_seasons": train_seasons, "validate_season": validate_season,
        "test_seasons": test_seasons, "split_date": split_date,
        "test_n": len(cand_actual),
        "families": families,
        "missingness": {fam: feature_svc.missingness_report(parts["test"], fam)
                        for fam in (families or ["team"])},
        "trained": trained_info,
        "metrics": metrics, "baseline_metrics": baseline_metrics,
        "deltas_vs_ensemble": deltas,
        "live_baseline_computed": live_computed,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    if not candidate.startswith("baseline_"):
        report["calibration"] = calibration
    key = artifact_svc.artifact_key(
        dataset["dataset_version"], candidate, seed,
        f"{league_code}-{'_'.join(train_seasons)}-{validate_season}-{'_'.join(test_seasons)}")
    if persist_artifacts:
        path = artifact_svc.save_artifact(key, "experiment", report)
        report["artifact"] = path
        row = promotion_svc.register(
            db, model_id=f"{candidate}@{league_code}",
            model_version=candidate if candidate.startswith("baseline_") else
            f"{candidate}_research_v1",
            status=promotion_svc.STATUS_RESEARCH,
            feature_version="research_features_v1",
            dataset_version=dataset["dataset_version"],
            training_period=",".join(train_seasons),
            validation_period=validate_season, test_period=",".join(test_seasons),
            parameters={"seed": seed, "mode": mode.value, "families": families},
            metrics=metrics, artifact_hash=artifact_svc.payload_hash(report))
        report["registry_id"] = row.id
    return report


def run_folds_experiment(db: Session, league_code: str, candidate: str,
                         n_folds: int = 3, min_train: int = 200,
                         mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                         seed: int = 7, hypothesis: str = "exploratory",
                         persist_artifacts: bool = True) -> Dict:
    """Expanding-window folds for single-season leagues. Per fold: train on
    all earlier rows (last 100 reserved as validation for temperature),
    test the next block. Predictions pooled chronologically for metrics."""
    import time as _time

    started = _time.monotonic()
    spec = candidate_svc.describe(candidate)
    families = spec.get("families", [])
    dataset = dataset_svc.build_dataset(db, league_code, seasons=None,
                                        families=families or ["team"], mode=mode)
    folds = splits_svc.expanding_folds(dataset["rows"], n_folds=n_folds,
                                       min_train=min_train)
    pooled_cand, pooled_base, pooled_actual = [], [], []
    fold_reports = []
    live_computed = 0
    for fold in folds:
        train_rows, test_rows = fold["train"], fold["test"]
        val_rows, fit_rows = train_rows[-100:], train_rows[:-100]
        if candidate.startswith("baseline_"):
            base = _probs_for_rows(db, test_rows, candidate, families, None,
                                   mode)
            live_computed += base["live_computed"]
            cand_probs, actual = base["probs"], base["actual"]
        else:
            selected = feature_svc.select_features(fit_rows, families)
            if selected["kept"] < 30:
                fold_reports.append({"fold": fold["fold"], "skipped":
                                     f"insufficient fold training rows ({selected['kept']})"})
                continue
            X = np.asarray(selected["X"], dtype=float)
            mean, scale = training_svc.standardize_fit(X)
            trained = training_svc.train_logreg(
                training_svc.standardize_apply(X, mean, scale),
                np.asarray(selected["labels"], dtype=int))
            val_selected = feature_svc.select_features(val_rows, families)
            val_probs = training_svc.predict_logreg(
                trained, training_svc.standardize_apply(
                    np.asarray(val_selected["X"], dtype=float), mean, scale)).tolist()
            temperature = training_svc.fit_temperature(
                val_probs, val_selected["labels"])
            test_selected = feature_svc.select_features(test_rows, families)
            raw = training_svc.predict_logreg(
                trained, training_svc.standardize_apply(
                    np.asarray(test_selected["X"], dtype=float), mean, scale)).tolist()
            cand_probs = training_svc.apply_temperature(raw, temperature)
            actual = test_selected["labels"]
            cand_ids = test_selected["match_ids"]
            stored = stored_baseline_probs(
                db, cand_ids, BASELINE_VERSIONS["baseline_ensemble"])
            keep = []
            for prob, act, mid in zip(cand_probs, actual, cand_ids):
                vec = stored.get(mid)
                if vec is None:
                    row = next((r for r in test_rows if r["match_id"] == mid), None)
                    if row is None:
                        continue
                    vec = live_baseline_probs(
                        db, mid, datetime.fromisoformat(row["kickoff"]),
                        mode, "baseline_ensemble")
                    if vec is None:
                        continue
                    live_computed += 1
                keep.append((prob, vec, act))
            if not keep:
                continue
            cand_probs = [k[0] for k in keep]
            base_fold = [k[1] for k in keep]
            actual = [k[2] for k in keep]
            pooled_cand.extend(cand_probs)
            pooled_base.extend(base_fold)
            pooled_actual.extend(actual)
            fold_reports.append({"fold": fold["fold"], "n": len(keep)})
            continue
        # Baseline candidate: identical populations by construction.
        base_ids = base["match_ids"]
        actual_by_id = {r["match_id"]: r["actual"] for r in test_rows}
        pooled_cand.extend(base["probs"])
        pooled_base.extend(base["probs"])
        pooled_actual.extend([actual_by_id[mid] for mid in base_ids])
        fold_reports.append({"fold": fold["fold"], "n": len(base_ids)})
    metrics = evaluation_svc.score_1x2(pooled_cand, pooled_actual)
    if not pooled_actual:
        raise ValueError("no successful folds: insufficient data")
    baseline_metrics = evaluation_svc.score_1x2(pooled_base, pooled_actual)
    deltas = significance_svc.paired_deltas(pooled_cand, pooled_base,
                                            pooled_actual, seed=seed)
    report = {
        "candidate": candidate, "league": league_code, "mode": mode.value,
        "hypothesis": hypothesis, "seed": seed,
        "dataset_version": dataset["dataset_version"],
        "protocol": f"expanding_folds_{n_folds}", "test_n": len(pooled_actual),
        "families": families,
        "metrics": metrics, "baseline_metrics": baseline_metrics,
        "deltas_vs_ensemble": deltas, "folds": fold_reports,
        "live_baseline_computed": live_computed,
        "duration_seconds": round(_time.monotonic() - started, 2),
    }
    key = artifact_svc.artifact_key(dataset["dataset_version"], candidate,
                                    seed, f"{league_code}-folds")
    if persist_artifacts:
        path = artifact_svc.save_artifact(key, "experiment", report)
        report["artifact"] = path
        row = promotion_svc.register(
            db, model_id=f"{candidate}@{league_code}",
            model_version=candidate if candidate.startswith("baseline_") else
            f"{candidate}_research_v1",
            status=promotion_svc.STATUS_RESEARCH,
            feature_version="research_features_v1",
            dataset_version=dataset["dataset_version"],
            training_period="expanding", validation_period="fold-tail-100",
            test_period=f"folds-{n_folds}",
            parameters={"seed": seed, "mode": mode.value, "families": families},
            metrics=metrics, artifact_hash=artifact_svc.payload_hash(report))
        report["registry_id"] = row.id
    return report


def _probs_for_rows(db: Session, rows: List[Dict], candidate: str,
                    families: List[str], trained, mode: TemporalMode) -> Dict:
    """Baseline probabilities for explicit rows (stored first, live fill)."""
    version = BASELINE_VERSIONS[candidate]
    stored = stored_baseline_probs(db, [r["match_id"] for r in rows], version)
    probs, actual, ids, live = [], [], [], 0
    for row in rows:
        vec = stored.get(row["match_id"])
        if vec is None:
            vec = live_baseline_probs(db, row["match_id"],
                                      datetime.fromisoformat(row["kickoff"]),
                                      mode, candidate)
            if vec is None:
                continue
            live += 1
        probs.append(vec)
        actual.append(row["actual"])
        ids.append(row["match_id"])
    return {"probs": probs, "actual": actual, "match_ids": ids,
            "live_computed": live}
