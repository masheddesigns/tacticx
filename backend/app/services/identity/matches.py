"""Canonical match identity (Phase 1.6, extended 1.8).

Canonical identity = (league_id, home_team_id, away_team_id, kickoff_at).
Resolution order: (1) known source mapping, (2) canonical tuple within
±15 min, (3) same-date fallback for wall-clock skew across sources (unique
same-day pairing only; refused when known finished scores disagree).
Provider IDs stay source-specific, so different providers pointing at the
same fixture resolve to ONE canonical row instead of duplicates.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.provenance import MatchSourceMapping
from app.logging_config import get_logger

log = get_logger(__name__)

# Kickoff tolerance for cross-source clock skew. Deterministic, not fuzzy:
# same fixture reported minutes apart still resolves canonically.
KICKOFF_TOLERANCE = timedelta(minutes=15)


class MatchResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve(
        self,
        source: str,
        source_match_id: str = "",
        league_id: Optional[int] = None,
        home_team_id: Optional[int] = None,
        away_team_id: Optional[int] = None,
        kickoff_at: Optional[datetime] = None,
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
    ) -> Optional[int]:
        """Return canonical match_id or None when it cannot be established."""
        db, src = self.db, (source or "").lower()

        # 1. Known mapping for this source's native ID.
        if source_match_id:
            mapping = (
                db.query(MatchSourceMapping)
                .filter_by(source=src, source_match_id=str(source_match_id))
                .first()
            )
            if mapping and db.get(Match, mapping.match_id):
                return mapping.match_id

        # 2. Canonical tuple. All four components required — no guessing.
        if league_id and home_team_id and away_team_id and kickoff_at:
            q = db.query(Match).filter(
                Match.league_id == league_id,
                Match.home_team_id == home_team_id,
                Match.away_team_id == away_team_id,
            ).all()
            for m in q:
                if m.kickoff_at is None or kickoff_at is None:
                    continue
                try:
                    a, b = m.kickoff_at, kickoff_at
                    if a.tzinfo is None or b.tzinfo is None:
                        delta = abs((a.replace(tzinfo=None) - b.replace(tzinfo=None)))
                    else:
                        delta = abs(a - b)
                except Exception:  # noqa: BLE001 — incomparable timestamps: no match
                    continue
                if delta <= KICKOFF_TOLERANCE:
                    self._store_mapping(m.id, src, str(source_match_id or ""))
                    return m.id
            # 3. Same-date fallback: sources use unknown wall-time zones and
            # scheduled-vs-actual times, so timed kickoffs for the same
            # fixture can legitimately differ by hours. Merge only when
            # EXACTLY ONE fixture pairs these teams in this league that day
            # AND any known scores agree (differing finished scores prove
            # distinct fixtures). Double-headers and score conflicts stay
            # unresolved rather than guessed.
            def _score(m) -> Optional[tuple]:
                if m.home_score is None or m.away_score is None:
                    return None
                return (m.home_score, m.away_score)

            try:
                want_day = kickoff_at.date()
            except Exception:  # noqa: BLE001
                return None
            same_day = [m for m in q
                        if m.kickoff_at is not None and m.kickoff_at.date() == want_day]
            if len(same_day) == 1:
                other = same_day[0]
                have_scores = home_score is not None and away_score is not None
                if _score(other) is not None and have_scores and \
                        _score(other) != (home_score, away_score):
                    log.warning("same-day fallback refused by score mismatch src=%s sid=%s",
                                src, source_match_id)
                    return None
                log.info("match resolved by same-day fallback src=%s sid=%s match=%s",
                         src, source_match_id, other.id)
                self._store_mapping(other.id, src, str(source_match_id or ""))
                return other.id
        return None

    def ensure(
        self,
        source: str,
        source_match_id: str = "",
        league_id: Optional[int] = None,
        home_team_id: Optional[int] = None,
        away_team_id: Optional[int] = None,
        kickoff_at: Optional[datetime] = None,
        status: str = "SCHEDULED",
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
    ) -> tuple[int, bool]:
        """Resolve or create the canonical match. Returns (match_id, created)."""
        match_id = self.resolve(source, source_match_id, league_id, home_team_id,
                                away_team_id, kickoff_at, home_score, away_score)
        if match_id is not None:
            return match_id, False
        if not (league_id and home_team_id and away_team_id):
            raise ValueError("cannot create canonical match without league + both teams")
        m = Match(league_id=league_id, home_team_id=home_team_id, away_team_id=away_team_id,
                  kickoff_at=kickoff_at, status=status,
                  provider=(source or "").lower(), provider_match_id=str(source_match_id or ""))
        # Scores only when actually known (finished matches); never invented.
        if home_score is not None:
            m.home_score = home_score
        if away_score is not None:
            m.away_score = away_score
        self.db.add(m)
        self.db.flush()
        self._store_mapping(m.id, (source or "").lower(), str(source_match_id or ""))
        self.db.commit()
        return m.id, True

    def _store_mapping(self, match_id: int, source: str, source_match_id: str) -> None:
        if not source_match_id:
            return
        existing = (
            self.db.query(MatchSourceMapping)
            .filter_by(source=source, source_match_id=source_match_id)
            .first()
        )
        if existing:
            return
        self.db.add(MatchSourceMapping(match_id=match_id, source=source,
                                       source_match_id=source_match_id))
        self.db.commit()
