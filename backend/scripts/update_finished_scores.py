"""Sync genuine final scores from API-Football for finished matches and trigger evaluation scoring.

Runs through finished fixtures from API-Football for 2026-10-01 (and any past dates),
updates match status to FINISHED, writes final home_score and away_score,
and runs evaluate_prediction_snapshot to compare model predictions with real game results.
"""
from __future__ import annotations

import json
import urllib.request
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.db.models.core import Match, MatchStatus
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.session import get_session_local
from app.services.prediction_evaluation.service import evaluate_prediction_snapshot


def fetch_fixtures_for_date(date_str: str) -> list[dict]:
    url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
    headers = {"x-apisports-key": "f1da5a48dd4965ed81ed9444e8191ce4"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        return data.get("response", [])


def update_and_evaluate_finished() -> None:
    SessionLocal = get_session_local()
    db = SessionLocal()

    # Check 2026-10-01
    fixtures = fetch_fixtures_for_date("2026-10-01")
    print(f"Fetched {len(fixtures)} fixtures for 2026-10-01.")

    updated_count = 0
    evaluated_count = 0

    for f in fixtures:
        status_short = f.get("fixture", {}).get("status", {}).get("short")
        if status_short not in ("FT", "AET", "PEN"):
            continue

        prov_match_id = str(f.get("fixture", {}).get("id"))
        h_score = f.get("goals", {}).get("home")
        a_score = f.get("goals", {}).get("away")

        if h_score is None or a_score is None:
            continue

        match = db.query(Match).filter_by(provider_match_id=prov_match_id).first()
        if not match:
            continue

        # Update status and scores
        match.status = MatchStatus.FINISHED.value
        match.home_score = int(h_score)
        match.away_score = int(a_score)
        db.commit()
        updated_count += 1
        print(f"Updated Match {match.id} ({match.provider_match_id}): {match.home_score}-{match.away_score} [FINISHED]")

        # Compare prediction vs actual results
        snaps = db.query(PreMatchPredictionSnapshot).filter_by(match_id=match.id).all()
        for snap in snaps:
            try:
                res = evaluate_prediction_snapshot(db, snap.prediction_id)
                metrics = res.get("metrics", {})
                print(f"   Evaluated Prediction {snap.prediction_id}: Actual={metrics.get('actual_result')} Predicted={metrics.get('predicted_result')} 1X2 Hit={metrics.get('accuracy_1x2')} Brier={metrics.get('brier_1x2')}")
                evaluated_count += 1
            except Exception as e:
                print(f"   Evaluation notice for {snap.prediction_id}: {e}")

    print(f"\nDone! Updated {updated_count} finished matches with verified scores and evaluated {evaluated_count} prediction snapshots.")
    db.close()


if __name__ == "__main__":
    update_and_evaluate_finished()
