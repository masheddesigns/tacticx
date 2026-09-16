"""Initial schema for Phase 1. Generated from models (offline-friendly hand write)."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_league_id", sa.String(32), nullable=False, server_default=""),
        sa.Column("season", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_leagues_code", "leagues", ["code"])
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("short_name", sa.String(32), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_team_id", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_team_id", name="uq_team_provider"),
    )
    op.create_index("ix_teams_name", "teams", ["name"])
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("position", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_player_id", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint("provider", "provider_player_id", name="uq_player_provider"),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=True),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="SCHEDULED"),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_match_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_match_id", name="uq_match_provider"),
    )
    op.create_index("ix_matches_kickoff", "matches", ["kickoff_at"])
    op.create_index("ix_matches_status", "matches", ["status"])
    for tbl, cols, name in [
        ("match_statistics", ["match_id", "team", "stat_name", "period"], "uq_match_stat"),
        ("match_events", None, None),
        ("lineups", ["match_id", "team", "player_name"], "uq_lineup_player"),
        ("team_statistics", ["team_id", "league_id", "season", "stat_name"], "uq_team_stat"),
        ("standings", ["league_id", "team_id", "season"], "uq_standing"),
    ]:
        _create_aux(tbl)
    _create_odds()
    _create_predictions()
    _create_logs()


def _create_aux(tbl: str) -> None:
    if tbl == "match_statistics":
        op.create_table(
            "match_statistics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("team", sa.String(8), nullable=False),
            sa.Column("stat_name", sa.String(64), nullable=False),
            sa.Column("stat_value", sa.String(64), nullable=False, server_default=""),
            sa.Column("period", sa.String(16), nullable=False, server_default="full"),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("match_id", "team", "stat_name", "period", name="uq_match_stat"),
        )
        op.create_index("ix_match_statistics_match", "match_statistics", ["match_id"])
    elif tbl == "match_events":
        op.create_table(
            "match_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("minute", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("detail", sa.String(256), nullable=False, server_default=""),
            sa.Column("team", sa.String(8), nullable=False, server_default=""),
            sa.Column("player_name", sa.String(128), nullable=False, server_default=""),
            sa.Column("provider", sa.String(32), nullable=False, server_default=""),
            sa.Column("provider_event_id", sa.String(64), nullable=False, server_default=""),
            sa.UniqueConstraint("provider", "provider_event_id", name="uq_event_provider"),
        )
        op.create_index("ix_match_events_match", "match_events", ["match_id"])
    elif tbl == "lineups":
        op.create_table(
            "lineups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("team", sa.String(8), nullable=False, server_default=""),
            sa.Column("player_name", sa.String(128), nullable=False),
            sa.Column("position", sa.String(32), nullable=True),
            sa.Column("is_starting", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("match_id", "team", "player_name", name="uq_lineup_player"),
        )
        op.create_index("ix_lineups_match", "lineups", ["match_id"])
    elif tbl == "team_statistics":
        op.create_table(
            "team_statistics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=True),
            sa.Column("season", sa.String(16), nullable=False, server_default=""),
            sa.Column("stat_name", sa.String(64), nullable=False),
            sa.Column("stat_value", sa.String(64), nullable=False, server_default=""),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("team_id", "league_id", "season", "stat_name", name="uq_team_stat"),
        )
        op.create_index("ix_team_statistics_team", "team_statistics", ["team_id"])
    elif tbl == "standings":
        op.create_table(
            "standings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=False),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("season", sa.String(16), nullable=False, server_default=""),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("played", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("won", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("drawn", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lost", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("league_id", "team_id", "season", name="uq_standing"),
        )
        op.create_index("ix_standings_league", "standings", ["league_id"])


def _create_odds() -> None:
    op.create_table(
        "bookmakers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_bookmaker_id", sa.String(64), nullable=False, server_default=""),
        sa.UniqueConstraint("provider", "provider_bookmaker_id", name="uq_bookmaker"),
    )
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_key", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), nullable=False, server_default=""),
        sa.UniqueConstraint("market_key"),
    )
    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("bookmaker_id", sa.Integer(), sa.ForeignKey("bookmakers.id"), nullable=True),
        sa.Column("market_type", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default=""),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_odds_snapshots_match", "odds_snapshots", ["match_id"])
    op.create_index("ix_odds_snapshots_ts", "odds_snapshots", ["timestamp"])
    op.create_table(
        "odds_selections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("odds_snapshots.id"), nullable=False),
        sa.Column("selection", sa.String(64), nullable=False),
        sa.Column("odds", sa.Float(), nullable=False),
        sa.Column("point", sa.Float(), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("dedup_hash"),
    )
    op.create_index("ix_odds_selections_snap", "odds_selections", ["snapshot_id"])


def _create_predictions() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("prediction_timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False, server_default="stub-0.1"),
        sa.Column("prediction_type", sa.String(64), nullable=False, server_default="1x2"),
        sa.Column("predicted_probability", sa.Float(), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index("ix_predictions_match", "predictions", ["match_id"])
    op.create_table(
        "prediction_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("actual_result", sa.String(64), nullable=False),
        sa.Column("resolved_timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _create_logs() -> None:
    op.create_table(
        "data_sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("league", sa.String(32), nullable=False, server_default=""),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("errors", sa.String(1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_provider", "data_sync_logs", ["provider"])
    op.create_table(
        "provider_request_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(1024), nullable=False, server_default=""),
        sa.Column("request_cost", sa.Float(), nullable=True),
    )
    op.create_index("ix_reqlog_provider", "provider_request_logs", ["provider"])
    op.create_index("ix_reqlog_ts", "provider_request_logs", ["timestamp"])


def downgrade() -> None:
    for tbl in [
        "provider_request_logs", "data_sync_logs", "prediction_results", "predictions",
        "odds_selections", "odds_snapshots", "markets", "bookmakers", "standings",
        "team_statistics", "lineups", "match_events", "match_statistics",
        "matches", "players", "teams", "leagues",
    ]:
        op.drop_table(tbl)
