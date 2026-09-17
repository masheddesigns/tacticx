"""Bookmaker + market identity normalization (Phase 8).

Bookmakers resolve on exact (provider, provider_bookmaker_id) keys; display
names map through a reviewable alias table (never fuzzy). Similarly named
bookmakers are NOT assumed identical. Markets/selections canonicalize
through explicit maps with original labels preserved. Raw odds rows stay
distinct per source/bookmaker/market/selection/timestamp — consensus happens
downstream, never by merging raw records.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.odds import Bookmaker

# Display-name variants known to denote one bookmaker (reviewable, explicit).
BOOKMAKER_ALIASES: Dict[str, str] = {
    "bet365": "Bet365",
    "bet 365": "Bet365",
    "b365": "Bet365",
    "pinnacle": "Pinnacle",
    "pin": "Pinnacle",
    "william hill": "William Hill",
    "williamhill": "William Hill",
    "wh": "William Hill",
    "betway": "Betway",
    "bw": "Betway",
    "unibet": "Unibet",
    "betvictor": "Bet Victor",
    "bet victor": "Bet Victor",
    "vc": "Bet Victor",
    "ladbrokes": "Ladbrokes",
    "interwetten": "Interwetten",
    "iw": "Interwetten",
}

# Source selection label -> canonical selection (original preserved on rows).
SELECTION_MAP: Dict[str, str] = {
    "home": "home", "1": "home", "team1": "home",
    "draw": "draw", "x": "draw", "tie": "draw",
    "away": "away", "2": "away", "team2": "away",
    "over": "over", "o": "over",
    "under": "under", "u": "under",
}

MARKET_MAP: Dict[str, str] = {
    "h2h": "h2h", "1x2": "h2h", "match_winner": "h2h", "moneyline": "h2h",
    "totals": "totals", "over_under": "totals", "o_u": "totals",
    "asian_handicap": "asian_handicap", "handicap": "asian_handicap", "ah": "asian_handicap",
    "btts": "btts", "both_teams_to_score": "btts",
}


def canonical_bookmaker_name(display: str) -> str:
    key = (display or "").strip().lower()
    return BOOKMAKER_ALIASES.get(key, (display or "").strip())


def canonical_market(market_type: str) -> str:
    return MARKET_MAP.get((market_type or "").strip().lower(), (market_type or "").strip())


def canonical_selection(selection: str) -> str:
    key = (selection or "").strip().lower()
    if key in SELECTION_MAP:
        return SELECTION_MAP[key]
    # Generic fallback: "Over 2.5" -> "over_2.5" (original label preserved
    # on the raw row; this only yields the canonical form).
    return key.replace(" ", "_").replace("-", "_")


def resolve_bookmaker(db: Session, source: str, provider_bookmaker_id: str = "",
                      display_name: str = "") -> Dict:
    """Exact-key resolution first; display alias only to label, never to merge
    distinct provider IDs. New provider IDs create rows (identity evidence),
    ambiguous display names never merge."""
    if provider_bookmaker_id:
        row = db.query(Bookmaker).filter_by(
            provider=source, provider_bookmaker_id=str(provider_bookmaker_id)).first()
        if row is not None:
            return {"canonical_bookmaker_id": row.id, "display_name": row.name,
                    "method": "existing_mapping", "confidence": 0.95}
    if display_name:
        canonical = canonical_bookmaker_name(display_name)
        same_name = db.query(Bookmaker).filter_by(name=canonical).all()
        if len(same_name) == 1 and not provider_bookmaker_id:
            return {"canonical_bookmaker_id": same_name[0].id,
                    "display_name": same_name[0].name,
                    "method": "deterministic_normalization", "confidence": 0.8}
    return {"canonical_bookmaker_id": None, "display_name": display_name,
            "method": "unresolved",
            "confidence": 0.0,
            "reason": "no exact provider key; display names never merge distinct IDs"}


def bookmaker_matrix(db: Session) -> List[Dict]:
    rows = db.query(Bookmaker).order_by(Bookmaker.name.asc()).all()
    return [{"canonical_bookmaker_id": r.id, "display_name": r.name,
             "provider": r.provider,
             "provider_bookmaker_id": r.provider_bookmaker_id} for r in rows]
