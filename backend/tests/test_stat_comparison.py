from datetime import datetime, timezone
from app.db.models.core import League, Match, Team, MatchStatistic
from app.db.models.enums import MatchStatus


def test_stat_comparison_endpoint_not_found(client):
    response = client.get("/api/v1/matches/99999999/stat-comparison")
    assert response.status_code == 404


def test_stat_comparison_endpoint_finished_match(client, db):
    lg = League(code="CMP_TEST", name="Test League", provider="test", provider_league_id="p-cmp", season="2026")
    db.add(lg)
    db.flush()

    home = Team(league_id=lg.id, name="Test Home", provider="test", provider_team_id="p-cmp-h")
    away = Team(league_id=lg.id, name="Test Away", provider="test", provider_team_id="p-cmp-a")
    db.add_all([home, away])
    db.flush()

    m = Match(
        league_id=lg.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED.value,
        home_score=2,
        away_score=1,
        provider="test",
        provider_match_id="p-cmp-m1",
    )
    db.add(m)
    db.flush()

    # Add match stats
    db.add(MatchStatistic(match_id=m.id, team="home", stat_name="corners", stat_value="6", period="full"))
    db.add(MatchStatistic(match_id=m.id, team="away", stat_name="corners", stat_value="3", period="full"))
    db.commit()

    response = client.get(f"/api/v1/matches/{m.id}/stat-comparison")
    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == m.id
    assert data["is_finished"] is True
    assert data["has_score"] is True
    assert data["actual_score"] == {"home": 2, "away": 1}
    assert "accuracy_summary" in data
    assert "comparisons" in data
    assert len(data["comparisons"]) >= 4

    metrics = [c["metric"] for c in data["comparisons"]]
    assert "Match Winner (1X2)" in metrics
    assert "Scoreline vs Expected Goals (xG)" in metrics
    assert "Total Goals Over/Under 2.5" in metrics
    assert "Both Teams To Score (BTTS)" in metrics


def test_stat_comparison_endpoint_scheduled_match(client, db):
    lg = db.query(League).filter_by(code="CMP_TEST").first()
    if not lg:
        lg = League(code="CMP_TEST", name="Test League", provider="test", provider_league_id="p-cmp", season="2026")
        db.add(lg)
        db.flush()

    home = Team(league_id=lg.id, name="Test Home 2", provider="test", provider_team_id="p-cmp-h2")
    away = Team(league_id=lg.id, name="Test Away 2", provider="test", provider_team_id="p-cmp-a2")
    db.add_all([home, away])
    db.flush()

    m = Match(
        league_id=lg.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
        status=MatchStatus.SCHEDULED.value,
        provider="test",
        provider_match_id="p-cmp-m2",
    )
    db.add(m)
    db.commit()

    response = client.get(f"/api/v1/matches/{m.id}/stat-comparison")
    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == m.id
    assert data["is_finished"] is False
    assert "comparisons" in data
    assert len(data["comparisons"]) >= 4
    for c in data["comparisons"]:
        assert c["status"] == "PENDING"
