"""Reusable scraper framework (Phase 1.6).

    Scraper
     ├── request()    (polite fetch: delays, ceilings, robots, caching, logging)
     ├── parse()      (versioned parser: source_x_match_parser_v1 ...)
     ├── validate()   (schema + quality checks; never silently fix)
     ├── normalize()  (→ Normalized* records with provenance)
     └── persist()    (idempotent pipeline ingest + raw provenance)

Every parser carries a version stored on raw_data_records so we always know
which parser produced a normalized record.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models.provenance import RawDataRecord
from app.logging_config import get_logger
from app.services.scraping.polite import PoliteFetcher

log = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


PARSER_REGISTRY: dict[str, str] = {}


def register_parser(name: str, version: str) -> str:
    """Register a parser version. Returns the qualified 'name@version' tag."""
    tag = f"{name}@{version}"
    PARSER_REGISTRY[tag] = version
    return tag


class ScrapeOutcome(BaseModel):
    fetched: int = 0
    parsed: int = 0
    valid: int = 0
    persisted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


def record_raw(
    db: Session,
    *,
    source: str,
    entity_type: str,
    source_record_id: str,
    payload: str,
    parser_version: str,
    status: str,
    error_message: str = "",
) -> RawDataRecord:
    """Upsert a provenance row. Returns the record (committed)."""
    payload_hash = hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()
    row = (
        db.query(RawDataRecord)
        .filter_by(source=source, entity_type=entity_type, source_record_id=source_record_id)
        .first()
    )
    now = utcnow()
    if row:
        row.payload_hash = payload_hash
        row.parser_version = parser_version
        row.processed_at = now
        row.processing_status = status
        row.error_message = (error_message or "")[:1024]
        db.commit()
        return row
    row = RawDataRecord(
        source=source, entity_type=entity_type, source_record_id=source_record_id,
        retrieved_at=now, payload_hash=payload_hash, parser_version=parser_version,
        processed_at=now, processing_status=status, error_message=(error_message or "")[:1024],
    )
    db.add(row)
    db.commit()
    return row


class BaseScraper:
    """Template: subclasses implement parse/validate/normalize/persist."""

    source_name: str = "base"
    parser_name: str = "base_parser"
    parser_version: str = "v1"
    entity_type: str = "record"

    def __init__(self, db: Optional[Session] = None, fetcher: Optional[PoliteFetcher] = None,
                 db_session_factory=None):
        self.db = db
        self.db_session_factory = db_session_factory
        self.fetcher = fetcher or PoliteFetcher(source=self.source_name,
                                                db_session_factory=db_session_factory)
        self.parser_tag = register_parser(self.parser_name, self.parser_version)

    # -- request ---------------------------------------------------------
    async def request(self, url: str) -> str:
        return await self.fetcher.fetch_text(url)

    # -- parse -----------------------------------------------------------
    def parse(self, payload: str) -> list[dict]:
        raise NotImplementedError

    # -- validate --------------------------------------------------------
    def validate(self, row: dict) -> list[str]:
        """Return a list of issue strings; empty means valid."""
        return []

    # -- normalize -------------------------------------------------------
    def normalize(self, row: dict) -> Any:
        raise NotImplementedError

    # -- persist ---------------------------------------------------------
    def persist(self, db: Session, record: Any) -> str:
        """Persist one normalized record. Returns: inserted|updated|duplicate|quarantined."""
        raise NotImplementedError

    # -- driver ----------------------------------------------------------
    def source_record_id(self, row: dict) -> str:
        return str(row.get("id", "") or "")

    async def run_url(self, db: Session, url: str, *, dry_run: bool = False) -> ScrapeOutcome:
        outcome = ScrapeOutcome()
        try:
            payload = await self.request(url)
        except Exception as exc:  # noqa: BLE001 — graceful failure, logged + recorded
            log.warning("scrape request failed source=%s url=%s err=%s", self.source_name, url, exc)
            outcome.failed += 1
            outcome.errors.append(f"request: {exc}"[:300])
            return outcome
        outcome.fetched += 1
        try:
            rows = self.parse(payload)
        except Exception as exc:  # noqa: BLE001 — parser failure is recorded, not raised
            log.warning("scrape parse failed source=%s parser=%s err=%s",
                        self.source_name, self.parser_tag, exc)
            record_raw(db, source=self.source_name, entity_type=self.entity_type,
                       source_record_id=url, payload=payload[:4000],
                       parser_version=self.parser_tag, status="failed", error_message=str(exc))
            outcome.failed += 1
            outcome.errors.append(f"parse: {exc}"[:300])
            return outcome
        outcome.parsed = len(rows)
        for row in rows:
            if not isinstance(row, dict):
                outcome.quarantined += 1
                continue
            rid = self.source_record_id(row) or f"row:{outcome.parsed}"
            issues = self.validate(row)
            if issues:
                if not dry_run:
                    record_raw(db, source=self.source_name, entity_type=self.entity_type,
                               source_record_id=rid, payload=str(row)[:4000],
                               parser_version=self.parser_tag, status="quarantined",
                               error_message="; ".join(issues)[:1000])
                outcome.quarantined += 1
                continue
            outcome.valid += 1
            try:
                record = self.normalize(row)
            except Exception as exc:  # noqa: BLE001
                if not dry_run:
                    record_raw(db, source=self.source_name, entity_type=self.entity_type,
                               source_record_id=rid, payload=str(row)[:4000],
                               parser_version=self.parser_tag, status="failed",
                               error_message=str(exc))
                outcome.failed += 1
                outcome.errors.append(f"normalize: {exc}"[:300])
                continue
            if dry_run:
                outcome.persisted += 1
                continue
            try:
                result = self.persist(db, record)
                if result == "duplicate":
                    outcome.duplicates += 1
                    record_raw(db, source=self.source_name, entity_type=self.entity_type,
                               source_record_id=rid, payload=str(row)[:4000],
                               parser_version=self.parser_tag, status="duplicate")
                else:
                    outcome.persisted += 1
                    record_raw(db, source=self.source_name, entity_type=self.entity_type,
                               source_record_id=rid, payload=str(row)[:4000],
                               parser_version=self.parser_tag, status="processed")
            except Exception as exc:  # noqa: BLE001
                record_raw(db, source=self.source_name, entity_type=self.entity_type,
                           source_record_id=rid, payload=str(row)[:4000],
                           parser_version=self.parser_tag, status="failed",
                           error_message=str(exc))
                outcome.failed += 1
                outcome.errors.append(f"persist: {exc}"[:300])
        return outcome
