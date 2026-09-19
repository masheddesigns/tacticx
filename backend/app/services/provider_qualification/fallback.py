"""Fallback orchestration across qualified sources (Phase 19).

Sources are attempted in qualification/priority order. Outcome classes are
distinguished: unavailable / empty / unsupported / partial / malformed /
rate-limited / auth-failure. A genuine empty result never auto-triggers
fallback unless the plan's qualification policy permits it. Previously
persisted observations are never deleted on fallback or switch.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

OUTCOME_SUCCESS = "success"
OUTCOME_PARTIAL = "partial"
OUTCOME_EMPTY = "empty"
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_MALFORMED = "malformed"
OUTCOME_RATE_LIMITED = "rate_limited"
OUTCOME_AUTH_FAILURE = "auth_failure"
OUTCOME_UNAVAILABLE = "unavailable"

FALLBACK_ELIGIBLE = {OUTCOME_UNAVAILABLE, OUTCOME_MALFORMED,
                     OUTCOME_RATE_LIMITED, OUTCOME_PARTIAL}


def classify_outcome(records: Optional[List[Any]],
                     error: Optional[Exception]) -> str:
    """Classify one source attempt. Empty-without-error is 'empty', which
    only falls back when the plan explicitly allows it."""
    if error is not None:
        from app.services.provider_qualification.qualification import (
            _classify_transport_error,
        )

        kind = _classify_transport_error(error)
        mapping = {
            "authentication_failure": OUTCOME_AUTH_FAILURE,
            "rate_limited": OUTCOME_RATE_LIMITED,
            "provider_malformed": OUTCOME_MALFORMED,
            "provider_5xx": OUTCOME_UNAVAILABLE,
            "provider_timeout": OUTCOME_UNAVAILABLE,
            "provider_error": OUTCOME_UNAVAILABLE,
        }
        return mapping.get(kind, OUTCOME_UNAVAILABLE)
    if records is None:
        return OUTCOME_UNSUPPORTED
    if len(records) == 0:
        return OUTCOME_EMPTY
    return OUTCOME_SUCCESS


async def run_with_fallback(
    attempts: List[Dict[str, Any]],
    allow_empty_fallback: bool = False,
) -> Dict[str, Any]:
    """Run ordered source attempts.

    Each attempt: {"source_id": str, "call": async-callable -> records|None}.
    Returns per-source outcomes plus the selected records. Stops at the
    first success (or partial); falls back only on eligible outcomes, or on
    empty when explicitly allowed.
    """
    outcomes: List[Dict[str, Any]] = []
    selected: Optional[List[Any]] = None
    selected_source: Optional[str] = None
    for attempt in attempts:
        source_id = attempt["source_id"]
        try:
            result = attempt["call"]()
            records = await result if asyncio.iscoroutine(result) else result
            outcome = classify_outcome(records, None)
            outcomes.append({"source_id": source_id, "outcome": outcome,
                             "records": len(records or [])})
            if outcome == OUTCOME_SUCCESS:
                selected, selected_source = records, source_id
                break
            if outcome == OUTCOME_PARTIAL:
                selected, selected_source = records, source_id
                break
            if outcome == OUTCOME_EMPTY and allow_empty_fallback:
                continue
            if outcome in FALLBACK_ELIGIBLE:
                continue
            break  # auth failure / unsupported: stop, do not cascade
        except Exception as exc:
            outcome = classify_outcome(None, exc)
            outcomes.append({"source_id": source_id, "outcome": outcome,
                             "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            if outcome in FALLBACK_ELIGIBLE:
                continue
            break
    return {"selected_source": selected_source, "records": selected or [],
            "outcomes": outcomes,
            "used_fallback": len(outcomes) > 1}
