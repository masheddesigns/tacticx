"""Phase 1.5: persist provider-reported quota remaining on request logs."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_quota_remaining"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_request_logs", sa.Column("quota_remaining", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_request_logs", "quota_remaining")
