"""Phase 26 model-output validation. Failed validation = no persistence."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from .contracts import PROB_SUM_TOLERANCE


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def validate_prediction_output(payload: Dict[str, Any]) -> List[str]:
    """Return a list of violations; empty means the payload is persistable."""
    violations: List[str] = []

    if payload.get("status") != "valid":
        violations.append(
            f"prediction status is not valid: {payload.get('status')!r}")
        return violations

    probs = [payload.get("home_win_probability"),
             payload.get("draw_probability"),
             payload.get("away_win_probability")]
    names = ("home_win_probability", "draw_probability", "away_win_probability")
    for name, value in zip(names, probs):
        if not _finite(value):
            violations.append(f"{name} is not finite: {value!r}")
        elif not 0.0 <= value <= 1.0:
            violations.append(f"{name} out of range [0,1]: {value!r}")
    if all(_finite(v) for v in probs):
        total = sum(probs)
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            violations.append(f"1X2 probabilities sum to {total!r}, not 1.0")

    for name in ("expected_home_goals", "expected_away_goals",
                 "expected_total_goals"):
        value = payload.get(name)
        if value is None:
            continue
        if not _finite(value):
            violations.append(f"{name} is not finite: {value!r}")
        elif value < 0.0:
            violations.append(f"{name} is negative: {value!r}")

    market_pairs = (
        ("over_1_5_probability", "under_1_5_probability"),
        ("over_2_5_probability", "under_2_5_probability"),
        ("over_3_5_probability", "under_3_5_probability"),
        ("btts_yes_probability", "btts_no_probability"),
    )
    for over_name, under_name in market_pairs:
        over_v, under_v = payload.get(over_name), payload.get(under_name)
        for name, value in ((over_name, over_v), (under_name, under_v)):
            if value is None:
                continue
            if not _finite(value):
                violations.append(f"{name} is not finite: {value!r}")
            elif not 0.0 <= value <= 1.0:
                violations.append(f"{name} out of range [0,1]: {value!r}")
        if _finite(over_v) and _finite(under_v) \
                and abs((over_v + under_v) - 1.0) > 1e-3:
            violations.append(
                f"{over_name}/{under_name} are inconsistent: "
                f"{over_v!r} + {under_v!r} != 1.0")

    scores = payload.get("score_probabilities") or {}
    if not isinstance(scores, dict):
        violations.append("score_probabilities is not a mapping")
    else:
        for key, value in scores.items():
            if not _finite(value):
                violations.append(
                    f"score_probabilities[{key!r}] is not finite: {value!r}")
            elif not 0.0 <= value <= 1.0:
                violations.append(
                    f"score_probabilities[{key!r}] out of range: {value!r}")

    return violations
