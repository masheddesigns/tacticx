"""prediction evaluation records

Revision ID: 0012_evaluation_records
Revises: 0011_prediction_snapshots
Create Date: 2026-09-23

Adds match_outcome_snapshots and prediction_evaluation_records
(Phase 27 prediction evaluation lifecycle).

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
revision = "0012_evaluation_records"
down_revision = "0011_prediction_snapshots"
branch_labels = None
depends_on = None

_OUTCOME_TABLE = "match_outcome_snapshots"
_EVAL_TABLE = "prediction_evaluation_records"


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
        _OUTCOME_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("outcome_id", sa.String(64), unique=True, nullable=False),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("final_home_goals", sa.Integer, nullable=False),
        sa.Column("final_away_goals", sa.Integer, nullable=False),
        sa.Column("final_result", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, default="FINISHED"),
        sa.Column("outcome_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_match_id", sa.String(128), nullable=True),
        sa.Column("provenance", sa.JSON, nullable=True),
        sa.Column("outcome_hash", sa.String(64), nullable=False),
        sa.Column("supersedes_outcome_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_outcome_outcome_id", _OUTCOME_TABLE,
                       ["outcome_id"], unique=True)
    _safe_create_index("ix_outcome_match_id", _OUTCOME_TABLE, ["match_id"])
    _safe_create_index("ix_outcome_final_result", _OUTCOME_TABLE, ["final_result"])
    _safe_create_index("ix_outcome_hash", _OUTCOME_TABLE, ["outcome_hash"])
    _safe_create_index("ix_outcome_created_at", _OUTCOME_TABLE, ["created_at"])
    _safe_create_index("ix_outcome_match_hash", _OUTCOME_TABLE,
                       ["match_id", "outcome_hash"], unique=True)

    _safe_create_table(
        _EVAL_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("evaluation_id", sa.String(64), unique=True, nullable=False),
        sa.Column("prediction_id", sa.String(64), nullable=False, index=True),
        sa.Column("prediction_hash", sa.String(64), nullable=False),
        sa.Column("outcome_snapshot_id", sa.String(64), nullable=False),
        sa.Column("outcome_hash", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prediction_mode", sa.String(32), nullable=False, default="PRE_MATCH"),
        sa.Column("competition", sa.String(32), nullable=True),
        sa.Column("season", sa.String(32), nullable=True),
        sa.Column("prediction_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kickoff_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_result", sa.String(16), nullable=False),
        sa.Column("actual_home_goals", sa.Integer, nullable=False),
        sa.Column("actual_away_goals", sa.Integer, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("evaluation_version", sa.Integer, nullable=False, default=1),
        sa.Column("evaluation_key", sa.String(64), unique=True, nullable=False),
        sa.Column("evaluation_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("provenance", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_eval_evaluation_id", _EVAL_TABLE,
                       ["evaluation_id"], unique=True)
    _safe_create_index("ix_eval_prediction_id", _EVAL_TABLE, ["prediction_id"])
    _safe_create_index("ix_eval_outcome_snapshot_id", _EVAL_TABLE,
                       ["outcome_snapshot_id"])
    _safe_create_index("ix_eval_model_id", _EVAL_TABLE, ["model_id"])
    _safe_create_index("ix_eval_competition", _EVAL_TABLE, ["competition"])
    _safe_create_index("ix_eval_season", _EVAL_TABLE, ["season"])
    _safe_create_index("ix_eval_evaluation_key", _EVAL_TABLE,
                       ["evaluation_key"], unique=True)
    _safe_create_index("ix_eval_evaluation_hash", _EVAL_TABLE,
                       ["evaluation_hash"], unique=True)
    _safe_create_index("ix_eval_created_at", _EVAL_TABLE, ["created_at"])
    _safe_create_index("ix_eval_match_created", _EVAL_TABLE,
                       ["prediction_id", "created_at"])
    _safe_create_index("ix_eval_model_version", _EVAL_TABLE,
                       ["model_id", "model_version"])
    _safe_create_index("ix_eval_competition_season", _EVAL_TABLE,
                       ["competition", "season"])


def downgrade() -> None:
    _safe_drop_index("ix_eval_competition_season", _EVAL_TABLE)
    _safe_drop_index("ix_eval_model_version", _EVAL_TABLE)
    _safe_drop_index("ix_eval_match_created", _EVAL_TABLE)
    _safe_drop_index("ix_eval_created_at", _EVAL_TABLE)
    _safe_drop_index("ix_eval_evaluation_hash", _EVAL_TABLE)
    _safe_drop_index("ix_eval_evaluation_key", _EVAL_TABLE)
    _safe_drop_index("ix_eval_season", _EVAL_TABLE)
    _safe_drop_index("ix_eval_competition", _EVAL_TABLE)
    _safe_drop_index("ix_eval_model_id", _EVAL_TABLE)
    _safe_drop_index("ix_eval_outcome_snapshot_id", _EVAL_TABLE)
    _safe_drop_index("ix_eval_prediction_id", _EVAL_TABLE)
    _safe_drop_index("ix_eval_evaluation_id", _EVAL_TABLE)
    _safe_drop_table(_EVAL_TABLE)

    _safe_drop_index("ix_outcome_match_hash", _OUTCOME_TABLE)
    _safe_drop_index("ix_outcome_created_at", _OUTCOME_TABLE)
    _safe_drop_index("ix_outcome_hash", _OUTCOME_TABLE)
    _safe_drop_index("ix_outcome_final_result", _OUTCOME_TABLE)
    _safe_drop_index("ix_outcome_match_id", _OUTCOME_TABLE)
    _safe_drop_index("ix_outcome_outcome_id", _OUTCOME_TABLE)
    _safe_drop_table(_OUTCOME_TABLE)
