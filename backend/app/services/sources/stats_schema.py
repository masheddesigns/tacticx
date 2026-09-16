"""Canonical match-statistic schema (Phase 1.7).

Different sources name the same measurement differently. Every adapter (and,
defensively, the pipeline) maps raw names to these canonical per-team names:

    shots_total, shots_on_target, corners, fouls, yellow_cards, red_cards,
    possession, expected_goals, offsides, passes_total, passes_accurate,
    goalkeeper_saves, goals

Storage is one row per (match, team=home|away, stat_name, period); half-time
goals use period="1h". Unknown names pass through unchanged — never dropped.
Missing fields stay missing; derived values (e.g. off-target = total - on)
are NEVER stored as source data.
"""
from __future__ import annotations

# Raw name (lowercased, spaces/punctuation -> _) -> canonical name.
ALIASES = {
    # football-data.co.uk columns (already canonical in most cases)
    "hs": "shots_total",
    "as": "shots_total",
    "hst": "shots_on_target",
    "ast": "shots_on_target",
    "hc": "corners",
    "ac": "corners",
    "hf": "fouls",
    "af": "fouls",
    "hy": "yellow_cards",
    "ay": "yellow_cards",
    "hr": "red_cards",
    "ar": "red_cards",
    # API-Football /fixtures/statistics types
    "shots_on_goal": "shots_on_target",
    "shots_off_goal": "shots_off_target",
    "total_shots": "shots_total",
    "blocked_shots": "shots_blocked",
    "shots_insidebox": "shots_inside_box",
    "shots_outsidebox": "shots_outside_box",
    "ball_possession": "possession",
    "corner_kicks": "corners",
    "offsides": "offsides",
    "fouls": "fouls",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "goalkeeper_saves": "goalkeeper_saves",
    "goals_prevented": "goals_prevented",
    "total_passes": "passes_total",
    "passes_accurate": "passes_accurate",
    "passes": "passes_total",
    "expected_goals": "expected_goals",
    "xg": "expected_goals",
    "goals": "goals",
}

# StatsBomb-derived aggregates (computed ONLY from that source's own events,
# labelled with source provenance — never mixed into another source's rows).
STATSBOMB_PREFIX = "sb_"


def normalize_stat_name(raw: str) -> str:
    """Map a raw stat name to canonical form. Unknown names pass through."""
    if raw is None:
        return ""
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


# Stat names counted by the coverage report.
SHOTS_STATS = {"shots_total", "shots_on_target", "shots_off_target", "shots_blocked",
               "shots_inside_box", "shots_outside_box"}
POSSESSION_STATS = {"possession"}
CORNERS_STATS = {"corners"}
CARDS_STATS = {"yellow_cards", "red_cards"}
XG_STATS = {"xg", "expected_goals", "expected_goals_for", "exp_g"}
FORMATION_STATS = {"formation"}
