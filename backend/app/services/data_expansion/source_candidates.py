"""Source candidate registry: measured, never assumed (Phase 13).

Statuses: candidate → tested → validated / rejected; active only after the
validation gate. Rejections carry reasons (legal, technical, quota, value).
"""
from __future__ import annotations

from typing import Dict, List, Optional

STATUS_CANDIDATE, STATUS_TESTED, STATUS_VALIDATED = (
    "candidate", "tested", "validated")
STATUS_REJECTED, STATUS_ACTIVE = "rejected", "active"

CANDIDATES: List[Dict] = [
    {
        "source": "football_data_co_uk",
        "domain": "historical CSV datasets (football-data.co.uk)",
        "data_families": ["fixtures", "results", "statistics", "shots",
                          "closing_odds"],
        "competition_coverage": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA",
                                 "LIGUE_1"],
        "season_coverage": "1516–2425 (HEAD-verified per league file, 2026-09-18)",
        "historical_depth": "10 seasons per league",
        "temporal_metadata": "event dates only; no effective_at (unknown timing)",
        "license": "free for personal/non-commercial use; no redistribution "
                   "of raw files in this repo (downloaded at runtime, never committed)",
        "access_method": "HTTPS GET per season CSV, polite UA, rate-limited",
        "rate_limits": "self-imposed: ≥2s between requests, small batches",
        "validation_status": "validated",
        "reason": "proven import path (csv_source), contiguous missing seasons, "
                  "shots + closing odds included; no xG/events/lineups expected",
    },
    {
        "source": "statsbomb_open_data",
        "domain": "open research event data (GitHub)",
        "data_families": ["events", "lineups", "xg", "player_identity"],
        "competition_coverage": ["LA_LIGA 2015 (+ others outside our leagues)"],
        "season_coverage": "already ingested where overlapping; no new "
                           "EPL/Serie A/Bundesliga/Ligue 1 free seasons found",
        "historical_depth": "none incremental",
        "temporal_metadata": "event dates only; no effective_at",
        "license": "public research use with attribution",
        "access_method": "GitHub raw JSON (existing adapter)",
        "rate_limits": "GitHub raw rate limits respected",
        "validation_status": "rejected",
        "reason": "no incremental coverage for our five leagues beyond what "
                  "is stored (re-check before future phases)",
    },
    {
        "source": "api_football_history",
        "domain": "validated API (fixtures/statistics/events/lineups)",
        "data_families": ["fixtures", "events", "lineups", "statistics"],
        "competition_coverage": ["EPL 2024 verified (380 fixtures)"],
        "season_coverage": "past seasons supported; current season empty on key",
        "historical_depth": "multi-season",
        "temporal_metadata": "response timestamps; effective_at unknown",
        "license": "paid plan quotas apply",
        "access_method": "existing adapter with rate limiter + cache",
        "rate_limits": "PROVIDER_MAX_REQUESTS_PER_MINUTE + daily quota",
        "validation_status": "tested",
        "reason": "path validated (1-match events/lineups probe in Phase 13); "
                  "bulk backfill deferred: ~3 calls/match over quota budget "
                  "without a dedicated allocation",
    },
    {
        "source": "odds_api_history",
        "domain": "validated odds API",
        "data_families": ["odds"],
        "competition_coverage": "upcoming events only",
        "season_coverage": "no historical depth",
        "historical_depth": "none",
        "temporal_metadata": "snapshot timestamps",
        "license": "quota-bound",
        "access_method": "existing adapter",
        "rate_limits": "ODDS_API_RATE_LIMIT_PER_MINUTE",
        "validation_status": "rejected",
        "reason": "no historical odds depth; upcoming-only (Phase 7 finding stands)",
    },
    {
        "source": "aggressive_scraping",
        "domain": "unlicensed scraping",
        "data_families": ["unknown"],
        "competition_coverage": [],
        "season_coverage": "",
        "historical_depth": "",
        "temporal_metadata": "",
        "license": "incompatible",
        "access_method": "rejected",
        "rate_limits": "",
        "validation_status": "rejected",
        "reason": "robots/terms/licensing incompatible with project use; "
                  "never pursued",
    },
]


def registry() -> List[Dict]:
    return [dict(entry) for entry in CANDIDATES]


def accepted() -> List[Dict]:
    return [entry for entry in CANDIDATES
            if entry["validation_status"] in (STATUS_VALIDATED, STATUS_ACTIVE)]


def rejected() -> List[Dict]:
    return [entry for entry in CANDIDATES
            if entry["validation_status"] == STATUS_REJECTED]
