"""real-world evidence

Revision ID: 0016_evidence
Revises: 0015_shadow_execution
Create Date: 2026-09-23

Adds evidence_cohorts and evidence_snapshots (Phase 33 real-world
performance validation; string linkage only, no production FKs).

Safety conventions (Phase 23): guarded create/index/drop, idempotent
rerun, raise on unexpected errors.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0016_evidence"
down_revision = "0015_shadow_execution"
branch_labels = None
depends_on = None

_COHORT = "evidence_cohorts"
_SNAPSHOT = "evidence_snapshots"


def _safe_create_table(name: str, *columns, **kwargs) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if name not in insp.get_table_names():
        op.create_table(name, *columns, **kwargs)


def _safe_create_index(
    index_name: str, table_name: str, columns: list, **kwargs
) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table_name not in insp.get_table_names():
        return
    existing = [idx["name"] for idx in insp.get_indexes(table_name)]
    if index_name in existing:
        return
    try:
        op.create_index(index_name, table_name, columns, **kwargs)
    except (sa.exc.OperationalError, sa.exc.ProgrammingError) as exc:
        msg = str(exc).lower()
        if "already exists" not in msg and "duplicate" not in msg:
            raise


def _safe_drop_index(index_name: str, table_name: str = None, **kwargs) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table_name and table_name not in insp.get_table_names():
        return
    existing = [idx["name"] for idx in insp.get_indexes(table_name)] if table_name else []
    if index_name not in existing:
        return
    try:
        op.drop_index(index_name, table_name=table_name, **kwargs)
    except (sa.exc.OperationalError, sa.exc.ProgrammingError) as exc:
        msg = str(exc).lower()
        if "does not exist" not in msg and "not found" not in msg:
            raise


def _safe_drop_table(name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if name in insp.get_table_names():
        op.drop_table(name)


def _created_at():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"))


def upgrade() -> None:
    _safe_create_table(
        _COHORT,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cohort_id", sa.String(64), unique=True, nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=True),
        sa.Column("challenger_artifact_id", sa.String(64), nullable=True),
        sa.Column("competitions", sa.JSON, nullable=True),
        sa.Column("seasons", sa.JSON, nullable=True),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prediction_mode", sa.String(32), nullable=False,
                  default="PRE_MATCH"),
        sa.Column("min_completeness", sa.Float, nullable=False, default=1.0),
        sa.Column("query_fingerprint", sa.JSON, nullable=True),
        sa.Column("cohort_hash", sa.String(64), unique=True, nullable=False),
        _created_at(),
    )
    _safe_create_index("ix_evd_coh_cohort_id", _COHORT,
                       ["cohort_id"], unique=True)
    _safe_create_index("ix_evd_coh_hash", _COHORT,
                       ["cohort_hash"], unique=True)
    _safe_create_index("ix_evd_coh_created_at", _COHORT, ["created_at"])

    _safe_create_table(
        _SNAPSHOT,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("snapshot_id", sa.String(64), unique=True, nullable=False),
        sa.Column("cohort_id", sa.String(64), nullable=False),
        sa.Column("cohort_hash", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False,
                  default="evidence_calc_v1"),
        sa.Column("observation_count", sa.Integer, nullable=False, default=0),
        sa.Column("paired_count", sa.Integer, nullable=False, default=0),
        sa.Column("excluded_count", sa.Integer, nullable=False, default=0),
        sa.Column("observation_ids", sa.JSON, nullable=True),
        sa.Column("champion_metrics", sa.JSON, nullable=True),
        sa.Column("challenger_metrics", sa.JSON, nullable=True),
        sa.Column("differences", sa.JSON, nullable=True),
        sa.Column("uncertainty", sa.JSON, nullable=True),
        sa.Column("calibration", sa.JSON, nullable=True),
        sa.Column("data_quality", sa.JSON, nullable=True),
        sa.Column("temporal_audit", sa.JSON, nullable=True),
        sa.Column("evidence_state", sa.String(32), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), unique=True, nullable=False),
        _created_at(),
    )
    _safe_create_index("ix_evd_snap_snapshot_id", _SNAPSHOT,
                       ["snapshot_id"], unique=True)
    _safe_create_index("ix_evd_snap_cohort_id", _SNAPSHOT, ["cohort_id"])
    _safe_create_index("ix_evd_snap_state", _SNAPSHOT, ["evidence_state"])
    _safe_create_index("ix_evd_snap_hash", _SNAPSHOT,
                       ["snapshot_hash"], unique=True)
    _safe_create_index("ix_evd_snap_created_at", _SNAPSHOT, ["created_at"])


def downgrade() -> None:
    for index_name in ("ix_evd_snap_created_at", "ix_evd_snap_hash",
                       "ix_evd_snap_state", "ix_evd_snap_cohort_id",
                       "ix_evd_snap_snapshot_id"):
        _safe_drop_index(index_name, _SNAPSHOT)
    _safe_drop_table(_SNAPSHOT)

    for index_name in ("ix_evd_coh_created_at", "ix_evd_coh_hash",
                       "ix_evd_coh_cohort_id"):
        _safe_drop_index(index_name, _COHORT)
    _safe_drop_table(_COHORT)
