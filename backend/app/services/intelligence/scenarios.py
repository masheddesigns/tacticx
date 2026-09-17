"""Deterministic scenario engine (Phase 6).

Named scenarios apply small, labeled, validated transformations to the
baseline goal-model inputs (lambda multipliers, Elo shifts) and recompute
1X2, expected goals, totals, BTTS and score distributions from the modified
distribution. Every scenario returns baseline + scenario + difference, so it
reads as a sensitivity analysis — never as a prediction of what will happen.

No arbitrary probabilities are invented; parameters come from a validated
whitelist with documented ranges. Scenario configuration is data, never code.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.services.intelligence import derived
from app.services.intelligence.schemas import ScenarioOutput
from app.services.predictions.math_utils import MAX_GRID_GOALS

CALCULATION_VERSION = "scenarios_v1"

# name -> {kind, params, description}. Multipliers stay close to 1 by design.
SCENARIOS: Dict[str, Dict] = {
    "baseline": {
        "kind": "none", "params": {},
        "description": "Unmodified baseline inputs.",
    },
    "home_strength_up": {
        "kind": "lambda", "params": {"home_mult": 1.10, "away_mult": 1.00},
        "description": "Home scoring rate +10% (e.g. key attacker available).",
    },
    "home_strength_down": {
        "kind": "lambda", "params": {"home_mult": 0.90, "away_mult": 1.00},
        "description": "Home scoring rate -10% (e.g. key attacker missing).",
    },
    "away_strength_up": {
        "kind": "lambda", "params": {"home_mult": 1.00, "away_mult": 1.10},
        "description": "Away scoring rate +10%.",
    },
    "away_strength_down": {
        "kind": "lambda", "params": {"home_mult": 1.00, "away_mult": 0.90},
        "description": "Away scoring rate -10%.",
    },
    "high_scoring": {
        "kind": "lambda", "params": {"home_mult": 1.10, "away_mult": 1.10},
        "description": "Both scoring rates +10% (e.g. open tactical matchup).",
    },
    "low_scoring": {
        "kind": "lambda", "params": {"home_mult": 0.90, "away_mult": 0.90},
        "description": "Both scoring rates -10% (e.g. cagey tactical matchup).",
    },
}

MULT_MIN, MULT_MAX = 0.50, 2.00


def validate_scenario_params(kind: str, params: Dict) -> Dict:
    """Whitelist validation for scenario configuration (no code execution)."""
    errors = []
    if kind == "lambda":
        for key in ("home_mult", "away_mult"):
            value = params.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"{key} must be a finite number")
            elif not (MULT_MIN <= value <= MULT_MAX):
                errors.append(f"{key}={value} outside [{MULT_MIN}, {MULT_MAX}]")
    elif kind == "none":
        if params:
            errors.append("baseline scenario takes no parameters")
    else:
        errors.append(f"unknown scenario kind: {kind!r}")
    return {"valid": not errors, "errors": errors}


def list_scenarios() -> Dict[str, Dict]:
    return {name: {"kind": spec["kind"], "params": dict(spec["params"]),
                   "description": spec["description"]}
            for name, spec in SCENARIOS.items()}


def run_scenario(baseline_1x2: Dict[str, float], lambda_home: float,
                 lambda_away: float, name: str,
                 custom_params: Optional[Dict] = None,
                 top_n_scores: int = 8) -> ScenarioOutput:
    """Apply one named scenario. Baseline inputs are never mutated."""
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {name} (known: {sorted(SCENARIOS)})")
    spec = SCENARIOS[name]
    params = dict(spec["params"])
    if custom_params:
        params.update(custom_params)
    check = validate_scenario_params(spec["kind"], params)
    if not check["valid"]:
        raise ValueError(f"invalid scenario params: {check['errors']}")
    if lambda_home is None or lambda_away is None:
        raise ValueError("scenario requires baseline goal lambdas")
    home_mult = params.get("home_mult", 1.0)
    away_mult = params.get("away_mult", 1.0)
    scen_home = lambda_home * home_mult
    scen_away = lambda_away * away_mult

    base_joint = derived.goal_distributions(lambda_home, lambda_away)["joint"]
    scen_dist = derived.goal_distributions(scen_home, scen_away)
    scen_joint = scen_dist["joint"]

    from app.services.predictions.math_utils import markets_from_grid

    base_m = markets_from_grid(base_joint)
    scen_m = markets_from_grid(scen_joint)
    scen_totals = derived.totals_from_joint(scen_joint)["probabilities"]
    scen_btts = derived.btts_from_joint(scen_joint)
    base_totals = derived.totals_from_joint(base_joint)["probabilities"]
    base_btts = derived.btts_from_joint(base_joint)

    scen_1x2 = {"home": scen_m["home_win_probability"],
                "draw": scen_m["draw_probability"],
                "away": scen_m["away_win_probability"]}
    scen_goals = {"home_lambda": round(scen_home, 4),
                  "away_lambda": round(scen_away, 4),
                  "total_lambda": round(scen_home + scen_away, 4)}
    scen_markets = {
        "over_1_5": scen_totals["over_1_5"], "over_2_5": scen_totals["over_2_5"],
        "over_3_5": scen_totals["over_3_5"], "btts": scen_btts["yes"],
    }
    base_markets = {
        "over_1_5": base_totals["over_1_5"], "over_2_5": base_totals["over_2_5"],
        "over_3_5": base_totals["over_3_5"], "btts": base_btts["yes"],
    }
    base_1x2 = {"home": base_m["home_win_probability"],
                "draw": base_m["draw_probability"],
                "away": base_m["away_win_probability"]}
    base_goals = {"home_lambda": round(lambda_home, 4),
                  "away_lambda": round(lambda_away, 4),
                  "total_lambda": round(lambda_home + lambda_away, 4)}
    diff = {
        "probabilities": {k: round(scen_1x2[k] - baseline_1x2.get(k, base_1x2[k]), 6)
                          for k in scen_1x2},
        "goals": {k: round(scen_goals[k] - base_goals[k], 6) for k in scen_goals},
        "markets": {k: round(scen_markets[k] - base_markets[k], 6) for k in scen_markets},
    }
    top = derived.correct_scores(scen_joint, top_n=top_n_scores)["top"]
    return ScenarioOutput(
        name=name,
        parameters={"kind": spec["kind"], "home_mult": home_mult,
                    "away_mult": away_mult, "description": spec["description"],
                    "calculation_version": CALCULATION_VERSION},
        probabilities={k: round(v, 6) for k, v in scen_1x2.items()},
        goals=scen_goals, markets=scen_markets, score_top=top,
        difference_from_baseline=diff,
    )


def run_all(baseline_1x2: Dict[str, float], lambda_home: float,
            lambda_away: float, names: Optional[List[str]] = None,
            top_n_scores: int = 8) -> List[ScenarioOutput]:
    """Baseline-preserving batch: baseline output always included first."""
    names = names or ["baseline"] + sorted(n for n in SCENARIOS if n != "baseline")
    outputs = []
    for name in names:
        outputs.append(run_scenario(baseline_1x2, lambda_home, lambda_away, name,
                                    top_n_scores=top_n_scores))
    return outputs
