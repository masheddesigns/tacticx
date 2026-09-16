from __future__ import annotations

import enum


class MatchStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    PRE_MATCH = "PRE_MATCH"
    LIVE = "LIVE"
    HALFTIME = "HALFTIME"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
