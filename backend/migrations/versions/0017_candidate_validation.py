"""candidate validation reports

Revision ID: 0017_candidate_validation
Revises: 0016_evidence
Create Date: 2026-09-23

Adds candidate_validation_reports (Phase 34 controlled candidate
validation gate; string linkage only, no production FKs).

Safety conventions (Phase 23): guarded create/index/drop, idempotent
rerun, raise on unexpected errors.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0017_candidate_validation"
down_revision = "0016_evidence"
branch_labels = None
depends_on = None

_TABLE = "candidate_validation_reports"


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
        _TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("validation_id", sa.String(64), unique=True, nullable=False),
        sa.Column("candidate_artifact_id", sa.String(64), nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("validation_config_id", sa.String(32), nullable=False),
        sa.Column("validation_config_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(32), nullable=False),
        sa.Column("evidence_state", sa.String(32), nullable=True),
        sa.Column("rule_results", sa.JSON, nullable=True),
        sa.Column("performance_summary", sa.JSON, nullable=True),
        sa.Column("uncertainty_summary", sa.JSON, nullable=True),
        sa.Column("data_quality_summary", sa.JSON, nullable=True),
        sa.Column("temporal_summary", sa.JSON, nullable=True),
        sa.Column("compatibility_summary", sa.JSON, nullable=True),
        sa.Column("operational_summary", sa.JSON, nullable=True),
        sa.Column("blocking_reasons", sa.JSON, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=True),
        sa.Column("validation_hash", sa.String(64), unique=True, nullable=False),
        _created_at(),
    )
    _safe_create_index("ix_cval_validation_id", _TABLE,
                       ["validation_id"], unique=True)
    _safe_create_index("ix_cval_candidate", _TABLE, ["candidate_artifact_id"])
    _safe_create_index("ix_cval_champion", _TABLE, ["champion_artifact_id"])
    _safe_create_index("ix_cval_snapshot", _TABLE, ["evidence_snapshot_id"])
    _safe_create_index("ix_cval_state", _TABLE, ["validation_state"])
    _safe_create_index("ix_cval_hash", _TABLE,
                       ["validation_hash"], unique=True)
    _safe_create_index("ix_cval_created_at", _TABLE, ["created_at"])


def downgrade() -> None:
    for index_name in ("ix_cval_created_at", "ix_cval_hash",
                       "ix_cval_state", "ix_cval_snapshot",
                       "ix_cval_champion", "ix_cval_candidate",
                       "ix_cval_validation_id"):
        _safe_drop_index(index_name, _TABLE)
    _safe_drop_table(_TABLE)
