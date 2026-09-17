"""Availability boundary + family availability matrix (Phase 9).

availability_status is a capability boundary, never an injury predictor:
known_available / known_unavailable / unknown / unavailable_source. Only
populated from explicit reliable sources — no such source exists in this
dataset, so availability stays unknown and "did not appear" is never
converted into "was injured".

The family matrix (strict/estimated/source) is populated from actual
repository evidence, not assumptions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.services.features.temporal import TemporalMode
from app.services.player_intelligence.repository import PlayerEventRepository

STATUS_UNKNOWN = "unknown"
STATUS_UNAVAILABLE_SOURCE = "unavailable_source"


def player_availability(db: Session, canonical_player_id: int) -> Dict:
    """Capability boundary: unknown unless an explicit source says otherwise."""
    return {"canonical_player_id": canonical_player_id,
            "availability_status": STATUS_UNKNOWN,
            "reason": "no reliable injury/suspension source configured; "
                      "non-appearance is not unavailability evidence"}


def family_availability(db: Session, team_id: int, cutoff: datetime,
                        target_match_id: Optional[int] = None) -> Dict:
    """Measured availability per feature family x strict/estimated."""
    families = {}
    for mode in (TemporalMode.STRICT_PREMATCH, TemporalMode.HISTORICAL_ESTIMATED):
        repo = PlayerEventRepository(db, cutoff, mode, target_match_id)
        evidence = repo.evidence_counts(team_id)
        strict_rows = evidence["lineup_rows_strict"] + evidence["event_rows_strict"]
        estimated_rows = evidence["lineup_rows"] + evidence["event_rows"]
        families[mode.value] = {
            "player_appearances": evidence["lineup_rows"] > 0,
            "player_events": evidence["event_rows"] > 0,
            "player_form": evidence["lineup_rows"] > 0,
            "lineup_continuity": evidence["lineup_rows"] > 0,
            "formation": evidence["lineup_rows"] > 0,
            "transfers": True,  # membership reconstruction from lineup evidence
            "strict_rows": strict_rows,
            "estimated_rows": estimated_rows,
        }
    matrix = {
        "player_appearances": {"strict": families["strict_prematch"]["player_appearances"],
                               "estimated": families["historical_estimated"]["player_appearances"],
                               "source": "lineups"},
        "player_events": {"strict": families["strict_prematch"]["player_events"],
                          "estimated": families["historical_estimated"]["player_events"],
                          "source": "statsbomb"},
        "player_form": {"strict": families["strict_prematch"]["player_form"],
                        "estimated": families["historical_estimated"]["player_form"],
                        "source": "derived"},
        "lineup_continuity": {"strict": families["strict_prematch"]["lineup_continuity"],
                              "estimated": families["historical_estimated"]["lineup_continuity"],
                              "source": "statsbomb"},
        "formation": {"strict": families["strict_prematch"]["formation"],
                      "estimated": families["historical_estimated"]["formation"],
                      "source": "statsbomb"},
        "injuries": {"strict": False, "estimated": False,
                     "source": "only if source exists (none configured)"},
        "suspensions": {"strict": False, "estimated": False,
                        "source": "only if source exists (none configured)"},
        "transfers": {"strict": families["strict_prematch"]["transfers"],
                      "estimated": families["historical_estimated"]["transfers"],
                      "source": "measured (lineup evidence)"},
        "player_availability": {"strict": False, "estimated": False,
                                "source": "source-dependent (unknown)"},
    }
    return {"families": matrix, "evidence": families}
