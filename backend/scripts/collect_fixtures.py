"""Collect fixtures via the source registry (Phase 1.6).

    python scripts/collect_fixtures.py --league EPL --season 2024 --from 2024-08-01 --to 2024-08-31
    python scripts/collect_fixtures.py --league EPL --season 2024 --from 2024-08-01 --to 2024-08-31 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.quality import validate_match  # noqa: E402
from app.services.sources.pipeline import Pipeline  # noqa: E402
from scripts.collect_lib import (  # noqa: E402
    attempt,
    common_args,
    configured_leagues,
    football_chain,
    open_db,
    run_async,
)


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Collect fixtures (idempotent, resumable).")
    common_args(ap)
    args = ap.parse_args()

    skwargs = {"file_path": args.file} if args.file else {}
    summary: dict = {"operation": "collect_fixtures", "leagues": {}}
    db = None if args.dry_run else open_db()
    try:
        for entry in configured_leagues(args.league):
            def op(source, _e=entry):
                return run_async(lambda: source.get_fixtures(
                    _e["code"], args.season or _e["season"],
                    args.date_from or None, args.date_to or None))

            try:
                served_by, fixtures = attempt(football_chain(args.source, **skwargs), op)
            except RuntimeError as exc:
                summary["leagues"][entry["code"]] = {"error": str(exc)}
                continue
            valid = sum(1 for f in fixtures if validate_match(
                f.home_team, f.away_team, f.home_score, f.away_score,
                f.kickoff_at, f.league_code, f.season).valid)
            league_out = {"source": served_by, "received": len(fixtures), "valid": valid}
            if not args.dry_run:
                assert db is not None
                pipe = Pipeline(db, served_by)
                for f in fixtures:
                    pipe.ingest_match(f, parser_version=f.provenance.parser_version)
                stats = pipe.finish("collect_fixtures", league=entry["code"])
                league_out.update({"inserted": stats.inserted, "updated": stats.updated,
                                   "duplicates": stats.duplicates,
                                   "quarantined": stats.quarantined,
                                   "unresolved": stats.unresolved})
            summary["leagues"][entry["code"]] = league_out
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
