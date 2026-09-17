"""Team-level player aggregation (Phase 9).

Availability/history, attack, defense and workload features from regular
contributors, each with contributing players + aggregation metadata.
Minutes do not exist in the schema: workload uses appearance counts and
rest days, never synthesized minutes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.player_intelligence import aggregation as agg
from app.services.player_intelligence import event_features as registry
from app.services.player_intelligence import player_form as form_svc


def _env(value, available: bool, source: str, as_of: str, quality: str,
         contributors: List[Dict], method: str) -> Dict:
    return {"value": value, "available": available, "source": source,
            "as_of": as_of, "quality": quality, "contributors": contributors,
            "aggregation": method}


def team_features(db: Session, team_id: int, cutoff: datetime,
                  mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                  target_match_id=None,
                  precomputed_forms: Dict | None = None,
                  precomputed_appearances: Dict | None = None) -> Dict:
    """Transparent team aggregates over regular contributors."""
    forms = precomputed_forms if precomputed_forms is not None else \
        form_svc.player_form(db, team_id, cutoff, mode, target_match_id)
    as_of = forms["as_of"]
    regulars = agg.regulars(forms["players"])
    contributors = [{"canonical_player_id": v.get("canonical_player_id"),
                     "player_name": v.get("player_name"),
                     "matches_played": v.get("matches_played")}
                    for v in regulars.values()]
    n_regular = len(regulars)
    gate = n_regular >= 1
    quality = "estimated" if mode == TemporalMode.HISTORICAL_ESTIMATED else "strict"
    out: Dict = {"mode": forms["mode"], "as_of": as_of,
                 "n_regular_contributors": n_regular,
                 "matches_considered": forms["matches_considered"]}
    # Availability/history.
    all_players = [v for v in forms["players"].values()
                   if not v.get("unresolved", False)]
    starter_apps = [v for v in all_players
                    if v.get("matches_played", 0) >= 3]
    out["regular_starter_continuity"] = _env(
        round(len(starter_apps) / len(all_players), 4) if all_players else None,
        gate and bool(all_players), "lineups", as_of, quality,
        contributors, "share of known players with >=3 appearances")
    out["meaningful_minutes_players"] = _env(
        len(starter_apps) if gate else None, gate, "lineups", as_of, quality,
        contributors, "count of known players with >=3 appearances "
                      "(appearances, not minutes: minutes unavailable)")
    # Attack / defense rates from regulars (per appearance).
    for family, names in (("attack", ("goals", "penalties_scored")),
                          ("defense", ("yellow_cards", "red_cards"))):
        total_events = sum(regulars[k]["event_counts"].get(n, 0)
                           for k in regulars for n in names)
        total_apps = sum(regulars[k]["matches_played"] for k in regulars)
        out[f"recent_{family}_event_rate"] = _env(
            round(total_events / total_apps, 4) if gate and total_apps else None,
            gate and total_apps > 0, "statsbomb-events", as_of, quality,
            contributors, f"{family} events per appearance over regulars")
        shares = [sum(regulars[k]["event_counts"].get(n, 0) for n in names)
                  for k in regulars]
        conc = agg.concentration(shares)
        out[f"{family}_contribution_concentration"] = _env(
            conc, gate and conc.get("available", False), "statsbomb-events",
            as_of, quality, contributors,
            "top-contributor/top-3 share of counted events")
    top_attack = sorted(
        ((k, sum(v["event_counts"].get(n, 0) for n in ("goals", "penalties_scored")))
         for k, v in regulars.items()),
        key=lambda kv: kv[1], reverse=True)
    out["top_contributor_share"] = _env(
        round(top_attack[0][1] / max(1, sum(s for _, s in top_attack)), 4)
        if gate and top_attack and sum(s for _, s in top_attack) > 0 else None,
        gate and bool(top_attack), "statsbomb-events", as_of, quality,
        [{"key": k, "goals": s} for k, s in top_attack[:3]],
        "top scorer share of regulars' goals")
    # Workload (appearances + rest, never minutes).
    rests = []
    naive_cutoff = as_naive_utc(cutoff)
    for v in regulars.values():
        apps = v.get("matches_played", 0)
        rests.append(apps)
    out["squad_appearance_concentration"] = _env(
        agg.concentration(rests) if gate and rests else {"available": False},
        gate and bool(rests), "lineups", as_of, quality, contributors,
        "appearance-share concentration over regulars")
    # Roster staleness: days from cutoff to the most recent appearance among
    # regulars. Old parent-anchored rows are temporally valid but stale; this
    # number makes that visible instead of hiding it.
    apps_by_key = (precomputed_appearances or {}).get("players", {})
    staleness = []
    for key in regulars:
        days = (apps_by_key.get(key) or {}).get("days_since_last_appearance")
        if isinstance(days, (int, float)):
            staleness.append(days)
    out["roster_staleness_days"] = _env(
        round(max(staleness), 1) if staleness else None,
        gate and bool(staleness), "lineups", as_of, quality, contributors,
        "max days since last appearance among regulars")
    return out
