# Phase 33 Evidence Architecture

Contract: `REAL_WORLD_EVIDENCE_V1` · Calculation: `evidence_calc_v1` ·
Metrics: `monitoring_metrics_v1` · Buckets: `reliability_buckets_v1`

> Phase 33 produces evidence; it does not make model-promotion decisions.

## 1. Data flow

```
Phase 32 shadow evaluations + Phase 27 champion evaluations
                        ↓
              ELIGIBILITY AUDIT (per-row checks, exclusion ledger)
                        ↓
              EVIDENCE COHORT (deterministic population definition)
                        ↓
              PAIRED OBSERVATIONS (dedupe by shadow: latest wins)
                        ↓
        ┌───────────────┴───────────────┐
        ↓                               ↓
  CHAMPION METRICS              CHALLENGER METRICS
  (means over pairs)            (means over pairs)
        │                               │
        └───────────────┬───────────────┘
                        ↓
              PAIRED DIFFERENCES (challenger − champion)
                        ↓
              UNCERTAINTY (seeded bootstrap CIs + Wilson)
                        ↓
              DATA QUALITY (counts, exclusions, coverage)
                        ↓
              EVIDENCE STATE (deterministic rules)
                        ↓
              IMMUTABLE SNAPSHOT (hash-pinned, versioned)
```

## 2. Populations

- A. Champion evaluated predictions (Phase 27 records in scope).
- B. Challenger evaluated predictions (shadow evaluations in scope).
- C. Paired predictions (shadow rows binding both arms).
- D. Valid paired observations (pass all eligibility checks).
- E. Excluded observations (counted with codes, never repaired).

Comparison uses D only. Champion-only cohorts (no challenger) yield
descriptive champion metrics with INCONCLUSIVE state (no comparison).

## 3. Pairing

Primary unit: the evaluated shadow row (match, both artifacts, shared
snapshot, cutoff, shared outcome). Deduplicated by shadow id keeping
the latest evaluation (corrected outcomes supersede; old rows stay
immutable). Same match/kickoff/cutoff/feature/outcome verified per row;
violations excluded with codes.

## 4. Metrics & uncertainty

Means per arm + paired differences (no single score). Uncertainty:
seeded percentile bootstrap (seed 7, 500 resamples, 95%) on difference
series; Wilson intervals on hit rates; method/seed/resamples recorded.
Calibration recomputed from stored immutable payloads (reliability +
ECE + MCE); <10 pairs ⇒ INSUFFICIENT_DATA section.

## 5. Evidence states

NO_DATA (nothing anywhere) · INSUFFICIENT_REAL_DATA (0 valid pairs) ·
DESCRIPTIVE_ONLY (1–19) · INVALID (temporal violation) ·
INCONCLUSIVE / SUPPORTED_DIFFERENCE / CONFLICTING_EVIDENCE (n≥20,
paired bootstrap CIs: both exclude 0 same direction ⇒ supported; both
exclude 0 opposite ⇒ conflicting; else inconclusive).

## 6. Temporal rules

cutoff < kickoff per pair; feature hash equality with stored row;
outcome known after cutoff (FINISHED + scores). Counters:
temporal_valid/invalid, excluded_post_cutoff, excluded_unknown_timing.

## 7. Snapshot immutability & hashing

Hash covers cohort hash, observation ids, outcome hashes, metric +
uncertainty config, calculation version, results. Reruns return the
existing row. Corrections create new snapshots; old rows frozen.

## 8. Operational refresh

`performance_evidence_refresh` (6h, read-only + append-only) builds the
default cohort and snapshots it. No model/governance writes possible
in these paths (asserted by tests).

## 9. Limitations

Evidence describes measured reality with denominators; it establishes
no causality, ranks nothing, and authorizes nothing. Small samples are
reported, never concluded from. Calibration needs ≥10 pairs;
inference needs ≥20.
