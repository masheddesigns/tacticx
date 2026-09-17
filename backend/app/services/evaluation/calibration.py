"""Per-class calibration analysis with configurable bins."""
from __future__ import annotations

from typing import Dict, List, Optional

from app.services.backtesting import metrics as met

CLASSES = ("home", "draw", "away")
DEFAULT_BINS = 10
MIN_BIN_N = 20


def per_class_calibration(details: List[Dict], n_bins: int = DEFAULT_BINS,
                          min_bin_n: int = MIN_BIN_N) -> Dict:
    """ECE + reliability curve per outcome class.

    Bins with fewer than min_bin_n observations are reported but flagged
    sparse: no conclusions are drawn from them.
    """
    out = {}
    for idx, name in enumerate(CLASSES):
        probs = [r["probs"][idx] for r in details]
        outcomes = [1 if r["actual"] == idx else 0 for r in details]
        curve = met.reliability_curve(probs, outcomes, n_bins=n_bins)
        for b in curve["bins"]:
            b["sparse"] = (b["count"] or 0) < min_bin_n
        out[name] = {
            "ece": met.expected_calibration_error(probs, outcomes, n_bins=n_bins),
            "n": len(details),
            "curve": curve,
        }
    return out


def calibration_summary(details: List[Dict], n_bins: int = DEFAULT_BINS) -> Dict:
    """Aggregate ECE (home-win, as in Phase 2) plus per-class table."""
    per_class = per_class_calibration(details, n_bins=n_bins)
    home_probs = [r["probs"][0] for r in details]
    home_out = [1 if r["actual"] == 0 else 0 for r in details]
    return {
        "n": len(details),
        "n_bins": n_bins,
        "ece_home_win": met.expected_calibration_error(home_probs, home_out,
                                                       n_bins=n_bins),
        "per_class": {name: {"ece": v["ece"], "n": v["n"]} for name, v in per_class.items()},
        "curves": {name: v["curve"] for name, v in per_class.items()},
    }
