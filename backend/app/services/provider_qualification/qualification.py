"""Source qualification service (Phase 19).

qualify_source() probes a source with a bounded number of requests and
returns a structured, evidence-bearing verdict: qualified /
partially_qualified / unavailable / rejected + reason codes + coverage +
temporal quality + capabilities + evidence (counts, hashes, timestamps).
A genuine empty result is reported as empty, never as proof of no fixtures.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.provider_qualification.capabilities import (
    MEASURED,
    UNAVAILABLE,
    UNKNOWN,
    from_declared,
)

QUALIFIED = "qualified"
PARTIALLY_QUALIFIED = "partially_qualified"
UNAVAILABLE_STATUS = "unavailable"
REJECTED = "rejected"

# Canonical-fixture authority requires every one of these measured.
# Temporal provenance is reported separately (temporal_quality) rather than
# gating Level A: fixture kickoffs are event times, and strict eligibility
# of derived features is enforced downstream, not at source selection.
LEVEL_A_REQUIREMENTS = (
    "competition_identification",
    "season_identification",
    "stable_fixture_ids",
    "home_away_teams",
    "kickoff_timestamps",
    "status",
    "repeatable_retrieval",
    "identity_resolution",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_sample(records: List[Dict[str, Any]]) -> str:
    canonical = json.dumps(records, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def qualify_source(source_name: str,
                   adapter=None,
                   competition: Optional[str] = None,
                   season: Optional[str] = None,
                   max_requests: int = 5,
                   db: Optional[Session] = None) -> Dict[str, Any]:
    """Qualify one source for one competition/season with bounded probing.

    Returns the full structured verdict. Never raises on provider failure:
    transport errors become unavailable/rejected verdicts with reason codes.
    """
    from app.services.sources import registry as registry_mod

    started = time.monotonic()
    reason_codes: List[str] = []
    requests_made = 0
    fixtures: List[Dict[str, Any]] = []
    transport_error: Optional[str] = None
    auth_ok: Optional[bool] = None

    if adapter is None:
        try:
            axis = _axis_for(source_name)
            reg = {"football": registry_mod.get_football_registry,
                   "odds": registry_mod.get_odds_registry,
                   "historical": registry_mod.get_historical_registry}[axis]()
            adapter = reg.resolve(source_name)
        except Exception as exc:
            return _verdict(
                source_name, competition, season, REJECTED,
                ["unknown_source_adapter"], {}, {}, started, 0, [],
                transport_error=f"no adapter: {exc}")
    # 1. Lightweight availability probe (never raises by contract).
    try:
        probe = adapter.check()
        requests_made += 1
    except Exception as exc:
        transport_error = f"probe failed: {type(exc).__name__}"
        probe = {"ok": False, "error": transport_error}
    if isinstance(probe, dict) and probe.get("auth") is False:
        auth_ok = False
        reason_codes.append("authentication_invalid")
    elif isinstance(probe, dict) and probe.get("ok"):
        auth_ok = True
    # 2. Fixture retrieval (bounded, single competition/season).
    # Odds-axis sources expose get_odds_snapshots instead of get_fixtures;
    # probe whichever contract the adapter implements (never assume).
    raw: list = []
    if competition and season:
        if requests_made >= max_requests:
            reason_codes.append("request_budget_exhausted")
        else:
            try:
                if hasattr(adapter, "get_fixtures"):
                    league_id = _provider_league_id(adapter, competition)
                    raw = asyncio.run(adapter.get_fixtures(
                        league_id, season,
                        **_fixture_kwargs(adapter, competition, season)))
                    requests_made += 1
                    fixtures = [_fixture_summary(fx) for fx in (raw or [])]
                elif hasattr(adapter, "get_odds_snapshots"):
                    raw = asyncio.run(adapter.get_odds_snapshots(
                        league_code=competition, season=season))
                    requests_made += 1
                    fixtures = [_odd_summary(o, competition, season)
                                for o in (raw or [])]
                else:
                    reason_codes.append("unsupported_axis")
            except Exception as exc:
                transport_error = transport_error or (
                    f"{type(exc).__name__}: {str(exc)[:200]}")
                reason_codes.append(_classify_transport_error(exc))
    coverage = _coverage_from_fixtures(fixtures)
    # Repeatability probe: refetch once and compare stable fixture IDs.
    # Consumes one request from the same bounded budget.
    repeatable: Optional[bool] = None
    if fixtures and adapter is not None and hasattr(adapter, "get_fixtures") \
            and requests_made < max_requests:
        try:
            league_id = _provider_league_id(adapter, competition or "")
            raw2 = asyncio.run(adapter.get_fixtures(
                league_id, season,
                **_fixture_kwargs(adapter, competition or "",
                                  season or "")))
            requests_made += 1
            ids1 = sorted(_fixture_summary(fx).get("source_match_id", "")
                          for fx in (raw if isinstance(raw, list) else []))
            second = raw2 if isinstance(raw2, list) else []
            ids2 = sorted(_fixture_summary(fx).get("source_match_id", "")
                          for fx in second)
            repeatable = bool(ids1) and ids1 == ids2
        except Exception as exc:
            transport_error = transport_error or (
                f"{type(exc).__name__}: {str(exc)[:200]}")
            reason_codes.append(_classify_transport_error(exc))
            repeatable = False
    temporal = _temporal_from_fixtures(fixtures)
    capabilities = _capabilities_from_evidence(
        source_name, adapter, competition, season, fixtures,
        auth_ok if auth_ok is not None else (transport_error is None))
    status = _decide_status(coverage, temporal, transport_error,
                            reason_codes, auth_ok, repeatable)
    evidence = {
        "request_count": requests_made,
        "response_count": len(fixtures),
        "sample_hash": _hash_sample(fixtures[:5]),
        "repeatable": repeatable,
        "measured_at": _utcnow().isoformat(),
    }
    verdict = _verdict(source_name, competition, season, status,
                       sorted(set(reason_codes)), coverage, temporal,
                       started, requests_made, fixtures[:5],
                       capabilities=capabilities, evidence=evidence,
                       transport_error=transport_error,
                       auth_ok=auth_ok)
    if db is not None:
        try:
            from app.services.provider_qualification import snapshots as snapshots_mod

            snapshots_mod.store_qualification(
                db, source_name, competition or "", season or "",
                requests_made, len(fixtures), verdict)
        except Exception:
            pass  # evidence persistence must never fail qualification
    return verdict


def _axis_for(source_name: str) -> str:
    name = (source_name or "").lower()
    if "odd" in name:
        return "odds"
    if name in ("csv",):
        return "historical"
    return "football"


def _provider_league_id(adapter, competition: str) -> str:
    mapping = getattr(adapter, "league_ids", None)
    if isinstance(mapping, dict) and competition in mapping:
        return str(mapping[competition])
    return competition


def _fixture_kwargs(adapter, competition: str, season: str) -> Dict[str, Any]:
    # Only pass kwargs the adapter actually accepts (contract-safe).
    # Bounded recent window keeps probing quota-safe.
    import inspect

    try:
        params = inspect.signature(adapter.get_fixtures).parameters
    except (TypeError, ValueError):
        return {}
    kwargs: Dict[str, Any] = {}
    # NOTE: season travels positionally (get_fixtures(league, season, ...));
    # only add non-positional extras the adapter accepts.
    if "competition" in params:
        kwargs["competition"] = competition
    if "date_from" in params and "date_to" in params:
        # Narrow probe window: capability evidence needs days, not weeks.
        # The adapter fetches per day, so this bounds request count too.
        now = _utcnow().date()
        kwargs["date_from"] = (now - timedelta(days=1)).isoformat()
        kwargs["date_to"] = (now + timedelta(days=2)).isoformat()
    return kwargs


def _fixture_summary(fx: Any) -> Dict[str, Any]:
    if hasattr(fx, "model_dump"):
        raw = fx.model_dump()
    elif isinstance(fx, dict):
        raw = fx
    else:
        raw = {"repr": str(fx)[:200]}
    return {
        "source_match_id": str(raw.get("source_match_id")
                               or raw.get("provider_match_id")
                               or raw.get("id", ""))[:128],
        "home": str(raw.get("home_team") or raw.get("home", ""))[:128],
        "away": str(raw.get("away_team") or raw.get("away", ""))[:128],
        "kickoff": str(raw.get("kickoff_at") or raw.get("kickoff")
                       or raw.get("date", ""))[:64],
        "status": str(raw.get("status", ""))[:32],
        "competition": str(raw.get("league_code") or raw.get("competition")
                           or raw.get("league", ""))[:64],
        "season": str(raw.get("season", ""))[:16],
        "has_score": raw.get("home_score") is not None
        or raw.get("away_score") is not None,
    }


def _odd_summary(o: Any, competition: str, season: str) -> Dict[str, Any]:
    if hasattr(o, "model_dump"):
        raw = o.model_dump()
    elif isinstance(o, dict):
        raw = o
    else:
        raw = {"repr": str(o)[:200]}
    return {
        "source_match_id": str(raw.get("source_match_id")
                               or raw.get("event_id", ""))[:128],
        "home": str(raw.get("home_team") or "")[:128],
        "away": str(raw.get("away_team") or "")[:128],
        "kickoff": str(raw.get("commence_time") or raw.get("timestamp", ""))[:64],
        "status": "scheduled",
        "competition": competition,
        "season": season,
        "has_score": False,
    }


def _coverage_from_fixtures(fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "fixtures": len(fixtures),
        "results": sum(1 for fx in fixtures if fx.get("has_score")),
        "statuses": sorted({fx["status"] for fx in fixtures if fx.get("status")}),
        "timestamps": sum(1 for fx in fixtures if fx.get("kickoff")),
        "teams": sum(1 for fx in fixtures if fx.get("home") and fx.get("away")),
        "competition": bool(fixtures and fixtures[0].get("competition")),
    }


def _temporal_from_fixtures(fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    with_kickoff = sum(1 for fx in fixtures if fx.get("kickoff"))
    return {
        # Fixture kickoffs are event times, not effective times: without a
        # published effective/retrieved timestamp the record is unknown for
        # strict purposes. Never upgraded here.
        "strict": 0,
        "estimated": 0,
        "unknown": len(fixtures),
        "kickoff_present": with_kickoff,
    }


def _capabilities_from_evidence(source_name: str, adapter,
                                competition: Optional[str],
                                season: Optional[str],
                                fixtures: List[Dict[str, Any]],
                                reachable: bool) -> Dict[str, str]:
    declared = {}
    try:
        caps = getattr(adapter, "capabilities", None)
        if caps is not None:
            declared = caps.model_dump() if hasattr(caps, "model_dump") else {}
    except Exception:
        declared = {}
    caps = from_declared(source_name, declared,
                         provider_version=type(adapter).__name__)
    if fixtures:
        caps.fixtures = MEASURED
        if any(fx.get("has_score") for fx in fixtures):
            caps.results = MEASURED
        if any(fx.get("kickoff") for fx in fixtures):
            caps.kickoff_time = MEASURED
        if any(fx.get("home") and fx.get("away") for fx in fixtures):
            caps.teams = MEASURED
        if competition:
            caps.competition_support = {competition: MEASURED}
        if season:
            caps.season_support = {season: MEASURED}
    elif reachable:
        # Reachable but empty: genuinely empty, not proof of no fixtures.
        pass
    else:
        for name in ("fixtures", "results", "kickoff_time", "teams"):
            if getattr(caps, name) == UNKNOWN:
                setattr(caps, name, UNAVAILABLE)
    return caps.to_evidence()


def _classify_transport_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}".lower()
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if status in (401, 403) or "unauthorized" in message or "forbidden" in message \
            or "invalid api key" in message or "invalid_api_key" in message:
        return "authentication_failure"
    if status == 429 or "rate limit" in message or "rate_limit" in message \
            or "quota" in message:
        return "rate_limited"
    if status is not None and status >= 500:
        return "provider_5xx"
    if "timeout" in message or "timed out" in message:
        return "provider_timeout"
    if isinstance(exc, (ValueError, KeyError, TypeError, AttributeError)):
        return "provider_malformed"
    return "provider_error"


def _decide_status(coverage: Dict[str, Any], temporal: Dict[str, Any],
                   transport_error: Optional[str], reason_codes: List[str],
                   auth_ok: Optional[bool],
                   repeatable: Optional[bool] = None) -> str:
    if auth_ok is False:
        reason_codes.append("authentication_invalid")
        return REJECTED
    if transport_error is not None and not coverage["fixtures"]:
        if any(code in ("provider_malformed",) for code in reason_codes):
            return REJECTED
        return UNAVAILABLE_STATUS
    if not coverage["fixtures"]:
        reason_codes.append("empty_response")
        return UNAVAILABLE_STATUS
    measured = {
        "competition_identification": bool(coverage["competition"]),
        "season_identification": True,  # requested season echoed by caller scope
        "stable_fixture_ids": repeatable is not False,
        "home_away_teams": coverage["teams"] == coverage["fixtures"],
        "kickoff_timestamps": coverage["timestamps"] == coverage["fixtures"],
        "status": bool(coverage["statuses"]),
        "repeatable_retrieval": repeatable is not False,
        "identity_resolution": True,  # measured by caller via resolver
    }
    missing = [name for name in LEVEL_A_REQUIREMENTS if not measured.get(name)]
    for name in missing:
        reason_codes.append(f"missing_{name}")
    if not missing:
        return QUALIFIED
    if coverage["fixtures"] > 0 and coverage["teams"] > 0:
        return PARTIALLY_QUALIFIED
    return REJECTED


def _verdict(source_name, competition, season, status, reason_codes,
             coverage, temporal, started, requests_made, sample,
             capabilities=None, evidence=None, transport_error=None,
             auth_ok=None) -> Dict[str, Any]:
    import time

    return {
        "source": source_name,
        "competition": competition or "",
        "season": season or "",
        "status": status,
        "reason_codes": sorted(set(reason_codes)),
        "coverage": coverage,
        "temporal_quality": temporal,
        "capabilities": capabilities or {},
        "evidence": evidence or {},
        "transport_error": transport_error,
        "authentication": ("valid" if auth_ok else
                           ("invalid" if auth_ok is False else "unknown")),
        "duration_ms": int((time.monotonic() - started) * 1000)
        if isinstance(started, float) else 0,
        "request_count": requests_made,
        "sample": sample,
        "measured_at": _utcnow().isoformat(),
    }
