"""Phase 28 monitoring contracts: versions, safe arithmetic, intervals.

All monitoring is observational. Nothing here writes to immutable records,
changes models, or activates providers.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional

import numpy as np

MONITORING_CONTRACT_VERSION = "PRODUCTION_MONITORING_V1"
METRIC_DEFINITION_VERSION = "monitoring_metrics_v1"
BUCKET_DEFINITION_VERSION = "reliability_buckets_v1"
CALIBRATION_BINS = 10

# Drift states (documented, observational — never a model verdict).
STATE_STABLE = "STABLE"
STATE_WATCH = "WATCH"
STATE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Data-quality states.
DATA_VALID = "DATA_VALID"
DATA_DEGRADED = "DATA_DEGRADED"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
DATA_BLOCKED = "DATA_BLOCKED"

# Sample-size rules (documented thresholds for reporting, not verdicts).
MIN_WINDOW_SAMPLE = 20
MIN_DRIFT_SAMPLE = 20
# Observational watch bands for drift deltas (absolute units).
WATCH_BRIER_DELTA = 0.05
WATCH_ACCURACY_DELTA = 0.10
WATCH_LOGLOSS_DELTA = 0.20


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Rate with explicit unknown: None when denominator is zero.

    Missing data must not be interpreted as zero; callers expose the
    denominator alongside every rate.
    """
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def wilson_interval(successes: int, trials: int,
                    confidence: float = 0.95) -> Optional[Dict[str, Any]]:
    """Wilson score interval for a binomial proportion.

    Used instead of naive normal approximations, especially for small
    samples and boundary proportions. Deterministic. Returns None for
    zero trials (unknown, not zero).
    """
    if trials <= 0:
        return None
    z = 1.96  # 95% two-sided normal quantile (fixed, documented)
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / trials
                          + z * z / (4.0 * trials * trials))) / denom
    return {
        "method": "wilson",
        "confidence": confidence,
        "proportion": round(p, 4),
        "lo": round(max(0.0, center - half), 4),
        "hi": round(min(1.0, center + half), 4),
        "trials": trials,
    }


def bootstrap_mean_ci(values: List[float], n_boot: int = 500,
                      seed: int = 7, ci: float = 95.0) -> Optional[Dict[str, Any]]:
    """Seeded percentile bootstrap CI for a scalar mean. Deterministic."""
    vals = [v for v in values if isinstance(v, (int, float))
            and not isinstance(v, bool) and math.isfinite(v)]
    n = len(vals)
    if n == 0:
        return None
    arr = np.asarray(vals, dtype=float)
    rng = np.random.RandomState(seed)
    estimates = []
    for _ in range(max(1, n_boot)):
        idx = rng.randint(0, n, size=n)
        estimates.append(float(arr[idx].mean()))
    lower_pct = (100.0 - ci) / 2.0
    return {
        "method": "bootstrap_mean",
        "lo": round(float(np.percentile(estimates, lower_pct)), 4),
        "hi": round(float(np.percentile(estimates, 100.0 - lower_pct)), 4),
        "n_boot": len(estimates),
        "n": n,
    }


def max_calibration_error(reliability: Dict[str, Any]) -> Optional[float]:
    """MCE: maximum |predicted - empirical| over non-empty bins."""
    best = None
    for b in reliability.get("bins", []):
        if b.get("count") and b.get("mean_predicted") is not None \
                and b.get("empirical_rate") is not None:
            err = abs(b["mean_predicted"] - b["empirical_rate"])
            best = err if best is None else max(best, err)
    return round(best, 4) if best is not None else None
