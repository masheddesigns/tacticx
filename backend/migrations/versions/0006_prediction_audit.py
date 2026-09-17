"""Phase 2: prediction audit columns + backtest run records.

Additive only: model_name, prediction_cutoff, temporal_mode, status,
feature_availability, model_config, random_seed on predictions; new
backtest_runs table. Nothing renamed, nothing dropped.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_prediction_audit"
down_revision = "0005_event_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("model_name", sa.String(64),
                                           nullable=False, server_default=""))
    op.add_column("predictions", sa.Column("prediction_cutoff", sa.DateTime(timezone=True),
                                           nullable=True))
    op.add_column("predictions", sa.Column("temporal_mode", sa.String(32),
                                           nullable=False, server_default="strict_prematch"))
    op.add_column("predictions", sa.Column("status", sa.String(32),
                                           nullable=False, server_default="valid"))
    op.add_column("predictions", sa.Column("feature_availability", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("model_config", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("random_seed", sa.Integer(), nullable=True))
    op.create_index("ix_predictions_model", "predictions", ["model_name"])
    op.create_index("ix_predictions_status", "predictions", ["status"])

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("league", sa.String(32), nullable=False, server_default=""),
        sa.Column("season", sa.String(16), nullable=False, server_default=""),
        sa.Column("temporal_mode", sa.String(32), nullable=False, server_default="strict_prematch"),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_insufficient", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_temporal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("model_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_backtest_runs_model", "backtest_runs", ["model_name"])


def downgrade() -> None:
    op.drop_table("backtest_runs")
    op.drop_index("ix_predictions_status", table_name="predictions")
    op.drop_index("ix_predictions_model", table_name="predictions")
    op.drop_column("predictions", "random_seed")
    op.drop_column("predictions", "model_config")
    op.drop_column("predictions", "feature_availability")
    op.drop_column("predictions", "status")
    op.drop_column("predictions", "temporal_mode")
    op.drop_column("predictions", "prediction_cutoff")
    op.drop_column("predictions", "model_name")
