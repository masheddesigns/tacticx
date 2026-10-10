"""Reconcile authentic fixtures and verified scores for October 10 and 11, 2026.

Purges phantom/duplicate match fixtures and populates authentic official scores.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, "/app")

from sqlalchemy import text
from app.db.session import get_session_local
from app.db.models.core import Match
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.models.enums import MatchStatus
from app.services.prediction_evaluation.service import evaluate_prediction_snapshot
from app.services.match_progression import AUTHENTIC_FIXTURE_RESULTS, ensure_match_statistics

PHANTOM_PROVIDER_IDS = [
    "bl_2026_1010_fcb_bvb",
    "bl_2026_1010_dor_hei",
    "bl_2026_1010_boc_wob",
    "ll_2026_1010_soc_ath",
    "ll_2026_1010_gir_sev",
    "sa_2026_1010_mil_laz",
    "sa_2026_1010_juv_tor",
    "epl_2026_1010_new_whu",
    "l1_2026_1010_mar_len",
    "nl_2026_1010_esp_por",
    "ll_2026_1011_bar_mal",
    "sa_2026_1011_int_rom",
    "bl_2026_1011_stu_hof",
    "sa_2026_1011_ata_ver",
    "l1_2026_1011_mar_mon",
]


def reconcile():
    Session = get_session_local()
    db = Session()

    # 1. Purge phantom fixtures
    print("Purging phantom fixtures...")
    for pid in PHANTOM_PROVIDER_IDS:
        m = db.query(Match).filter_by(provider_match_id=pid).first()
        if m:
            mid = m.id
            print(f"  Removing phantom match ID {mid} ({pid})")
            db.execute(text("DELETE FROM match_statistics WHERE match_id = :mid"), {"mid": mid})
            db.execute(text("DELETE FROM mirofish_scenario_runs WHERE match_id = :mid"), {"mid": mid})
            db.execute(text("DELETE FROM intelligence_snapshots WHERE match_id = :mid"), {"mid": mid})
            db.execute(text("DELETE FROM predictions WHERE match_id = :mid"), {"mid": mid})
            db.execute(text("DELETE FROM matches WHERE id = :mid"), {"mid": mid})
    db.commit()

    # 2. Update authentic scores
    print("\nUpdating authentic match results...")
    updated = 0
    evaluated = 0

    for pid, res in AUTHENTIC_FIXTURE_RESULTS.items():
        m = db.query(Match).filter_by(provider_match_id=pid).first()
        if not m:
            continue

        status_val = res["status"]
        m.status = status_val
        m.minute = res.get("minute")
        m.home_score = res.get("home_score")
        m.away_score = res.get("away_score")

        if status_val == MatchStatus.FINISHED.value:
            ensure_match_statistics(
                db,
                m,
                lam_home=1.45,
                lam_away=1.15,
                home_mins=res.get("home_mins", []),
                away_mins=res.get("away_mins", []),
            )

            # Evaluate any snapshots
            snaps = db.query(PreMatchPredictionSnapshot).filter_by(match_id=m.id).all()
            for s in snaps:
                try:
                    evaluate_prediction_snapshot(db, s.prediction_id)
                    evaluated += 1
                except Exception as ex:
                    print(f"    Evaluation error for snap {s.prediction_id}: {ex}")

        updated += 1
        print(f"  Updated {pid}: {m.home_score}-{m.away_score} (Status: {m.status})")

    db.commit()
    db.close()
    print(f"\nDone! Reconciled {updated} authentic matches, evaluated {evaluated} predictions.")


if __name__ == "__main__":
    reconcile()
