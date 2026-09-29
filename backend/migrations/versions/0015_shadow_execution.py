"""shadow execution bindings

Revision ID: 0015_shadow_execution
Revises: 0014_model_governance
Create Date: 2026-09-23

Phase 32 real-data champion/challenger shadow pipeline:
- Extends shadow_prediction_snapshots with shared Phase 26 feature
  snapshot binding, production prediction linkage, and a deterministic
  idempotency key (no data rewrite; additive columns only).
- Creates shadow_evaluation_records for immutable challenger-vs-champion
  scoring against shared verified outcomes.

Safety conventions (Phase 23):
- Additive changes only; guarded by inspector checks (idempotent rerun).
- Downgrade removes what upgrade added, in reverse order.
- Raises on unexpected errors (no broad exception swallowing).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0015_shadow_execution"
down_revision = "0014_model_governance"
branch_labels = None
depends_on = None

_SHADOW = "shadow_prediction_snapshots"
_SHADOW_EVAL = "shadow_evaluation_records"


def _columns(table_name: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table_name not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(table_name)}


def _safe_add_column(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _safe_drop_column(table_name: str, column_name: str) -> None:
    if column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


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
    # Shared-input bindings on the existing shadow table (additive only).
    _safe_add_column(
        _SHADOW, sa.Column("feature_snapshot_id", sa.String(64), nullable=True))
    _safe_add_column(
        _SHADOW, sa.Column("production_prediction_id", sa.String(64),
                           nullable=True))
    _safe_add_column(
        _SHADOW, sa.Column("shadow_execution_key", sa.String(64),
                           nullable=True))
    _safe_add_column(
        _SHADOW, sa.Column("evaluation_state", sa.String(32), nullable=False,
                           server_default="PENDING"))
    _safe_create_index("ix_gov_shdw_feature_snapshot_id", _SHADOW,
                       ["feature_snapshot_id"])
    _safe_create_index("ix_gov_shdw_production_prediction_id", _SHADOW,
                       ["production_prediction_id"])
    _safe_create_index("ix_gov_shdw_execution_key", _SHADOW,
                       ["shadow_execution_key"], unique=True)

    _safe_create_table(
        _SHADOW_EVAL,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("evaluation_id", sa.String(64), unique=True, nullable=False),
        sa.Column("shadow_id", sa.String(64), nullable=False),
        sa.Column("match_id", sa.Integer, nullable=False),
        sa.Column("challenger_artifact_id", sa.String(64), nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=False),
        sa.Column("outcome_snapshot_id", sa.String(64), nullable=False),
        sa.Column("outcome_hash", sa.String(64), nullable=False),
        sa.Column("champion_metrics", sa.JSON, nullable=True),
        sa.Column("challenger_metrics", sa.JSON, nullable=True),
        sa.Column("differences", sa.JSON, nullable=True),
        sa.Column("sample_note", sa.String(256), nullable=False, default=""),
        sa.Column("evaluation_hash", sa.String(64), unique=True, nullable=False),
        _created_at(),
    )
    _safe_create_index("ix_shdw_eval_evaluation_id", _SHADOW_EVAL,
                       ["evaluation_id"], unique=True)
    _safe_create_index("ix_shdw_eval_shadow_id", _SHADOW_EVAL, ["shadow_id"])
    _safe_create_index("ix_shdw_eval_match_id", _SHADOW_EVAL, ["match_id"])
    _safe_create_index("ix_shdw_eval_challenger", _SHADOW_EVAL,
                       ["challenger_artifact_id"])
    _safe_create_index("ix_shdw_eval_champion", _SHADOW_EVAL,
                       ["champion_artifact_id"])
    _safe_create_index("ix_shdw_eval_hash", _SHADOW_EVAL,
                       ["evaluation_hash"], unique=True)
    _safe_create_index("ix_shdw_eval_created_at", _SHADOW_EVAL, ["created_at"])


def downgrade() -> None:
    for index_name in ("ix_shdw_eval_created_at", "ix_shdw_eval_hash",
                       "ix_shdw_eval_champion", "ix_shdw_eval_challenger",
                       "ix_shdw_eval_match_id", "ix_shdw_eval_shadow_id",
                       "ix_shdw_eval_evaluation_id"):
        _safe_drop_index(index_name, _SHADOW_EVAL)
    _safe_drop_table(_SHADOW_EVAL)

    _safe_drop_index("ix_gov_shdw_execution_key", _SHADOW)
    _safe_drop_index("ix_gov_shdw_production_prediction_id", _SHADOW)
    _safe_drop_index("ix_gov_shdw_feature_snapshot_id", _SHADOW)
    _safe_drop_column(_SHADOW, "evaluation_state")
    _safe_drop_column(_SHADOW, "shadow_execution_key")
    _safe_drop_column(_SHADOW, "production_prediction_id")
    _safe_drop_column(_SHADOW, "feature_snapshot_id")
