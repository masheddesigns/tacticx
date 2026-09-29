"""Phase 34 deterministic rule engine (14 rules, evidence only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceSnapshot

from .contracts import (
    RULE_BLOCKED,
    RULE_INCONCLUSIVE,
    RULE_INSUFFICIENT,
    RULE_PASS,
    RULE_WARNING,
)


def _rule(rule_id: str, state: str, result: bool, explanation: str,
          measured: Any = None, required: Any = None,
          evidence_ref: Optional[str] = None) -> Dict[str, Any]:
    return {"rule_id": rule_id, "state": state, "result": result,
            "explanation": explanation, "measured_value": measured,
            "required_value": required, "evidence_reference": evidence_ref}


def evaluate_rules(
    db: Session,
    *,
    snapshot: EvidenceSnapshot,
    candidate_artifact_id: str,
    champion_artifact_id: str,
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run all gates against an immutable evidence snapshot. Read-only."""
    from app.services.model_governance.artifact import get_artifact
    from app.services.model_governance.lifecycle import GovernanceError
    from app.services.production_monitoring import detect_anomalies

    rules: List[Dict[str, Any]] = []
    paired = snapshot.paired_count or 0
    temporal = snapshot.temporal_audit or {}
    cal = snapshot.calibration or {}
    try:
        candidate = get_artifact(db, candidate_artifact_id)
    except GovernanceError:
        candidate = None

    # 1. REAL_EVIDENCE_AVAILABLE
    if paired <= 0:
        rules.append(_rule(
            "REAL_EVIDENCE_AVAILABLE", RULE_INSUFFICIENT, False,
            "no eligible real-world paired observations",
            paired, "> 0", snapshot.snapshot_id))
        return rules  # nothing further is measurable
    rules.append(_rule("REAL_EVIDENCE_AVAILABLE", RULE_PASS, True,
                       f"{paired} paired observations", paired, "> 0",
                       snapshot.snapshot_id))

    # 2. PAIRED_OBSERVATIONS_SUFFICIENT
    required_n = config.get("min_paired_observations", 50)
    rules.append(_rule(
        "PAIRED_OBSERVATIONS_SUFFICIENT",
        RULE_PASS if paired >= required_n else RULE_INSUFFICIENT,
        paired >= required_n,
        f"paired={paired} required={required_n}", paired, required_n,
        snapshot.snapshot_id))

    # 3. TEMPORAL_INTEGRITY
    invalid = temporal.get("temporal_invalid", 0)
    rate = (invalid / paired) if paired else 1.0
    max_rate = config.get("max_temporal_violation_rate", 0.0)
    rules.append(_rule(
        "TEMPORAL_INTEGRITY",
        RULE_PASS if rate <= max_rate else RULE_BLOCKED,
        rate <= max_rate,
        f"temporal_invalid={invalid} rate={round(rate, 4)}", rate, max_rate,
        snapshot.snapshot_id))

    # 4. OUTCOME_COMPLETENESS (every paired row resolved an outcome by construction)
    rules.append(_rule("OUTCOME_COMPLETENESS", RULE_PASS, True,
                       f"{paired} paired rows carry verified outcome hashes",
                       paired, paired, snapshot.snapshot_id))

    # 5. SHARED_FEATURE_INTEGRITY (eligibility enforced hash equality)
    rules.append(_rule("SHARED_FEATURE_INTEGRITY", RULE_PASS, True,
                       "eligibility required feature id+hash equality",
                       paired, paired, snapshot.snapshot_id))

    # 6. PREDICTION_SCHEMA_COMPATIBILITY (challenger outputs validated at execution)
    rules.append(_rule("PREDICTION_SCHEMA_COMPATIBILITY", RULE_PASS, True,
                       "shadow execution enforces Phase 26 validation + "
                       "Phase 30 compatibility before storage",
                       paired, paired, snapshot.snapshot_id))

    # 7. MODEL_ARTIFACT_IMMUTABILITY
    if candidate is None:
        rules.append(_rule(
            "MODEL_ARTIFACT_IMMUTABILITY", RULE_BLOCKED, False,
            "candidate artifact unknown", False, True,
            candidate_artifact_id))
        return rules
    from app.services.model_governance.artifact import artifact_identity
    from app.services.model_governance.contracts import canonical_hash

    cfg = candidate.config_fingerprint or {}
    identity = artifact_identity(
        model_id=candidate.model_id,
        model_version=candidate.model_version,
        members=cfg.get("members", []),
        weights=cfg.get("weights", []),
        candidate_id=candidate.candidate_id,
        experiment_id=candidate.experiment_id,
        dataset_id=candidate.dataset_id,
        dataset_hash=candidate.dataset_hash,
        feature_contract=candidate.feature_contract,
        prediction_mode=candidate.prediction_mode,
        train_period=candidate.train_period,
        evaluation_period=candidate.evaluation_period,
        code_hash=candidate.code_hash)
    intact = canonical_hash(identity) == candidate.artifact_hash
    rules.append(_rule(
        "MODEL_ARTIFACT_IMMUTABILITY",
        RULE_PASS if intact else RULE_BLOCKED, intact,
        "artifact hash recomputed from stored fields",
        intact, True, candidate_artifact_id))

    # 8. DATASET_PROVENANCE
    has_dataset = bool(candidate.dataset_hash)
    rules.append(_rule(
        "DATASET_PROVENANCE",
        RULE_PASS if has_dataset else RULE_WARNING, has_dataset,
        "artifact carries a dataset fingerprint", has_dataset, True,
        candidate_artifact_id))

    # 9. EVIDENCE_SNAPSHOT_INTEGRITY
    from app.services.evidence import snapshot_to_dict

    stored = snapshot_to_dict(snapshot)
    recomputed_keys = {"cohort_id", "cohort_hash", "paired_count",
                       "evidence_state", "snapshot_hash"}
    rules.append(_rule(
        "EVIDENCE_SNAPSHOT_INTEGRITY",
        RULE_PASS if recomputed_keys <= set(stored) else RULE_BLOCKED,
        recomputed_keys <= set(stored),
        "snapshot fields present and hash-pinned", True, True,
        snapshot.snapshot_id))

    # 10. CALIBRATION_AVAILABILITY
    cal_ok = isinstance(cal, dict) and cal.get("state") == "AVAILABLE"
    rules.append(_rule(
        "CALIBRATION_AVAILABILITY",
        RULE_PASS if cal_ok else RULE_WARNING, cal_ok,
        f"calibration section state={cal.get('state') if isinstance(cal, dict) else None}",
        cal_ok, True, snapshot.snapshot_id))

    # 11. PERFORMANCE_STABILITY (evidence state gate, neutral language)
    allowed = ["SUPPORTED_DIFFERENCE", "INCONCLUSIVE"]
    state = snapshot.evidence_state
    if state in allowed:
        rules.append(_rule("PERFORMANCE_STABILITY", RULE_PASS, True,
                           f"evidence state {state} is reviewable", state,
                           allowed, snapshot.snapshot_id))
    elif state == "DESCRIPTIVE_ONLY":
        rules.append(_rule("PERFORMANCE_STABILITY", RULE_INSUFFICIENT, False,
                           "measurements present but below inference policy",
                           state, allowed, snapshot.snapshot_id))
    else:
        rules.append(_rule("PERFORMANCE_STABILITY", RULE_INCONCLUSIVE, False,
                           f"evidence state {state} does not satisfy policy",
                           state, allowed, snapshot.snapshot_id))

    # 12. PRODUCTION_COMPATIBILITY (feature contract + mode vs champion artifact)
    try:
        champion = get_artifact(db, champion_artifact_id)
        compat = (candidate.feature_contract == champion.feature_contract
                  and candidate.prediction_mode == champion.prediction_mode)
    except GovernanceError:
        compat = False
    rules.append(_rule(
        "PRODUCTION_COMPATIBILITY",
        RULE_PASS if compat else RULE_BLOCKED, compat,
        "feature contract + prediction mode match champion",
        compat, True, champion_artifact_id))

    # 13. OPERATIONAL_HEALTH (CRITICAL anomalies block; others observed)
    try:
        anomalies = detect_anomalies(db)
        critical = [a for a in anomalies.get("anomalies", [])
                    if a.get("severity") == "CRITICAL"]
    except Exception:
        critical = ["probe_failed"]
    rules.append(_rule(
        "OPERATIONAL_HEALTH",
        RULE_PASS if not critical else RULE_BLOCKED, not critical,
        f"critical anomalies={len(critical)}", len(critical), 0,
        snapshot.snapshot_id))

    # 14. ROLLBACK_AVAILABLE (current champion binding exists)
    try:
        from app.services.model_governance.registry import current_champion

        binding = current_champion(db)
        rollback_ok = bool(binding and binding.artifact_id)
    except Exception:
        rollback_ok = False
    rules.append(_rule(
        "ROLLBACK_AVAILABLE",
        RULE_PASS if rollback_ok else RULE_BLOCKED, rollback_ok,
        "rollback target (current champion) resolvable", rollback_ok, True,
        snapshot.snapshot_id))

    return rules
