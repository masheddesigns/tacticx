"""Phase 9 tests: temporal safety, identity, aggregation, events, lineups,
quality, determinism, API. Prediction engine untouched (regression below).
No live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Lineup, Match, MatchEvent, Player, Team
from app.db.models.player_intelligence import PlayerFeatureSnapshot
from app.services.features.temporal import TemporalMode
from app.services.player_intelligence import (
    appearances,
    availability as availability_svc,
    event_features as registry,
    feature_snapshot,
    lineup_features,
    memberships,
    player_form,
    quality as quality_svc,
    team_event_features,
)
from app.services.player_intelligence.repository import PlayerEventRepository

STRICT = TemporalMode.STRICT_PREMATCH
ESTIMATED = TemporalMode.HISTORICAL_ESTIMATED
BASE = datetime(2024, 9, 1, 12, 0)


def _league(db, code="P9"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="p9",
                    provider_league_id="p9", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="p9",
                    provider_team_id=f"p9-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _players(db, teams, names, source="p9stats"):
    out = {}
    for i, name in enumerate(names):
        player = Player(name=name, team_id=None, provider=source,
                        provider_player_id=f"p9-{i}")
        db.add(player)
        db.flush()
        out[name] = player
    db.commit()
    return out


def _past_match(db, league, teams, home, away, day, hs=1, aws=0):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=BASE + timedelta(days=day), status="FINISHED",
        home_score=hs, away_score=aws, provider="p9",
        provider_match_id=f"p9-{home}-{away}-{day}")
    db.add(match)
    db.commit()
    return match


def _lineup(db, match, side, player_name, provider_id, starting=1,
            formation="4231", effective_at=None):
    db.add(Lineup(match_id=match.id, team=side, player_name=player_name,
                  position="MID", is_starting=starting, formation=formation,
                  source="p9stats", player_provider_id=provider_id,
                  effective_at=effective_at))
    db.commit()


def _event(db, match, side, event_type, player_name, minute,
           effective_at=None, second=0):
    tag = f"{match.id}-{side}-{event_type}-{player_name}-{minute}-{second}"
    db.add(MatchEvent(match_id=match.id, team=side, event_type=event_type,
                      player_name=player_name, minute=minute, second=second,
                      period="1H" if minute <= 45 else "2H", source="p9stats",
                      provider="p9stats", provider_event_id=f"p9-{tag}"))
    db.commit()


def _world(db, code="P9W"):
    """Two finished matches with verified-timing lineups/events + target."""
    league = _league(db, code)
    teams = _teams(db, league, ("H", "A"))
    players = _players(db, teams, ("Alpha", "Beta", "Gamma", "Delta"))
    m1 = _past_match(db, league, teams, "H", "A", 0, 2, 0)
    m2 = _past_match(db, league, teams, "A", "H", 7, 1, 1)
    verified = BASE - timedelta(days=30)
    for match, side in ((m1, "home"), (m2, "away")):
        _lineup(db, match, side, "Alpha", "p9-0", starting=1,
                effective_at=verified)
        _lineup(db, match, side, "Beta", "p9-1", starting=1,
                effective_at=verified)
        _lineup(db, match, side, "Gamma", "p9-2", starting=0,
                effective_at=verified)
    _event(db, m1, "home", "goal", "Alpha", 23, effective_at=verified)
    _event(db, m2, "away", "goal", "Alpha", 60, effective_at=verified)
    _event(db, m1, "home", "yellow_card", "Beta", 70, effective_at=verified)
    target = Match(
        league_id=league.id, home_team_id=teams["H"].id, away_team_id=teams["A"].id,
        kickoff_at=BASE + timedelta(days=14), status="SCHEDULED",
        provider="p9", provider_match_id="p9-target")
    db.add(target)
    db.commit()
    return league, teams, players, target


# -- temporal safety --------------------------------------------------------------

def test_target_match_contributes_zero(db):
    league, teams, players, target = _world(db)
    # Poison the target with its own rows: output must not change.
    _lineup(db, target, "home", "Alpha", "p9-0", starting=1,
            effective_at=BASE)
    _event(db, target, "home", "goal", "Alpha", 10, effective_at=BASE)
    repo = PlayerEventRepository(db, target.kickoff_at, STRICT,
                                 target_match_id=target.id)
    lineups = repo.team_lineups_before(teams["H"].id)
    assert target.id not in {m.id for m, _, _ in lineups}
    assert repo.excluded_target >= 1
    events = repo.team_events_before(teams["H"].id)
    assert target.id not in {m.id for m, _, _ in events}


def test_strict_excludes_unknown_timing_estimated_allows(db):
    league = _league(db, code="P9U")
    teams = _teams(db, league, ("H", "A"))
    match = _past_match(db, league, teams, "H", "A", 0)
    _lineup(db, match, "home", "Ghost", "p9-g", effective_at=None)
    cutoff = BASE + timedelta(days=14)
    strict_repo = PlayerEventRepository(db, cutoff, STRICT)
    assert strict_repo.team_lineups_before(teams["H"].id) == []
    assert strict_repo.excluded_unknown_timing >= 1
    est_repo = PlayerEventRepository(db, cutoff, ESTIMATED)
    rows = est_repo.team_lineups_before(teams["H"].id)
    assert len(rows) == 1 and rows[0][2] == "estimated"


def test_future_records_excluded(db):
    league, teams, players, target = _world(db)
    future = _past_match(db, league, teams, "H", "A", 30)  # after cutoff
    _lineup(db, future, "home", "Alpha", "p9-0",
            effective_at=BASE + timedelta(days=29))
    repo = PlayerEventRepository(db, target.kickoff_at, ESTIMATED,
                                 target_match_id=target.id)
    match_ids = {m.id for m, _, _ in repo.team_lineups_before(teams["H"].id)}
    assert future.id not in match_ids


def test_cutoff_equality_excludes_kickoff_at_cutoff(db):
    league, teams, players, target = _world(db)
    edge = _past_match(db, league, teams, "H", "A", 14)  # kickoff == cutoff
    assert edge.kickoff_at == target.kickoff_at
    repo = PlayerEventRepository(db, target.kickoff_at, ESTIMATED,
                                 target_match_id=target.id)
    match_ids = {m.id for m, _, _ in repo.team_lineups_before(teams["H"].id)}
    assert edge.id not in match_ids


def test_adversarial_future_injection_unchanged_output(db):
    league, teams, players, target = _world(db)
    before = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                             ESTIMATED, persist=False)
    # Inject future rows + post-match corrections + target rows.
    future = _past_match(db, league, teams, "H", "A", 30, 9, 9)
    _lineup(db, future, "home", "Alpha", "p9-0", effective_at=BASE)
    _event(db, future, "home", "goal", "Alpha", 1, effective_at=BASE)
    _lineup(db, target, "home", "Alpha", "p9-0", effective_at=BASE)
    after = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                            ESTIMATED, persist=False)
    assert after["payload_hash"] == before["payload_hash"]
    assert after["home"] == before["home"] and after["away"] == before["away"]


# -- identity -------------------------------------------------------------------------

def test_canonical_player_mapping_and_unresolved_lane(db):
    league, teams, players, target = _world(db)
    apps = appearances.team_appearances(db, teams["H"].id, target.kickoff_at,
                                        ESTIMATED, target.id)
    assert "player:1" in apps["players"] or any(
        v.get("canonical_player_id") == players["Alpha"].id
        for v in apps["players"].values())
    # Unknown provider id: counted, never merged.
    other = _past_match(db, league, teams, "H", "A", 10)
    _lineup(db, other, "home", "Mystery", "p9-zzz",
            effective_at=BASE + timedelta(days=9))
    apps2 = appearances.team_appearances(db, teams["H"].id, target.kickoff_at,
                                         ESTIMATED, target.id)
    assert apps2["unresolved_appearances"] >= 1
    assert any(v.get("unresolved") for v in apps2["players"].values())


def test_same_name_cross_team_not_merged(db):
    from app.services.reconciliation import identities

    league = _league(db, code="P9X")
    teams = _teams(db, league, ("H", "A"))
    db.add(Player(name="Same Name", team_id=teams["H"].id, provider="p9x",
                  provider_player_id="x-1"))
    db.commit()
    result = identities.resolve_player(db, "p9x", name="Same Name", team="A")
    assert result["canonical_player_id"] is None


def test_transfer_two_memberships(db):
    league = _league(db, code="P9TR")
    teams = _teams(db, league, ("H", "A"))
    players = _players(db, teams, ("Mover",))
    m1 = _past_match(db, league, teams, "H", "A", 0)
    m2 = _past_match(db, league, teams, "H", "A", 7)
    verified = BASE - timedelta(days=30)
    _lineup(db, m1, "home", "Mover", "p9-0", effective_at=verified)
    _lineup(db, m2, "away", "Mover", "p9-0", effective_at=verified)
    from app.services.player_intelligence import memberships

    report = memberships.rebuild_memberships(db, ESTIMATED)
    assert report["status"] == "rebuilt"
    rows = memberships.membership_at(db, players["Mover"].id, BASE + timedelta(days=14))
    assert {r["team_id"] for r in rows} == {teams["H"].id, teams["A"].id}


# -- aggregation / events / lineups ------------------------------------------------------

def test_appearances_starts_windows_and_no_minutes(db):
    league, teams, players, target = _world(db)
    apps = appearances.team_appearances(db, teams["H"].id, target.kickoff_at,
                                        ESTIMATED, target.id)
    alpha = next(v for v in apps["players"].values()
                 if v.get("canonical_player_id") == players["Alpha"].id)
    assert alpha["matches_played"] == 2 and alpha["starts"] == 2
    assert alpha["minutes_played"] is None
    assert alpha["appearances_last_3"] == 2
    assert alpha["days_since_last_appearance"] == 7.0


def test_per_appearance_rates_and_sample_gates(db):
    league, teams, players, target = _world(db)
    forms = player_form.player_form(db, teams["H"].id, target.kickoff_at,
                                    ESTIMATED, target.id)
    alpha = next(v for v in forms["players"].values()
                 if v.get("canonical_player_id") == players["Alpha"].id)
    assert alpha["form_3"]["available"] is False  # 2 < 3: unavailable, not zero
    assert "below minimum sample" in alpha["form_3"]["reason"]
    assert alpha["event_counts"]["goals"] == 2


def test_event_registry_refuses_unregistered():
    assert registry.is_supported("goals")
    assert not registry.is_supported("shots")
    assert not registry.is_supported("tackles")
    assert "minutes_played" in registry.UNREGISTERED
    assert registry.definition("goals")["source"] == "statsbomb"


def test_team_aggregation_transparent(db):
    league, teams, players, target = _world(db)
    team = team_event_features.team_features(db, teams["H"].id,
                                             target.kickoff_at, ESTIMATED,
                                             target.id)
    assert team["n_regular_contributors"] == 0  # 2 apps < gate of 3
    assert team["regular_starter_continuity"]["available"] is False
    assert team["roster_staleness_days"]["available"] is False


def test_lineup_continuity_and_formation(db):
    league, teams, players, target = _world(db)
    feats = lineup_features.lineup_features(db, teams["H"].id,
                                            target.kickoff_at, ESTIMATED,
                                            target.id)
    assert feats["status"] == "ok"
    assert feats["most_frequent_formation"]["value"] == "4231"
    assert feats["starting_xi_continuity"]["value"] == 1.0
    # Verified-timing rows ARE strict-eligible; unknown-timing rows are not.
    strict = lineup_features.lineup_features(db, teams["H"].id,
                                             target.kickoff_at, STRICT,
                                             target.id)
    assert strict["status"] == "ok"
    ghost = _past_match(db, league, teams, "H", "A", 10)
    _lineup(db, ghost, "home", "Ghost", "p9-ghost", effective_at=None)
    strict_ghost = PlayerEventRepository(db, BASE + timedelta(days=30), STRICT)
    ghost_rows = [m.id for m, _, _ in
                  strict_ghost.team_lineups_before(teams["H"].id)]
    assert ghost.id not in ghost_rows


# -- quality / determinism / API ----------------------------------------------------------------

def test_quality_dimensions_preserved(db):
    league, teams, players, target = _world(db)
    out = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                          ESTIMATED, persist=False)
    quality = out["home"]["quality"]
    assert set(quality["components"]) == {"identity_quality", "temporal_quality",
                                          "source_quality", "sample_size_quality",
                                          "definition_quality"}
    assert quality["quality"] in ("high", "medium", "low", "unknown")


def test_snapshot_determinism_and_persist_dedup(db):
    league, teams, players, target = _world(db)
    first = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                            ESTIMATED, persist=True)
    second = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                             ESTIMATED, persist=True)
    assert first["payload_hash"] == second["payload_hash"]
    assert first["snapshot_id"] == second["snapshot_id"]
    assert db.query(PlayerFeatureSnapshot).count() == 1


def test_availability_matrix_measured(db):
    league, teams, players, target = _world(db)
    matrix = availability_svc.family_availability(db, teams["H"].id,
                                                  target.kickoff_at, target.id)
    assert matrix["families"]["player_appearances"]["estimated"] is True
    assert matrix["families"]["player_appearances"]["strict"] is True
    assert matrix["families"]["injuries"]["strict"] is False
    unknown = availability_svc.player_availability(db, players["Alpha"].id)
    assert unknown["availability_status"] == "unknown"


def test_api_player_endpoints(client, db):
    league, teams, players, target = _world(db, code="P9API")
    response = client.get(f"/api/v1/features/player/{target.id}?mode=historical_estimated")
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["feature_version"] == "player_features_v1"
    assert "provenance" in body and "availability" in body
    assert client.get(f"/api/v1/features/player/{target.id}/availability").status_code == 200
    assert client.get(f"/api/v1/features/player/{target.id}/contributors?mode=historical_estimated").status_code == 200
    assert client.get(f"/api/v1/features/player/{target.id}/quality?mode=historical_estimated").status_code == 200
    assert client.get("/api/v1/features/player/999999").status_code == 404
    assert client.get(f"/api/v1/features/player/{target.id}?mode=nope").status_code == 400


def test_prediction_engine_untouched():
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "status", "--porcelain", "backend/app/services/predictions/",
         "backend/app/services/intelligence/", "backend/app/services/evaluation/"],
        capture_output=True, text=True, cwd=repo_root)
    assert result.stdout.strip() == "", result.stdout

