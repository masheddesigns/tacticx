"""Phase 8 reconciliation tables.

New tables (no migration needed — create_all pattern). The legacy
source_conflicts table is left untouched; ReconciliationConflict carries
the full Phase 8 conflict schema. Resolved conflicts are never deleted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReconciliationConflict(Base):
    """One field-level disagreement between two sources. Never deleted."""

    __tablename__ = "reconciliation_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    canonical_entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field: Mapped[str] = mapped_column(String(64))
    source_a: Mapped[str] = mapped_column(String(64), default="")
    source_b: Mapped[str] = mapped_column(String(64), default="")
    value_a: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    value_b: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    classification: Mapped[str] = mapped_column(String(32), default="unknown")
    resolution_status: Mapped[str] = mapped_column(String(32), default="unresolved",
                                                  index=True)
    resolved_by: Mapped[str] = mapped_column(String(64), default="")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_recon_conflict_entity", "entity_type", "canonical_entity_id"),
    )


class CanonicalFieldVersion(Base):
    """Version history of canonical field changes (old/new/source/reason)."""

    __tablename__ = "canonical_field_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    canonical_entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_canon_version_entity", "entity_type", "canonical_entity_id", "field"),
    )


class UnresolvedRecord(Base):
    """Persistent queue for records that cannot be canonically resolved."""

    __tablename__ = "unresolved_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(String(512), default="")
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    dedup_key: Mapped[str] = mapped_column(String(128), default="", index=True)


class ManualMapping(Base):
    """Audited, versioned, source-specific explicit mappings."""

    __tablename__ = "manual_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    canonical_entity_id: Mapped[int] = mapped_column(Integer, index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="cli")
    version: Mapped[int] = mapped_column(Integer, default=1)
    superseded_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class StatDefinition(Base):
    """Semantic definition of one (source, raw stat) measurement."""

    __tablename__ = "stat_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    provider_definition: Mapped[str] = mapped_column(String(512), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    aggregation: Mapped[str] = mapped_column(String(64), default="")
    canonical_name: Mapped[str] = mapped_column(String(64), default="")
