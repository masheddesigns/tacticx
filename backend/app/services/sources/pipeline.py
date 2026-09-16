"""Normalized-record ingestion pipeline (Phase 1.6).

Flow per record: identity resolution -> quality validation -> idempotent
persist -> provenance row -> conflict detection. Resumable by construction:
re-running any import only touches changed rows.

Prediction code must never touch sources directly — this pipeline (and the
registries) is the only path from raw sources to canonical entities.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.core import (
    League,
    Lineup,
    Match,
    MatchEvent,
    MatchStatistic,
    Standing,
)
from app.db.models.logs import DataSyncLog
from app.db.models.odds import Bookmaker, Market, OddsSelection, OddsSnapshot
from app.db.models.provenance import RawDataRecord
from app.logging_config import get_logger
from app.services import ingestion as legacy
from app.services.conflicts import check_score, check_stat_observation
from app.services.identity.matches import MatchResolver
from app.services.identity.players import PlayerIdentityResolver
from app.services.identity.teams import TeamIdentityResolver
from app.services.quality import (
    assess_temporal_quality,
    validate_event,
    validate_match,
    validate_minute,
    validate_odds,
    validate_stat,
    validate_xg,
)
from app.services.sources.normalized import (
    NormalizedEvent,
    NormalizedLineup,
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedOddsSnapshot,
    NormalizedStanding,
    Provenance,
)
from app.services.sources.stats_schema import normalize_stat_name

log = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStats:
    def __init__(self):
        self.received = 0
        self.inserted = 0
        self.updated = 0
        self.duplicates = 0
        self.quarantined = 0
        self.unresolved = 0
        self.errors: list[str] = []


def _log_run(db: Session, source: str, operation: str, stats: PipelineStats,
             league: str = "", duration: float = 0.0) -> None:
    db.add(DataSyncLog(
        provider=source, operation=operation, league=league,
        records_received=stats.received, records_inserted=stats.inserted,
        records_updated=stats.updated,
        records_skipped=stats.duplicates + stats.quarantined + stats.unresolved,
        duration_seconds=duration, errors="; ".join(stats.errors)[:1000],
    ))
    db.commit()


def _provenance_key(source: str, entity: str, record_id: str) -> tuple[str, str, str]:
    return (source or "").lower(), entity, record_id or ""


def track_raw(db: Session, source: str, entity_type: str, source_record_id: str,
              payload: str, parser_version: str, status: str, error_message: str = "",
              temporal_quality: str = "unknown", source_url: str = "") -> None:
    """Idempotent provenance upsert (same key -> one row, latest status)."""
    src, entity, rid = _provenance_key(source, entity_type, source_record_id)
    payload_hash = hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()
    now = _utcnow()
    row = (
        db.query(RawDataRecord)
        .filter_by(source=src, entity_type=entity, source_record_id=rid)
        .first()
    )
    if temporal_quality not in ("verified", "estimated", "unknown"):
        temporal_quality = "unknown"
    if row:
        row.payload_hash = payload_hash
        row.parser_version = parser_version or row.parser_version
        row.processed_at = now
        row.processing_status = status
        row.error_message = (error_message or "")[:1024]
        row.temporal_quality = temporal_quality
        if source_url:
            row.source_url = source_url[:512]
    else:
        db.add(RawDataRecord(
            source=src, entity_type=entity, source_record_id=rid, retrieved_at=now,
            payload_hash=payload_hash, parser_version=parser_version or "",
            processed_at=now, processing_status=status, error_message=(error_message or "")[:1024],
            temporal_quality=temporal_quality, source_url=(source_url or "")[:512],
        ))
    db.commit()


def _quality_of(prov: Provenance, event_time=None) -> str:
    """Provenance flag if set, else assessed from the timing chain."""
    if prov.temporal_quality in ("verified", "estimated"):
        return prov.temporal_quality
    return assess_temporal_quality(
        event_time=event_time, published_at=prov.published_at,
        effective_at=prov.effective_at, collected_at=prov.collected_at)


def _effective(prov: Provenance, fallback: Optional[datetime] = None) -> Optional[datetime]:
    return prov.effective_at or prov.published_at or fallback


class Pipeline:
    """Stateful ingestion context: resolvers + stats + league cache."""

    def __init__(self, db: Session, source: str, create_teams: bool = True,
                 source_url: str = ""):
        self.db = db
        self.source = (source or "").lower()
        self.create_teams = create_teams
        self.source_url = source_url or ""
        self.teams = TeamIdentityResolver(db)
        self.players = PlayerIdentityResolver(db)
        self.matches = MatchResolver(db)
        self.stats = PipelineStats()
        self._leagues: dict[str, League] = {}

    # -- leagues ---------------------------------------------------------
    def ensure_league(self, code: str, name: str = "", season: str = "",
                      country: Optional[str] = None) -> League:
        key = f"{code}::{season}"
        if key in self._leagues:
            return self._leagues[key]
        row = self.db.query(League).filter_by(code=code).first()
        if row:
            if season:
                row.season = season
            if name:
                row.name = name
            self.db.commit()
        else:
            row = League(code=code, name=name or code, season=season or "",
                         country=country, provider=self.source, provider_league_id="")
            self.db.add(row)
            self.db.commit()
        self._leagues[key] = row
        return row

    # -- teams -----------------------------------------------------------
    def resolve_team(self, name: str, native_id: str = "", league: str = "",
                     country: Optional[str] = None, parser_version: str = "") -> Optional[int]:
        team_id, method = self.teams.resolve(self.source, native_id, name,
                                             league=league, country=country)
        if team_id is not None:
            return team_id
        if self.create_teams and (name or "").strip():
            team_id, _ = self.teams.ensure(self.source, native_id, name,
                                            league=league, country=country)
            self.stats.inserted += 1
            return team_id
        self.stats.unresolved += 1
        track_raw(self.db, self.source, "team", (name or "").strip() or native_id,
                  (name or "").strip(), parser_version, "unresolved",
                  f"identity unresolved (method={method})",
                  assess_temporal_quality(), self.source_url)
        return None

    # -- matches ---------------------------------------------------------
    def ingest_match(self, m: NormalizedMatch, league_id: Optional[int] = None,
                     parser_version: str = "") -> Optional[int]:
        """Resolve/create canonical match. Returns match_id or None."""
        self.stats.received += 1
        rid = m.provenance.source_record_id or m.provider_match_id
        quality = validate_match(m.home_team, m.away_team, m.home_score, m.away_score,
                                 m.kickoff_at, m.league_code or "", m.season or "")
        if not quality.valid:
            self.stats.quarantined += 1
            track_raw(self.db, self.source, "match", rid, m.model_dump_json(),
                      parser_version or m.provenance.parser_version,
                      "quarantined", "; ".join(quality.messages()),
                      _quality_of(m.provenance, m.kickoff_at), self.source_url)
            return None

        if league_id is None and m.league_code:
            league_id = self.ensure_league(m.league_code, season=m.season).id
        home_id = self.resolve_team(m.home_team, m.home_team_id, league=m.league_code,
                                    parser_version=parser_version or m.provenance.parser_version)
        away_id = self.resolve_team(m.away_team, m.away_team_id, league=m.league_code,
                                    parser_version=parser_version or m.provenance.parser_version)
        if home_id is None or away_id is None or league_id is None:
            track_raw(self.db, self.source, "match", rid, m.model_dump_json(),
                      parser_version or m.provenance.parser_version,
                      "unresolved", "team or league identity unresolved",
                      _quality_of(m.provenance, m.kickoff_at), self.source_url)
            return None

        match_id, created = self.matches.ensure(
            self.source, rid, league_id, home_id, away_id, m.kickoff_at,
            status=m.status or "SCHEDULED",
            home_score=m.home_score, away_score=m.away_score)
        if created:
            self.stats.inserted += 1
        else:
            before = self.db.get(Match, match_id)
            had_score = before is not None and before.home_score is not None

        # Scores: conflict-aware, never blindly overwritten.
        if m.home_score is not None and m.away_score is not None:
            conflict = check_score(self.db, match_id, self.source, m.home_score, m.away_score)
            if conflict is not None:
                log.warning("score conflict recorded match=%s source=%s", match_id, self.source)
        if not created:
            after = self.db.get(Match, match_id)
            now_has = after is not None and after.home_score is not None
            self.stats.updated += (now_has and not had_score)
            self.stats.duplicates += (now_has == had_score)
        track_raw(self.db, self.source, "match", rid, m.model_dump_json(),
                  parser_version or m.provenance.parser_version, "processed",
                  "", _quality_of(m.provenance, m.kickoff_at), self.source_url)
        return match_id

    # -- statistics / events / lineups -----------------------------------
    def ingest_statistics(self, match_id: int, rows: list[NormalizedMatchStatistics],
                          parser_version: str = "") -> None:
        match = self.db.get(Match, match_id)
        event_time = match.kickoff_at if match else None
        for s in rows:
            self.stats.received += 1
            name = normalize_stat_name(s.stat_name)
            quality = validate_stat(name, s.stat_value)
            if name in ("expected_goals", "xg"):
                xg_quality = validate_xg(s.stat_value)
                if not xg_quality.valid:
                    quality = xg_quality
            rid = s.provenance.source_record_id or f"{match_id}:{s.team}:{name}:{s.period}"
            tq = _quality_of(s.provenance, event_time)
            if not quality.valid:
                self.stats.quarantined += 1
                track_raw(self.db, self.source, "statistic", rid, s.model_dump_json(),
                          parser_version or s.provenance.parser_version,
                          "quarantined", "; ".join(quality.messages()), tq, self.source_url)
                continue
            team = (s.team or "").lower()
            if team not in ("home", "away"):
                self.stats.quarantined += 1
                track_raw(self.db, self.source, "statistic", rid, s.model_dump_json(),
                          parser_version or s.provenance.parser_version,
                          "quarantined", f"team must be home|away, got {s.team!r}",
                          tq, self.source_url)
                continue
            period = s.period or "full"
            row = self.db.query(MatchStatistic).filter_by(
                match_id=match_id, team=team, stat_name=name, period=period).first()
            effective = _effective(s.provenance)
            if row is None:
                self.db.add(MatchStatistic(
                    match_id=match_id, team=team, stat_name=name,
                    stat_value=s.stat_value, period=period,
                    source=self.source, source_record_id=rid, effective_at=effective))
                self.stats.inserted += 1
            elif (row.source or "") == self.source:
                # Same-source refresh: update in place, never a conflict.
                if row.stat_value != s.stat_value:
                    row.stat_value = s.stat_value
                    if effective:
                        row.effective_at = effective
                    self.stats.updated += 1
                else:
                    self.stats.duplicates += 1
            elif row.stat_value == s.stat_value:
                self.stats.duplicates += 1  # cross-source agreement
            else:
                # Different source, different value: preserve both observations.
                check_stat_observation(self.db, match_id, team, name,
                                       s.stat_value, self.source)
                log.warning("stat divergence kept canonical match=%s stat=%s",
                            match_id, name)
                self.stats.duplicates += 1
            self.db.commit()
            track_raw(self.db, self.source, "statistic", rid, s.model_dump_json(),
                      parser_version or s.provenance.parser_version, "processed",
                      "", tq, self.source_url)

    def ingest_events(self, match_id: int, rows: list[NormalizedEvent],
                      parser_version: str = "") -> None:
        match = self.db.get(Match, match_id)
        event_time = match.kickoff_at if match else None
        for e in rows:
            self.stats.received += 1
            quality = validate_event(e.minute, e.event_type)
            minute_quality = validate_minute(e.minute, e.minute_added)
            if not minute_quality.valid:
                quality = minute_quality
            rid = e.provenance.source_record_id or f"{match_id}:{e.minute}:{e.event_type}:{e.player_name}"
            tq = _quality_of(e.provenance, event_time)
            if not quality.valid:
                self.stats.quarantined += 1
                track_raw(self.db, self.source, "event", rid, e.model_dump_json(),
                          parser_version or e.provenance.parser_version,
                          "quarantined", "; ".join(quality.messages()), tq, self.source_url)
                continue
            row = self.db.query(MatchEvent).filter_by(
                match_id=match_id, minute=e.minute, event_type=e.event_type,
                player_name=e.player_name or "", team=e.team or "").first()
            if row:
                self.stats.duplicates += 1
            else:
                self.db.add(MatchEvent(
                    match_id=match_id, minute=e.minute, minute_added=e.minute_added,
                    second=e.second, period=e.period or "", event_type=e.event_type,
                    detail=e.detail or "", team=e.team or "", player_name=e.player_name or "",
                    assist_player=e.assist_player or "", outcome=e.outcome or "",
                    provider=self.source, provider_event_id=rid,
                    source=self.source, source_record_id=rid,
                    effective_at=_effective(e.provenance)))
                self.stats.inserted += 1
            self.db.commit()
            track_raw(self.db, self.source, "event", rid, e.model_dump_json(),
                      parser_version or e.provenance.parser_version, "processed",
                      "", tq, self.source_url)

    def ingest_lineups(self, match_id: int, rows: list[NormalizedLineup],
                       parser_version: str = "") -> None:
        match = self.db.get(Match, match_id)
        event_time = match.kickoff_at if match else None
        home_id = match.home_team_id if match else None
        away_id = match.away_team_id if match else None
        for lu in rows:
            self.stats.received += 1
            rid = lu.provenance.source_record_id or f"{match_id}:{lu.team}:{lu.player_name}"
            tq = _quality_of(lu.provenance, event_time)
            if not (lu.player_name or "").strip():
                self.stats.quarantined += 1
                track_raw(self.db, self.source, "lineup", rid, lu.model_dump_json(),
                          parser_version or lu.provenance.parser_version,
                          "quarantined", "missing player name", tq, self.source_url)
                continue
            team_side = (lu.team or "").lower()
            scope_team = home_id if team_side == "home" else away_id if team_side == "away" else None
            player_id: Optional[int] = None
            try:
                # Resolves (or creates) the canonical player + mapping as a
                # side effect; the lineup row itself stays name-keyed.
                player_id, _ = self.players.ensure(
                    self.source, lu.provider_player_id or "", lu.player_name,
                    team_id=scope_team, position=lu.position)
                assert player_id is not None
            except ValueError as exc:
                self.stats.unresolved += 1
                track_raw(self.db, self.source, "lineup", rid, lu.model_dump_json(),
                          parser_version or lu.provenance.parser_version,
                          "unresolved", str(exc)[:300], tq, self.source_url)
                continue
            row = self.db.query(Lineup).filter_by(
                match_id=match_id, team=lu.team or "", player_name=lu.player_name).first()
            if row:
                self.stats.duplicates += 1
            else:
                self.db.add(Lineup(
                    match_id=match_id, team=lu.team or "", player_name=lu.player_name,
                    position=lu.position, is_starting=lu.is_starting,
                    formation=lu.formation or "", is_captain=1 if lu.is_captain else 0,
                    player_provider_id=lu.provider_player_id or "",
                    jersey_number=lu.jersey_number,
                    source=self.source, source_record_id=rid,
                    effective_at=_effective(lu.provenance)))
                self.stats.inserted += 1
            self.db.commit()
            track_raw(self.db, self.source, "lineup", rid, lu.model_dump_json(),
                      parser_version or lu.provenance.parser_version, "processed",
                      "", tq, self.source_url)

    # -- standings -------------------------------------------------------
    def ingest_standings(self, league_code: str, season: str, rows: list[NormalizedStanding],
                         parser_version: str = "") -> None:
        league = self.ensure_league(league_code, season=season)
        for s in rows:
            self.stats.received += 1
            team_id = self.resolve_team(s.team_name, s.team_provider_id, league=league_code)
            rid = s.provenance.source_record_id or f"{league_code}:{season}:{s.team_name}"
            tq = _quality_of(s.provenance)
            if team_id is None:
                track_raw(self.db, self.source, "standing", rid, s.model_dump_json(),
                          parser_version or s.provenance.parser_version,
                          "unresolved", "team identity unresolved", tq, self.source_url)
                continue
            row = self.db.query(Standing).filter_by(
                league_id=league.id, team_id=team_id, season=season).first()
            effective = _effective(s.provenance)
            if row:
                row.position, row.played = s.position, s.played
                row.won, row.drawn, row.lost, row.points = s.won, s.drawn, s.lost, s.points
                if effective:
                    row.effective_at = effective
                self.stats.updated += 1
            else:
                self.db.add(Standing(
                    league_id=league.id, team_id=team_id, season=season,
                    position=s.position, played=s.played, won=s.won,
                    drawn=s.drawn, lost=s.lost, points=s.points,
                    source=self.source, source_record_id=rid, effective_at=effective))
                self.stats.inserted += 1
            self.db.commit()
            track_raw(self.db, self.source, "standing", rid, s.model_dump_json(),
                      parser_version or s.provenance.parser_version, "processed",
                      "", _quality_of(s.provenance), self.source_url)

    # -- odds (append-only) ----------------------------------------------
    def ingest_odds(self, snap: NormalizedOddsSnapshot, parser_version: str = "") -> Optional[int]:
        """Resolve the canonical match, then append the snapshot. Never overwrites."""
        self.stats.received += 1
        if not snap.market:
            self.stats.quarantined += 1
            return None
        if not snap.selections:
            # No prices actually provided — never store empty snapshots.
            self.stats.quarantined += 1
            return None
        for sel in snap.selections:
            quality = validate_odds(sel.price, sel.selection, snap.market)
            if not quality.valid:
                self.stats.quarantined += 1
                return None
        league = self.db.query(League).filter_by(code=snap.league_code).first() if snap.league_code else None
        home_id = self.resolve_team(snap.home_team, league=snap.league_code) if snap.home_team else None
        away_id = self.resolve_team(snap.away_team, league=snap.league_code) if snap.away_team else None
        if home_id is None or away_id is None:
            track_raw(self.db, self.source, "odds",
                      snap.source_event_id or "unknown", snap.model_dump_json(),
                      parser_version, "unresolved", "match teams unresolved",
                      _quality_of(snap.provenance, snap.kickoff_at), self.source_url)
            return None
        match_id = self.matches.resolve(
            self.source, snap.source_event_id,
            league.id if league else None, home_id, away_id, snap.kickoff_at)
        if match_id is None:
            track_raw(self.db, self.source, "odds",
                      snap.source_event_id or "unknown", snap.model_dump_json(),
                      parser_version, "unresolved", "canonical match unresolved",
                      _quality_of(snap.provenance, snap.kickoff_at), self.source_url)
            return None
        ts = snap.timestamp or snap.collected_at or _utcnow()
        bm = self.db.query(Bookmaker).filter_by(
            provider=self.source, provider_bookmaker_id=snap.selections[0].bookmaker_id if snap.selections else "").first()
        bookmaker_name = snap.selections[0].bookmaker if snap.selections else ""
        bookmaker_pid = snap.selections[0].bookmaker_id if snap.selections else ""
        if not bm:
            bm = Bookmaker(name=bookmaker_name or bookmaker_pid, provider=self.source,
                           provider_bookmaker_id=bookmaker_pid or bookmaker_name)
            self.db.add(bm)
            self.db.flush()
        if not self.db.query(Market).filter_by(market_key=snap.market).first():
            self.db.add(Market(market_key=snap.market))
            self.db.flush()
        shot = OddsSnapshot(match_id=match_id, bookmaker_id=bm.id, market_type=snap.market,
                            timestamp=ts, source=self.source, is_live=snap.is_live,
                            source_event_id=snap.source_event_id or None,
                            source_market_id=snap.source_market_id or None)
        self.db.add(shot)
        self.db.flush()
        for sel in snap.selections:
            dh = legacy.dedup_hash(match_id, bookmaker_pid, snap.market,
                                   sel.selection, sel.price, ts.isoformat())
            if self.db.query(OddsSelection).filter_by(dedup_hash=dh).first():
                self.stats.duplicates += 1
                continue
            self.db.add(OddsSelection(snapshot_id=shot.id, selection=sel.selection,
                                      odds=sel.price, point=sel.point, dedup_hash=dh))
            self.stats.inserted += 1
        self.db.commit()
        track_raw(self.db, self.source, "odds",
                  f"{snap.source_event_id}:{snap.market}:{ts.isoformat()}",
                  snap.model_dump_json(), parser_version, "processed",
                  "", _quality_of(snap.provenance, snap.kickoff_at), self.source_url)
        return shot.id

    def finish(self, operation: str, league: str = "") -> PipelineStats:
        _log_run(self.db, self.source, operation, self.stats, league=league, duration=0.0)
        return self.stats
