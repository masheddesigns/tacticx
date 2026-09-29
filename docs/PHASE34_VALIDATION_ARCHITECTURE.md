# Phase 34 Validation Architecture

Contract: `CANDIDATE_VALIDATION_V1` · Calculation: `validation_calc_v1`

> Phase 34 validates whether a candidate satisfies configured
> requirements for human governance review. It does not authorize or
> perform production activation.

## 1. Data flow

```
Phase 29 candidate artifact + Phase 33 evidence snapshot + config v1
                        ↓
              14 deterministic rules (read-only)
                        ↓
              BLOCKED / INSUFFICIENT / INCONCLUSIVE / VALIDATED
                        ↓
              immutable candidate_validation_reports row
                        ↓
              human reads report → Phase 30 workflow (explicit)
```

## 2. Rule engine

REAL_EVIDENCE_AVAILABLE · PAIRED_OBSERVATIONS_SUFFICIENT (n ≥ 50) ·
TEMPORAL_INTEGRITY (0 violations) · OUTCOME_COMPLETENESS ·
SHARED_FEATURE_INTEGRITY · PREDICTION_SCHEMA_COMPATIBILITY ·
MODEL_ARTIFACT_IMMUTABILITY (hash recompute) · DATASET_PROVENANCE ·
EVIDENCE_SNAPSHOT_INTEGRITY · CALIBRATION_AVAILABILITY ·
PERFORMANCE_STABILITY (allowed states: SUPPORTED_DIFFERENCE,
INCONCLUSIVE) · PRODUCTION_COMPATIBILITY · OPERATIONAL_HEALTH
(no CRITICAL anomalies) · ROLLBACK_AVAILABLE (champion resolvable).
Rule states: PASS / BLOCKED / INSUFFICIENT_DATA / INCONCLUSIVE /
WARNING. Overall: BLOCKED > INSUFFICIENT_DATA > VALIDATED (if evidence
allowed) / INCONCLUSIVE.

## 3. Configuration

`candidate_validation_v1` (code-versioned): min 50 pairs, 30% max
exclusion, 0 temporal violations, calibration required, rationale
recorded. Human/domain sign-off required before production use.
Unknown config ids fail closed.

## 4. Evidence binding & staleness

Reports pin candidate + champion + evidence snapshot + config + hash.
`check_staleness`: SUPERSEDED (newer report exists) > STALE (champion
changed) > VALID. Reruns deterministic (same hash, same id).

## 5. No-governance guarantee

The package imports governance read paths only (artifact lookup,
champion resolution, compatibility probe, anomaly read). No imports of
promotion/approval/activation/rollback writers; asserted by tests and
reviewable in one directory listing.

## 6. Surfaces

API `/candidate-validation/*` (reads open; run/refresh/cohort-create
guarded); CLI `validation *` (service reuse); frontend `/validation`
(status, candidates, rules, metrics — never Approved/Production/Best).
No scheduler integration by design (manual invocation preferred).

## 7. Limitations

- With 0 real pairs the only possible outcome is INSUFFICIENT_DATA.
- Neutral-but-measured evidence validates the package, not superiority.
- Worse-on-both-metrics evidence stays INCONCLUSIVE (reviewable, not
  auto-rejected).
- Actors are self-asserted (no auth infrastructure).
