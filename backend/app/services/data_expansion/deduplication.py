"""Deterministic dedup keys for expansion records (Phase 13).

Keys cover competition/season/home/away/kickoff/source/record-type without
assuming exact timestamp equality (normalization precedes keying; canonical
match resolution remains authoritative).
"""
from __future__ import annotations

import hashlib
from typing import Dict


def record_key(league: str, season: str, home: str, away: str, kickoff: str,
               source: str, record_type: str) -> str:
    from app.services.identity.normalize import normalize_name

    canonical = "|".join([
        (league or "").strip().upper(),
        (season or "").strip(),
        normalize_name(home), normalize_name(away),
        (kickoff or "").strip()[:13],  # hour precision: formatting-tolerant
        (source or "").strip().lower(), (record_type or "").strip().lower(),
    ])
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def same_observation(key_a: str, key_b: str) -> bool:
    return key_a == key_b
