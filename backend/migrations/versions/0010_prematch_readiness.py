"""prematch readiness certificates

Revision ID: 0010_prematch_readiness
Revises: 0009_production_schema_complete
Create Date: 2026-09-19

Adds the prematch_readiness_certificates table (Phase 25 pre-match gate).

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
revision = "0010_prematch_readiness"
down_revision = "0009_production_schema_complete"
branch_labels = None
depends_on = None

_TABLE = "prematch_readiness_certificates"


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
        _TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("certificate_id", sa.String(64), unique=True, nullable=False),
        sa.Column("certificate_version", sa.String(32), nullable=False, default="PREMATCH_CERTIFICATE_V1"),
        sa.Column("readiness_contract_version", sa.String(32), nullable=False, default="PREMATCH_CERTIFICATE_V1"),
        # Match identity
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("competition", sa.String(32), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("home_team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        # Temporal envelope
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        # Readiness verdict
        sa.Column("readiness_state", sa.String(32), nullable=False),
        sa.Column("gate_verdicts", sa.JSON, nullable=True),
        sa.Column("blocking_reasons", sa.JSON, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=True),
        # Payload integrity
        sa.Column("payload_hash", sa.String(64), nullable=False),
        # Superseding chain (append-only)
        sa.Column("supersedes_certificate_id", sa.String(64), nullable=True),
        # Provenance (Phase 25.1)
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_match_id", sa.String(128), nullable=True),
        sa.Column("activation_state", sa.String(32), nullable=True),
        sa.Column("provider_qualification_version", sa.String(64), nullable=True),
        sa.Column("prediction_config", sa.JSON, nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("prediction_mode", sa.String(32), nullable=True),
        sa.Column("required_features", sa.JSON, nullable=True),
        sa.Column("available_features", sa.JSON, nullable=True),
        sa.Column("missing_required_features", sa.JSON, nullable=True),
        sa.Column("missing_optional_features", sa.JSON, nullable=True),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Core indices
    _safe_create_index("ix_prematch_cert_certificate_id", _TABLE, ["certificate_id"], unique=True)
    _safe_create_index("ix_prematch_cert_match_id", _TABLE, ["match_id"])
    _safe_create_index("ix_prematch_cert_competition", _TABLE, ["competition"])
    _safe_create_index("ix_prematch_cert_season", _TABLE, ["season"])
    _safe_create_index("ix_prematch_cert_readiness_state", _TABLE, ["readiness_state"])
    _safe_create_index("ix_prematch_cert_payload_hash", _TABLE, ["payload_hash"])
    _safe_create_index("ix_prematch_cert_created_at", _TABLE, ["created_at"])
    # Composite indices
    _safe_create_index("ix_prematch_cert_match_created", _TABLE, ["match_id", "created_at"])
    _safe_create_index("ix_prematch_cert_season_state", _TABLE, ["season", "readiness_state"])


def downgrade() -> None:
    _safe_drop_index("ix_prematch_cert_season_state", _TABLE)
    _safe_drop_index("ix_prematch_cert_match_created", _TABLE)
    _safe_drop_index("ix_prematch_cert_created_at", _TABLE)
    _safe_drop_index("ix_prematch_cert_payload_hash", _TABLE)
    _safe_drop_index("ix_prematch_cert_readiness_state", _TABLE)
    _safe_drop_index("ix_prematch_cert_season", _TABLE)
    _safe_drop_index("ix_prematch_cert_competition", _TABLE)
    _safe_drop_index("ix_prematch_cert_match_id", _TABLE)
    _safe_drop_index("ix_prematch_cert_certificate_id", _TABLE)
    _safe_drop_table(_TABLE)
