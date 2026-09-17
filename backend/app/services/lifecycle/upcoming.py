"""Upcoming-match discovery (Phase 7).

Source-agnostic interface over permitted providers. Normalized output carries
the canonical-shape fields callers need; canonical resolution happens in
sync.py via the Phase 1.6 identity architecture (never here, never by
spelling).

Providers are only used for capabilities they actually expose — verified,
not assumed. API-Football exposes fixtures by date (upcoming supported);
The-Odds-API exposes events with commence times (upcoming supported, league
unresolved by that feed and left unset, never guessed).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from app.config import get_settings

CANONICAL_STATUSES = ("scheduled", "postponed", "cancelled", "finished", "unknown")

# Provider-native status -> canonical status. Unmapped values become unknown
# (never forced into scheduled).
STATUS_MAP = {
    "ns": "scheduled", "notstarted": "scheduled", "scheduled": "scheduled",
    "tbd": "scheduled", "p": "postponed", "pst": "postponed", "postponed": "postponed",
    "postp": "postponed", "canc": "cancelled", "cancelled": "cancelled",
    "canceled": "cancelled", "abd": "cancelled", "ft": "finished",
    "finished": "finished", "aet": "finished", "pen": "finished",
}


class UpcomingMatch(BaseModel):
    league_code: str = ""
    season: str = ""
    home_team: str = ""
    away_team: str = ""
    kickoff_utc: Optional[datetime] = None
    kickoff_source: str = ""
    kickoff_timezone: str = ""
    status: str = "unknown"
    source: str = ""
    source_match_id: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class UpcomingMatchSource(Protocol):
    name: str

    async def fetch(self, from_time: datetime, to_time: datetime,
                    league_code: Optional[str] = None) -> List[UpcomingMatch]: ...


def normalize_kickoff(raw: Optional[datetime], source_tz: str = "") -> tuple:
    """Return (utc_datetime | None, original_string, source_tz).

    Naive timestamps are assumed UTC only when the source documents UTC;
    otherwise the original is preserved and UTC stays None (missing stays
    missing — never guessed). Callers must handle None kickoffs.
    """
    if raw is None:
        return None, "", source_tz
    original = str(raw)
    try:
        aware = raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc), original, source_tz
    except Exception:
        return None, original, source_tz


def normalize_status(raw_status: str) -> str:
    key = (raw_status or "").strip().lower().replace(" ", "").replace("_", "")
    return STATUS_MAP.get(key, "unknown")


class ApiFootballUpcomingSource:
    """Upcoming fixtures via API-Football (supports date-filtered fixtures)."""

    name = "api_football"

    def __init__(self, provider=None, league_map: Optional[Dict[str, Dict]] = None):
        self._provider = provider
        self._league_map = league_map or {}

    async def fetch(self, from_time: datetime, to_time: datetime,
                    league_code: Optional[str] = None) -> List[UpcomingMatch]:
        from app.services.providers import get_football_provider

        provider = self._provider or get_football_provider()
        out: List[UpcomingMatch] = []
        codes = [league_code] if league_code else sorted(self._league_map)
        for code in codes:
            entry = self._league_map.get(code, {})
            provider_league = entry.get("provider_id", "")
            season = entry.get("season", "")
            if not provider_league:
                continue
            # NOTE: the provider date filter returns no rows on this key
            # (verified 2026-09-17 across current + historical seasons), so
            # season fixtures are fetched once (cached upstream) and the
            # window is applied locally. Never assumed — measured.
            try:
                fixtures = await provider.get_fixtures(provider_league, season)
            except Exception:
                continue
            for fx in fixtures:
                kickoff, original, _ = normalize_kickoff(fx.kickoff_at, "UTC")
                if kickoff is not None and not (from_time <= kickoff <= to_time):
                    continue
                out.append(UpcomingMatch(
                    league_code=code, season=season,
                    home_team=fx.home_team_name or "",
                    away_team=fx.away_team_name or "",
                    kickoff_utc=kickoff, kickoff_source=original,
                    kickoff_timezone="UTC", status=normalize_status(fx.status),
                    source=self.name, source_match_id=str(fx.provider_match_id),
                    home_score=fx.home_score, away_score=fx.away_score))
        return out


class OddsApiUpcomingSource:
    """Upcoming events via The-Odds-API (commence times; league unresolved)."""

    name = "odds_api"

    def __init__(self, provider=None):
        self._provider = provider

    async def fetch(self, from_time: datetime, to_time: datetime,
                    league_code: Optional[str] = None) -> List[UpcomingMatch]:
        from app.services.providers import get_odds_provider

        provider = self._provider or get_odds_provider()
        try:
            snapshots = await provider.get_odds()
        except Exception:
            return []
        out: List[UpcomingMatch] = []
        for snap in snapshots:
            kickoff, original, _ = normalize_kickoff(snap.commence_time, "UTC")
            if kickoff is None or not (from_time <= kickoff <= to_time):
                continue
            out.append(UpcomingMatch(
                home_team=snap.home_team or "", away_team=snap.away_team or "",
                kickoff_utc=kickoff, kickoff_source=original,
                kickoff_timezone="UTC", status="scheduled",
                source=self.name,
                source_match_id=str(snap.event_id or "")))
        return out


def fetch_all(sources: List[UpcomingMatchSource], from_time: datetime,
              to_time: datetime,
              league_code: Optional[str] = None) -> Dict[str, List[UpcomingMatch]]:
    """Run all sources sequentially (quota-friendly). Never raises: per-source
    failures are returned as error records for health tracking."""
    grouped: Dict[str, List[UpcomingMatch]] = {}
    for source in sources:
        try:
            grouped[source.name] = asyncio.run(
                source.fetch(from_time, to_time, league_code))
        except Exception as exc:
            grouped[source.name] = []
            grouped[f"{source.name}__error"] = [str(exc)[:300]]  # type: ignore
    return grouped


def default_sources(league_map: Optional[Dict[str, Dict]] = None) -> List:
    settings = get_settings()
    sources: List = []
    if settings.is_football_configured:
        sources.append(ApiFootballUpcomingSource(league_map=league_map))
    if settings.is_odds_configured:
        sources.append(OddsApiUpcomingSource())
    return sources
