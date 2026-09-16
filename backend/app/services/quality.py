"""Data quality validation (Phase 1.6).

Validators RETURN issues — they never silently fix data. The pipeline
quarantines offending records (marked for review) instead of persisting them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QualityIssue(BaseModel):
    field: str = ""
    message: str = ""
    severity: str = "error"  # error | warning


class QualityReport(BaseModel):
    valid: bool = True
    issues: list[QualityIssue] = Field(default_factory=list)

    def error(self, field: str, message: str) -> None:
        self.valid = False
        self.issues.append(QualityIssue(field=field, message=message, severity="error"))

    def warn(self, field: str, message: str) -> None:
        self.issues.append(QualityIssue(field=field, message=message, severity="warning"))

    def messages(self) -> list[str]:
        return [f"{i.field}: {i.message}" for i in self.issues]


def _check_score(value: Optional[int], field: str, report: QualityReport) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        report.error(field, f"not an integer: {value!r}")
    elif value < 0:
        report.error(field, f"goals cannot be negative: {value}")
    elif value > 30:
        report.error(field, f"impossible score: {value}")


def validate_match(home_team: str, away_team: str, home_score: Optional[int] = None,
                   away_score: Optional[int] = None,
                   kickoff_at: Optional[datetime] = None,
                   league_code: str = "", season: str = "") -> QualityReport:
    report = QualityReport()
    if not (home_team or "").strip():
        report.error("home_team", "missing required home team")
    if not (away_team or "").strip():
        report.error("away_team", "missing required away team")
    if (home_team or "").strip() and (home_team or "").strip().lower() == (away_team or "").strip().lower():
        report.error("teams", "home_team == away_team")
    _check_score(home_score, "home_score", report)
    _check_score(away_score, "away_score", report)
    if home_score is None and away_score is not None:
        report.warn("home_score", "away score without home score")
    if away_score is None and home_score is not None:
        report.warn("away_score", "home score without away score")
    if kickoff_at is not None and not isinstance(kickoff_at, datetime):
        report.error("kickoff_at", f"invalid timestamp: {kickoff_at!r}")
    if not (league_code or "").strip():
        report.error("league_code", "missing required competition")
    return report


def validate_stat(stat_name: str, stat_value: str) -> QualityReport:
    report = QualityReport()
    if not (stat_name or "").strip():
        report.error("stat_name", "missing stat name")
        return report
    name = stat_name.strip().lower()
    try:
        numeric = float(str(stat_value).rstrip("%"))
    except (TypeError, ValueError):
        if name not in ("raw",):
            report.warn("stat_value", f"non-numeric value: {stat_value!r}")
        return report
    if "possession" in name and not 0.0 <= numeric <= 100.0:
        report.error("stat_value", f"possession out of range 0-100: {stat_value!r}")
    elif numeric < 0:
        report.error("stat_value", f"statistic cannot be negative: {stat_name}={stat_value!r}")
    return report


def validate_odds(price: float, selection: str = "", market: str = "") -> QualityReport:
    report = QualityReport()
    try:
        value = float(price)
    except (TypeError, ValueError):
        report.error("price", f"not a number: {price!r}")
        return report
    if not value > 1.0:
        report.error("price", f"decimal odds must be > 1.0: {price!r} ({market}/{selection})")
    elif value > 10000:
        report.error("price", f"suspicious price: {price!r} ({market}/{selection})")
    if not (selection or "").strip():
        report.error("selection", "missing selection")
    if not (market or "").strip():
        report.error("market", "missing market")
    return report


def validate_event(minute: Optional[int], event_type: str) -> QualityReport:
    report = QualityReport()
    if minute is not None and (not isinstance(minute, int) or isinstance(minute, bool)
                               or not -5 <= minute <= 150):
        report.error("minute", f"implausible minute: {minute!r}")
    if not (event_type or "").strip():
        report.error("event_type", "missing event type")
    return report


def validate_minute(minute: Optional[int], minute_added: Optional[int] = None) -> QualityReport:
    """Valid football minute representation, including stoppage time."""
    report = QualityReport()
    if minute is not None and (not isinstance(minute, int) or isinstance(minute, bool)
                               or not 0 <= minute <= 120):
        report.error("minute", f"implausible minute: {minute!r}")
    if minute_added is not None and (not isinstance(minute_added, int)
                                     or isinstance(minute_added, bool)
                                     or not 0 <= minute_added <= 30):
        report.error("minute_added", f"implausible added time: {minute_added!r}")
    return report


def validate_xg(value: object, field: str = "expected_goals") -> QualityReport:
    """xG must be a non-negative number. Never estimated — source values only."""
    report = QualityReport()
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        report.error(field, f"xG is not a number: {value!r}")
        return report
    if numeric != numeric:  # NaN
        report.error(field, "xG is NaN")
    elif numeric < 0:
        report.error(field, f"xG cannot be negative: {value!r}")
    elif numeric > 15:
        report.error(field, f"implausible xG: {value!r}")
    return report


VALID_TEMPORAL = ("verified", "estimated", "unknown")

LEAKAGE_RISK = "LEAKAGE_RISK"


def audit_leakage(db) -> dict:
    """Flag feature records that may postdate the pre-match cutoff (kickoff).

    For every match, prediction_cutoff = kickoff. A feature record is flagged
    LEAKAGE_RISK when its timing is unknown OR its effective/observed time is
    after cutoff. Nothing is deleted — Phase 2 consumes these flags to filter.

    Checks: match_statistics (effective_at), match_events (effective_at),
    lineups (effective_at), standings (effective_at), odds_snapshots
    (non-live snapshots timestamped after kickoff).
    """
    from app.db.models.core import Lineup, Match, MatchEvent, MatchStatistic, Standing
    from app.db.models.odds import OddsSnapshot

    def _aware(dt):
        from datetime import timezone as _tz

        if dt is None:
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=_tz.utc)

    flags: list[dict] = []
    counts = {"statistics": 0, "events": 0, "lineups": 0, "standings": 0, "odds": 0}
    matches = {m.id: m for m in db.query(Match).all()}

    def cutoff(mid: int):
        m = matches.get(mid)
        return _aware(m.kickoff_at) if m else None

    for row in db.query(MatchStatistic).all():
        cut, eff = cutoff(row.match_id), _aware(row.effective_at)
        if cut is None or eff is None or eff > cut:
            counts["statistics"] += 1
            if len(flags) < 20:
                flags.append({"entity": "statistic", "match_id": row.match_id,
                              "stat": row.stat_name, "reason": _reason(cut, eff)})
    for row in db.query(MatchEvent).all():
        cut, eff = cutoff(row.match_id), _aware(row.effective_at)
        if cut is None or eff is None or eff > cut:
            counts["events"] += 1
            if len(flags) < 20:
                flags.append({"entity": "event", "match_id": row.match_id,
                              "stat": row.event_type, "reason": _reason(cut, eff)})
    for row in db.query(Lineup).all():
        cut, eff = cutoff(row.match_id), _aware(row.effective_at)
        if cut is None or eff is None or eff > cut:
            counts["lineups"] += 1
            if len(flags) < 20:
                flags.append({"entity": "lineup", "match_id": row.match_id,
                              "stat": row.player_name, "reason": _reason(cut, eff)})
    for row in db.query(Standing).all():
        eff = _aware(row.effective_at)
        if eff is None:
            counts["standings"] += 1
            if len(flags) < 20:
                flags.append({"entity": "standing", "match_id": None,
                              "stat": f"league={row.league_id} season={row.season}",
                              "reason": "unknown timing"})
    for row in db.query(OddsSnapshot).all():
        cut, ts = cutoff(row.match_id), _aware(row.timestamp)
        if row.is_live:
            continue  # live odds are post-kickoff by definition, not leakage
        # Closing lines stamped AT kickoff cannot prove pre-kickoff
        # availability, so >= (not just >) is flagged here.
        if cut is None or ts is None or ts >= cut:
            counts["odds"] += 1
            if len(flags) < 20:
                flags.append({"entity": "odds", "match_id": row.match_id,
                              "stat": row.market_type, "reason": _reason(cut, ts)})
    return {"counts": counts, "total": sum(counts.values()), "examples": flags}


def _reason(cutoff, moment) -> str:
    if cutoff is None:
        return "LEAKAGE_RISK: match kickoff unknown"
    if moment is None:
        return "LEAKAGE_RISK: timing unknown"
    return "LEAKAGE_RISK: effective after kickoff"


def assess_temporal_quality(    event_time: Optional[datetime] = None,
    published_at: Optional[datetime] = None,
    effective_at: Optional[datetime] = None,
    collected_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """Leakage flag for Phase 2 filtering (never deletes, only flags).

    verified: full timing chain known and consistent (effective/published at or
      before collection; event not in the future relative to collection).
    estimated: event time known but publication/collection inferred.
    unknown: timing cannot be established.
    """
    from datetime import timezone as _tz

    moment = now or datetime.now(_tz.utc)
    anchors = [a for a in (published_at, effective_at, collected_at) if a is not None]
    if event_time is None and not anchors:
        return "unknown"
    try:
        if event_time is not None and collected_at is not None and event_time > collected_at:
            return "unknown"  # event after collection: inconsistent, flag it
        if collected_at is not None and collected_at > moment:
            return "unknown"  # collection in the future: clock skew, flag it
    except TypeError:
        return "unknown"  # naive vs aware: cannot establish ordering
    if published_at is not None or effective_at is not None:
        return "verified"
    if event_time is not None:
        return "estimated"
    return "unknown"
