"""Inspect a reproducible pre-match feature snapshot (Phase 4).

    python scripts/features.py --match-id 123
    python scripts/features.py --match-id 123 --cutoff 2024-09-15T14:00:00 --json

The snapshot shows every feature value with availability, source, as-of
timestamp and quality. Missing data appears as available=False — never as
an invented number.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import Match  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.features.engineered import build_feature_snapshot  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Inspect a pre-match feature snapshot.")
    ap.add_argument("--match-id", type=int, required=True)
    ap.add_argument("--cutoff", default="",
                    help="ISO timestamp (default: match kickoff)")
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        match = db.get(Match, args.match_id)
        if match is None:
            print(f"no match with id {args.match_id}")
            return 1
        cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else match.kickoff_at
        if cutoff is None:
            print("match has no kickoff; pass --cutoff explicitly")
            return 1
        snapshot = build_feature_snapshot(
            db, args.match_id, cutoff, TemporalMode(args.temporal_mode))
        if args.as_json:
            print(json.dumps(snapshot, indent=2, default=str))
        else:
            print(f"match={snapshot['match_id']} cutoff={snapshot['cutoff']} "
                  f"features={snapshot['feature_version']} mode={snapshot['temporal_mode']}")
            for side in ("home_team", "away_team"):
                print(f"[{side}]")
                for key, env in snapshot[side].items():
                    if isinstance(env, dict) and "available" in env:
                        print(f"  {key}: available={env['available']} "
                              f"value={env['value']} ({env['quality']})")
            print(f"[elo] {snapshot['elo']}")
            print(f"[h2h] available={snapshot['h2h']['available']} "
                  f"value={snapshot['h2h']['value']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
