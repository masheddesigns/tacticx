"""Cutoff-safe player/event/lineup repository (Phase 9).

Temporal heart of the layer. Every accessor answers: "could this value have
been known immediately before the target match kickoff?"

- Strict mode: only rows with explicit effective_at <= cutoff contribute.
  Rows with unknown timing are EXCLUDED (counted, never assumed).
- Estimated mode: additionally allows rows parent-anchored to a finished
  match with kickoff strictly before cutoff, labeled estimated.
- The target match is structurally excluded everywhere: it contributes zero
  historical information, even when its rows predate cutoff by timestamp.

No cache in this module bypasses cutoff checks (callers key on
match+cutoff+version+mode if they memoize at all).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Lineup, Match, MatchEvent
from app.services.features.temporal import TemporalMode, as_naive_utc

STRICT = TemporalMode.STRICT_PREMATCH


class PlayerEventRepository:
    def __init__(self, db: Session, cutoff: datetime,
                 mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                 target_match_id: Optional[int] = None):
        naive = as_naive_utc(cutoff)
        if naive is None:
            raise ValueError("cutoff is required")
        self.db = db
        self.cutoff = naive
        self.mode = mode
        self.target_match_id = target_match_id
        self.excluded_unknown_timing = 0
        self.excluded_target = 0

    # -- timing ----------------------------------------------------------
    def _eligible(self, effective_at: Optional[datetime],
                  parent_kickoff: Optional[datetime]) -> Tuple[bool, str]:
        """(eligible, quality). Strict needs explicit timing; estimated
        accepts parent-anchored rows."""
        eff = as_naive_utc(effective_at)
        if eff is not None:
            return (eff <= self.cutoff,
                    "verified" if eff <= self.cutoff else "future")
        self.excluded_unknown_timing += 1
        if self.mode == STRICT:
            return False, "unknown"
        parent = as_naive_utc(parent_kickoff)
        if parent is not None and parent < self.cutoff:
            return True, "estimated"
        return False, "unknown"

    def _parent_kickoff(self, match_id: int) -> Optional[datetime]:
        match = self.db.get(Match, match_id)
        return match.kickoff_at if match else None

    # -- lineups ----------------------------------------------------------
    def team_lineups_before(self, team_id: int) -> List[Tuple[Match, Lineup, str]]:
        """Eligible (match, lineup, quality) for one team, oldest first.
        Target match structurally excluded. Team attribution goes through the
        match side (lineup.team_id is NULL throughout this dataset; the
        side string 'home'/'away' plus the parent match is the evidence)."""
        matches = (self.db.query(Match)
                   .filter(((Match.home_team_id == team_id)
                            | (Match.away_team_id == team_id)))
                   .order_by(Match.kickoff_at.asc(), Match.id.asc()).all())
        out = []
        for match in matches:
            if self.target_match_id is not None and match.id == self.target_match_id:
                self.excluded_target += 1
                continue
            if match.kickoff_at is None or as_naive_utc(match.kickoff_at) >= self.cutoff:
                continue
            if match.status != "FINISHED":
                continue
            side = "home" if match.home_team_id == team_id else "away"
            for lineup in self.db.query(Lineup).filter_by(
                    match_id=match.id, team=side).all():
                eligible, quality = self._eligible(lineup.effective_at,
                                                   match.kickoff_at)
                if eligible:
                    out.append((match, lineup, quality))
        return out

    # -- events -----------------------------------------------------------
    def team_events_before(self, team_id: int) -> List[Tuple[Match, MatchEvent, str]]:
        """Eligible (match, event, quality) involving one team, oldest first."""
        matches = (self.db.query(Match)
                   .filter(((Match.home_team_id == team_id)
                            | (Match.away_team_id == team_id)))
                   .order_by(Match.kickoff_at.asc(), Match.id.asc()).all())
        out = []
        for match in matches:
            if self.target_match_id is not None and match.id == self.target_match_id:
                self.excluded_target += 1
                continue
            if match.kickoff_at is None or as_naive_utc(match.kickoff_at) >= self.cutoff:
                continue
            if match.status != "FINISHED":
                continue
            for event in self.db.query(MatchEvent).filter_by(match_id=match.id).all():
                eligible, quality = self._eligible(event.effective_at, match.kickoff_at)
                if eligible:
                    out.append((match, event, quality))
        return out

    # -- availability evidence ---------------------------------------------
    def evidence_counts(self, team_id: int) -> Dict:
        lineups = self.team_lineups_before(team_id)
        events = self.team_events_before(team_id)
        strict_lineups = sum(1 for _, _, q in lineups if q == "verified")
        strict_events = sum(1 for _, _, q in events if q == "verified")
        return {
            "lineup_rows": len(lineups),
            "lineup_rows_strict": strict_lineups,
            "event_rows": len(events),
            "event_rows_strict": strict_events,
            "matches_with_lineups": len({m.id for m, _, _ in lineups}),
            "matches_with_events": len({m.id for m, _, _ in events}),
            "excluded_unknown_timing": self.excluded_unknown_timing,
            "excluded_target": self.excluded_target,
        }
