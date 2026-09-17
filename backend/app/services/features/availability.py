"""Feature availability gating (Phase 2).

A model may only consume features that meet minimum coverage AND temporal
requirements. Availability is computed per match/cutoff/mode and stored with
every prediction, so any result can be audited for what the model was and
was not allowed to see.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy.orm import Session

from app.db.models.core import MatchStatistic
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode

SECONDARY_STATS = ("shots_total", "shots_on_target", "corners", "fouls",
                   "yellow_cards", "red_cards")


@dataclass
class FeatureAvailability:
    goals: bool = False
    shots: bool = False
    corners: bool = False
    cards: bool = False
    xg: bool = False
    events: bool = False
    lineups: bool = False
    possession: bool = False  # no legitimate bulk source; always False in v1
    home_history: int = 0
    away_history: int = 0
    home_xg_history: int = 0
    away_xg_history: int = 0
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "goals": self.goals, "shots": self.shots, "corners": self.corners,
            "cards": self.cards, "xg": self.xg, "events": self.events,
            "lineups": self.lineups, "possession": self.possession,
            "home_history": self.home_history, "away_history": self.away_history,
            "home_xg_history": self.home_xg_history,
            "away_xg_history": self.away_xg_history,
            "notes": self.notes,
        }


def assess_availability(db: Session, match_id: int, cutoff,
                        mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                        minimum_team_matches: int = 5,
                        minimum_xg_matches: int = 3) -> FeatureAvailability:
    """Decide which features are eligible for predicting one match."""
    from app.db.models.core import Match

    avail = FeatureAvailability()
    match = db.get(Match, match_id)
    if match is None or match.home_team_id is None or match.away_team_id is None:
        avail.notes.append("match or teams missing")
        return avail
    repo = HistoricalFeatureRepository(db, cutoff, mode)
    home_hist = repo.team_matches_before(match.home_team_id)
    away_hist = repo.team_matches_before(match.away_team_id)
    avail.home_history = len(home_hist)
    avail.away_history = len(away_hist)
    avail.goals = (len(home_hist) >= minimum_team_matches
                   and len(away_hist) >= minimum_team_matches)
    if not avail.goals:
        avail.notes.append(
            f"insufficient goal history (home={len(home_hist)}, away={len(away_hist)}, "
            f"minimum={minimum_team_matches})")
    # Secondary stats: eligible when goals are eligible AND the stat types
    # exist anywhere in pre-cutoff league history (coverage proxy).
    if avail.goals and match.league_id is not None:
        present = {r[0] for r in db.query(MatchStatistic.stat_name).join(
            Match, Match.id == MatchStatistic.match_id).filter(
            Match.league_id == match.league_id,
            Match.kickoff_at < repo.cutoff).distinct().all()}
        avail.shots = bool({"shots_total", "shots_on_target"} & present)
        avail.corners = "corners" in present
        avail.cards = bool({"yellow_cards", "red_cards"} & present)
    # xG: each team needs its own minimum of pre-cutoff xG observations.
    # Never substituted with goals/shots/estimates when missing.
    home_xg = repo.team_xg_before(match.home_team_id)
    away_xg = repo.team_xg_before(match.away_team_id)
    avail.home_xg_history = len(home_xg)
    avail.away_xg_history = len(away_xg)
    avail.xg = (len(home_xg) >= minimum_xg_matches and len(away_xg) >= minimum_xg_matches)
    if not avail.xg:
        avail.notes.append(
            f"insufficient xG history (home={len(home_xg)}, away={len(away_xg)}, "
            f"minimum={minimum_xg_matches}); xG excluded, goals-only fallback")
    # Events/lineups recorded for transparency; v1 model math does not consume them.
    avail.events = False
    avail.lineups = False
    avail.notes.append("events/lineups collected but not consumed by v1 model math")
    return avail
