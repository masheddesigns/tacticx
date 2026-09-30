"""Phase 39 competition taxonomy (configuration, not behavior).

Distinguishes domestic leagues from international competitions without
representing internationals as fake domestic leagues. Canonical codes
follow the existing UPPER_SNAKE convention.
"""
from __future__ import annotations

from typing import Dict, Optional

DOMESTIC_LEAGUE = "DOMESTIC_LEAGUE"
UEFA_NATIONS_LEAGUE = "UEFA_NATIONS_LEAGUE"
INTERNATIONAL_FRIENDLY = "INTERNATIONAL_FRIENDLY"

# Canonical competition codes.
NATIONS_LEAGUE = "NATIONS_LEAGUE"
FRIENDLIES = "FRIENDLIES"

COMPETITION_TYPES: Dict[str, str] = {
    "EPL": DOMESTIC_LEAGUE,
    "LA_LIGA": DOMESTIC_LEAGUE,
    "SERIE_A": DOMESTIC_LEAGUE,
    "BUNDESLIGA": DOMESTIC_LEAGUE,
    "LIGUE_1": DOMESTIC_LEAGUE,
    # UCL is continental club football; grouped with domestic leagues for
    # pipeline purposes (round-robin history, standings reconstruction).
    "UCL": DOMESTIC_LEAGUE,
    NATIONS_LEAGUE: UEFA_NATIONS_LEAGUE,
    FRIENDLIES: INTERNATIONAL_FRIENDLY,
}

ORGANIZATIONS: Dict[str, str] = {
    "EPL": "Premier League",
    "LA_LIGA": "LaLiga",
    "SERIE_A": "Serie A",
    "BUNDESLIGA": "Bundesliga",
    "LIGUE_1": "Ligue 1",
    "UCL": "UEFA",
    NATIONS_LEAGUE: "UEFA",
    FRIENDLIES: "International",
}

INTERNATIONAL_COMPETITIONS = (NATIONS_LEAGUE, FRIENDLIES)


def competition_type(code: str) -> str:
    """Return the taxonomy type for a canonical competition code."""
    return COMPETITION_TYPES.get((code or "").upper(), DOMESTIC_LEAGUE)


def organization(code: str) -> str:
    """Return the governing organization label for a competition code."""
    return ORGANIZATIONS.get((code or "").upper(), "")


def is_international(code: str) -> bool:
    return (code or "").upper() in INTERNATIONAL_COMPETITIONS


def describe(code: str) -> Dict[str, Optional[str]]:
    upper = (code or "").upper()
    return {"code": upper or code,
            "competition_type": competition_type(upper),
            "organization": organization(upper) or None}
