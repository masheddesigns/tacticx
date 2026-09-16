"""Deterministic team-name normalization (Phase 1.6).

Lowercase, strip accents/whitespace/punctuation, drop a small explicit list
of club suffixes. Deterministic only — NO fuzzy matching anywhere.
"""
from __future__ import annotations

import re
import unicodedata

_SUFFIXES = (" fc", " cf", " sc", " ac", " afc")

_WHITESPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[.'’`-]")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = _PUNCT.sub("", text.lower().strip())
    text = _WHITESPACE.sub(" ", text).strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix) + 2:
            text = text[: -len(suffix)].strip()
            break
    return text
