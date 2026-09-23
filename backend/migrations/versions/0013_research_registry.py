"""research registry

Revision ID: 0013_research_registry
Revises: 0012_evaluation_records
Create Date: 2026-09-23

Adds research_candidates, research_datasets, research_experiments
(Phase 29 controlled research pipeline; no production FKs).

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
revision = "0013_research_registry"
down_revision = "0012_evaluation_records"
branch_labels = None
depends_on = None

_CANDIDATE_TABLE = "research_candidates"
_DATASET_TABLE = "research_datasets"
_EXPERIMENT_TABLE = "research_experiments"


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
        _CANDIDATE_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("candidate_id", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, default="v1"),
        sa.Column("description", sa.String(1024), nullable=False, default=""),
        sa.Column("hypothesis", sa.String(1024), nullable=False, default=""),
        sa.Column("feature_set", sa.JSON, nullable=True),
        sa.Column("model_family", sa.String(64), nullable=False, default=""),
        sa.Column("hyperparameters", sa.JSON, nullable=True),
        sa.Column("declared_inputs", sa.JSON, nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=False, default=""),
        sa.Column("status", sa.String(32), nullable=False, default="DRAFT"),
        sa.Column("supersedes_candidate_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_research_cand_candidate_id", _CANDIDATE_TABLE,
                       ["candidate_id"], unique=True)
    _safe_create_index("ix_research_cand_status", _CANDIDATE_TABLE, ["status"])
    _safe_create_index("ix_research_cand_created_at", _CANDIDATE_TABLE,
                       ["created_at"])

    _safe_create_table(
        _DATASET_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dataset_id", sa.String(64), unique=True, nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False, default="v1"),
        sa.Column("competitions", sa.JSON, nullable=True),
        sa.Column("seasons", sa.JSON, nullable=True),
        sa.Column("feature_version", sa.String(32), nullable=False,
                  default="features_v1"),
        sa.Column("cutoff_policy", sa.String(64), nullable=False, default=""),
        sa.Column("inclusion_rules", sa.JSON, nullable=True),
        sa.Column("observations", sa.JSON, nullable=True),
        sa.Column("train_period", sa.JSON, nullable=True),
        sa.Column("validation_period", sa.JSON, nullable=True),
        sa.Column("test_period", sa.JSON, nullable=True),
        sa.Column("provenance", sa.JSON, nullable=True),
        sa.Column("dataset_hash", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_research_ds_dataset_id", _DATASET_TABLE,
                       ["dataset_id"], unique=True)
    _safe_create_index("ix_research_ds_dataset_hash", _DATASET_TABLE,
                       ["dataset_hash"], unique=True)
    _safe_create_index("ix_research_ds_created_at", _DATASET_TABLE,
                       ["created_at"])

    _safe_create_table(
        _EXPERIMENT_TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experiment_id", sa.String(64), unique=True, nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("candidate_version", sa.String(32), nullable=False, default=""),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_hash", sa.String(64), nullable=False),
        sa.Column("baseline_model_id", sa.String(64), nullable=False, default=""),
        sa.Column("baseline_model_version", sa.String(64), nullable=False, default=""),
        sa.Column("evaluation_protocol", sa.String(64), nullable=False, default=""),
        sa.Column("evaluation_protocol_version", sa.String(32), nullable=False,
                  default="v1"),
        sa.Column("random_seed", sa.Integer, nullable=False, default=7),
        sa.Column("baseline_metrics", sa.JSON, nullable=True),
        sa.Column("candidate_metrics", sa.JSON, nullable=True),
        sa.Column("comparison", sa.JSON, nullable=True),
        sa.Column("uncertainty", sa.JSON, nullable=True),
        sa.Column("calibration", sa.JSON, nullable=True),
        sa.Column("leakage_status", sa.String(32), nullable=False, default="PASS"),
        sa.Column("evidence_state", sa.String(32), nullable=False, default=""),
        sa.Column("reproducibility", sa.JSON, nullable=True),
        sa.Column("execution_metadata", sa.JSON, nullable=True),
        sa.Column("result_hash", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _safe_create_index("ix_research_exp_experiment_id", _EXPERIMENT_TABLE,
                       ["experiment_id"], unique=True)
    _safe_create_index("ix_research_exp_candidate_id", _EXPERIMENT_TABLE,
                       ["candidate_id"])
    _safe_create_index("ix_research_exp_dataset_id", _EXPERIMENT_TABLE,
                       ["dataset_id"])
    _safe_create_index("ix_research_exp_result_hash", _EXPERIMENT_TABLE,
                       ["result_hash"], unique=True)
    _safe_create_index("ix_research_exp_created_at", _EXPERIMENT_TABLE,
                       ["created_at"])


def downgrade() -> None:
    _safe_drop_index("ix_research_exp_created_at", _EXPERIMENT_TABLE)
    _safe_drop_index("ix_research_exp_result_hash", _EXPERIMENT_TABLE)
    _safe_drop_index("ix_research_exp_dataset_id", _EXPERIMENT_TABLE)
    _safe_drop_index("ix_research_exp_candidate_id", _EXPERIMENT_TABLE)
    _safe_drop_index("ix_research_exp_experiment_id", _EXPERIMENT_TABLE)
    _safe_drop_table(_EXPERIMENT_TABLE)

    _safe_drop_index("ix_research_ds_created_at", _DATASET_TABLE)
    _safe_drop_index("ix_research_ds_dataset_hash", _DATASET_TABLE)
    _safe_drop_index("ix_research_ds_dataset_id", _DATASET_TABLE)
    _safe_drop_table(_DATASET_TABLE)

    _safe_drop_index("ix_research_cand_created_at", _CANDIDATE_TABLE)
    _safe_drop_index("ix_research_cand_status", _CANDIDATE_TABLE)
    _safe_drop_index("ix_research_cand_candidate_id", _CANDIDATE_TABLE)
    _safe_drop_table(_CANDIDATE_TABLE)
