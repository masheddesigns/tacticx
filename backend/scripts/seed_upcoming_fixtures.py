"""Seed upcoming matchday fixtures and comprehensive pre-match intelligence.

Delegates directly to sync_real_upcoming.py to ensure zero data fabrication,
using authentic fixtures from API-Football for current international matchdays
and genuine calendar dates.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from scripts.sync_real_upcoming import sync_real_fixtures


def seed_upcoming() -> None:
    print("Executing genuine fixture synchronization (Zero Data Fabrication)...")
    sync_real_fixtures()


if __name__ == "__main__":
    seed_upcoming()
