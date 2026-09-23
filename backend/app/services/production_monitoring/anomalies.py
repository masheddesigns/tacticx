"""Phase 28 conservative deterministic anomaly detection.

Rules (all deterministic, all sample-guarded; insufficient samples yield
no anomaly, never a guess):
1. ZERO_PREDICTION_GENERATION — eligible certs exist but no snapshots.
2. PREDICTION_COVERAGE_COLLAPSE — coverage rate halved vs prior window.
3. EVALUATION_COVERAGE_COLLAPSE — evaluation rate halved vs prior window.
4. PROVIDER_FRESHNESS_BREACH — source health stale beyond threshold.
5. READINESS_BLOCK_SPIKE — BLOCKED share above threshold.
6. CERTIFICATE_FAILURE_SPIKE — BLOCKED rate above threshold (rate view).
7. EXECUTION_FAILURE_SPIKE — ready matches without predictions spike.
8. IMPOSSIBLE_METRIC_VALUES — stored metrics outside valid ranges.
9. INVALID_PROBABILITY_VALUES — stored probabilities outside [0,1]/NaN.
10. DUPLICATE_EXECUTION_SPIKE — same match+cutoff snapshots duplicated.

Severity: INFO / WARNING / CRITICAL. No automatic root-cause claims.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.db.models.lifecycle import SourceHealth
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.services.prediction_execution.contracts import ELIGIBLE_READINESS

from .contracts import (
    MONITORING_CONTRACT_VERSION,
    canonical_hash,
)

FRESHNESS_BREACH_HOURS = 48
BLOCK_SHARE_THRESHOLD = 0.5
COVERAGE_COLLAPSE_RATIO = 0.5
MIN_ANOMALY_SAMPLE = 10


def _anomaly(anomaly_type: str, severity: str, observed: Any,
             reference: Any, sample_size: int, evidence: Dict[str, Any],
             scope: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"type": anomaly_type, "observed": observed,
               "reference": reference, "scope": scope}
    return {
        "anomaly_id": f"anom_{canonical_hash(payload)[:12]}",
        "anomaly_type": anomaly_type,
        "severity": severity,
        "detected_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
        "period": evidence.get("period"),
        "observed_value": observed,
        "reference_value": reference,
        "sample_size": sample_size,
        "evidence": evidence,
        "scope": scope,
    }


def _latest_certs(db: Session) -> List[PreMatchReadinessCertificate]:
    rows = (db.query(PreMatchReadinessCertificate)
            .order_by(PreMatchReadinessCertificate.id.asc()).all())
    latest: Dict[int, PreMatchReadinessCertificate] = {}
    for row in rows:
        latest[row.match_id] = row
    return list(latest.values())


def detect_anomalies(db: Session, *,
                     scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run all deterministic rules. Read-only."""
    scope = scope or {}
    found: List[Dict[str, Any]] = []

    certs = _latest_certs(db)
    eligible = [c for c in certs if c.readiness_state in ELIGIBLE_READINESS]
    blocked = [c for c in certs if c.readiness_state == "BLOCKED"]
    snap_match_ids = {row[0] for row in
                      db.query(PreMatchPredictionSnapshot.match_id).all()}
    snap_count = db.query(PreMatchPredictionSnapshot).count()

    # 1. Zero generation with eligible demand.
    if len(eligible) >= MIN_ANOMALY_SAMPLE and snap_count == 0:
        found.append(_anomaly(
            "ZERO_PREDICTION_GENERATION", "CRITICAL", 0, len(eligible),
            len(eligible), {"period": "all_time",
                            "note": "eligible certificates but no snapshots"},
            scope))

    # 5/6. Block rate + absolute block count.
    if len(certs) >= MIN_ANOMALY_SAMPLE:
        share = len(blocked) / len(certs)
        if share > BLOCK_SHARE_THRESHOLD:
            found.append(_anomaly(
                "READINESS_BLOCK_SPIKE", "WARNING", len(blocked), len(certs),
                len(certs), {"period": "all_time",
                             "blocked_share": round(share, 4)}, scope))
            found.append(_anomaly(
                "CERTIFICATE_FAILURE_SPIKE", "WARNING", round(share, 4),
                BLOCK_SHARE_THRESHOLD, len(certs),
                {"period": "all_time",
                 "note": "BLOCKED rate view of the same certificates"},
                scope))

    # 7. Ready matches with no prediction at all.
    ready_unpredicted = [c.match_id for c in eligible
                         if c.match_id not in snap_match_ids]
    if len(eligible) >= MIN_ANOMALY_SAMPLE and \
            len(ready_unpredicted) > len(eligible) / 2:
        found.append(_anomaly(
            "EXECUTION_FAILURE_SPIKE", "WARNING", len(ready_unpredicted),
            len(eligible), len(eligible),
            {"period": "all_time",
             "match_ids": ready_unpredicted[:50]}, scope))

    # 4. Provider freshness breach.
    for health in db.query(SourceHealth).all():
        if health.updated_at is None:
            continue
        updated = health.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - updated).total_seconds() / 3600.0
        if age_h > FRESHNESS_BREACH_HOURS:
            found.append(_anomaly(
                "PROVIDER_FRESHNESS_BREACH", "WARNING", round(age_h, 2),
                FRESHNESS_BREACH_HOURS, 1,
                {"period": "all_time", "source": health.source,
                 "state": health.state}, scope))

    # 8/9. Impossible stored values.
    bad_metrics = 0
    bad_probs = 0
    eval_rows = db.query(PredictionEvaluationRecord).limit(5000).all()
    for row in eval_rows:
        m = row.metrics if isinstance(row.metrics, dict) else {}
        acc = m.get("accuracy_1x2")
        if acc is not None and acc not in (0, 1):
            bad_metrics += 1
        for key in ("p_home", "p_draw", "p_away"):
            v = m.get(key)
            if v is not None and (
                    not isinstance(v, (int, float)) or isinstance(v, bool)
                    or not math.isfinite(v) or not 0.0 <= v <= 1.0):
                bad_probs += 1
                break
    if bad_metrics > 0:
        found.append(_anomaly(
            "IMPOSSIBLE_METRIC_VALUES", "CRITICAL", bad_metrics, 0,
            len(eval_rows), {"period": "all_time"}, scope))
    if bad_probs > 0:
        found.append(_anomaly(
            "INVALID_PROBABILITY_VALUES", "CRITICAL", bad_probs, 0,
            len(eval_rows), {"period": "all_time"}, scope))

    # 10. Duplicate same-match same-cutoff snapshots.
    dup_groups = 0
    seen: Dict[Any, int] = {}
    for row in db.query(PreMatchPredictionSnapshot.match_id,
                        PreMatchPredictionSnapshot.cutoff_time).all():
        key = (row[0], str(row[1]))
        seen[key] = seen.get(key, 0) + 1
    dup_groups = sum(1 for v in seen.values() if v > 1)
    if dup_groups > 0:
        found.append(_anomaly(
            "DUPLICATE_EXECUTION_SPIKE", "WARNING", dup_groups, 0,
            len(seen), {"period": "all_time"}, scope))

    # 2/3. Coverage collapse: recent 30d kickoff window vs prior 30d,
    # using the deterministic coverage funnel for both windows.
    from .coverage import coverage_funnel

    now = datetime.now(timezone.utc)
    recent_cov = coverage_funnel(
        db, date_from=now - timedelta(days=30), date_to=now)
    prior_cov = coverage_funnel(
        db, date_from=now - timedelta(days=60),
        date_to=now - timedelta(days=30))
    for rule, key in (("PREDICTION_COVERAGE_COLLAPSE",
                       "prediction_coverage_rate"),
                      ("EVALUATION_COVERAGE_COLLAPSE",
                       "evaluation_coverage_rate")):
        recent_rate = recent_cov.get(key)
        prior_rate = prior_cov.get(key)
        recent_n = recent_cov["denominators"].get(key, 0)
        prior_n = prior_cov["denominators"].get(key, 0)
        if recent_rate is None or prior_rate is None:
            continue
        if recent_n < MIN_ANOMALY_SAMPLE or prior_n < MIN_ANOMALY_SAMPLE:
            continue
        if prior_rate > 0 and recent_rate / prior_rate < COVERAGE_COLLAPSE_RATIO:
            found.append(_anomaly(
                rule, "WARNING", recent_rate, prior_rate, recent_n,
                {"period": "last_30d_vs_prior_30d",
                 "recent_denominator": recent_n,
                 "prior_denominator": prior_n}, scope))

    return {
        "contract": MONITORING_CONTRACT_VERSION,
        "anomaly_count": len(found),
        "anomalies": found,
        "generated_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
    }
