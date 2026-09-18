"""Coverage delta: before/after/incremental measurement (Phase 13)."""
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.services.data_expansion import inventory as inventory_svc

FAMILIES = ("matches", "stats", "xg", "shots", "events", "lineups", "odds",
            "players", "minutes")


def snapshot_coverage(db: Session, league_code: Optional[str] = None) -> Dict:
    report = inventory_svc.league_inventory(db, league_code)
    return report.get("totals", {})


def delta(before: Dict, after: Dict) -> Dict:
    table = {}
    for family in FAMILIES:
        before_n = before.get(family, 0)
        after_n = after.get(family, 0)
        table[family] = {"before": before_n, "after": after_n,
                         "delta": after_n - before_n}
    return {"families": table,
            "new_matches": table["matches"]["delta"]}
