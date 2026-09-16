"""Phase 1.6: source-agnostic data layer.

New tables: team_provider_mappings, match_source_mappings, raw_data_records,
source_conflicts. Lineage columns (source, source_record_id, effective_at)
on statistics/events/lineups/team_statistics/standings; source_event_id +
source_market_id on odds_snapshots. All additions nullable — no data loss.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_source_layer"
down_revision = "0002_quota_remaining"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_provider_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("provider_team_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider_team_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("normalized_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("league", sa.String(32), nullable=False, server_default=""),
        sa.Column("resolution_method", sa.String(32), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "provider_team_id", name="uq_team_mapping_source"),
    )
    op.create_index("ix_team_mapping_team", "team_provider_mappings", ["team_id"])
    op.create_index("ix_team_mapping_source", "team_provider_mappings", ["source"])
    op.create_index("ix_team_mapping_norm", "team_provider_mappings", ["normalized_name"])

    op.create_table(
        "match_source_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_match_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_match_id", name="uq_match_mapping_source"),
    )
    op.create_index("ix_match_mapping_match", "match_source_mappings", ["match_id"])
    op.create_index("ix_match_mapping_source", "match_source_mappings", ["source"])

    op.create_table(
        "raw_data_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("parser_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(1024), nullable=False, server_default=""),
        sa.UniqueConstraint("source", "entity_type", "source_record_id", name="uq_raw_record"),
    )
    op.create_index("ix_raw_source", "raw_data_records", ["source"])
    op.create_index("ix_raw_entity", "raw_data_records", ["entity_type"])
    op.create_index("ix_raw_status", "raw_data_records", ["processing_status"])
    op.create_index("ix_raw_retrieved", "raw_data_records", ["retrieved_at"])

    op.create_table(
        "source_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=True),
        sa.Column("entity_type", sa.String(32), nullable=False, server_default="match"),
        sa.Column("field", sa.String(64), nullable=False, server_default="score"),
        sa.Column("values", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("resolution", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conflict_match", "source_conflicts", ["match_id"])
    op.create_index("ix_conflict_status", "source_conflicts", ["status"])

    for table in ("match_statistics", "match_events", "lineups", "team_statistics", "standings"):
        op.add_column(table, sa.Column("source", sa.String(32), nullable=False, server_default=""))
        op.add_column(table, sa.Column("source_record_id", sa.String(128), nullable=False,
                                       server_default=""))
        op.add_column(table, sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("odds_snapshots", sa.Column("source_event_id", sa.String(128), nullable=True))
    op.add_column("odds_snapshots", sa.Column("source_market_id", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("odds_snapshots", "source_market_id")
    op.drop_column("odds_snapshots", "source_event_id")
    for table in ("match_statistics", "match_events", "lineups", "team_statistics", "standings"):
        op.drop_column(table, "effective_at")
        op.drop_column(table, "source_record_id")
        op.drop_column(table, "source")
    for table in ("source_conflicts", "raw_data_records", "match_source_mappings",
                  "team_provider_mappings"):
        op.drop_table(table)
