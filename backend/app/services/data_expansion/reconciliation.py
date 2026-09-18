"""Reconciliation entry for expansion (Phase 13).

No new reconciliation logic: everything routes through Phase 1.6 identity,
Phase 8 typed conflicts, Phase 10 temporal validation and Phase 11
acquisition. This module only adds the expansion-specific classification:
source-scope difference (different populations/definitions, not disagreement)
so conflict counts are never inflated.
"""
from __future__ import annotations

from typing import Dict

SCOPE_DIFFERENCE = "scope_difference"


def classify_expansion_outcome(have_families, new_families) -> str:
    """scope_difference when sources cover different populations without
    disagreeing; disagreement classes come from Phase 8."""
    if set(have_families) & set(new_families):
        return "overlap"
    return SCOPE_DIFFERENCE
