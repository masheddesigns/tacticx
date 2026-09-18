"""Statistical significance + multiple-comparison discipline (Phase 12).

Every candidate improvement reports paired ΔBrier/ΔLogLoss/ΔAccuracy with
95% bootstrap CIs on identical populations. CI including zero =
inconclusive unless another documented reason exists. Experiments declare
primary vs exploratory status up front; the registry counts tested
candidates so a winner is never selected from an unreported crowd.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.services.backtesting.metrics import bootstrap_ci


def paired_deltas(candidate_probs, baseline_probs, actual,
                  n_boot: int = 2000, seed: int = 7) -> Dict:
    """Δ = baseline_metric - candidate_metric per match (positive favors the
    candidate), with bootstrap CIs. Point estimates alone never declare."""
    import numpy as np

    from app.services.backtesting import metrics as met

    cand = np.asarray(candidate_probs, dtype=float)
    base = np.asarray(baseline_probs, dtype=float)
    act = np.asarray(actual, dtype=int)
    brier_d = np.array([met.multiclass_brier([b.tolist()], [int(a)])
                        - met.multiclass_brier([c.tolist()], [int(a)])
                        for c, b, a in zip(cand, base, act)])
    ll_d = np.array([met.multiclass_log_loss([b.tolist()], [int(a)])
                     - met.multiclass_log_loss([c.tolist()], [int(a)])
                     for c, b, a in zip(cand, base, act)])
    cand_pred = met.argmax_labels(candidate_probs)
    base_pred = met.argmax_labels(baseline_probs)
    acc_d = np.array([(1 if cp == a else 0) - (1 if bp == a else 0)
                      for cp, bp, a in zip(cand_pred, base_pred, act)],
                     dtype=float)
    out = {}
    for name, diffs in (("brier", brier_d), ("log_loss", ll_d),
                        ("accuracy", acc_d)):
        ci = bootstrap_ci(lambda p, a: float(np.mean(p)), diffs.tolist(),
                          [0] * len(diffs), n_boot=n_boot, seed=seed)
        lo, hi = (ci["lo"], ci["hi"]) if ci else (None, None)
        out[f"delta_{name}"] = {
            "mean": round(float(np.mean(diffs)), 6),
            "ci95": [lo, hi],
            "n": len(diffs),
            "verdict": "inconclusive (CI includes zero)"
            if lo is None or (lo <= 0 <= hi) else
            ("improvement" if float(np.mean(diffs)) > 0 else "degradation"),
        }
    return out
