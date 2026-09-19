"""Safe version and build metadata helper for TacticX."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache
def get_version_info() -> dict[str, Any]:
    """Return non-sensitive version, git commit, and environment metadata."""
    version = os.getenv("APP_VERSION", "0.1.0")
    commit_sha = os.getenv("GIT_COMMIT_SHA", os.getenv("COMMIT_SHA", "unknown"))

    if commit_sha == "unknown":
        try:
            import subprocess

            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                commit_sha = res.stdout.strip()
        except Exception:  # noqa: BLE001
            commit_sha = "unknown"

    build_date = os.getenv("BUILD_DATE", "unknown")
    environment = os.getenv("ENVIRONMENT", "development")

    return {
        "service": "tacticx-backend",
        "version": version,
        "commit": commit_sha,
        "build_date": build_date,
        "environment": environment,
    }
