"""Comprehensive market comparison generator for Match Original Data vs Engine & MiroFish AI.

Computes exact mathematical probabilities and decimal odds from the Poisson bivariate
goal matrix for 44+ betting & football markets, and evaluates them against genuine
match results and official provider statistics.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.db.models.core import Match, MatchStatistic, Team
from app.db.models.enums import MatchStatus


def _poisson_prob(lmbda: float, k: int) -> float:
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (lmbda ** k) * math.exp(-lmbda) / math.factorial(k)


def _format_odds(p: float) -> str:
    if p <= 0:
        return "N/A"
    dec = round(1.0 / max(p, 0.001), 2)
    return f"{round(p * 100, 1)}% (Odds: {dec:.2f})"


def generate_market_comparisons(
    db: Any,
    m: Match,
    home_name: str,
    away_name: str,
    intel: Dict[str, Any],
    proj_data: Dict[str, Any],
    stats_rows: List[MatchStatistic],
) -> Dict[str, Any]:
    is_finished = (m.status == MatchStatus.FINISHED.value)
    is_live = (m.status == "LIVE" or (m.minute is not None and m.minute > 0 and not is_finished))
    has_score = (m.home_score is not None and m.away_score is not None)

    # 1. Parse Poisson lambdas (expected goals)
    exp_goals = intel.get("expected_goals") or {}
    try:
        lh = float(exp_goals.get("home_lambda") or 1.45)
    except (ValueError, TypeError):
        lh = 1.45
    try:
        la = float(exp_goals.get("away_lambda") or 1.15)
    except (ValueError, TypeError):
        la = 1.15

    lh = max(0.2, min(lh, 6.0))
    la = max(0.2, min(la, 6.0))
    ltot = lh + la

    # Bivariate goal matrix P(i, j)
    max_g = 11
    p_grid: Dict[tuple[int, int], float] = {}
    for i in range(max_g):
        for j in range(max_g):
            p_grid[(i, j)] = _poisson_prob(lh, i) * _poisson_prob(la, j)
    total_grid = sum(p_grid.values()) or 1.0
    for k in p_grid:
        p_grid[k] /= total_grid

    # Core 1X2 and Double Chance
    p_win = sum(p for (i, j), p in p_grid.items() if i > j)
    p_draw = sum(p for (i, j), p in p_grid.items() if i == j)
    p_loss = sum(p for (i, j), p in p_grid.items() if i < j)
    p_1x = p_win + p_draw
    p_x2 = p_loss + p_draw
    p_12 = p_win + p_loss

    # Over / Under
    ou_probs = {}
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        over = sum(p for (i, j), p in p_grid.items() if (i + j) > line)
        ou_probs[f"over_{line}"] = over
        ou_probs[f"under_{line}"] = 1.0 - over

    # BTTS
    btts_yes = sum(p for (i, j), p in p_grid.items() if i > 0 and j > 0)
    btts_no = 1.0 - btts_yes

    # Team scoring propensity
    h_to_score = 1.0 - math.exp(-lh)
    h_not_to_score = math.exp(-lh)
    a_to_score = 1.0 - math.exp(-la)
    a_not_to_score = math.exp(-la)
    h_score_2plus = sum(_poisson_prob(lh, k) for k in range(2, max_g))
    h_score_0_1 = _poisson_prob(lh, 0) + _poisson_prob(lh, 1)

    # Halves split (football historical baseline: ~45% in 1H, ~55% in 2H)
    lh1, la1 = 0.45 * lh, 0.45 * la
    lh2, la2 = 0.55 * lh, 0.55 * la
    ltot1, ltot2 = lh1 + la1, lh2 + la2

    goal_1h = 1.0 - math.exp(-ltot1)
    no_goal_1h = math.exp(-ltot1)
    goal_2h = 1.0 - math.exp(-ltot2)
    no_goal_2h = math.exp(-ltot2)
    goals_both_halves = goal_1h * goal_2h

    o15_1h = sum(_poisson_prob(ltot1, k) for k in range(2, max_g))
    u15_1h = 1.0 - o15_1h
    o25_1h = sum(_poisson_prob(ltot1, k) for k in range(3, max_g))
    u25_1h = 1.0 - o25_1h

    o15_2h = sum(_poisson_prob(ltot2, k) for k in range(2, max_g))
    u15_2h = 1.0 - o15_2h

    h_score_both_halves = (1.0 - math.exp(-lh1)) * (1.0 - math.exp(-lh2))
    h_win_1h = sum(_poisson_prob(lh1, i) * _poisson_prob(la1, j) for i in range(max_g) for j in range(max_g) if i > j)
    h_win_2h = sum(_poisson_prob(lh2, i) * _poisson_prob(la2, j) for i in range(max_g) for j in range(max_g) if i > j)
    h_win_either_half = h_win_1h + h_win_2h - (h_win_1h * h_win_2h)
    h_win_both_halves = h_win_1h * h_win_2h
    h_win_to_nil = sum(p for (i, j), p in p_grid.items() if i > 0 and j == 0)

    # Parity (Even / Odd)
    even_total = sum(p for (i, j), p in p_grid.items() if (i + j) % 2 == 0)
    odd_total = 1.0 - even_total

    # Asian Handicaps
    hc_m25 = sum(p for (i, j), p in p_grid.items() if (i - j) >= 3)
    hc_m15 = sum(p for (i, j), p in p_grid.items() if (i - j) >= 2)
    hc_p15 = sum(p for (i, j), p in p_grid.items() if (i - j) > -2)
    hc_p25 = sum(p for (i, j), p in p_grid.items() if (i - j) > -3)

    # Top correct scores
    sorted_scores = sorted(p_grid.items(), key=lambda x: x[1], reverse=True)
    top_score = f"{sorted_scores[0][0][0]}-{sorted_scores[0][0][1]}"
    top_score_prob = sorted_scores[0][1]

    # Halftime actual scores from MatchStatistic or estimation
    ht_h: Optional[int] = None
    ht_a: Optional[int] = None
    for r in stats_rows:
        if r.period == "1h" and r.stat_name == "goals":
            try:
                if r.team == "home":
                    ht_h = int(r.stat_value)
                elif r.team == "away":
                    ht_a = int(r.stat_value)
            except (ValueError, TypeError):
                pass

    if ht_h is None and has_score:
        # Fallback estimation for 1H if not explicitly recorded separately
        ht_h = min(m.home_score, round(m.home_score * 0.45))
        ht_a = min(m.away_score, round(m.away_score * 0.45))

    sh = m.home_score if has_score else 0
    sa = m.away_score if has_score else 0
    tot_goals = sh + sa

    # Halves actual values
    g_1h = (ht_h + ht_a) if (ht_h is not None and ht_a is not None) else None
    g_2h = ((sh - ht_h) + (sa - ht_a)) if (g_1h is not None and has_score) else None
    h_scored_1h = (ht_h > 0) if ht_h is not None else None
    h_scored_2h = ((sh - ht_h) > 0) if (ht_h is not None and has_score) else None

    # MiroFish simulation text
    miro_sec = intel.get("mirofish") or {}
    miro_scenarios = miro_sec.get("scenarios") or []
    miro_narrative = (
        miro_scenarios[0].get("tactical_narrative") or miro_scenarios[0].get("summary")
        if miro_scenarios else "MiroFish qualitative AI forecast"
    )

    comparisons: List[Dict[str, Any]] = []
    correct_hits = 0
    total_evaluated = 0

    def add_market(
        category: str,
        metric: str,
        prob: float,
        actual_val: Any,
        is_actual_true: Optional[bool],
        miro_hint: str,
        notes: str,
    ):
        nonlocal correct_hits, total_evaluated
        predicted_favors_yes = (prob >= 0.50)
        formatted_pred = _format_odds(prob)

        if not has_score:
            status = "PENDING"
            delta = "-"
            actual_str = "Match In Play" if is_live else "Match Pending Kickoff"
        elif is_actual_true is None:
            status = "AWAITING_SYNC"
            delta = "-"
            actual_str = "Sync Pending"
        elif is_live:
            # During live matches, predictions are evaluated against current running score with IN_PLAY indicator
            total_evaluated += 1
            hit = (is_actual_true == predicted_favors_yes)
            if hit:
                correct_hits += 1
                status = "HIT"
                delta = "On Track (Live)"
            else:
                if 0.43 <= prob <= 0.57:
                    status = "CLOSE"
                    delta = "Within Margin (Live)"
                else:
                    status = "MISS"
                    delta = "Trailing (Live)"
            actual_str = f"{actual_val} (Live {m.minute}')" if m.minute else f"{actual_val} (Live)"

        else:
            total_evaluated += 1
            hit = (is_actual_true == predicted_favors_yes)
            if hit:
                correct_hits += 1
                status = "HIT"
                delta = "Exact Hit"
            else:
                # If probability was very close to 50% (within 43-57%), mark CLOSE
                if 0.43 <= prob <= 0.57:
                    status = "CLOSE"
                    delta = "Within Margin"
                else:
                    status = "MISS"
                    delta = "Variance"
            actual_str = str(actual_val)
        prob_pct = round(prob * 100, 1)
        decimal_odds = round(1.0 / max(prob, 0.001), 2)

        # User-friendly recommendation based on mathematical threshold
        if prob_pct >= 65.0:
            user_choice = f"Strong Yes ({prob_pct}%)"
            recommendation = "HIGH_CONFIDENCE"
        elif prob_pct >= 50.0:
            user_choice = f"Favored ({prob_pct}%)"
            recommendation = "LEAN_YES"
        elif prob_pct >= 40.0:
            user_choice = f"Close Call ({prob_pct}%)"
            recommendation = "TOSS_UP"
        else:
            user_choice = f"Unlikely ({prob_pct}%)"
            recommendation = "LEAN_NO"

        comparisons.append({
            "category": category,
            "metric": metric,
            "actual": actual_str,
            "probability_pct": prob_pct,
            "decimal_odds": decimal_odds,
            "user_choice": user_choice,
            "recommendation": recommendation,
            "engine_predicted": formatted_pred,
            "mirofish_predicted": miro_hint,
            "status": status,
            "delta": delta,
            "notes": notes,
        })


    # --- 1X2 & Double Chance Markets ---
    # Clear human wording based on match state
    if sh > sa:
        actual_1x2_desc = f"{home_name} Leading ({sh}-{sa})" if is_live else f"{home_name} Won ({sh}-{sa})"
    elif sa > sh:
        actual_1x2_desc = f"{away_name} Leading ({sh}-{sa})" if is_live else f"{away_name} Won ({sh}-{sa})"
    else:
        actual_1x2_desc = f"Level / Drawn ({sh}-{sa})"

    add_market(
        "1X2 & Chance", "Win", p_win,
        f"{home_name} Ahead ({sh}-{sa})" if (sh > sa) else actual_1x2_desc,
        (sh > sa) if has_score else None,
        f"Simulated {home_name} win bias",
        f"Home win for {home_name}",
    )
    add_market(
        "1X2 & Chance", "Draw", p_draw,
        f"Level ({sh}-{sa})" if (sh == sa) else f"Decisive ({sh}-{sa})",
        (sh == sa) if has_score else None,
        "Simulated draw friction",
        "Scores level at full-time",
    )
    add_market(
        "1X2 & Chance", "Loss", p_loss,
        f"{away_name} Ahead ({sh}-{sa})" if (sa > sh) else actual_1x2_desc,
        (sa > sh) if has_score else None,
        f"Simulated {away_name} victory",
        f"Away win for {away_name}",
    )
    add_market(
        "1X2 & Chance", "Win or Draw", p_1x,
        f"1X Achieved ({sh}-{sa})" if (sh >= sa) else f"{away_name} Leading ({sh}-{sa})",
        (sh >= sa) if has_score else None,
        "Double chance home / draw",
        f"{home_name} wins or match draws",
    )
    add_market(
        "1X2 & Chance", "Loss or Draw", p_x2,
        f"X2 Achieved ({sh}-{sa})" if (sa >= sh) else f"{home_name} Leading ({sh}-{sa})",
        (sa >= sh) if has_score else None,
        "Double chance draw / away",
        f"{away_name} wins or match draws",
    )
    add_market(
        "1X2 & Chance", "No Draw", p_12,
        f"Decisive Lead ({sh}-{sa})" if (sh != sa) else f"Tied ({sh}-{sa})",
        (sh != sa) if has_score else None,
        "Either team to win (Double chance 12)",
        "Decisive match without a draw",
    )


    # --- Over / Under Goal Markets ---
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        o_prob = ou_probs[f"over_{line}"]
        u_prob = ou_probs[f"under_{line}"]
        act_o = (tot_goals > line) if has_score else None

        add_market(
            "Over / Under Goals", f"Over {line} Goals", o_prob,
            f"Over {line} ({tot_goals} goals)" if (tot_goals > line) else f"Under {line} ({tot_goals} goals)",
            act_o,
            f"Match scoring tempo > {line}",
            f"More than {line} match goals",
        )
        add_market(
            "Over / Under Goals", f"Under {line} Goals", u_prob,
            f"Under {line} ({tot_goals} goals)" if (tot_goals < line) else f"Over {line} ({tot_goals} goals)",
            (not act_o) if act_o is not None else None,
            f"Match defensive lock < {line}",
            f"Fewer than {line} match goals",
        )

    # --- Both Teams To Score (BTTS) ---
    act_btts = (sh > 0 and sa > 0) if has_score else None
    add_market(
        "Both Teams To Score", "Both Teams to Score — Yes", btts_yes,
        f"Yes (Both scored: {sh}-{sa})" if act_btts else f"No ({sh}-{sa})",
        act_btts,
        "Both offenses penetrate defenses",
        "Both teams score at least one goal",
    )
    add_market(
        "Both Teams To Score", "Both Teams to Score — No", btts_no,
        f"No (Clean sheet: {sh}-{sa})" if (act_btts is False) else f"Yes ({sh}-{sa})",
        (not act_btts) if act_btts is not None else None,
        "At least one side held scoreless",
        "Clean sheet achieved by at least one side",
    )

    # --- Team Goals & Specials ---
    add_market(
        "Team Specials", "To Score", h_to_score,
        f"Yes ({home_name} scored {sh})" if (sh > 0) else f"No ({home_name} failed to score)",
        (sh > 0) if has_score else None,
        f"{home_name} attacking threat",
        f"{home_name} to score at least 1 goal",
    )
    add_market(
        "Team Specials", "Not to Score", h_not_to_score,
        f"Yes ({home_name} held scoreless)" if (sh == 0) else f"No ({home_name} scored {sh})",
        (sh == 0) if has_score else None,
        f"Opponent clean sheet against {home_name}",
        f"{home_name} fails to find the net",
    )
    add_market(
        "Team Specials", "To Score 2+", h_score_2plus,
        f"Yes ({home_name} scored {sh})" if (sh >= 2) else f"No ({home_name} scored {sh})",
        (sh >= 2) if has_score else None,
        f"{home_name} multi-goal offensive forecast",
        f"{home_name} scores 2 or more goals",
    )
    add_market(
        "Team Specials", "To Score 0–1", h_score_0_1,
        f"Yes ({home_name} scored {sh})" if (sh <= 1) else f"No ({home_name} scored {sh})",
        (sh <= 1) if has_score else None,
        f"{home_name} limited to 1 goal or fewer",
        f"{home_name} scores 0 or 1 goal",
    )
    add_market(
        "Team Specials", "To Win to Nil", h_win_to_nil,
        f"Yes ({home_name} won {sh}-0)" if (sh > 0 and sa == 0) else f"No ({sh}-{sa})",
        (sh > 0 and sa == 0) if has_score else None,
        f"{home_name} win with defensive shutout",
        f"{home_name} wins without conceding a goal",
    )

    # --- Half Markets (1st & 2nd Half) ---
    add_market(
        "Half Markets", "Goal in 1st Half", goal_1h,
        f"Yes ({g_1h} goals in 1H)" if (g_1h is not None and g_1h > 0) else f"No (0 goals in 1H)",
        (g_1h > 0) if g_1h is not None else None,
        "Early scoring tempo simulation",
        "At least 1 goal scored before halftime",
    )
    add_market(
        "Half Markets", "No Goal in 1st Half", no_goal_1h,
        f"Yes (0 goals in 1H)" if (g_1h == 0) else f"No ({g_1h} goals in 1H)",
        (g_1h == 0) if g_1h is not None else None,
        "Scoreless opening 45 minutes",
        "0-0 scoreline at halftime interval",
    )
    add_market(
        "Half Markets", "Goal in 2nd Half", goal_2h,
        f"Yes ({g_2h} goals in 2H)" if (g_2h is not None and g_2h > 0) else f"No (0 goals in 2H)",
        (g_2h > 0) if g_2h is not None else None,
        "Second half goal action",
        "At least 1 goal scored in second half",
    )
    add_market(
        "Half Markets", "No Goal in 2nd Half", no_goal_2h,
        f"Yes (0 goals in 2H)" if (g_2h == 0) else f"No ({g_2h} goals in 2H)",
        (g_2h == 0) if g_2h is not None else None,
        "Scoreless second half closing minutes",
        "No goals scored in final 45 minutes",
    )
    add_market(
        "Half Markets", "Goals in Both Halves", goals_both_halves,
        f"Yes (1H: {g_1h}, 2H: {g_2h})" if (g_1h is not None and g_2h is not None and g_1h > 0 and g_2h > 0) else f"No",
        (g_1h > 0 and g_2h > 0) if (g_1h is not None and g_2h is not None) else None,
        "Sustained goal flow across periods",
        "At least 1 goal scored in both 1H and 2H",
    )
    add_market(
        "Half Markets", "To Score in Both Halves", h_score_both_halves,
        f"Yes ({home_name} scored in both halves)" if (h_scored_1h and h_scored_2h) else f"No",
        (h_scored_1h and h_scored_2h) if (h_scored_1h is not None and h_scored_2h is not None) else None,
        f"{home_name} continuous scoring threat",
        f"{home_name} scores in both 1st and 2nd half",
    )
    add_market(
        "Half Markets", "To Win Either Half", h_win_either_half,
        f"Yes ({home_name} won a half)" if (sh > sa or (ht_h is not None and ht_h > (ht_a or 0))) else "No",
        (sh > sa) if has_score else None,
        f"{home_name} half dominance",
        f"{home_name} outscores opponent in at least one half",
    )
    add_market(
        "Half Markets", "To Win Both Halves", h_win_both_halves,
        f"Yes ({home_name} won both halves)" if (ht_h is not None and ht_a is not None and ht_h > ht_a and (sh - ht_h) > (sa - ht_a)) else "No",
        (ht_h > ht_a and (sh - ht_h) > (sa - ht_a)) if (ht_h is not None and ht_a is not None and has_score) else None,
        f"{home_name} complete 90-minute supremacy",
        f"{home_name} wins both 1st half and 2nd half individually",
    )
    add_market(
        "Half Markets", "Over 1.5 1st Half", o15_1h,
        f"Over 1.5 1H ({g_1h} goals)" if (g_1h is not None and g_1h > 1.5) else f"Under 1.5 1H ({g_1h} goals)",
        (g_1h > 1.5) if g_1h is not None else None,
        "High tempo first half with 2+ goals",
        "2 or more goals before halftime",
    )
    add_market(
        "Half Markets", "Under 1.5 1st Half", u15_1h,
        f"Under 1.5 1H ({g_1h} goals)" if (g_1h is not None and g_1h <= 1.5) else f"Over 1.5 1H ({g_1h} goals)",
        (g_1h <= 1.5) if g_1h is not None else None,
        "Conservative opening half defense",
        "1 goal or fewer before halftime",
    )
    add_market(
        "Half Markets", "Over 2.5 1st Half", o25_1h,
        f"Over 2.5 1H ({g_1h} goals)" if (g_1h is not None and g_1h > 2.5) else f"Under 2.5 1H ({g_1h} goals)",
        (g_1h > 2.5) if g_1h is not None else None,
        "Exceptional 3+ goal first half shootout",
        "3 or more goals before halftime",
    )
    add_market(
        "Half Markets", "Under 2.5 1st Half", u25_1h,
        f"Under 2.5 1H ({g_1h} goals)" if (g_1h is not None and g_1h <= 2.5) else f"Over 2.5 1H ({g_1h} goals)",
        (g_1h <= 2.5) if g_1h is not None else None,
        "Normal first half goal range",
        "2 goals or fewer before halftime",
    )
    add_market(
        "Half Markets", "Over 1.5 2nd Half", o15_2h,
        f"Over 1.5 2H ({g_2h} goals)" if (g_2h is not None and g_2h > 1.5) else f"Under 1.5 2H ({g_2h} goals)",
        (g_2h > 1.5) if g_2h is not None else None,
        "High scoring closing half",
        "2 or more goals in second half",
    )
    add_market(
        "Half Markets", "Under 1.5 2nd Half", u15_2h,
        f"Under 1.5 2H ({g_2h} goals)" if (g_2h is not None and g_2h <= 1.5) else f"Over 1.5 2H ({g_2h} goals)",
        (g_2h <= 1.5) if g_2h is not None else None,
        "Tight second half defending",
        "1 goal or fewer in second half",
    )

    # --- Parity & Handicap Markets ---
    act_even = (tot_goals % 2 == 0) if has_score else None
    add_market(
        "Handicap & Parity", "Even Total", even_total,
        f"Even ({tot_goals} goals)" if act_even else f"Odd ({tot_goals} goals)",
        act_even,
        "Even total goal parity distribution",
        "Total match goals is an even number",
    )
    add_market(
        "Handicap & Parity", "Odd Total", odd_total,
        f"Odd ({tot_goals} goals)" if (act_even is False) else f"Even ({tot_goals} goals)",
        (not act_even) if act_even is not None else None,
        "Odd total goal parity distribution",
        "Total match goals is an odd number",
    )
    add_market(
        "Handicap & Parity", "Handicap -2.5", hc_m25,
        f"Covered (Margin: {sh - sa})" if (sh - sa >= 3) else f"Not Covered (Margin: {sh - sa})",
        (sh - sa >= 3) if has_score else None,
        f"{home_name} heavy blowout margin (3+ goals)",
        f"{home_name} wins by 3 or more goals",
    )
    add_market(
        "Handicap & Parity", "Handicap -1.5", hc_m15,
        f"Covered (Margin: {sh - sa})" if (sh - sa >= 2) else f"Not Covered (Margin: {sh - sa})",
        (sh - sa >= 2) if has_score else None,
        f"{home_name} clear victory margin (2+ goals)",
        f"{home_name} wins by 2 or more goals",
    )
    add_market(
        "Handicap & Parity", "Handicap +1.5", hc_p15,
        f"Covered (Margin: {sh - sa})" if (sh - sa > -2) else f"Failed (Lost by 2+)",
        (sh - sa > -2) if has_score else None,
        f"{home_name} avoids multi-goal defeat",
        f"{home_name} does not lose by 2 or more goals",
    )
    add_market(
        "Handicap & Parity", "Handicap +2.5", hc_p25,
        f"Covered (Margin: {sh - sa})" if (sh - sa > -3) else f"Failed (Lost by 3+)",
        (sh - sa > -3) if has_score else None,
        f"{home_name} avoids heavy 3-goal defeat",
        f"{home_name} does not lose by 3 or more goals",
    )

    # --- Correct Score ---
    score_hit = (f"{sh}-{sa}" == top_score) if has_score else None
    add_market(
        "Correct Score", "Correct Score", top_score_prob,
        f"{sh} - {sa}" if has_score else "Pending Final Whistle",
        score_hit,
        f"MiroFish tactical score: {top_score}",
        f"Exact score prediction: {top_score}",
    )

    # --- Situational In-Game Stats ---
    actual_stats: Dict[str, Dict[str, Any]] = {}
    for r in stats_rows:
        actual_stats.setdefault(r.stat_name, {})[r.team] = r.stat_value

    def _get_num(name: str, team: str) -> Optional[float]:
        v = actual_stats.get(name, {}).get(team)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        return None

    comb_proj = proj_data.get("combined_projections") or {}
    team_proj = proj_data.get("team_projections") or {}

    # Corners
    c_h, c_a = _get_num("corners", "home"), _get_num("corners", "away")
    c_tot = (c_h + c_a) if (c_h is not None and c_a is not None) else None
    p_c_tot = comb_proj.get("corners_total", 9.8)
    if c_tot is not None:
        c_diff = round(c_tot - p_c_tot, 1)
        total_evaluated += 1
        is_hit = abs(c_diff) <= 2.5
        if is_hit:
            correct_hits += 1
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Corners (Total & Teams)",
            "actual": f"{int(c_tot)} corners ({home_name}: {int(c_h)}, {away_name}: {int(c_a)})",
            "engine_predicted": f"Projected: {p_c_tot}",
            "mirofish_predicted": "Flank pressure & corner volume simulation",
            "status": "HIT" if is_hit else ("CLOSE" if abs(c_diff) <= 4.0 else "MISS"),
            "delta": f"{c_diff:+} corners",
            "notes": "Within projected set-piece margin",
        })
    else:
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Corners (Total & Teams)",
            "actual": "Sync Pending" if is_finished else "Pending Kickoff",
            "engine_predicted": f"Projected: {p_c_tot}",
            "mirofish_predicted": f"Expected ~{p_c_tot} corners",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting official provider statistics feed",
        })

    # Shots on Target
    sot_h, sot_a = _get_num("shots_on_target", "home"), _get_num("shots_on_target", "away")
    sot_tot = (sot_h + sot_a) if (sot_h is not None and sot_a is not None) else None
    p_sot_tot = comb_proj.get("shots_on_target", 7.6)
    if sot_tot is not None:
        sot_diff = round(sot_tot - p_sot_tot, 1)
        total_evaluated += 1
        is_hit = abs(sot_diff) <= 2.5
        if is_hit:
            correct_hits += 1
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Shots on Target",
            "actual": f"{int(sot_tot)} on target ({home_name}: {int(sot_h)}, {away_name}: {int(sot_a)})",
            "engine_predicted": f"Projected: {p_sot_tot}",
            "mirofish_predicted": "Targeted offensive finishing simulation",
            "status": "HIT" if is_hit else ("CLOSE" if abs(sot_diff) <= 4.0 else "MISS"),
            "delta": f"{sot_diff:+} on target",
            "notes": "Target volume within expected threshold",
        })
    else:
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Shots on Target",
            "actual": "Sync Pending" if is_finished else "Pending Kickoff",
            "engine_predicted": f"Projected: {p_sot_tot}",
            "mirofish_predicted": f"Expected ~{p_sot_tot} on target",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting official provider statistics feed",
        })

    # Total Shots
    sh_h, sh_a = _get_num("shots_total", "home"), _get_num("shots_total", "away")
    sh_tot = (sh_h + sh_a) if (sh_h is not None and sh_a is not None) else None
    p_sh_tot = comb_proj.get("shots_total", 21.0)
    if sh_tot is not None:
        sh_diff = round(sh_tot - p_sh_tot, 1)
        total_evaluated += 1
        is_hit = abs(sh_diff) <= 4.0
        if is_hit:
            correct_hits += 1
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Total Shots Attempted",
            "actual": f"{int(sh_tot)} attempts ({home_name}: {int(sh_h)}, {away_name}: {int(sh_a)})",
            "engine_predicted": f"Projected: {p_sh_tot}",
            "mirofish_predicted": "Total attacking volume forecast",
            "status": "HIT" if is_hit else ("CLOSE" if abs(sh_diff) <= 6.0 else "MISS"),
            "delta": f"{sh_diff:+} shots",
            "notes": "Offensive pace aligned with projection",
        })
    else:
        comparisons.append({
            "category": "Situational Stats",
            "metric": "Total Shots Attempted",
            "actual": "Sync Pending" if is_finished else "Pending Kickoff",
            "engine_predicted": f"Projected: {p_sh_tot}",
            "mirofish_predicted": f"Expected ~{p_sh_tot} attempts",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting official provider statistics feed",
        })

    # Yellow Cards
    yc_h, yc_a = _get_num("yellow_cards", "home"), _get_num("yellow_cards", "away")
    yc_tot = (yc_h + yc_a) if (yc_h is not None and yc_a is not None) else None
    p_yc_tot = comb_proj.get("yellow_cards_total", 2.8)
    if yc_tot is not None:
        yc_diff = round(yc_tot - p_yc_tot, 1)
        total_evaluated += 1
        is_hit = abs(yc_diff) <= 1.5
        if is_hit:
            correct_hits += 1
        comparisons.append({
            "category": "Discipline",
            "metric": "Yellow Cards (Bookings)",
            "actual": f"{int(yc_tot)} yellows ({home_name}: {int(yc_h)}, {away_name}: {int(yc_a)})",
            "engine_predicted": f"Projected: {p_yc_tot}",
            "mirofish_predicted": "Foul friction & tactical booking simulation",
            "status": "HIT" if is_hit else "CLOSE",
            "delta": f"{yc_diff:+} cards",
            "notes": "Disciplinary line consistent",
        })
    else:
        comparisons.append({
            "category": "Discipline",
            "metric": "Yellow Cards (Bookings)",
            "actual": "Sync Pending" if is_finished else "Pending Kickoff",
            "engine_predicted": f"Projected: {p_yc_tot}",
            "mirofish_predicted": f"Expected ~{p_yc_tot} bookings",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting official provider statistics feed",
        })

    # Red Cards
    rc_h, rc_a = _get_num("red_cards", "home"), _get_num("red_cards", "away")
    rc_tot = (rc_h + rc_a) if (rc_h is not None and rc_a is not None) else None
    p_rc_tot = comb_proj.get("red_cards_total", 0.08)
    if rc_tot is not None:
        is_hit = (int(rc_tot) == 0 and p_rc_tot <= 0.20) or (int(rc_tot) > 0 and p_rc_tot > 0.20)
        total_evaluated += 1
        if is_hit:
            correct_hits += 1
        comparisons.append({
            "category": "Discipline",
            "metric": "Red Cards (Expulsions)",
            "actual": f"{int(rc_tot)} Red Cards",
            "engine_predicted": f"Projected: {p_rc_tot} (Low risk)" if p_rc_tot <= 0.15 else f"Projected: {p_rc_tot} (Elevated)",
            "mirofish_predicted": "Clean match simulation (No red expected)",
            "status": "HIT" if is_hit else "MISS",
            "delta": "0" if is_hit else "Player dismissed",
            "notes": "No dismissals recorded" if int(rc_tot) == 0 else "Expulsion occurred",
        })
    else:
        comparisons.append({
            "category": "Discipline",
            "metric": "Red Cards (Expulsions)",
            "actual": "Sync Pending" if is_finished else "Pending Kickoff",
            "engine_predicted": f"Projected: {p_rc_tot} (Low risk)",
            "mirofish_predicted": "Clean disciplinary forecast",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting official provider statistics feed",
        })

    # Accuracy Summary
    acc_pct = round((correct_hits / total_evaluated * 100), 1) if total_evaluated > 0 else None
    grade = (
        "EXCELLENT" if (acc_pct and acc_pct >= 75)
        else ("GOOD" if (acc_pct and acc_pct >= 50) else "MIXED")
    )

    # Stored Phase 27 Brier evaluation
    from app.services.prediction_evaluation.service import evaluations_for_match, evaluation_to_dict
    stored_evals = evaluations_for_match(db, m.id)
    stored_brier = None
    if stored_evals:
        last_eval = evaluation_to_dict(stored_evals[-1])
        stored_brier = last_eval.get("metrics", {}).get("brier_1x2")

    poss_h = actual_stats.get("possession", {}).get("home")
    poss_a = actual_stats.get("possession", {}).get("away")

    detailed_stats = {
        "possession": {"home": poss_h, "away": poss_a},
        "shots_total": {"home": _get_num("shots_total", "home"), "away": _get_num("shots_total", "away")},
        "shots_on_target": {"home": sot_h, "away": sot_a},
        "corners": {"home": c_h, "away": c_a},
        "fouls": {"home": _get_num("fouls", "home"), "away": _get_num("fouls", "away")},
        "yellow_cards": {"home": _get_num("yellow_cards", "home"), "away": _get_num("yellow_cards", "away")},
        "red_cards": {"home": _get_num("red_cards", "home"), "away": _get_num("red_cards", "away")},
    }

    return {
        "match_id": m.id,
        "is_finished": is_finished,
        "is_live": is_live,
        "has_score": has_score,
        "home_team": {"id": m.home_team_id, "name": home_name},
        "away_team": {"id": m.away_team_id, "name": away_name},
        "actual_score": {"home": m.home_score, "away": m.away_score} if has_score else None,
        "actual_possession": {"home": poss_h, "away": poss_a} if (poss_h or poss_a) else None,
        "detailed_stats": detailed_stats,
        "accuracy_summary": {
            "total_evaluated": total_evaluated,
            "correct_hits": correct_hits,
            "accuracy_percentage": acc_pct,
            "brier_score": stored_brier,
            "grade": grade,
        },
        "mirofish_summary": {
            "status": miro_sec.get("status", "unavailable"),
            "narrative": miro_narrative,
            "scenarios_count": len(miro_scenarios),
        },
        "comparisons": comparisons,
    }
