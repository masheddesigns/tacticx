"""Safe configuration diagnostic — presence only, NEVER secret values.

Usage: python -m scripts.diag_config
Exit 0 always (informational); smoke tests decide pass/fail.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.services.caching import cache as cache_mod  # noqa: E402


def main() -> None:
    s = get_settings()
    report = s.diagnose()
    report["cache"] = cache_mod.backend_status()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
