"""Phase 1.7: player identity, event/lineup detail, temporal quality.

New table: player_provider_mappings. New columns: match_events.minute_added,
match_events.assist_player, lineups.formation, lineups.is_captain,
lineups.player_provider_id, raw_data_records.temporal_quality,
raw_data_records.source_url. All additions nullable — no data loss.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_player_temporal_detail"
down_revision = "0003_source_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_provider_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("provider_player_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider_player_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("normalized_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("resolution_method", sa.String(32), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "provider_player_id", name="uq_player_mapping_source"),
    )
    op.create_index("ix_player_mapping_player", "player_provider_mappings", ["player_id"])
    op.create_index("ix_player_mapping_source", "player_provider_mappings", ["source"])
    op.create_index("ix_player_mapping_norm", "player_provider_mappings", ["normalized_name"])

    op.add_column("match_events", sa.Column("minute_added", sa.Integer(), nullable=True))
    op.add_column("match_events", sa.Column("assist_player", sa.String(128),
                                            nullable=False, server_default=""))
    op.add_column("lineups", sa.Column("formation", sa.String(16),
                                       nullable=False, server_default=""))
    op.add_column("lineups", sa.Column("is_captain", sa.Integer(),
                                       nullable=False, server_default="0"))
    op.add_column("lineups", sa.Column("player_provider_id", sa.String(64),
                                       nullable=False, server_default=""))
    op.add_column("raw_data_records", sa.Column("temporal_quality", sa.String(16),
                                                nullable=False, server_default="unknown"))
    op.add_column("raw_data_records", sa.Column("source_url", sa.String(512),
                                                nullable=False, server_default=""))
    op.create_index("ix_raw_temporal", "raw_data_records", ["temporal_quality"])


def downgrade() -> None:
    op.drop_index("ix_raw_temporal", table_name="raw_data_records")
    op.drop_column("raw_data_records", "source_url")
    op.drop_column("raw_data_records", "temporal_quality")
    op.drop_column("lineups", "player_provider_id")
    op.drop_column("lineups", "is_captain")
    op.drop_column("lineups", "formation")
    op.drop_column("match_events", "assist_player")
    op.drop_column("match_events", "minute_added")
    op.drop_table("player_provider_mappings")
