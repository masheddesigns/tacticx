"""Shared prediction math (Phase 2): Poisson grids, market aggregation."""
from __future__ import annotations

import math
from typing import Dict, Tuple

MAX_GRID_GOALS = 10


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def score_grid(lambda_home: float, lambda_away: float,
               max_goals: int = MAX_GRID_GOALS) -> Dict[str, float]:
    """Independent-Poisson scoreline distribution, renormalized to sum 1.

    Independence is a documented simplification (no Dixon-Coles correlation).
    """
    grid = {}
    for home in range(max_goals + 1):
        for away in range(max_goals + 1):
            grid[f"{home}-{away}"] = poisson_pmf(home, lambda_home) * poisson_pmf(away, lambda_away)
    total = sum(grid.values())
    if total <= 0:
        return {"0-0": 1.0}
    return {k: v / total for k, v in grid.items()}


def markets_from_grid(grid: Dict[str, float]) -> Dict[str, float]:
    """Aggregate 1X2 / totals / BTTS from a scoreline distribution."""
    home = draw = away = 0.0
    over_15 = over_25 = over_35 = 0.0
    btts_yes = 0.0
    for key, prob in grid.items():
        try:
            home_goals, away_goals = (int(x) for x in key.split("-"))
        except (ValueError, AttributeError):
            continue
        total = home_goals + away_goals
        if home_goals > away_goals:
            home += prob
        elif home_goals < away_goals:
            away += prob
        else:
            draw += prob
        if total > 1.5:
            over_15 += prob
        if total > 2.5:
            over_25 += prob
        if total > 3.5:
            over_35 += prob
        if home_goals > 0 and away_goals > 0:
            btts_yes += prob
    return {
        "home_win_probability": home,
        "draw_probability": draw,
        "away_win_probability": away,
        "over_1_5_probability": over_15,
        "under_1_5_probability": 1.0 - over_15,
        "over_2_5_probability": over_25,
        "under_2_5_probability": 1.0 - over_25,
        "over_3_5_probability": over_35,
        "under_3_5_probability": 1.0 - over_35,
        "btts_yes_probability": btts_yes,
        "btts_no_probability": 1.0 - btts_yes,
    }


def logistic_expected(rating_diff: float) -> float:
    """Standard Elo expected score for the rated-first side."""
    return 1.0 / (1.0 + 10.0 ** (-rating_diff / 400.0))


def normalize_triplet(home: float, draw: float, away: float) -> Tuple[float, float, float]:
    total = home + draw + away
    if total <= 0:
        return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
    return home / total, draw / total, away / total
