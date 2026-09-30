"""Phase 39 — international fixture expansion tests (isolated test DBs).

Covers: taxonomy, config, activation allowlist, season map,
qualification seeds, acquisition identity/idempotency, duplicate
handling, temporal safety, readiness gates, scheduler scoping,
provider capability mapping, domestic regression, golden regression.
Synthetic fixtures exist only here; production tables untouched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team


def _league(db, code, name="Intl League"):
    lg = League(code=code, name=name, provider="api_football",
                provider_league_id="5", season="2024")
    db.add(lg)
    db.commit()
    return lg


def _teams(db, league, code, home="Home NT", away="Away NT"):
    hid = f"p39-{code}-h"
    aid = f"p39-{code}-a"
    home = Team(league_id=league.id, name=home, provider="api_football",
                provider_team_id=hid)
    away = Team(league_id=league.id, name=away, provider="api_football",
                provider_team_id=aid)
    db.add_all([home, away])
    db.commit()
    return home, away


def _finished(db, league, home_id, away_id, kickoff, hs=2, aws=0, tag="h"):
    db.add(Match(
        league_id=league.id, home_team_id=home_id, away_team_id=away_id,
        kickoff_at=kickoff, status="FINISHED", home_score=hs, away_score=aws,
        provider="api_football",
        provider_match_id=f"p39-{tag}-{kickoff.isoformat()}"))
    db.commit()


# -- taxonomy -------------------------------------------------------------------------------------

class TestTaxonomy:
    def test_competition_types(self):
        from app.services.acquisition.competition_types import (
            DOMESTIC_LEAGUE,
            INTERNATIONAL_FRIENDLY,
            UEFA_NATIONS_LEAGUE,
            competition_type,
            describe,
            is_international,
            organization,
        )

        assert competition_type("NATIONS_LEAGUE") == UEFA_NATIONS_LEAGUE
        assert competition_type("FRIENDLIES") == INTERNATIONAL_FRIENDLY
        assert competition_type("EPL") == DOMESTIC_LEAGUE
        assert organization("NATIONS_LEAGUE") == "UEFA"
        assert organization("FRIENDLIES") == "International"
        assert is_international("NATIONS_LEAGUE") is True
        assert is_international("FRIENDLIES") is True
        assert is_international("EPL") is False
        info = describe("NATIONS_LEAGUE")
        assert info["code"] == "NATIONS_LEAGUE"
        assert info["competition_type"] == UEFA_NATIONS_LEAGUE

    def test_no_fake_domestic_mapping(self):
        from app.services.acquisition.competition_types import (
            INTERNATIONAL_COMPETITIONS,
            competition_type,
        )

        for code in INTERNATIONAL_COMPETITIONS:
            assert competition_type(code) != "DOMESTIC_LEAGUE"


# -- configuration ----------------------------------------------------------------------------------

class TestConfiguration:
    def test_supported_leagues_include_internationals(self):
        from app.config import Settings

        default = Settings.model_fields["SUPPORTED_LEAGUES"].default
        assert "NATIONS_LEAGUE:5:2024" in default
        assert "FRIENDLIES:10:2024" in default
        # Domestic entries unchanged.
        assert "EPL:39:2024" in default

    def test_env_examples_documented(self):
        from pathlib import Path

        repo = Path(__file__).parent.parent.parent
        for name in (".env.example", "backend/.env.example"):
            text = (repo / name).read_text()
            assert "NATIONS_LEAGUE:5:2024" in text
            assert "FRIENDLIES:10:2024" in text


# -- activation ----------------------------------------------------------------------------------------

class TestActivation:
    def test_international_codes_allowed(self):
        from app.services.acquisition.activation import TARGET_LEAGUES

        assert "NATIONS_LEAGUE" in TARGET_LEAGUES
        assert "FRIENDLIES" in TARGET_LEAGUES
        # Domestic allowlist intact.
        for code in ("EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"):
            assert code in TARGET_LEAGUES

    def test_no_unsupported_competition_reason(self, db):
        from app.services.acquisition.activation import can_activate_current_season

        league = _league(db, "NATIONS_LEAGUE", "UEFA Nations League")
        _teams(db, league, "P39A", "France", "Spain")
        decision = can_activate_current_season(
            "api_football", "NATIONS_LEAGUE", "2024", db)
        assert "unsupported_competition" not in str(decision)


# -- season map + qualification -----------------------------------------------------------------------------

class TestSeasonMapQualification:
    def test_season_map_entries(self):
        from app.services.acquisition.current_season import SEASON_MAP

        pairs = {(e["competition"], e["provider_season"]) for e in SEASON_MAP}
        assert ("NATIONS_LEAGUE", "2024") in pairs
        assert ("FRIENDLIES", "2024") in pairs
        assert ("EPL", "2026") in pairs

    def test_qualification_seeds(self):
        from app.services.provider_qualification import registry as reg

        entries = reg.get_registry().describe()
        assert "NATIONS_LEAGUE" in entries["api_football"]["supported_competitions"]
        assert "FRIENDLIES" in entries["api_football"]["supported_competitions"]


# -- acquisition ----------------------------------------------------------------------------------------------------------------

def _normalized(code="P39Q", kickoff=None, prov_id="p39-nl-1"):
    from app.services.sources.normalized import NormalizedMatch, Provenance

    now = datetime.now(timezone.utc)
    return NormalizedMatch(
        league_code="NATIONS_LEAGUE", season="2024", home_team="France",
        home_team_id="F1", away_team="Spain", away_team_id="S1",
        kickoff_at=kickoff or (now + timedelta(days=3)),
        status="SCHEDULED", provider_match_id=prov_id,
        provenance=Provenance(source="api_football",
                              source_record_id=f"{prov_id}-rec",
                              collected_at=now))


class TestAcquisition:
    def _league_nl(self, db):
        lg = League(code="NATIONS_LEAGUE", name="UEFA Nations League",
                    provider="api_football", provider_league_id="5",
                    season="2024")
        db.add(lg)
        db.commit()
        return lg

    def test_fixture_persistence_idempotent(self, db):
        from app.services.sources.pipeline import Pipeline

        self._league_nl(db)
        pipe = Pipeline(db, "api_football")
        first = pipe.ingest_match(_normalized())
        second = pipe.ingest_match(_normalized())
        assert first is not None and first == second
        assert db.query(Match).filter_by(
            provider_match_id="p39-nl-1-rec").count() == 1

    def test_malformed_rejected(self, db):
        from app.services.sources.pipeline import Pipeline

        self._league_nl(db)
        pipe = Pipeline(db, "api_football")
        bad = _normalized(prov_id="p39-bad")
        bad.home_team = ""
        assert pipe.ingest_match(bad) is None

    def test_cross_provider_duplicate_suspected(self, db):
        from app.services.acquisition.readiness_gate import (
            evaluate_pre_match_readiness,
        )

        league = self._league_nl(db)
        home, away = _teams(db, league, "P39D", "France", "Spain")
        now = datetime.now(timezone.utc)
        kickoff = now + timedelta(days=3)
        for i, prov in enumerate(("api_football", "csv")):
            db.add(Match(
                league_id=league.id, home_team_id=home.id,
                away_team_id=away.id, kickoff_at=kickoff,
                status="SCHEDULED", provider=prov,
                provider_match_id=f"p39-dup-{i}"))
        db.commit()
        target = db.query(Match).filter_by(
            provider_match_id="p39-dup-0").one()
        result = evaluate_pre_match_readiness(db, target.id)
        dup = result["gate_verdicts"]["gate2_reconciliation"]
        assert dup["duplicate_state"] in (
            "DUPLICATE_CANDIDATE", "DUPLICATE_CONFIRMED",
            "DUPLICATE_RESOLUTION_REQUIRED")


# -- temporal -----------------------------------------------------------------------------------------------------------------

class TestTemporal:
    def _ready_fixture(self, db, code="P39T"):
        league = _league(db, code, "UEFA Nations League")
        league.provider_league_id = "5"
        db.commit()
        home, away = _teams(db, league, code, "France", "Spain")
        now = datetime.now(timezone.utc)
        for i in range(3):
            _finished(db, league, home.id, away.id,
                      now - timedelta(days=21 - i * 7), hs=2, aws=0,
                      tag=f"{code}a{i}")
            _finished(db, league, away.id, home.id,
                      now - timedelta(days=20 - i * 7), hs=1, aws=1,
                      tag=f"{code}b{i}")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="api_football", provider_match_id=f"p39-{code}-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        return target, now + timedelta(hours=1)

    def test_eligible_uses_only_precutoff(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )

        target, cutoff = self._ready_fixture(db, code="P39TE")
        cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        assert cert.readiness_state in ("PREDICTION_READY", "READY_DEGRADED")

    def test_post_cutoff_excluded(self, db):
        from app.db.models.odds import OddsSnapshot
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )
        from app.services.prediction_execution.features import (
            build_cutoff_safe_snapshot,
        )

        target, cutoff = self._ready_fixture(db, code="P39TP")
        before = build_cutoff_safe_snapshot(
            db, target.id, cutoff, "ensemble_v1-elo+poisson",
            "ensemble_v1-elo+poisson")
        db.add(OddsSnapshot(
            match_id=target.id, market_type="1x2",
            timestamp=cutoff + timedelta(hours=2)))
        db.commit()
        after = build_cutoff_safe_snapshot(
            db, target.id, cutoff, "ensemble_v1-elo+poisson",
            "ensemble_v1-elo+poisson")
        assert after["snapshot_hash"] == before["snapshot_hash"]

    def test_snapshot_immutable(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )

        target, cutoff = self._ready_fixture(db, code="P39TI")
        first = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        early_hash = first.payload_hash
        target.status = "FINISHED"
        target.home_score = 3
        target.away_score = 0
        db.commit()
        assert db.query(
            __import__("app.db.models.prematch",
                       fromlist=["PreMatchReadinessCertificate"])
            .PreMatchReadinessCertificate).filter_by(
            certificate_id=first.certificate_id).one().payload_hash == early_hash


# -- readiness ---------------------------------------------------------------------------------------------------------------------

class TestReadiness:
    def test_insufficient_history_blocked(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )

        league = _league(db, "FRIENDLIES", "International Friendlies")
        home, away = _teams(db, league, "P39RB", "Brazil", "Germany")
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="api_football", provider_match_id="p39-P39RB-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cert = generate_readiness_certificate(
            db, target.id, cutoff=now + timedelta(hours=1))
        assert cert.readiness_state == "BLOCKED"
        assert any("INSUFFICIENT_HISTORICAL_MATCHES" in r
                   for r in cert.blocking_reasons)


# -- prediction -------------------------------------------------------------------------------------------------------------------------

class TestPrediction:
    def test_uses_existing_path(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )

        league = _league(db, "NATIONS_LEAGUE", "UEFA Nations League")
        home, away = _teams(db, league, "P39PX", "France", "Spain")
        now = datetime.now(timezone.utc)
        for i in range(3):
            _finished(db, league, home.id, away.id,
                      now - timedelta(days=21 - i * 7), tag=f"P39PXa{i}")
            _finished(db, league, away.id, home.id,
                      now - timedelta(days=20 - i * 7), hs=1, aws=1,
                      tag=f"P39PXb{i}")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="api_football", provider_match_id="p39-P39PX-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        result = execute_pre_match_prediction(db, target.id, cutoff)
        assert result["model_id"] == "ensemble_v1-elo+poisson"
        probs = result["prediction_payload"]["prediction"]
        assert abs(probs["home_win_probability"] + probs["draw_probability"]
                   + probs["away_win_probability"] - 1.0) < 1e-4


# -- scheduler -------------------------------------------------------------------------------------------------------------------------------

class TestScheduler:
    def test_international_scope_filters(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_STATUS_REFRESH
        from app.services.scheduler.executors import get_executor

        league = _league(db, "NATIONS_LEAGUE", "UEFA Nations League")
        _teams(db, league, "P39SJ", "France", "Spain")
        cfg = get_job_config(JOB_STATUS_REFRESH)
        cfg["competitions"] = ["NATIONS_LEAGUE"]
        result = get_executor(JOB_STATUS_REFRESH)(db, cfg, dry_run=True)
        assert result["status"] == "dry_run"

    def test_domestic_defaults_unchanged(self):
        from app.services.scheduler.config import DEFAULT_JOBS

        assert DEFAULT_JOBS["fixture_refresh"]["competitions"] == [
            "EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"]


# -- provider capability ------------------------------------------------------------------------------------------------------------------------------

class TestProviderCapability:
    def test_api_football_accepts_internationals(self, monkeypatch):
        from app.config import get_settings
        from app.services.sources.football.api_football_source import (
            ApiFootballSource,
        )

        monkeypatch.setenv(
            "SUPPORTED_LEAGUES",
            "EPL:39:2024,NATIONS_LEAGUE:5:2024,FRIENDLIES:10:2024")
        get_settings.cache_clear()
        try:
            src = ApiFootballSource.__new__(ApiFootballSource)
            assert src._league_entry("NATIONS_LEAGUE")["provider_id"] == "5"
            assert src._league_entry("FRIENDLIES")["provider_id"] == "10"
        finally:
            get_settings.cache_clear()

    def test_csv_documents_limitation(self):
        from app.services.sources.football.football_data_co_uk import (
            season_url,
        )

        with pytest.raises(ValueError, match="no division"):
            season_url("https://x.test", "NATIONS_LEAGUE", "2024")


# -- golden regression ---------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P39GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
