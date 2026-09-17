"""Parameter sensitivity + Monte Carlo convergence + Poisson truncation."""
from __future__ import annotations

import math
from typing import Dict, List

from app.services.backtesting import metrics as met


def sensitivity_runs() -> Dict[str, List[Dict]]:
    """Small predefined perturbation grids. Sensitivity analysis is not
    hyperparameter tuning: nothing here selects production parameters."""
    return {
        "elo": [
            {"label": "baseline", "k_factor": 20, "home_advantage": 60},
            {"label": "k_low", "k_factor": 18, "home_advantage": 60},
            {"label": "k_high", "k_factor": 22, "home_advantage": 60},
            {"label": "hfa_low", "k_factor": 20, "home_advantage": 50},
            {"label": "hfa_high", "k_factor": 20, "home_advantage": 70},
        ],
        "poisson_half_life_days": [60, 120, 240, 365],
        "montecarlo_simulations": [1000, 5000, 10000, 25000],
    }


def summarize_sensitivity(baseline_metrics: Dict, runs: List[Dict]) -> Dict:
    """Metric deltas of perturbed runs vs the baseline run."""
    out = []
    for run in runs:
        delta = {}
        for key in ("accuracy_1x2", "log_loss_1x2", "brier_1x2", "ece_home_win"):
            base_val, run_val = baseline_metrics.get(key), run["metrics"].get(key)
            if isinstance(base_val, (int, float)) and isinstance(run_val, (int, float)):
                delta[key] = round(run_val - base_val, 6)
            else:
                delta[key] = None
        out.append({"label": run["label"], "n": run["sample_size"], "delta": delta,
                    "max_prob_change": run.get("max_prob_change")})
    return {"baseline": baseline_metrics, "runs": out}


def max_probability_change(details_a: List[Dict], details_b: List[Dict]) -> float | None:
    """Largest absolute 1X2 probability shift on shared matches."""
    map_b = {r["match_id"]: r["probs"] for r in details_b}
    peak = 0.0
    shared = 0
    for row in details_a:
        if row["match_id"] not in map_b:
            continue
        shared += 1
        for pa, pb in zip(row["probs"], map_b[row["match_id"]]):
            peak = max(peak, abs(float(pa) - float(pb)))
    return round(peak, 6) if shared else None


def mc_convergence_stats(grids: Dict[int, List[Dict]]) -> Dict:
    """Compare Monte Carlo markets across simulation counts.

    grids: {n_simulations: detail_rows}. Reports pairwise probability
    differences vs the largest count. Deterministic seeds required upstream.
    """
    counts = sorted(grids)
    if not counts:
        return {"counts": [], "comparisons": []}
    reference = counts[-1]
    ref_map = {r["match_id"]: r["probs"] for r in grids[reference]}
    comparisons = []
    for count in counts[:-1]:
        peak_1x2 = peak_ou = peak_btts = peak_score = 0.0
        shared = 0
        for row in grids[count]:
            other = ref_map.get(row["match_id"])
            if other is None:
                continue
            shared += 1
            for pa, pb in zip(row["probs"], other):
                peak_1x2 = max(peak_1x2, abs(float(pa) - float(pb)))
        comparisons.append({"n_simulations": count, "reference": reference,
                            "shared_matches": shared,
                            "max_1x2_probability_difference": round(peak_1x2, 6)})
    return {"counts": counts, "comparisons": comparisons,
            "note": "10k simulations are sufficient when differences vs 25k "
                    "stay within tolerance on the evaluated population."}


def poisson_tail_mass(lambda_home: float, lambda_away: float,
                      max_goals: int = 10) -> Dict:
    """Probability mass inside vs outside the 0..max_goals grid.

    Uses the Poisson survival function directly (no sampling). If the
    outside mass is negligible across actual predictions, the limit stands;
    the grid is only widened on measured evidence.
    """
    def sf(lam: float, k: int) -> float:
        # P(X > k) via the regularized upper tail sum.
        total = 0.0
        term = math.exp(-lam)
        for i in range(k + 1):
            if i:
                term *= lam / i
            total += term
        return max(0.0, 1.0 - total)

    p_home_out = sf(lambda_home, max_goals)
    p_away_out = sf(lambda_away, max_goals)
    p_home_in = 1.0 - p_home_out
    p_away_in = 1.0 - p_away_out
    return {"lambda_home": lambda_home, "lambda_away": lambda_away,
            "max_goals": max_goals,
            "inside_mass": round(p_home_in * p_away_in, 8),
            "outside_mass": round(1.0 - p_home_in * p_away_in, 8)}


def truncation_audit(lambdas: List[tuple], max_goals: int = 10) -> Dict:
    """Aggregate tail mass over observed lambda pairs."""
    if not lambdas:
        return {"n": 0, "max_outside_mass": 0.0, "mean_outside_mass": 0.0}
    masses = [poisson_tail_mass(lh, la, max_goals)["outside_mass"]
              for lh, la in lambdas]
    return {"n": len(masses),
            "max_outside_mass": round(max(masses), 8),
            "mean_outside_mass": round(sum(masses) / len(masses), 8)}
