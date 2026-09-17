"""Model comparison on identical populations with paired uncertainty."""
from __future__ import annotations

from typing import Dict, List, Optional

from app.services.backtesting import metrics as met

INDEX = {"home": 0, "draw": 1, "away": 2}


def intersect_populations(results: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Restrict every model's detail rows to match_ids present in ALL models.

    Different models legitimately cover different matches (insufficient_data
    exclusions). Comparing aggregates across different populations would be
    misleading, so intersections are explicit and reported.
    """
    if not results:
        return {}
    common = set.intersection(*(set(r["match_id"] for r in rows) for rows in results.values()))
    out = {}
    for name, rows in results.items():
        out[name] = [r for r in rows if r["match_id"] in common]
    out["_common_n"] = len(common)
    return out


def paired_metric_difference(metric_fn, probs_a, actual_a, probs_b, actual_b,
                             n_boot: int = 2000, seed: int = 7,
                             ci: float = 95.0) -> Dict:
    """Per-match metric(A) - metric(B) with mean, median and bootstrap CI.

    Both sides must already share one population (use intersect_populations).
    Positive mean => B is better (lower metric). CI quantifies uncertainty;
    it is never a model-selection mechanism.
    """
    import numpy as np

    a = np.asarray(actual_a, dtype=int)
    diffs = []
    for pa, pb, y in zip(np.asarray(probs_a, dtype=float),
                         np.asarray(probs_b, dtype=float), a):
        try:
            diffs.append(float(metric_fn([pa.tolist()], [int(y)])
                              - metric_fn([pb.tolist()], [int(y)])))
        except Exception:
            continue
    diffs = np.asarray(diffs, dtype=float)
    if diffs.size == 0:
        return {"n": 0, "mean": None, "median": None, "ci": None}
    rng = np.random.RandomState(seed)
    boots = [float(np.mean(rng.choice(diffs, size=diffs.size, replace=True)))
             for _ in range(max(1, n_boot))]
    lower_pct = (100.0 - ci) / 2.0
    return {"n": int(diffs.size),
            "mean": round(float(np.mean(diffs)), 6),
            "median": round(float(np.median(diffs)), 6),
            "ci": {"lo": round(float(np.percentile(boots, lower_pct)), 6),
                   "hi": round(float(np.percentile(boots, 100.0 - lower_pct)), 6),
                   "n_boot": len(boots), "seed": seed}}


def _brier_single(probs, actual):
    return met.multiclass_brier(probs, actual)


def _logloss_single(probs, actual):
    return met.multiclass_log_loss(probs, actual)


def compare_pair(details_a: List[Dict], details_b: List[Dict],
                 name_a: str = "A", name_b: str = "B",
                 n_boot: int = 2000, seed: int = 7) -> Dict:
    """Paired Brier + log-loss comparison on two detail row lists.

    Row format: {"match_id": int, "probs": [h, d, a], "actual": 0|1|2}.
    Populations are intersected first; the report states both N values.
    """
    map_a = {r["match_id"]: r for r in details_a}
    map_b = {r["match_id"]: r for r in details_b}
    common = sorted(set(map_a) & set(map_b))
    if not common:
        return {"model_a": name_a, "model_b": name_b, "n_a": len(details_a),
                "n_b": len(details_b), "n_common": 0,
                "note": "no shared matches; cannot compare"}
    pa = [map_a[m]["probs"] for m in common]
    pb = [map_b[m]["probs"] for m in common]
    ya = [map_a[m]["actual"] for m in common]
    yb = [map_b[m]["actual"] for m in common]
    return {
        "model_a": name_a, "model_b": name_b,
        "n_a": len(details_a), "n_b": len(details_b), "n_common": len(common),
        "brier": paired_metric_difference(_brier_single, pa, ya, pb, yb,
                                          n_boot=n_boot, seed=seed),
        "log_loss": paired_metric_difference(_logloss_single, pa, ya, pb, yb,
                                             n_boot=n_boot, seed=seed + 1),
    }
