"""Source records + field provenance (Phase 8).

Every normalized record stays traceable to source / source_record_id /
retrieved_at / raw reference / normalization version: raw-source evidence is
never destroyed during normalization. Canonical fields carry per-field
provenance (value + source + record + quality + observed/effective time),
never a single source label for a whole match.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    """Envelope binding a normalized payload to its raw evidence."""

    source: str = ""
    source_record_id: str = ""
    entity_type: str = ""
    retrieved_at: Optional[datetime] = None
    raw_record_reference: str = ""
    raw_payload_hash: str = ""
    normalization_version: str = "reconciliation_v1"
    payload: Dict = Field(default_factory=dict)

    def reference(self) -> str:
        return self.raw_record_reference or (
            f"{self.source}:{self.entity_type}:{self.source_record_id}")


def raw_reference(source: str, entity_type: str, source_record_id: str,
                  payload: Optional[Dict] = None) -> tuple:
    """(reference, payload_hash) for raw evidence preservation."""
    reference = f"{source}:{entity_type}:{source_record_id}"
    digest = ""
    if payload is not None:
        digest = hashlib.sha256(json.dumps(
            payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return reference, digest


class FieldValue(BaseModel):
    """One canonical field value with per-field provenance."""

    value: Any = None
    source: str = ""
    source_record_id: str = ""
    quality: str = "unknown"  # verified | estimated | unknown
    observed_at: Optional[datetime] = None
    effective_at: Optional[datetime] = None

    model_config = {"arbitrary_types_allowed": True}


def field_value(value: Any, source: str = "", source_record_id: str = "",
                quality: str = "unknown", observed_at: Optional[datetime] = None,
                effective_at: Optional[datetime] = None) -> FieldValue:
    return FieldValue(value=value, source=source,
                      source_record_id=str(source_record_id), quality=quality,
                      observed_at=observed_at, effective_at=effective_at)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
