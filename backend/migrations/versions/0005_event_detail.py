"""Phase 1.8: event granularity + lineup squad numbers.

New columns only, all nullable — no data loss:
match_events.second/period/outcome, lineups.jersey_number.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_event_detail"
down_revision = "0004_player_temporal_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match_events", sa.Column("second", sa.Integer(), nullable=True))
    op.add_column("match_events", sa.Column("period", sa.String(16),
                                            nullable=False, server_default=""))
    op.add_column("match_events", sa.Column("outcome", sa.String(64),
                                            nullable=False, server_default=""))
    op.add_column("lineups", sa.Column("jersey_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("lineups", "jersey_number")
    op.drop_column("match_events", "outcome")
    op.drop_column("match_events", "period")
    op.drop_column("match_events", "second")
