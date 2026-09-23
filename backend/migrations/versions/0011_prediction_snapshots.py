"""prematch prediction snapshots

Revision ID: 0011_prediction_snapshots
Revises: 0010_prematch_readiness
Create Date: 2026-09-23

Adds prediction_feature_snapshots and prematch_prediction_snapshots
(Phase 26 pre-match prediction execution layer).

Safety conventions (Phase 23):
- _safe_create_table: no-op if table already exists (idempotent on fresh DB)
- _safe_create_index: no-op if index already exists
- _safe_drop_index / _safe_drop_table: no-op if absent (safe downgrade)
- Raises on unexpected errors (no broad exception swallowing)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0011_prediction_snapshots"
down_revision = "0010_prematch_readiness"
branch_labels = None
depends_on = None

_FEATURE_TABLE = "prediction_feature_snapshots"
_PREDICTION_TABLE = "prematch_prediction_snapshots"


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


def upgrade() -> None:
    _safe_create_table(
        _FEATURE_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("snapshot_id", sa.String(64), unique=True, nullable=False),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(32), nullable=False, default="features_v1"),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("features", sa.JSON, nullable=True),
        sa.Column("provenance", sa.JSON, nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_pred_feat_snapshot_id", _FEATURE_TABLE, ["snapshot_id"], unique=True)
    _safe_create_index("ix_pred_feat_match_id", _FEATURE_TABLE, ["match_id"])
    _safe_create_index("ix_pred_feat_snapshot_hash", _FEATURE_TABLE, ["snapshot_hash"])
    _safe_create_index("ix_pred_feat_created_at", _FEATURE_TABLE, ["created_at"])
    _safe_create_index("ix_pred_feat_match_hash", _FEATURE_TABLE,
                       ["match_id", "snapshot_hash"], unique=True)

    _safe_create_table(
        _PREDICTION_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("prediction_id", sa.String(64), unique=True, nullable=False),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("prediction_version", sa.Integer, nullable=False, default=1),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prediction_mode", sa.String(32), nullable=False, default="PRE_MATCH"),
        sa.Column("cutoff_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kickoff_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("readiness_certificate_id", sa.String(64), nullable=False),
        sa.Column("readiness_certificate_hash", sa.String(64), nullable=False),
        sa.Column("readiness_state", sa.String(32), nullable=False),
        sa.Column("feature_snapshot_id", sa.String(64), nullable=False),
        sa.Column("feature_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("prediction_payload", sa.JSON, nullable=True),
        sa.Column("prediction_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("execution_key", sa.String(64), unique=True, nullable=False),
        sa.Column("provenance", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_prematch_pred_prediction_id", _PREDICTION_TABLE,
                       ["prediction_id"], unique=True)
    _safe_create_index("ix_prematch_pred_match_id", _PREDICTION_TABLE, ["match_id"])
    _safe_create_index("ix_prematch_pred_model_id", _PREDICTION_TABLE, ["model_id"])
    _safe_create_index("ix_prematch_pred_readiness_state", _PREDICTION_TABLE,
                       ["readiness_state"])
    _safe_create_index("ix_prematch_pred_cert_id", _PREDICTION_TABLE,
                       ["readiness_certificate_id"])
    _safe_create_index("ix_prematch_pred_feature_snapshot_id", _PREDICTION_TABLE,
                       ["feature_snapshot_id"])
    _safe_create_index("ix_prematch_pred_prediction_hash", _PREDICTION_TABLE,
                       ["prediction_hash"], unique=True)
    _safe_create_index("ix_prematch_pred_execution_key", _PREDICTION_TABLE,
                       ["execution_key"], unique=True)
    _safe_create_index("ix_prematch_pred_created_at", _PREDICTION_TABLE, ["created_at"])
    _safe_create_index("ix_prematch_pred_match_created", _PREDICTION_TABLE,
                       ["match_id", "created_at"])
    _safe_create_index("ix_prematch_pred_model_version", _PREDICTION_TABLE,
                       ["model_id", "model_version"])


def downgrade() -> None:
    _safe_drop_index("ix_prematch_pred_model_version", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_match_created", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_created_at", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_execution_key", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_prediction_hash", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_feature_snapshot_id", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_cert_id", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_readiness_state", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_model_id", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_match_id", _PREDICTION_TABLE)
    _safe_drop_index("ix_prematch_pred_prediction_id", _PREDICTION_TABLE)
    _safe_drop_table(_PREDICTION_TABLE)

    _safe_drop_index("ix_pred_feat_match_hash", _FEATURE_TABLE)
    _safe_drop_index("ix_pred_feat_created_at", _FEATURE_TABLE)
    _safe_drop_index("ix_pred_feat_snapshot_hash", _FEATURE_TABLE)
    _safe_drop_index("ix_pred_feat_match_id", _FEATURE_TABLE)
    _safe_drop_index("ix_pred_feat_snapshot_id", _FEATURE_TABLE)
    _safe_drop_table(_FEATURE_TABLE)
