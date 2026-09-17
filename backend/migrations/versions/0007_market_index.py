"""Phase 3: composite index for match/market time-range queries.

Additive, non-destructive. Existing single-column indexes are kept.
"""
from __future__ import annotations

from alembic import op

revision = "0007_market_index"
down_revision = "0006_prediction_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_odds_snapshots_match_market_time",
        "odds_snapshots",
        ["match_id", "market_type", "timestamp"],
    )
    op.create_index(
        "ix_odds_snapshots_match_bookmaker_market",
        "odds_snapshots",
        ["match_id", "bookmaker_id", "market_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_odds_snapshots_match_bookmaker_market", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_match_market_time", table_name="odds_snapshots")
