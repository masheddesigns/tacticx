"""Local dataset file cache (Phase 1.7).

Remote season files are downloaded once and reused from DATA_DIR/.cache —
re-running a multi-season import must not re-download what is already local.
`--refresh` forces re-download. Never committed (see .gitignore).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def cache_dir(source: str, base_dir: Optional[str] = None) -> Path:
    root = Path(base_dir or get_settings().DATA_DIR) / ".cache" / source
    root.mkdir(parents=True, exist_ok=True)
    return root


def read_cached(source: str, filename: str, base_dir: Optional[str] = None) -> Optional[str]:
    path = cache_dir(source, base_dir) / safe_filename(filename)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("dataset cache unreadable path=%s err=%s", path, exc)
        return None


def write_cached(source: str, filename: str, text: str,
                 base_dir: Optional[str] = None) -> str:
    path = cache_dir(source, base_dir) / safe_filename(filename)
    path.write_text(text, encoding="utf-8")
    return str(path)


async def fetch_cached(fetcher, url: str, source: str, filename: str,
                       refresh: bool = False, base_dir: Optional[str] = None,
                       validate=None) -> tuple[str, bool]:
    """Return (text, from_cache). Downloads only when missing or refresh=True.

    `validate` is an optional content sanity check. Cached content that fails
    validation is discarded and re-downloaded once; fresh content that fails
    raises instead of poisoning the cache.
    """
    if not refresh:
        cached = read_cached(source, filename, base_dir)
        if cached is not None:
            if validate is None or validate(cached):
                log.info("dataset cache hit source=%s file=%s", source, filename)
                return cached, True
            log.warning("dataset cache invalid source=%s file=%s (re-downloading)",
                        source, filename)
    text = await fetcher.fetch_text(url)
    if validate is not None and not validate(text):
        raise ValueError(f"downloaded dataset failed validation: {url}")
    write_cached(source, filename, text, base_dir)
    return text, False
