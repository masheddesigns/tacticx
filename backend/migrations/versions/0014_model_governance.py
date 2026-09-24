"""model governance

Revision ID: 0014_model_governance
Revises: 0013_research_registry
Create Date: 2026-09-23

Adds model_artifacts, model_registry, model_validation_reports,
model_promotion_requests, model_approval_records,
model_governance_events, shadow_prediction_snapshots
(Phase 30 controlled model governance; string linkage only, no
production foreign keys).

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
revision = "0014_model_governance"
down_revision = "0013_research_registry"
branch_labels = None
depends_on = None

_ARTIFACT = "model_artifacts"
_REGISTRY = "model_registry"
_VALIDATION = "model_validation_reports"
_PROMOTION = "model_promotion_requests"
_APPROVAL = "model_approval_records"
_EVENTS = "model_governance_events"
_SHADOW = "shadow_prediction_snapshots"


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
        _ARTIFACT,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("artifact_id", sa.String(64), unique=True, nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=True),
        sa.Column("experiment_id", sa.String(64), nullable=True),
        sa.Column("dataset_id", sa.String(64), nullable=True),
        sa.Column("dataset_hash", sa.String(64), nullable=True),
        sa.Column("config_fingerprint", sa.JSON, nullable=True),
        sa.Column("feature_contract", sa.String(32), nullable=False,
                  default="features_v1"),
        sa.Column("prediction_mode", sa.String(32), nullable=False,
                  default="PRE_MATCH"),
        sa.Column("train_period", sa.JSON, nullable=True),
        sa.Column("evaluation_period", sa.JSON, nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=False, default=""),
        sa.Column("lifecycle_state", sa.String(32), nullable=False,
                  default="RESEARCH_ONLY"),
        sa.Column("artifact_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("provenance", sa.JSON, nullable=True),
        _created_at(),
    )
    _safe_create_index("ix_gov_art_artifact_id", _ARTIFACT,
                       ["artifact_id"], unique=True)
    _safe_create_index("ix_gov_art_model_id", _ARTIFACT, ["model_id"])
    _safe_create_index("ix_gov_art_model_version", _ARTIFACT, ["model_version"])
    _safe_create_index("ix_gov_art_state", _ARTIFACT, ["lifecycle_state"])
    _safe_create_index("ix_gov_art_hash", _ARTIFACT,
                       ["artifact_hash"], unique=True)
    _safe_create_index("ix_gov_art_created_at", _ARTIFACT, ["created_at"])

    _safe_create_table(
        _REGISTRY,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("competition", sa.String(32), nullable=True),
        sa.Column("season", sa.String(32), nullable=True),
        sa.Column("prediction_mode", sa.String(32), nullable=False,
                  default="PRE_MATCH"),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, default="ACTIVE"),
        sa.Column("supersedes_registry_id", sa.Integer, nullable=True),
        _created_at(),
    )
    _safe_create_index("ix_gov_reg_role", _REGISTRY, ["role"])
    _safe_create_index("ix_gov_reg_artifact_id", _REGISTRY, ["artifact_id"])
    _safe_create_index("ix_gov_reg_created_at", _REGISTRY, ["created_at"])

    _safe_create_table(
        _VALIDATION,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("validation_id", sa.String(64), unique=True, nullable=False),
        sa.Column("candidate_artifact_id", sa.String(64), nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=False),
        sa.Column("experiment_id", sa.String(64), nullable=True),
        sa.Column("dataset_hash", sa.String(64), nullable=True),
        sa.Column("config_fingerprint", sa.JSON, nullable=True),
        sa.Column("evaluation_window", sa.JSON, nullable=True),
        sa.Column("competitions", sa.JSON, nullable=True),
        sa.Column("sample_sizes", sa.JSON, nullable=True),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("uncertainty", sa.JSON, nullable=True),
        sa.Column("evidence_state", sa.String(32), nullable=True),
        sa.Column("leakage_status", sa.String(32), nullable=True),
        sa.Column("temporal_integrity", sa.String(32), nullable=True),
        sa.Column("compatibility", sa.JSON, nullable=True),
        sa.Column("validation_result", sa.String(32), nullable=False),
        sa.Column("warnings", sa.JSON, nullable=True),
        sa.Column("validator_version", sa.String(32), nullable=False,
                  default="v1"),
        sa.Column("report_hash", sa.String(64), unique=True, nullable=False),
        _created_at(),
    )
    _safe_create_index("ix_gov_val_validation_id", _VALIDATION,
                       ["validation_id"], unique=True)
    _safe_create_index("ix_gov_val_candidate", _VALIDATION,
                       ["candidate_artifact_id"])
    _safe_create_index("ix_gov_val_result", _VALIDATION, ["validation_result"])
    _safe_create_index("ix_gov_val_hash", _VALIDATION,
                       ["report_hash"], unique=True)
    _safe_create_index("ix_gov_val_created_at", _VALIDATION, ["created_at"])

    _safe_create_table(
        _PROMOTION,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(64), unique=True, nullable=False),
        sa.Column("candidate_artifact_id", sa.String(64), nullable=False),
        sa.Column("validation_id", sa.String(64), nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=False),
        sa.Column("competition", sa.String(32), nullable=True),
        sa.Column("season", sa.String(32), nullable=True),
        sa.Column("prediction_mode", sa.String(32), nullable=False,
                  default="PRE_MATCH"),
        sa.Column("deployment_mode", sa.String(32), nullable=False,
                  default="SHADOW"),
        sa.Column("requester", sa.String(128), nullable=False, default=""),
        sa.Column("reason", sa.String(1024), nullable=False, default=""),
        sa.Column("state", sa.String(32), nullable=False, default="OPEN"),
        _created_at(),
    )
    _safe_create_index("ix_gov_promo_request_id", _PROMOTION,
                       ["request_id"], unique=True)
    _safe_create_index("ix_gov_promo_candidate", _PROMOTION,
                       ["candidate_artifact_id"])
    _safe_create_index("ix_gov_promo_state", _PROMOTION, ["state"])
    _safe_create_index("ix_gov_promo_created_at", _PROMOTION, ["created_at"])

    _safe_create_table(
        _APPROVAL,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("approval_id", sa.String(64), unique=True, nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False, default=""),
        sa.Column("reason", sa.String(1024), nullable=False, default=""),
        _created_at(),
    )
    _safe_create_index("ix_gov_appr_approval_id", _APPROVAL,
                       ["approval_id"], unique=True)
    _safe_create_index("ix_gov_appr_request_id", _APPROVAL,
                       ["request_id"])
    _safe_create_index("ix_gov_appr_decision", _APPROVAL, ["decision"])
    _safe_create_index("ix_gov_appr_created_at", _APPROVAL, ["created_at"])

    _safe_create_table(
        _EVENTS,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(64), unique=True, nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=True),
        sa.Column("from_state", sa.String(32), nullable=False, default=""),
        sa.Column("to_state", sa.String(32), nullable=False, default=""),
        sa.Column("actor", sa.String(128), nullable=False, default=""),
        sa.Column("reason", sa.String(1024), nullable=False, default=""),
        sa.Column("references", sa.JSON, nullable=True),
        _created_at(),
    )
    _safe_create_index("ix_gov_evt_event_id", _EVENTS,
                       ["event_id"], unique=True)
    _safe_create_index("ix_gov_evt_artifact_id", _EVENTS, ["artifact_id"])
    _safe_create_index("ix_gov_evt_created_at", _EVENTS, ["created_at"])

    _safe_create_table(
        _SHADOW,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shadow_id", sa.String(64), unique=True, nullable=False),
        sa.Column("match_id", sa.Integer, nullable=False),
        sa.Column("challenger_artifact_id", sa.String(64), nullable=False),
        sa.Column("champion_artifact_id", sa.String(64), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("champion_output", sa.JSON, nullable=True),
        sa.Column("challenger_output", sa.JSON, nullable=True),
        sa.Column("champion_output_hash", sa.String(64), nullable=False,
                  default=""),
        sa.Column("challenger_output_hash", sa.String(64), nullable=False,
                  default=""),
        _created_at(),
    )
    _safe_create_index("ix_gov_shdw_shadow_id", _SHADOW,
                       ["shadow_id"], unique=True)
    _safe_create_index("ix_gov_shdw_match_id", _SHADOW, ["match_id"])
    _safe_create_index("ix_gov_shdw_challenger", _SHADOW,
                       ["challenger_artifact_id"])
    _safe_create_index("ix_gov_shdw_champion", _SHADOW,
                       ["champion_artifact_id"])
    _safe_create_index("ix_gov_shdw_created_at", _SHADOW, ["created_at"])


def downgrade() -> None:
    for index_name in ("ix_gov_shdw_created_at", "ix_gov_shdw_champion",
                       "ix_gov_shdw_challenger", "ix_gov_shdw_match_id",
                       "ix_gov_shdw_shadow_id"):
        _safe_drop_index(index_name, _SHADOW)
    _safe_drop_table(_SHADOW)

    for index_name in ("ix_gov_evt_created_at", "ix_gov_evt_artifact_id",
                       "ix_gov_evt_event_id"):
        _safe_drop_index(index_name, _EVENTS)
    _safe_drop_table(_EVENTS)

    for index_name in ("ix_gov_appr_created_at", "ix_gov_appr_decision",
                       "ix_gov_appr_request_id", "ix_gov_appr_approval_id"):
        _safe_drop_index(index_name, _APPROVAL)
    _safe_drop_table(_APPROVAL)

    for index_name in ("ix_gov_promo_created_at", "ix_gov_promo_state",
                       "ix_gov_promo_candidate", "ix_gov_promo_request_id"):
        _safe_drop_index(index_name, _PROMOTION)
    _safe_drop_table(_PROMOTION)

    for index_name in ("ix_gov_val_created_at", "ix_gov_val_hash",
                       "ix_gov_val_result", "ix_gov_val_candidate",
                       "ix_gov_val_validation_id"):
        _safe_drop_index(index_name, _VALIDATION)
    _safe_drop_table(_VALIDATION)

    for index_name in ("ix_gov_reg_created_at", "ix_gov_reg_artifact_id",
                       "ix_gov_reg_role"):
        _safe_drop_index(index_name, _REGISTRY)
    _safe_drop_table(_REGISTRY)

    for index_name in ("ix_gov_art_created_at", "ix_gov_art_hash",
                       "ix_gov_art_state", "ix_gov_art_model_version",
                       "ix_gov_art_model_id", "ix_gov_art_artifact_id"):
        _safe_drop_index(index_name, _ARTIFACT)
    _safe_drop_table(_ARTIFACT)
