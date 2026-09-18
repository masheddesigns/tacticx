"""Polite historical acquisition: download → tmp file → proven import path (Phase 13).

Self-imposed politeness: identifiable UA, ≥2s between requests, small
batches, retries with backoff, checksum recorded. Downloads go to tmp (never
committed); raw retention policy = tmp lifetime (OS-managed).
"""
from __future__ import annotations

import hashlib
import time
import urllib.request
from pathlib import Path
from typing import Dict, Optional

BASE_URL = "https://football-data.co.uk/mmz4281"
USER_AGENT = "TacticX-research/1.0 (historical backfill; polite fetcher)"
MIN_DELAY_SECONDS = 2.0
TIMEOUT_SECONDS = 30

LEAGUE_FILES = {"EPL": "E0", "LA_LIGA": "SP1", "SERIE_A": "I1",
                "BUNDESLIGA": "D1", "LIGUE_1": "F1"}

_last_fetch: float = 0.0


def season_url(league_code: str, season_tag: str) -> str:
    """season_tag like '1617' (2016/17). Raises for unknown leagues."""
    code = LEAGUE_FILES.get(league_code)
    if code is None:
        raise ValueError(f"unknown league: {league_code}")
    return f"{BASE_URL}/{season_tag}/{code}.csv"


def probe(league_code: str, season_tag: str) -> Dict:
    """HEAD probe: exists + size, no download. Polite single request."""
    _polite_wait()
    url = season_url(league_code, season_tag)
    request = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return {"exists": response.status == 200,
                    "bytes": int(response.headers.get("Content-Length", 0) or 0),
                    "url": url}
    except Exception as exc:
        return {"exists": False, "bytes": 0, "url": url,
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def download(league_code: str, season_tag: str, dest_dir: str) -> Dict:
    """Download one season file (respects rate limit + retries)."""
    _polite_wait()
    url = season_url(league_code, season_tag)
    dest = Path(dest_dir) / f"{league_code}-{season_tag}.csv"
    attempts, last_error = 0, ""
    while attempts < 3:
        attempts += 1
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = response.read()
            dest.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()[:16]
            return {"path": str(dest), "bytes": len(data), "sha256_16": digest,
                    "url": url, "attempts": attempts}
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:200]
            time.sleep(MIN_DELAY_SECONDS * attempts)
    return {"path": "", "bytes": 0, "url": url, "attempts": attempts,
            "error": last_error}


def _polite_wait() -> None:
    global _last_fetch
    elapsed = time.monotonic() - _last_fetch
    if elapsed < MIN_DELAY_SECONDS:
        time.sleep(MIN_DELAY_SECONDS - elapsed)
    _last_fetch = time.monotonic()
