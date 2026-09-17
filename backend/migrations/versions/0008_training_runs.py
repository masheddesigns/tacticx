"""Phase 4: model training runs + evaluations. Additive, non-destructive."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_training_runs"
down_revision = "0007_market_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_training_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("feature_version", sa.String(32), nullable=False, server_default="features_v1"),
        sa.Column("league", sa.String(32), nullable=False, server_default=""),
        sa.Column("train_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_sample", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("train_dropped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temporal_mode", sa.String(32), nullable=False, server_default="strict_prematch"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_training_runs_model", "model_training_runs", ["model_name"])
    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("training_run_id", sa.Integer(), sa.ForeignKey("model_training_runs.id"), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("league", sa.String(32), nullable=False, server_default=""),
        sa.Column("season", sa.String(16), nullable=False, server_default=""),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temporal_mode", sa.String(32), nullable=False, server_default="strict_prematch"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_evaluations_model", "model_evaluations", ["model_name"])


def downgrade() -> None:
    op.drop_table("model_evaluations")
    op.drop_table("model_training_runs")
