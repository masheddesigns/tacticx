"""Historical feature repository (Phase 2).

The ONLY path through which prediction models may read historical data.
Every query is bounded by a prediction cutoff and a temporal mode:

- STRICT_PREMATCH: finished matches with kickoff < cutoff, plus feature
  records carrying explicit timing (effective_at) at or before the cutoff.
  Records with unknown timing are EXCLUDED (counts reported).
- HISTORICAL_ESTIMATED: additionally allows feature records whose parent
  match kicked off before the cutoff. Labeled uncertain; never mixed
  silently with strict predictions.

Models must never query arbitrary database rows directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Match, MatchEvent, MatchStatistic
from app.db.models.enums import MatchStatus
from app.services.features.temporal import TemporalMode, as_naive_utc

FINISHED = MatchStatus.FINISHED.value


class HistoricalFeatureRepository:
    def __init__(self, db: Session, cutoff: datetime,
                 mode: TemporalMode = TemporalMode.STRICT_PREMATCH):
        naive = as_naive_utc(cutoff)
        if naive is None:
            raise ValueError("cutoff is required")
        self.db = db
        self.cutoff = naive
        self.mode = mode
        self.excluded_unknown_timing = 0

    # -- matches ------------------------------------------------------
    def finished_before(self, league_id: Optional[int] = None) -> List[Match]:
        """Finished, scored matches with kickoff strictly before cutoff,
        oldest first. The chronological backbone of every model."""
        q = self.db.query(Match).filter(
            Match.status == FINISHED,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
            Match.kickoff_at.is_not(None),
            Match.kickoff_at < self.cutoff,
        )
        if league_id is not None:
            q = q.filter(Match.league_id == league_id)
        return q.order_by(Match.kickoff_at.asc()).all()

    def team_matches_before(self, team_id: int, venue: Optional[str] = None) -> List[Match]:
        """Pre-cutoff finished matches for one team, optionally venue-filtered."""
        q = self.db.query(Match).filter(
            Match.status == FINISHED,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
            Match.kickoff_at.is_not(None),
            Match.kickoff_at < self.cutoff,
            ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)),
        )
        if venue == "home":
            q = q.filter(Match.home_team_id == team_id)
        elif venue == "away":
            q = q.filter(Match.away_team_id == team_id)
        return q.order_by(Match.kickoff_at.asc()).all()

    # -- league context ------------------------------------------------
    def league_goal_averages(self, league_id: int) -> Tuple[float, float, int]:
        """(avg_home_goals, avg_away_goals, n) from pre-cutoff matches only."""
        rows = self.finished_before(league_id=league_id)
        if not rows:
            return 0.0, 0.0, 0
        home = sum(m.home_score for m in rows if m.home_score is not None)
        away = sum(m.away_score for m in rows if m.away_score is not None)
        n = len(rows)
        return home / n, away / n, n

    def league_draw_rate(self, league_id: int) -> Tuple[float, int]:
        """Pre-cutoff empirical draw frequency (Elo draw prior)."""
        rows = self.finished_before(league_id=league_id)
        if not rows:
            return 0.25, 0
        draws = sum(1 for m in rows if m.home_score == m.away_score)
        return draws / len(rows), len(rows)

    # -- feature records ----------------------------------------------
    def _timing_ok(self, effective_at: Optional[datetime], match_id: Optional[int]) -> bool:
        eff = as_naive_utc(effective_at)
        if eff is not None:
            return eff <= self.cutoff
        # Unknown timing: excluded in strict mode (counted), allowed in
        # estimated mode only when anchored to a pre-cutoff parent match.
        self.excluded_unknown_timing += 1
        if self.mode == TemporalMode.STRICT_PREMATCH:
            return False
        if match_id is None:
            return False
        parent = self.db.get(Match, match_id)
        if parent is None or parent.kickoff_at is None:
            return False
        return as_naive_utc(parent.kickoff_at) < self.cutoff

    def match_stats(self, match_id: int) -> List[MatchStatistic]:
        """Eligible statistic rows for one past match. Never call this for
        the match being predicted — callers must exclude it structurally."""
        rows = self.db.query(MatchStatistic).filter_by(match_id=match_id).all()
        return [r for r in rows if self._timing_ok(r.effective_at, match_id)]

    def team_xg_before(self, team_id: int, venue: Optional[str] = None) -> List[float]:
        """Pre-cutoff expected-goals values for a team (source values only)."""
        values: List[float] = []
        for m in self.team_matches_before(team_id, venue=venue):
            side = "home" if m.home_team_id == team_id else "away"
            for r in self.match_stats(m.id):
                if r.team == side and r.stat_name in ("expected_goals", "xg"):
                    try:
                        values.append(float(str(r.stat_value).rstrip("%")))
                    except (TypeError, ValueError):
                        continue
        return values

    def match_events(self, match_id: int):
        rows = self.db.query(MatchEvent).filter_by(match_id=match_id).all()
        return [r for r in rows if self._timing_ok(r.effective_at, match_id)]
