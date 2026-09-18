"""Ablation: add-one-family + leave-one-family-out (Phase 12).

Only families with actual coverage run. Both performance and coverage are
reported: a family improving a tiny population must not read as generally
superior. The runner delegates fitting/scoring to the experiment runner to
avoid duplicated training logic.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

ADDITIVE_LADDER = ["team", "xg", "player", "shots"]


def additive_plan(base: str = "team") -> List[List[str]]:
    """baseline(team) + team/xg + player + events/shots ladders."""
    plans = [[base]]
    if base == "team":
        plans.append(["team", "xg"])
        plans.append(["team", "player"])
        plans.append(["team", "xg", "shots"])
        plans.append(["team", "xg", "shots", "player"])
    return plans


def leave_one_out_plan(families: List[str]) -> List[List[str]]:
    full = list(families)
    plans = [full]
    for family in families:
        reduced = [f for f in full if f != family]
        if reduced:
            plans.append(reduced)
    return plans


def run_ablation(evaluate_fn: Callable[[List[str]], Dict],
                 families: List[str],
                 coverage_fn: Optional[Callable[[List[str]], Dict]] = None) -> Dict:
    """evaluate_fn(families) -> metrics dict. Reports performance + coverage
    per plan; skips plans whose coverage gate fails (reported, not hidden)."""
    results = {"additive": [], "leave_one_out": [], "skipped": []}
    for plan in additive_plan() + leave_one_out_plan(families):
        key = "+".join(plan)
        coverage = coverage_fn(plan) if coverage_fn else {"eligible": True}
        if isinstance(coverage, dict) and coverage.get("eligible") is False:
            results["skipped"].append({"plan": key, "reason": coverage.get(
                "reason", "coverage gate")})
            continue
        try:
            metrics = evaluate_fn(plan)
        except ValueError as exc:
            results["skipped"].append({"plan": key, "reason": str(exc)[:200]})
            continue
        entry = {"plan": key, "metrics": metrics, "coverage": coverage}
        if plan in additive_plan():
            results["additive"].append(entry)
        else:
            results["leave_one_out"].append(entry)
    return results
