"""football-data.co.uk historical dataset source (Phase 1.6).

Free public season CSVs (results + closing bookmaker odds), fetched over
plain HTTPS with the polite fetcher: robots.txt pre-check (verified
permissive), minimum delays, per-minute ceiling, caching, request logging.
No authentication, no protections to bypass — and none are attempted.
Doubles as FootballDataSource (results), OddsDataSource (closing lines) and
HistoricalDataSource (bulk seasons).
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger
from app.services.scraping.framework import utcnow
from app.services.scraping.polite import PoliteFetcher, SourceDisallowed
from app.services.sources.base import (
    FootballDataSource,
    HistoricalDataSource,
    OddsDataSource,
    SourceCapabilities,
)
from app.services.sources.historical.csv_source import (
    canonical_row,
    closing_odds_snapshots,
    import_rows,
)
from app.services.sources.normalized import (
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedOddsSnapshot,
    NormalizedTeam,
    Provenance,
)

log = get_logger(__name__)

PARSER = "fdco_csv_parser_v1"

# Our league codes -> football-data.co.uk division codes.
DIVISIONS = {
    "EPL": "E0",
    "LA_LIGA": "SP1",
    "SERIE_A": "I1",
    "BUNDESLIGA": "D1",
    "LIGUE_1": "F1",
}


def season_segment(season: str) -> str:
    """'2024' (2024/25) -> '2425'. Raises ValueError on bad input."""
    year = int(str(season).strip()[:4])
    if not 1990 <= year <= 2100:
        raise ValueError(f"implausible season: {season!r}")
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def season_url(base_url: str, league_code: str, season: str) -> str:
    div = DIVISIONS.get((league_code or "").upper())
    if not div:
        raise ValueError(
            f"football-data.co.uk has no division for league {league_code!r} "
            f"(covered: {sorted(DIVISIONS)})")
    return f"{base_url.rstrip('/')}/{season_segment(season)}/{div}.csv"


class FootballDataCoUkSource(HistoricalDataSource, FootballDataSource, OddsDataSource):
    source_name = "football_data_co_uk"
    capabilities = SourceCapabilities(fixtures=True, historical_bulk=True,
                                      odds_prematch=True)

    def __init__(self, db=None, db_session_factory=None, client=None, **kwargs):
        s = get_settings()
        self.db = db
        self.base_url = s.DATASET_BASE_URL
        self.fetcher = PoliteFetcher(source=self.source_name,
                                     db_session_factory=db_session_factory, client=client)

    def check(self) -> dict:
        return {"source": self.source_name,
                "base_url": self.base_url,
                "divisions": sorted(DIVISIONS),
                "role": "primary bulk history (results + closing odds)"}

    async def fetch_season_rows(self, league_code: str, season: str,
                               refresh: bool = False) -> list[dict]:
        """Download + parse one season CSV. Raises SourceDisallowed / ValueError /
        ProviderHTTPError — all fail cleanly, never bypassed."""
        from app.services.scraping.datasets import fetch_cached

        def _sane(text: str) -> bool:
            # Structural check only (header + at least one data row). A
            # mid-file truncation still parses, so --refresh re-downloads
            # whenever row counts look wrong; re-imports are idempotent.
            lines = text.splitlines()
            return len(lines) > 1 and "HomeTeam" in (lines[0] if lines else "")

        url = season_url(self.base_url, league_code, season)
        div = DIVISIONS[(league_code or "").upper()]
        try:
            text, _ = await fetch_cached(self.fetcher, url, self.source_name,
                                         f"{season_segment(season)}_{div}.csv",
                                         refresh=refresh, validate=_sane)
        except SourceDisallowed:
            raise
        except Exception as exc:  # noqa: BLE001
            from app.services.http_client import ProviderHTTPError
            raise ProviderHTTPError(f"football-data.co.uk fetch failed: {exc}") from exc
        try:
            reader = csv.DictReader(io.StringIO(text))
            rows = [dict(r) for r in reader if r.get("HomeTeam")]
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"cannot parse season CSV: {exc}") from exc
        if not rows:
            raise ValueError(f"season file empty or unusable: {url}")
        return rows

    # -- HistoricalDataSource --------------------------------------------
    def import_history(self, league_code: str, season: str,
                       date_from: Optional[str] = None, date_to: Optional[str] = None,
                       **kwargs) -> dict:
        import asyncio

        if self.db is None:
            raise ValueError("FootballDataCoUkSource needs db (pass db=session)")
        rows = asyncio.run(self.fetch_season_rows(
            league_code, season, refresh=bool(kwargs.get("refresh", False))))
        rejected: list = []
        report = import_rows(
            self.db, self.source_name, rows, league_code, season,
            date_from=date_from, date_to=date_to,
            create_teams=kwargs.get("create_teams", True),
            parser_version=PARSER, rejected_sink=rejected,
            rid_prefix=f"fdco:{league_code}:{season}#",
            source_url=season_url(self.base_url, league_code, season))
        report["_rejected"] = rejected
        return report

    # -- FootballDataSource surface ---------------------------------------
    async def get_leagues(self) -> list[dict]:
        return [{"code": code, "name": code, "country": "", "provider_league_id": div,
                 "season": ""}
                for code, div in DIVISIONS.items()]

    async def get_teams(self, league_code: str, season: str) -> list[NormalizedTeam]:
        try:
            rows = await self.fetch_season_rows(league_code, season)
        except Exception as exc:  # noqa: BLE001 — unavailable season: empty, not invented
            log.warning("fdco teams unavailable league=%s season=%s err=%s", league_code, season, exc)
            return []
        seen: dict[str, NormalizedTeam] = {}
        for raw in rows:
            try:
                row = canonical_row(raw)
            except Exception:  # noqa: BLE001
                continue
            for name in (row["home"], row["away"]):
                if name not in seen:
                    seen[name] = NormalizedTeam(
                        name=name, league_code=league_code,
                        provenance=Provenance(
                            source=self.source_name, source_record_id=f"team:{name}",
                            collected_at=utcnow(), parser_version=PARSER))
        return list(seen.values())

    async def get_fixtures(self, league_code: str, season: str,
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> list[NormalizedMatch]:
        from app.services.sources.historical.csv_source import parse_date

        div = DIVISIONS.get((league_code or "").upper(), "")
        if not div:
            raise ValueError(
                f"football-data.co.uk has no division for league {league_code!r} "
                f"(covered: {sorted(DIVISIONS)})")
        rows = await self.fetch_season_rows(league_code, season)
        df = parse_date(date_from).date() if date_from else None
        dt = parse_date(date_to).date() if date_to else None
        out = []
        for raw in rows:
            try:
                row = canonical_row(raw)
            except Exception:  # noqa: BLE001
                continue
            if row["kickoff"] and ((df and row["kickoff"].date() < df)
                                   or (dt and row["kickoff"].date() > dt)):
                continue
            date_iso = row["kickoff"].date().isoformat() if row["kickoff"] else ""
            out.append(NormalizedMatch(
                league_code=league_code, season=season,
                home_team=row["home"], away_team=row["away"], kickoff_at=row["kickoff"],
                status=row["status"], home_score=row["home_score"], away_score=row["away_score"],
                provenance=Provenance(
                    source=self.source_name,
                    source_record_id=f"{div}|{row['home']}|{row['away']}|{date_iso}",
                    collected_at=utcnow(), parser_version=PARSER,
                    temporal_quality="estimated")))
        return out

    @staticmethod
    def _split_sid(source_match_id: str) -> Optional[tuple[str, str, str, str]]:
        """Structured sid 'DIV|home|away|YYYY-MM-DD' -> parts. None when foreign."""
        parts = str(source_match_id or "").split("|")
        if len(parts) != 4 or not all(parts):
            return None
        return parts[0], parts[1], parts[2], parts[3]

    async def get_match_statistics(self, source_match_id: str) -> list[NormalizedMatchStatistics]:
        from app.services.sources.historical.csv_source import (
            match_stats_from_row,
            parse_date,
        )

        split = self._split_sid(source_match_id)
        if split is None:
            return []
        div, home, away, date_iso = split
        day = parse_date(date_iso)
        if day is None:
            return []
        season = str(day.year if day.month >= 8 else day.year - 1)
        league_code = next((c for c, d in DIVISIONS.items() if d == div), "")
        if not league_code:
            return []
        try:
            rows = await self.fetch_season_rows(league_code, season)
        except Exception as exc:  # noqa: BLE001
            log.warning("fdco stats unavailable sid=%s err=%s", source_match_id, exc)
            return []
        for raw in rows:
            try:
                row = canonical_row(raw)
            except Exception:  # noqa: BLE001
                continue
            if (row["home"] == home and row["away"] == away and row["kickoff"]
                    and row["kickoff"].date().isoformat() == date_iso):
                return match_stats_from_row(row, self.source_name, PARSER)
        return []

    async def get_match_events(self, source_match_id: str) -> list:
        return []

    async def get_lineups(self, source_match_id: str) -> list:
        return []

    async def get_standings(self, league_code: str, season: str) -> list:
        return []

    async def get_players(self, league_code: str, season: str) -> list:
        return []

    # -- OddsDataSource surface (closing lines) ---------------------------
    async def get_odds_snapshots(self, league_code: str = "", season: str = "",
                                 live: bool = False) -> list[NormalizedOddsSnapshot]:
        if live or not league_code or not season:
            return []  # files hold closing pre-match lines for a full season
        rows = await self.fetch_season_rows(league_code, season)
        out = []
        for raw in rows:
            try:
                row = canonical_row(raw)
            except Exception:  # noqa: BLE001
                continue
            out.extend(closing_odds_snapshots(row, self.source_name, league_code, season,
                                              row["kickoff"]))
        return out

    def supported_markets(self) -> list[str]:
        return ["h2h", "totals"]
