"""Derived-market math (Phase 6).

Pure functions over probability distributions. Everything derives from the
core goal distribution or 1X2 vector — nothing is trained or fitted here.
Invalid inputs are rejected with reasons, never silently renormalized
(except where a model's documented procedure already renormalizes, e.g.
the Poisson score grid, whose tail mass is then exposed, not hidden).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from app.services.predictions.math_utils import MAX_GRID_GOALS, poisson_pmf

TOL = 1e-6
REQUIRED_SCORES = ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2",
                   "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"]
TOTAL_LINES = (0.5, 1.5, 2.5, 3.5)
TEAM_LINES = (0.5, 1.5, 2.5)


def _in_unit(value: float) -> bool:
    return isinstance(value, (int, float)) and 0.0 <= value <= 1.0 and math.isfinite(value)


def validate_1x2(home: float, draw: float, away: float,
                 tol: float = TOL) -> Dict:
    """Reject invalid 1X2 vectors rather than silently normalizing."""
    errors = []
    for name, value in (("home", home), ("draw", draw), ("away", away)):
        if not _in_unit(value):
            errors.append(f"{name}={value!r} outside [0, 1]")
    total = (home or 0.0) + (draw or 0.0) + (away or 0.0)
    if abs(total - 1.0) > tol:
        errors.append(f"1X2 sums to {total:.9f}, not 1 (tol {tol})")
    return {"valid": not errors, "errors": errors, "sum": round(total, 9)}


def validate_distribution(name: str, probs: Dict[str, float],
                          tol: float = 1e-4) -> Dict:
    total = sum(probs.values())
    bad = [k for k, v in probs.items() if not _in_unit(v)]
    errors = []
    if bad:
        errors.append(f"{len(bad)} entries outside [0, 1]")
    if abs(total - 1.0) > tol:
        errors.append(f"{name} sums to {total:.6f}, not 1 (tol {tol})")
    return {"valid": not errors, "errors": errors, "sum": round(total, 6),
            "n": len(probs)}


def poisson_tail_mass(lam: float, max_goals: int = MAX_GRID_GOALS) -> float:
    """P(X > max_goals) for one Poisson marginal (Phase 5 method)."""
    total = 0.0
    term = math.exp(-lam) if lam > 0 else 1.0
    for i in range(max_goals + 1):
        if i:
            term *= lam / i
        total += term
    return max(0.0, 1.0 - total)


def goal_distributions(lambda_home: float, lambda_away: float,
                       max_goals: int = MAX_GRID_GOALS) -> Dict:
    """Marginal + joint goal distributions with exposed grid/tail mass."""
    if lambda_home is None or lambda_away is None:
        return {"status": "unavailable", "reason": "lambdas missing"}
    if lambda_home <= 0 or lambda_away <= 0:
        return {"status": "unavailable", "reason": "lambdas not positive"}
    home = {k: poisson_pmf(k, lambda_home) for k in range(max_goals + 1)}
    away = {k: poisson_pmf(k, lambda_away) for k in range(max_goals + 1)}
    home_sum, away_sum = sum(home.values()), sum(away.values())
    home = {k: v / home_sum for k, v in home.items()}
    away = {k: v / away_sum for k, v in away.items()}
    joint = {f"{h}-{a}": round(home[h] * away[a], 9)
             for h in home for a in away}
    tail_home = poisson_tail_mass(lambda_home, max_goals)
    tail_away = poisson_tail_mass(lambda_away, max_goals)
    return {
        "status": "ok",
        "lambda_home": lambda_home, "lambda_away": lambda_away,
        "total_lambda": round(lambda_home + lambda_away, 4),
        "max_goals": max_goals,
        "home_marginal": {str(k): round(v, 9) for k, v in home.items()},
        "away_marginal": {str(k): round(v, 9) for k, v in away.items()},
        "joint": joint,
        "grid_mass": round(home_sum * away_sum, 9),
        "tail_mass": round(1.0 - home_sum * away_sum, 9),
        "tail_mass_home": round(tail_home, 9),
        "tail_mass_away": round(tail_away, 9),
    }


def totals_from_joint(joint: Dict[str, float],
                      lines: Tuple[float, ...] = TOTAL_LINES,
                      tol: float = 1e-9) -> Dict:
    """Over/Under from the joint distribution. Over+Under ≈ 1 by construction."""
    totals: Dict[str, float] = {}
    checks = []
    for line in lines:
        over = sum(p for key, p in joint.items()
                   if int(key.split("-")[0]) + int(key.split("-")[1]) > line)
        under = 1.0 - over
        over, under = round(over, 9), round(under, 9)
        totals[f"over_{str(line).replace('.', '_')}"] = over
        totals[f"under_{str(line).replace('.', '_')}"] = under
        if abs(over + under - 1.0) > tol:
            checks.append(f"line {line}: over+under={over + under}")
    return {"probabilities": totals, "consistent": not checks, "checks": checks}


def btts_from_joint(joint: Dict[str, float]) -> Dict:
    """BTTS Yes/No from the joint distribution (independent-Poisson identity
    cross-checked against the closed form)."""
    yes = sum(p for key, p in joint.items()
              if int(key.split("-")[0]) > 0 and int(key.split("-")[1]) > 0)
    yes = round(yes, 9)
    return {"yes": yes, "no": round(1.0 - yes, 9)}


def btts_closed_form(p_home_zero: float, p_away_zero: float) -> Dict:
    """1 - P(H=0) - P(A=0) + P(H=0,A=0) under independence."""
    yes = 1.0 - p_home_zero - p_away_zero + p_home_zero * p_away_zero
    return {"yes": round(yes, 9), "no": round(1.0 - yes, 9)}


def double_chance(home: float, draw: float, away: float) -> Dict:
    """1X/X2/12 derived from 1X2 with identity validation."""
    out = {"1x": round(home + draw, 9), "x2": round(draw + away, 9),
           "12": round(home + away, 9)}
    checks = []
    if abs(out["1x"] - (home + draw)) > 1e-9:
        checks.append("1x identity failed")
    if abs(out["x2"] - (draw + away)) > 1e-9:
        checks.append("x2 identity failed")
    if abs(out["12"] - (home + away)) > 1e-9:
        checks.append("12 identity failed")
    return {"probabilities": out, "consistent": not checks, "checks": checks}


def team_totals(lambda_home: float, lambda_away: float,
                lines: Tuple[float, ...] = TEAM_LINES) -> Dict:
    """Home/Away team-goals overs from Poisson marginals (model-derived,
    not betting recommendations)."""
    if lambda_home is None or lambda_away is None:
        return {"status": "unavailable", "reason": "lambdas missing"}
    out = {"status": "ok", "home": {}, "away": {}}
    for line in lines:
        key = f"over_{str(line).replace('.', '_')}"
        out["home"][key] = round(1.0 - sum(poisson_pmf(k, lambda_home)
                                           for k in range(int(line) + 1)), 9)
        out["away"][key] = round(1.0 - sum(poisson_pmf(k, lambda_away)
                                           for k in range(int(line) + 1)), 9)
    return out


def correct_scores(joint: Dict[str, float], top_n: int = 16,
                   required: Optional[List[str]] = None) -> Dict:
    """Full score list, required-16 coverage, configurable top_n."""
    required = required or REQUIRED_SCORES
    ranked = sorted(joint.items(), key=lambda kv: kv[1], reverse=True)
    top_n = max(1, min(int(top_n), len(ranked)))
    covered = {s: round(joint.get(s, 0.0), 9) for s in required}
    return {
        "top": [{"score": s, "probability": round(p, 9)} for s, p in ranked[:top_n]],
        "required_16": covered,
        "required_16_mass": round(sum(covered.values()), 9),
        "tail_mass": round(max(0.0, 1.0 - sum(covered.values())), 9),
        "note": "Highest-probability score is the mode of the distribution, "
                "never a certain outcome.",
    }


def mc_crosscheck(analytic: Dict[str, float], mc: Dict[str, float],
                  tol: float = 0.02) -> Dict:
    """Compare analytic market probabilities against Monte Carlo estimates."""
    compared = {}
    worst = 0.0
    for key, value in analytic.items():
        other = mc.get(key)
        if other is None:
            continue
        diff = abs(value - other)
        worst = max(worst, diff)
        compared[key] = {"analytic": value, "montecarlo": round(other, 9),
                         "abs_diff": round(diff, 9),
                         "within_tolerance": diff <= tol}
    all_ok = all(c["within_tolerance"] for c in compared.values()) if compared else False
    return {"compared": compared, "max_abs_diff": round(worst, 9),
            "tolerance": tol, "consistent": all_ok}
