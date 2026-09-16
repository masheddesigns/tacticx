"""Prune old raw provenance rows per RAW_RETENTION_DAYS (Phase 1.7).

Normalized data is never touched — only the raw_data_records audit trail.
RAW_RETENTION_DAYS=0 keeps everything. Always dry-run first:

    python scripts/prune_raw.py --dry-run
    python scripts/prune_raw.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.provenance import RawDataRecord  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Prune raw_data_records past retention.")
    ap.add_argument("--dry-run", action="store_true", help="Report only (default)")
    ap.add_argument("--apply", action="store_true", help="Actually delete rows")
    ap.add_argument("--days", type=int, default=0, help="Override RAW_RETENTION_DAYS")
    args = ap.parse_args()

    days = args.days or get_settings().RAW_RETENTION_DAYS
    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        total = db.query(RawDataRecord).count()
        if not days:
            print(json.dumps({"retention_days": 0, "total": total,
                              "eligible": 0, "deleted": 0,
                              "note": "retention disabled; nothing pruned"}))
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = db.query(RawDataRecord).filter(RawDataRecord.retrieved_at < cutoff)
        eligible = q.count()
        deleted = 0
        if args.apply and eligible:
            deleted = q.delete(synchronize_session=False)
            db.commit()
        print(json.dumps({"retention_days": days, "total": total,
                          "eligible": eligible, "deleted": deleted,
                          "applied": bool(args.apply)}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
