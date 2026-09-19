"""Current-season acquisition orchestration (Phase 18).

Builds on the Phase 7/11 pipeline (discovery -> raw observation ->
normalization -> identity -> canonical resolution -> validation ->
append-only observation -> Match Universe). Adds: versioned season mapping,
extended status taxonomy (live/abandoned), per-competition isolation with
partial success, season-aware readiness, and five-league validation.

Prediction never initiates acquisition; acquisition never mutates
predictions. No new prediction model is created here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.services.acquisition.workflow import run_acquisition
from app.services.lifecycle.upcoming import UpcomingMatch

# Versioned provider-season <-> canonical-season mapping. Provider season
# numbering is NEVER assumed equal to TacticX numbering; each entry carries
# its validity window. Version 1 covers API-Football's August-July seasons.
SEASON_MAP_VERSION = 1
SEASON_MAP = [
    # provider, provider_season, canonical_season, competition, valid_from, valid_to
    {"provider": "api_football", "provider_season": "2026",
     "canonical_season": "2026/27", "competition": "EPL",
     "valid_from": "2026-08-01", "valid_to": "2027-07-31"},
    {"provider": "api_football", "provider_season": "2026",
     "canonical_season": "2026/27", "competition": "LA_LIGA",
     "valid_from": "2026-08-01", "valid_to": "2027-07-31"},
    {"provider": "api_football", "provider_season": "2026",
     "canonical_season": "2026/27", "competition": "SERIE_A",
     "valid_from": "2026-08-01", "valid_to": "2027-07-31"},
    {"provider": "api_football", "provider_season": "2026",
     "canonical_season": "2026/27", "competition": "BUNDESLIGA",
     "valid_from": "2026-08-01", "valid_to": "2027-07-31"},
    {"provider": "api_football", "provider_season": "2026",
     "canonical_season": "2026/27", "competition": "LIGUE_1",
     "valid_from": "2026-08-01", "valid_to": "2027-07-31"},
]

TARGET_LEAGUES = ("EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1")

# Canonical status taxonomy. Provider-native values map per source below;
# unmapped values become "unknown", never forced into "scheduled".
EXTENDED_STATUSES = ("scheduled", "postponed", "cancelled", "abandoned",
                     "live", "finished", "unknown")

# Documented per-source status mapping (extends Phase 7 STATUS_MAP with
# live/abandoned coverage).
STATUS_MAP_BY_SOURCE = {
    "api_football": {
        "ns": "scheduled", "tbd": "scheduled", "1h": "live", "ht": "live",
        "2h": "live", "et": "live", "bt": "live", "p": "live", "susp": "live",
        "int": "live", "live": "live", "ft": "finished", "aet": "finished",
        "pen": "finished", "pst": "postponed", "postponed": "postponed",
        "canc": "cancelled", "cancelled": "cancelled", "abd": "abandoned",
        "abandoned": "abandoned", "wo": "cancelled", "award": "finished",
    },
    "odds_api": {
        "scheduled": "scheduled", "upcoming": "scheduled",
    },
    "football-data.co.uk": {
        "scheduled": "scheduled", "finished": "finished",
    },
}


def normalize_source_status(source: str, raw_status: str) -> str:
    """Map a provider-native status into the canonical taxonomy."""
    mapping = STATUS_MAP_BY_SOURCE.get(source or "", {})
    key = (raw_status or "").strip().lower().replace(" ", "").replace("_", "")
    return mapping.get(key, "unknown")


def canonical_season_for(provider: str, provider_season: str,
                         competition: str) -> Optional[str]:
    """Deterministic season mapping lookup. Returns None when unmapped."""
    for entry in SEASON_MAP:
        if (entry["provider"] == provider
                and entry["provider_season"] == str(provider_season)
                and entry["competition"] == competition):
            return entry["canonical_season"]
    return None


def current_canonical_season(at: Optional[datetime] = None) -> str:
    """August-July canonical season label, e.g. 2026/27."""
    moment = at or datetime.now(timezone.utc)
    year = moment.year
    start = year if moment.month >= 8 else year - 1
    return f"{start}/{str(start + 1)[-2:]}"


def acquire_competition(db: Session, league_code: str, season: str,
                        sources=None, job: str = "current_season") -> Dict:
    """Acquire one competition's fixtures for one provider season.

    ``season`` is the PROVIDER season label (e.g. "2026"); the canonical
    season is resolved via the versioned map. Isolated per competition:
    failure here never touches other leagues' data.
    """
    from app.services.lifecycle.upcoming import default_sources, fetch_all

    outcome: Dict = {"league": league_code, "season": season, "sources": {},
                     "status": "success"}
    if sources is None:
        try:
            sources = default_sources()
        except Exception as exc:
            return {"league": league_code, "season": season,
                    "status": "failed", "error": f"no sources: {exc}"}
    now = datetime.now(timezone.utc)
    horizon = now.replace(year=now.year + 1)
    start = now
    try:
        start_year = int(str(season).split("/")[0])
        if len(str(season).split("/")) == 1:
            # Bare provider season ("2026"): window the Aug-Jul season.
            start = datetime(start_year, 8, 1, tzinfo=timezone.utc)
            horizon = datetime(start_year + 1, 7, 31, 23, 59,
                               tzinfo=timezone.utc)
    except ValueError:
        pass
    failures = 0
    for source in sources:
        name = getattr(source, "name", type(source).__name__)
        try:
            grouped = fetch_all([source], start, horizon, league_code)
            records = grouped.get(name, [])
            # Tag canonical season; leave provider season on the record.
            canonical = canonical_season_for(name, season, league_code)
            for record in records:
                if isinstance(record, UpcomingMatch) and canonical:
                    record.season = canonical
            result = run_acquisition(
                db, name, records, job=job,
                requested_scope={"league": league_code, "season": season,
                                 "canonical_season": canonical,
                                 "season_map_version": SEASON_MAP_VERSION})
            outcome["sources"][name] = result
            if result.get("status") not in ("success", "partial_success", "empty"):
                failures += 1
        except Exception as exc:
            outcome["sources"][name] = {"status": "failed",
                                        "error": f"{type(exc).__name__}: {exc}"[:300]}
            failures += 1
    if failures and len(outcome["sources"]) > failures:
        outcome["status"] = "partial"
    elif failures:
        outcome["status"] = "failed"
    return outcome


def acquire_current_season(db: Session, leagues: Optional[List[str]] = None,
                           season: str = "current",
                           sources=None) -> Dict:
    """Five-league (or subset) current-season acquisition.

    Each competition is isolated: one league's provider failure persists
    nothing for that league but never erases or corrupts the others.
    """
    targets = list(leagues) if leagues else list(TARGET_LEAGUES)
    if season == "current":
        season = current_canonical_season()
    report: Dict = {"season": season,
                    "season_map_version": SEASON_MAP_VERSION,
                    "leagues": {}, "status": "success"}
    failed = 0
    for league_code in targets:
        # Provider seasons are calendar years for August-July seasons.
        provider_season = season.split("/")[0]
        result = acquire_competition(db, league_code, provider_season,
                                     sources=sources)
        result["canonical_season"] = season
        report["leagues"][league_code] = result
        if result.get("status") not in ("success", "partial"):
            failed += 1
    if failed and failed < len(targets):
        report["status"] = "partial"
    elif failed:
        report["status"] = "failed"
    return report


def current_season_readiness(db: Session, leagues: Optional[List[str]] = None,
                             season: str = "current") -> Dict:
    """Per-league readiness split: fixtures / identity / history / market /
    eligibility. A league is never 'ready' merely because fixtures exist."""
    from app.services.acquisition.snapshot import readiness_report as match_readiness
    from app.services.freshness import eligibility

    targets = list(leagues) if leagues else list(TARGET_LEAGUES)
    if season == "current":
        season = current_canonical_season()
    now = datetime.now(timezone.utc)
    report: Dict = {"season": season, "leagues": {}}
    for league_code in targets:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            report["leagues"][league_code] = {"error": "unknown league"}
            continue
        matches = db.query(Match).filter_by(league_id=league.id).all()
        future = [m for m in matches
                  if m.kickoff_at and m.kickoff_at.replace(tzinfo=timezone.utc) > now]
        finished = [m for m in matches if (m.status or "") == "FINISHED"]
        live = [m for m in matches if (m.status or "") == "LIVE"]
        postponed = [m for m in matches if (m.status or "") == "POSTPONED"]
        eligible = ineligible = 0
        eligibility_notes: Dict[str, int] = {}
        for match in future[:50]:
            try:
                verdict = eligibility.check_eligibility(
                    db, match.id, now, mode="production_strict")
            except Exception as exc:
                verdict = {"eligible": False, "reason": str(exc)[:200]}
            if verdict.get("eligible"):
                eligible += 1
            else:
                ineligible += 1
                for note in (verdict.get("missing_families", []) or [])[:4]:
                    eligibility_notes[note] = eligibility_notes.get(note, 0) + 1
        sample = future[:10]
        details = []
        for match in sample:
            try:
                details.append(match_readiness(db, match.id))
            except Exception as exc:
                details.append({"match_id": match.id,
                                "error": str(exc)[:200]})
        report["leagues"][league_code] = {
            "fixtures": len(matches),
            "future": len(future),
            "finished": len(finished),
            "live": len(live),
            "postponed": len(postponed),
            "identity": {"resolved_teams": "see universe entry"},
            "temporal": {"mode": "production_strict"},
            "prediction_eligible": eligible,
            "prediction_ineligible": ineligible,
            "eligibility_notes": eligibility_notes,
            "sample": details,
        }
    return report


def validate_five_leagues(db: Session, season: str = "current") -> Dict:
    """Run acquisition + reconciliation + readiness across all five leagues."""
    from app.services.reconciliation.matches import reconcile_league

    report = acquire_current_season(db, season=season)

    for league_code, league_report in report["leagues"].items():
        try:
            recon = reconcile_league(db, league_code=league_code,
                                     season=season if season != "current"
                                     else current_canonical_season())
            if "error" in recon:
                league_report["reconciliation"] = {
                    "status": "failed", "error": recon["error"]}
            else:
                league_report["reconciliation"] = {
                    "status": "ok",
                    "matches_compared": recon.get("matches", 0),
                    "agreements": recon.get("agreements", 0),
                    "conflicts": recon.get("conflicts", 0),
                }
        except Exception as exc:
            league_report["reconciliation"] = {
                "status": "failed", "error": str(exc)[:300]}
    report["readiness"] = current_season_readiness(db, season=season)
    return report
