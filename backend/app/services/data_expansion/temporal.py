"""Temporal confidence hierarchy (Phase 13).

A: source provides publication/effective time      -> strict-eligible
B: reliable historical availability semantics     -> estimated (documented)
C: timing bounded by acquisition behavior         -> estimated (bounded)
D: only event date known                          -> unknown
E: timing completely unknown                      -> unknown

C/D/E are never silently promoted into strict mode.
"""
from __future__ import annotations

from typing import Dict

HIERARCHY = {
    "A": {"label": "explicit effective time", "strict": True},
    "B": {"label": "documented availability semantics", "strict": False},
    "C": {"label": "acquisition-bounded timing", "strict": False},
    "D": {"label": "event date only", "strict": False},
    "E": {"label": "timing unknown", "strict": False},
}

# Source -> hierarchy level (measured, reviewable).
SOURCE_LEVELS = {
    "football_data_co_uk": "D",
    "statsbomb": "D",
    "api_football": "C",
    "odds_api": "C",
    "csv": "D",
}


def level_for(source: str) -> Dict:
    level = SOURCE_LEVELS.get(source, "E")
    entry = dict(HIERARCHY[level])
    entry.update({"level": level, "source": source})
    return entry
