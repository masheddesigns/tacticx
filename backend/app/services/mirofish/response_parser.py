"""Response parsing with narrative safety (Phase 16).

Structured observations are kept machine-readable; free-form narrative is
preserved verbatim but labeled simulated/scenario output and NEVER upgraded
into certainty. Certainty-claiming phrases are flagged (not rewritten, not
trusted): the narrative stays narrative and statistical probabilities are
never modified from it — there is no validated methodology for converting
qualitative narrative into probabilities.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict

from app.services.mirofish.contracts import MiroFishObservation, canonical_json

CERTAINTY_PATTERNS = (
    r"\bwill happen\b",
    r"\bguaranteed\b",
    r"\bcertain\b",
    r"\bcertainty\b",
    r"\bsure win\b",
    r"\bsurewin\b",
    r"\bconfirmed result\b",
    r"\block\b.{0,12}\bwin\b",
)

SCENARIO_FRAMING = ("under this scenario", "the simulation indicates",
                    "the simulated environment produced",
                    "this scenario was associated with")


def scan_narrative(narrative: str) -> Dict[str, Any]:
    """Flag certainty language. Returns flags; the text itself is unchanged."""
    found = []
    lowered = (narrative or "").lower()
    for pattern in CERTAINTY_PATTERNS:
        if re.search(pattern, lowered):
            found.append(pattern.strip("\\b"))
    framed = any(phrase in lowered for phrase in SCENARIO_FRAMING)
    return {"certainty_phrases": found,
            "scenario_framed": framed,
            "label": "simulated scenario output; not a statistical claim"}


def parse_validated(payload: Dict[str, Any], started_at: str,
                    completed_at: str, duration_ms: int) -> Dict[str, Any]:
    """Build the structured result from an already-validated response."""
    observations = []
    for item in payload.get("structured_observations", []) or []:
        if isinstance(item, dict):
            observations.append(MiroFishObservation(
                kind=str(item.get("kind", ""))[:64],
                statement=str(item.get("statement", ""))[:2000],
                detail=item.get("detail", {}) if isinstance(
                    item.get("detail", {}), dict) else {},
            ).model_dump())
    narrative = str(payload.get("narrative", ""))[:8000]
    scan = scan_narrative(narrative)
    result = {
        "status": "ok",
        "contract_version": payload.get("contract_version", ""),
        "match_id": payload.get("match_id", 0),
        "cutoff": payload.get("cutoff", ""),
        "scenario_id": payload.get("scenario_id", ""),
        "scenario_hash": payload.get("scenario_hash", ""),
        "baseline_prediction_hash": payload.get("baseline_prediction_hash", ""),
        "intelligence_snapshot_hash": payload.get(
            "intelligence_snapshot_hash", ""),
        "provider": payload.get("provider", ""),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "structured_observations": observations,
        "narrative": narrative,
        "narrative_safety": scan,
        "warnings": [str(w)[:300] for w in payload.get("warnings", []) or []],
        "provenance": payload.get("provenance", {}) if isinstance(
            payload.get("provenance", {}), dict) else {},
    }
    result["response_hash"] = hashlib.sha256(
        canonical_json(result).encode()).hexdigest()
    return result


def unavailable_result(code: str, detail: str, provenance: Dict[str, Any],
                       provider: str = "") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": "unavailable",
        "error_code": code,
        "error_detail": detail,
        "contract_version": provenance.get("contract_version", ""),
        "match_id": provenance.get("match_id", 0),
        "cutoff": provenance.get("cutoff", ""),
        "scenario_id": provenance.get("scenario_id", ""),
        "provider": provider,
        "started_at": now,
        "completed_at": now,
        "duration_ms": 0,
        "structured_observations": [],
        "narrative": "",
        "warnings": [],
        "provenance": provenance,
        "response_hash": hashlib.sha256(
            canonical_json({"status": "unavailable", "code": code,
                            "provenance": provenance}).encode()).hexdigest(),
    }
