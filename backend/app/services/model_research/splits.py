"""Chronological splits + expanding walk-forward folds (Phase 12).

Never random. Season-labeled splits (older -> validation -> test) or
expanding folds (train grows, test advances). Every test row satisfies
training timestamp < target kickoff by construction (rows carry kickoffs;
folds cut on kickoff order).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional


def season_splits(rows: List[Dict], train_seasons: List[str],
                  validate_season: str, test_seasons: List[str],
                  season_of) -> Dict:
    """Split pre-labeled rows by season. Empty windows raise (never silently
    rebalanced or manufactured)."""
    train = [r for r in rows if season_of(r) in train_seasons]
    validate = [r for r in rows if season_of(r) == validate_season]
    test = [r for r in rows if season_of(r) in test_seasons]
    if not train:
        raise ValueError("empty training window")
    if not validate:
        raise ValueError("empty validation window")
    if not test:
        raise ValueError("empty test window")
    return {"train": train, "validate": validate, "test": test,
            "train_seasons": train_seasons, "validate_season": validate_season,
            "test_seasons": test_seasons}


def expanding_folds(rows: List[Dict], n_folds: int = 3,
                    min_train: int = 200) -> List[Dict]:
    """Expanding-window folds over kickoff-ordered rows. Fold k trains on
    everything before its test block."""
    ordered = sorted(rows, key=lambda r: (r["kickoff"], r["match_id"]))
    if len(ordered) < min_train + n_folds:
        raise ValueError("insufficient rows for expanding folds")
    block = (len(ordered) - min_train) // (n_folds + 1)
    if block < 1:
        raise ValueError("insufficient rows for expanding folds")
    folds = []
    for k in range(n_folds):
        test_start = min_train + k * block
        test_end = test_start + block
        folds.append({"fold": k,
                      "train": ordered[:test_start],
                      "test": ordered[test_start:test_end]})
    return folds
