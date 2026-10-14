"""team crest URLs

Revision ID: 0018_team_logos
Revises: 0017_candidate_validation
Create Date: 2026-10-14

Adds nullable teams.logo_url for verified provider CDN crest assets
(ESPN teamlogos for ESPN-sourced clubs). Nullable: pre-existing and
non-ESPN teams keep registry/initial fallbacks.

Safety conventions (Phase 23): guarded add/drop column, idempotent
rerun, raise on unexpected errors.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0018_team_logos"
down_revision = "0017_candidate_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("teams")]
    if "logo_url" not in cols:
        op.add_column("teams", sa.Column("logo_url", sa.String(512), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("teams")]
    if "logo_url" in cols:
        op.drop_column("teams", "logo_url")
