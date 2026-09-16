"""StatsBomb Open Data adapter (Phase 1.7).

Public research dataset (github.com/statsbomb/open-data — now hudl/open-data),
free for public research use with attribution (see README terms). Plain HTTPS
JSON over the polite fetcher: robots pre-check, delays, ceilings, caching,
request logging. No authentication, no protections — none attempted.

Provides what bulk CSVs cannot: per-match events (with shot xG), lineups with
native player IDs, and full seasons for La Liga (2004–2021), Bundesliga
(2015/16, 2023/24), Serie A (2015/16), Ligue 1 (2015/16, 2021–23), EPL
(2003/04, 2015/16) and UCL (many seasons).

Conventions (documented, deterministic):
- xG = sum of shot.statsbomb_xg per team, penalties included.
- shots_on_target = outcomes Goal + Saved (woodwork counts as off target).
- Events stored: goals, own goals, penalties, missed penalties, cards,
  substitutions. Passes/carries/etc. are out of scope for the model.
- Team sides resolved via team IDs from the season matches file.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger
from app.services.scraping.datasets import fetch_cached
from app.services.scraping.framework import utcnow
from app.services.scraping.polite import PoliteFetcher, SourceDisallowed
from app.services.sources.base import (
    FootballDataSource,
    HistoricalDataSource,
    SourceCapabilities,
)
from app.services.sources.normalized import (
    NormalizedEvent,
    NormalizedLineup,
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedTeam,
    Provenance,
)

log = get_logger(__name__)

PARSER = "statsbomb_parser_v1"

# Our league codes -> (StatsBomb competition name, competition id).
COMPETITIONS = {
    "EPL": ("Premier League", 2),
    "LA_LIGA": ("La Liga", 11),
    "SERIE_A": ("Serie A", 12),
    "BUNDESLIGA": ("1. Bundesliga", 9),
    "LIGUE_1": ("Ligue 1", 7),
    "UCL": ("Champions League", 16),
}

ON_TARGET = {"Goal", "Saved"}


def sb_season_name(season: str) -> str:
    """Our '2023' (2023/24) -> StatsBomb '2023/2024'."""
    year = int(str(season).strip()[:4])
    if not 1900 <= year <= 2100:
        raise ValueError(f"implausible season: {season!r}")
    return f"{year}/{year + 1}"


def season_date_range(season: str) -> tuple[date, date]:
    """Our season label -> inclusive kickoff window (Aug 1 .. Jul 31)."""
    year = int(str(season).strip()[:4])
    if not 1900 <= year <= 2100:
        raise ValueError(f"implausible season: {season!r}")
    return date(year, 8, 1), date(year + 1, 7, 31)


def _prov(record_id: str) -> Provenance:
    # Event dates known, publication chain unknown -> estimated (never verified).
    return Provenance(source="statsbomb", source_record_id=str(record_id),
                      collected_at=utcnow(), parser_version=PARSER,
                      temporal_quality="estimated")


def _parse_kickoff(match_date: str, kick_off: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(f"{match_date}T{kick_off}")
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(str(match_date))
        except (ValueError, TypeError):
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class StatsBombSource(HistoricalDataSource, FootballDataSource):
    source_name = "statsbomb"
    capabilities = SourceCapabilities(fixtures=True, match_detail=True,
                                      historical_bulk=True)

    def __init__(self, db=None, db_session_factory=None, client=None, **kwargs):
        self.db = db
        self.base_url = get_settings().STATSBOMB_BASE_URL.rstrip("/")
        self.fetcher = PoliteFetcher(source=self.source_name,
                                     db_session_factory=db_session_factory, client=client)
        self._matches_cache: dict[tuple[int, int], list[dict]] = {}
        self._current_events: list[dict] = []

    def check(self) -> dict:
        return {"source": self.source_name,
                "base_url": self.base_url,
                "competitions": sorted(COMPETITIONS),
                "role": "primary events/xG/lineups history (attribution required)"}

    def _comp(self, league_code: str) -> tuple[str, int]:
        try:
            return COMPETITIONS[(league_code or "").upper()]
        except KeyError:
            raise ValueError(
                f"statsbomb has no mapping for league {league_code!r} "
                f"(covered: {sorted(COMPETITIONS)})") from None

    async def _get_json(self, path: str, cache_name: str, refresh: bool = False):
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            text, _ = await fetch_cached(self.fetcher, url, self.source_name,
                                         cache_name, refresh=refresh)
        except SourceDisallowed:
            raise
        except Exception as exc:  # noqa: BLE001
            from app.services.http_client import ProviderHTTPError
            raise ProviderHTTPError(f"statsbomb fetch failed: {exc}") from exc
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ValueError(f"cannot parse statsbomb JSON {path}: {exc}") from exc

    async def _season_id(self, comp_name: str, comp_id: int, season: str,
                         refresh: bool = False) -> int:
        data = await self._get_json("competitions.json", "competitions.json",
                                    refresh=refresh)
        want = sb_season_name(season)
        for row in data if isinstance(data, list) else []:
            if not isinstance(row, dict):
                continue
            if (row.get("competition_name") == comp_name
                    and row.get("competition_id") == comp_id
                    and row.get("season_name") == want):
                return int(row["season_id"])
        raise ValueError(f"statsbomb has no {comp_name} {want} "
                         f"(see competitions.json for coverage)")

    async def fetch_season_matches(self, league_code: str, season: str,
                                   refresh: bool = False) -> list[dict]:
        comp_name, comp_id = self._comp(league_code)
        season_id = await self._season_id(comp_name, comp_id, season, refresh=refresh)
        key = (comp_id, season_id)
        if key not in self._matches_cache or refresh:
            data = await self._get_json(f"matches/{comp_id}/{season_id}.json",
                                        f"matches_{comp_id}_{season_id}.json", refresh=refresh)
            rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
            if not rows:
                raise ValueError(f"statsbomb matches empty: {comp_name} {season}")
            self._matches_cache[key] = rows
        return self._matches_cache[key]

    async def fetch_match_events(self, match_id: str, refresh: bool = False) -> list[dict]:
        data = await self._get_json(f"events/{match_id}.json", f"events_{match_id}.json",
                                    refresh=refresh)
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    async def fetch_match_lineups(self, match_id: str, refresh: bool = False) -> list[dict]:
        data = await self._get_json(f"lineups/{match_id}.json", f"lineups_{match_id}.json",
                                    refresh=refresh)
        return [t for t in data if isinstance(t, dict)] if isinstance(data, list) else []

    # -- shared converters -------------------------------------------------
    @staticmethod
    def _sides(match: dict) -> tuple[dict, dict]:
        return match.get("home_team", {}) or {}, match.get("away_team", {}) or {}

    def convert_match(self, m: dict, league_code: str, season: str,
                      sid: str = "") -> NormalizedMatch:
        home, away = self._sides(m)
        mid = str(m.get("match_id", ""))
        return NormalizedMatch(
            league_code=league_code, season=season,
            home_team=str(home.get("home_team_name", "")),
            home_team_id=str(home.get("home_team_id", "")),
            away_team=str(away.get("away_team_name", "")),
            away_team_id=str(away.get("away_team_id", "")),
            kickoff_at=_parse_kickoff(str(m.get("match_date", "")), str(m.get("kick_off", ""))),
            status="FINISHED" if m.get("match_status") == "available" else "SCHEDULED",
            home_score=m.get("home_score"), away_score=m.get("away_score"),
            provider_match_id=mid,
            provenance=_prov(sid or mid))

    def convert_events(self, match: dict) -> tuple[list[NormalizedEvent], list[NormalizedMatchStatistics]]:
        """Events worth storing + per-team aggregates (xG, shots).

        xG sums ONLY shots carrying statsbomb_xg; shots without a value do not
        contribute and are counted in a transparent `shots_missing_xg` stat
        (missing is reported, never silently zero-filled into the total as if
        measured).
        """
        home, away = self._sides(match)
        home_id, away_id = home.get("home_team_id"), away.get("away_team_id")
        by_id = {home_id: "home", away_id: "away"}
        match_id = str(match.get("match_id", ""))
        events: list[NormalizedEvent] = []
        xg = {"home": 0.0, "away": 0.0}
        shots = {"home": 0, "away": 0}
        on_target = {"home": 0, "away": 0}
        missing_xg = {"home": 0, "away": 0}

        def _second(e: dict) -> Optional[int]:
            sec = e.get("second")
            return sec if isinstance(sec, int) and 0 <= sec <= 59 else None

        def _period(e: dict) -> str:
            return {1: "1H", 2: "2H"}.get(e.get("period"), "")

        for e in self._current_events:
            if not isinstance(e, dict):
                continue
            team = (e.get("team") or {})
            side = by_id.get(team.get("id"))
            if side is None:
                continue
            etype = (e.get("type") or {}).get("name", "")
            minute = e.get("minute") if isinstance(e.get("minute"), int) else None
            player = e.get("player") or {}
            player_name = str(player.get("name", "") or "")
            player_id = str(player.get("id", "") or "")
            rid = f"{match_id}:{e.get('id', '')}"
            second, period = _second(e), _period(e)
            if etype == "Shot":
                shot = e.get("shot") or {}
                outcome = (shot.get("outcome") or {}).get("name", "")
                stype = (shot.get("type") or {}).get("name", "")
                raw_xg = shot.get("statsbomb_xg")
                try:
                    value = float(raw_xg) if raw_xg is not None else None
                except (TypeError, ValueError):
                    value = None
                if value is None:
                    missing_xg[side] += 1
                else:
                    xg[side] += value
                shots[side] += 1
                if outcome in ON_TARGET:
                    on_target[side] += 1
                if outcome == "Goal":
                    kind = "penalty" if stype == "Penalty" else "goal"
                    events.append(NormalizedEvent(
                        minute=minute, second=second, period=period, event_type=kind,
                        detail=f"{stype} Goal" if stype else "Goal",
                        team=side, player_name=player_name, provider_player_id=player_id,
                        outcome=outcome,
                        provenance=_prov(rid)))
                elif stype == "Penalty":
                    events.append(NormalizedEvent(
                        minute=minute, second=second, period=period,
                        event_type="missed_penalty",
                        detail=f"Penalty {outcome}", team=side,
                        player_name=player_name, provider_player_id=player_id,
                        outcome=outcome,
                        provenance=_prov(rid)))
            elif etype == "Own Goal For":
                events.append(NormalizedEvent(
                    minute=minute, second=second, period=period,
                    event_type="own_goal", detail="Own Goal",
                    team=side, player_name=player_name, provider_player_id=player_id,
                    provenance=_prov(rid)))
            elif etype in ("Foul Committed", "Bad Behaviour"):
                card = ((e.get("foul_committed") or {}).get("card")
                        or (e.get("bad_behaviour") or {}).get("card") or {})
                card_name = str(card.get("name", "") or "")
                if "Second Yellow" in card_name:
                    kind = "second_yellow"
                elif "Red" in card_name:
                    kind = "red_card"
                elif "Yellow" in card_name:
                    kind = "yellow_card"
                else:
                    continue  # foul without a card: not stored as an event
                events.append(NormalizedEvent(
                    minute=minute, second=second, period=period,
                    event_type=kind, detail=card_name,
                    team=side, player_name=player_name, provider_player_id=player_id,
                    outcome=card_name,
                    provenance=_prov(rid)))
            elif etype == "Substitution":
                sub = e.get("substitution") or {}
                replacement = sub.get("replacement") or {}
                events.append(NormalizedEvent(
                    minute=minute, second=second, period=period,
                    event_type="substitution",
                    detail=f"off: {player_name}; on: {replacement.get('name', '')}",
                    team=side, player_name=player_name, provider_player_id=player_id,
                    provenance=_prov(rid)))
        stats: list[NormalizedMatchStatistics] = []
        for side in ("home", "away"):
            stats.extend([
                NormalizedMatchStatistics(
                    team=side, stat_name="expected_goals",
                    stat_value=f"{xg[side]:.3f}", period="full",
                    provenance=_prov(f"{match_id}:{side}:expected_goals")),
                NormalizedMatchStatistics(
                    team=side, stat_name="shots_total",
                    stat_value=str(shots[side]), period="full",
                    provenance=_prov(f"{match_id}:{side}:shots_total")),
                NormalizedMatchStatistics(
                    team=side, stat_name="shots_on_target",
                    stat_value=str(on_target[side]), period="full",
                    provenance=_prov(f"{match_id}:{side}:shots_on_target")),
            ])
            if missing_xg[side]:
                stats.append(NormalizedMatchStatistics(
                    team=side, stat_name="shots_missing_xg",
                    stat_value=str(missing_xg[side]), period="full",
                    provenance=_prov(f"{match_id}:{side}:shots_missing_xg")))
        return events, stats

    def convert_lineups(self, match: dict, lineup_teams: list[dict],
                        events: list[dict]) -> list[NormalizedLineup]:
        """Starters from Starting-XI tactics; everyone else is a substitute.
        is_starting=0 covers bench + used subs (not distinguished — documented)."""
        starters: dict[str, dict] = {}  # player_id -> {position, formation}
        for e in events:
            if not isinstance(e, dict) or (e.get("type") or {}).get("name") != "Starting XI":
                continue
            tactics = e.get("tactics") or {}
            formation = str(tactics.get("formation", "") or "")
            for slot in tactics.get("lineup") or []:
                if not isinstance(slot, dict):
                    continue
                pl = slot.get("player") or {}
                pid = str(pl.get("id", "") or "")
                if pid:
                    starters[pid] = {"position": str((slot.get("position") or {}).get("name", "") or ""),
                                     "formation": formation}
        out: list[NormalizedLineup] = []
        home, away = self._sides(match)
        side_by_id = {home.get("home_team_id"): "home", away.get("away_team_id"): "away"}
        for team in lineup_teams:
            side = side_by_id.get(team.get("team_id"), "")
            for pl in team.get("lineup") or []:
                if not isinstance(pl, dict):
                    continue
                pid = str(pl.get("player_id", "") or "")
                info = starters.get(pid, {})
                jersey = pl.get("jersey_number")
                out.append(NormalizedLineup(
                    team=side, player_name=str(pl.get("player_name", "") or ""),
                    position=info.get("position") or None,
                    is_starting=1 if pid in starters else 0,
                    formation=info.get("formation", ""),
                    # Captaincy is not published in the lineups file: stays 0.
                    is_captain=0,
                    jersey_number=jersey if isinstance(jersey, int) else None,
                    provider_player_id=pid,
                    provenance=_prov(f"{match.get('match_id', '')}:{pid}")))
        return out

    @staticmethod
    def formation_stats(match: dict, events: list[dict]) -> list[NormalizedMatchStatistics]:
        """Source formations as per-team stat rows (with provenance).

        Stored facts, not inference: only Starting-XI tactics formations.
        """
        home, away = StatsBombSource._sides(match)
        side_by_id = {home.get("home_team_id"): "home", away.get("away_team_id"): "away"}
        formations: dict[str, str] = {}
        for e in events:
            if not isinstance(e, dict) or (e.get("type") or {}).get("name") != "Starting XI":
                continue
            team = e.get("team") or {}
            side = side_by_id.get(team.get("id"))
            formation = str((e.get("tactics") or {}).get("formation", "") or "")
            if side and formation and side not in formations:
                formations[side] = formation
        return [NormalizedMatchStatistics(
            team=side, stat_name="formation", stat_value=value, period="full",
            provenance=_prov(f"{match.get('match_id', '')}:{side}:formation"))
            for side, value in formations.items()]

    # -- HistoricalDataSource --------------------------------------------
    def import_history(self, league_code: str, season: str,
                       date_from: Optional[str] = None, date_to: Optional[str] = None,
                       **kwargs) -> dict:
        import asyncio

        if self.db is None:
            raise ValueError("StatsBombSource needs db (pass db=session)")
        from app.services.sources.historical.csv_source import parse_date
        from app.services.sources.pipeline import Pipeline

        max_detail = int(kwargs.get("max_detail_matches", 0) or 0)
        resume = bool(kwargs.get("resume", True))
        # Details (lineups + events/xG) are opt-in and bounded: a full season
        # would be hundreds of downloads, so --with-details/--max-matches
        # controls it. Resumable per match via raw records (disable with
        # resume=False to reprocess).
        comp_name, comp_id = self._comp(league_code)
        season_id = asyncio.run(self._season_id(comp_name, comp_id, season))
        matches = asyncio.run(self.fetch_season_matches(league_code, season))
        pipe = Pipeline(db=self.db, source=self.source_name,
                        source_url=f"{self.base_url}/matches",
                        create_teams=kwargs.get("create_teams", True))
        league = pipe.ensure_league(league_code, season=season)
        report = {"records_read": 0, "valid": 0, "filtered": 0, "inserted": 0,
                  "updated": 0, "duplicates_skipped": 0, "invalid": 0, "errors": [],
                  "detail_matches": 0}
        df = parse_date(date_from).date() if date_from else None
        dt = parse_date(date_to).date() if date_to else None
        detail_done = 0
        for m in matches:
            report["records_read"] += 1
            try:
                nm = self.convert_match(
                    m, league_code, season,
                    self.sid_for(comp_id, season_id, str(m.get("match_id", ""))))
            except Exception as exc:  # noqa: BLE001
                report["invalid"] += 1
                report["errors"].append(f"match {m.get('match_id')}: {exc}"[:200])
                continue
            if nm.kickoff_at and ((df and nm.kickoff_at.date() < df)
                                  or (dt and nm.kickoff_at.date() > dt)):
                report["filtered"] += 1
                continue
            report["valid"] += 1
            try:
                match_id = pipe.ingest_match(nm, league_id=league.id, parser_version=PARSER)
                if match_id is None:
                    continue
                if max_detail and detail_done < max_detail:
                    mid = str(m.get("match_id", ""))
                    from app.db.models.core import Lineup as _LU
                    from app.db.models.core import MatchEvent as _ME
                    from app.db.models.provenance import RawDataRecord as _RR
                    from app.services.http_client import ProviderHTTPError as _PHE
                    from app.services.sources.pipeline import track_raw as _track

                    # Resume: known-404 files are skipped without re-download.
                    known = self.db.query(_RR).filter_by(
                        source=self.source_name, entity_type="match_details",
                        source_record_id=mid).first()
                    if resume and known is not None and known.processing_status == "failed" \
                            and "404" in (known.error_message or ""):
                        detail_done += 1
                        continue
                    try:
                        # Resumable: matches that already have details are skipped
                        # (unless resume=False forces reprocessing).
                        if not resume or self.db.query(_LU).filter_by(
                                match_id=match_id).first() is None:
                            lineups = asyncio.run(self.fetch_match_lineups(mid))
                            events_for_lineups = asyncio.run(self.fetch_match_events(mid))
                            pipe.ingest_lineups(
                                match_id, self.convert_lineups(m, lineups, events_for_lineups),
                                parser_version=PARSER)
                        if not resume or self.db.query(_ME).filter_by(
                                match_id=match_id).first() is None:
                            self._current_events = asyncio.run(self.fetch_match_events(mid))
                            try:
                                events, stats = self.convert_events(m)
                                pipe.ingest_events(match_id, events, parser_version=PARSER)
                                pipe.ingest_statistics(match_id, stats, parser_version=PARSER)
                                pipe.ingest_statistics(
                                    match_id,
                                    self.formation_stats(m, self._current_events),
                                    parser_version=PARSER)
                            finally:
                                self._current_events = []
                        _track(self.db, self.source_name, "match_details", mid,
                               mid, PARSER, "processed", "", "estimated",
                               f"{self.base_url}/events/{mid}.json")
                    except _PHE as exc:
                        _track(self.db, self.source_name, "match_details", mid,
                               mid, PARSER, "failed", str(exc)[:300], "unknown",
                               f"{self.base_url}/events/{mid}.json")
                        raise
                    detail_done += 1
                    report["detail_matches"] += 1
            except Exception as exc:  # noqa: BLE001 — one bad match never kills the import
                report["errors"].append(f"match {m.get('match_id')}: {exc}"[:200])
        stats = pipe.stats
        report["inserted"] = stats.inserted
        report["updated"] = stats.updated
        report["duplicates_skipped"] = stats.duplicates
        report["invalid"] += stats.quarantined + stats.unresolved
        pipe.finish("import_history", league=league_code)
        return report

    # -- FootballDataSource surface ---------------------------------------
    async def get_leagues(self) -> list[dict]:
        return [{"code": code, "name": name, "country": "", "provider_league_id": str(cid),
                 "season": ""}
                for code, (name, cid) in COMPETITIONS.items()]

    async def get_teams(self, league_code: str, season: str) -> list[NormalizedTeam]:
        try:
            matches = await self.fetch_season_matches(league_code, season)
        except Exception as exc:  # noqa: BLE001
            log.warning("statsbomb teams unavailable league=%s season=%s err=%s",
                        league_code, season, exc)
            return []
        seen: dict[str, NormalizedTeam] = {}
        for m in matches:
            home, away = self._sides(m)
            for key, name in (("home_team_id", "home_team_name"), ("away_team_id", "away_team_name")):
                tname = str(home.get(name, "") if "home" in key else away.get(name, ""))
                tid = str(home.get(key, "") if "home" in key else away.get(key, ""))
                if tname and tname not in seen:
                    seen[tname] = NormalizedTeam(
                        name=tname, league_code=league_code, provider_team_id=tid,
                        provenance=_prov(f"team:{tid}"))
        return list(seen.values())

    async def get_fixtures(self, league_code: str, season: str,
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> list[NormalizedMatch]:
        from app.services.sources.historical.csv_source import parse_date

        comp_name, comp_id = self._comp(league_code)
        season_id = await self._season_id(comp_name, comp_id, season)
        matches = await self.fetch_season_matches(league_code, season)
        df = parse_date(date_from).date() if date_from else None
        dt = parse_date(date_to).date() if date_to else None
        out = []
        for m in matches:
            nm = self.convert_match(m, league_code, season,
                                    self.sid_for(comp_id, season_id, str(m.get("match_id", ""))))
            if nm.kickoff_at and ((df and nm.kickoff_at.date() < df)
                                  or (dt and nm.kickoff_at.date() > dt)):
                continue
            out.append(nm)
        return out

    def _locate(self, source_match_id: str) -> tuple[dict, str]:
        """sid 'comp:season_sb:match' -> (match dict, match_id). Cached season file."""
        try:
            comp_id, season_id, match_id = str(source_match_id).split(":")
        except ValueError:
            raise ValueError(f"bad statsbomb sid: {source_match_id!r}") from None
        key = (int(comp_id), int(season_id))
        if key not in self._matches_cache:
            raise ValueError("season matches not cached — import the season first")
        for m in self._matches_cache[key]:
            if str(m.get("match_id", "")) == match_id:
                return m, match_id
        raise ValueError(f"match {match_id} not in cached season file")

    async def get_match_statistics(self, source_match_id: str) -> list[NormalizedMatchStatistics]:
        match, _ = self._locate(source_match_id)
        self._current_events = await self.fetch_match_events(str(match.get("match_id", "")))
        try:
            _, stats = self.convert_events(match)
            return stats
        finally:
            self._current_events = []

    async def get_match_events(self, source_match_id: str) -> list[NormalizedEvent]:
        match, _ = self._locate(source_match_id)
        self._current_events = await self.fetch_match_events(str(match.get("match_id", "")))
        try:
            events, _ = self.convert_events(match)
            return events
        finally:
            self._current_events = []

    async def get_lineups(self, source_match_id: str) -> list[NormalizedLineup]:
        match, match_id = self._locate(source_match_id)
        lineups = await self.fetch_match_lineups(match_id)
        self._current_events = await self.fetch_match_events(match_id)
        try:
            return self.convert_lineups(match, lineups, self._current_events)
        finally:
            self._current_events = []

    async def get_standings(self, league_code: str, season: str) -> list:
        return []

    async def get_players(self, league_code: str, season: str) -> list:
        return []

    # -- provenance sid ----------------------------------------------------
    def sid_for(self, comp_id: int, season_id: int, match_id: str) -> str:
        return f"{comp_id}:{season_id}:{match_id}"
