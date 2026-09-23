# TacticX Phase 26 — Pre-Match Prediction Execution Layer

Contract Version: `PREMATCH_PREDICTION_V1`

## 1. Overview

Phase 26 is the production-safe execution/integration layer between the
Phase 25.1 readiness gate and downstream consumers:

```
Readiness Certificate (Phase 25.1)
        ↓
Cutoff-Safe Feature Snapshot (features_v1, STRICT_PREMATCH)
        ↓
Prediction Configuration (PredictionReadinessConfig registry)
        ↓
Existing Production Model (ensemble_v1-elo+poisson, unmodified)
        ↓
Output Validation (probabilities, lambdas, markets)
        ↓
Immutable Prediction Snapshot (append-only, content-addressed)
        ↓
Match Intelligence (read-only attach, same cutoff)
        ↓
API / Scheduler / Frontend
```

This is an execution/integration phase, NOT a model-research phase. No
Elo/Poisson/ensemble mathematics were changed. No weights tuned. No models
trained. No betting recommendations introduced.

## 2. Execution Contract

Entry point: `execute_pre_match_prediction(db, match_id, cutoff, ...)`.

Execution REQUIRES, in order:
1. Valid match with both teams and a kickoff.
2. `PRE_MATCH` mode with `cutoff` strictly before `kickoff`.
3. `model_id` in the supported set (`ensemble_v1-elo+poisson`) with a
   registered `PredictionReadinessConfig`.
4. A bound Phase 25.1 readiness certificate (see §3).
5. A cutoff-safe feature snapshot (see §4).
6. A `valid` model output that passes output validation (see §6).

Allowed readiness: `PREDICTION_READY`, `READY_DEGRADED`. The degraded flag
is preserved in snapshot metadata and surfaced in API/UI. `BLOCKED` never
yields a prediction.

## 3. Readiness Binding

Every prediction binds to the exact latest Phase 25.1 certificate:
`resolve_certificate()` enforces that the certificate exists, belongs to
the match, is the latest evaluation (superseded certificates refuse with
`CERTIFICATE_SUPERSEDED`), has a cutoff equal to the execution cutoff
(`CERTIFICATE_CUTOFF_MISMATCH`), and carries eligible readiness
(`READINESS_BLOCKED` otherwise). The certificate id + hash are stored in
the snapshot and covered by the prediction hash.

## 4. Cutoff-Safe Feature Snapshot

`build_cutoff_safe_snapshot()` wraps the existing `features_v1` builders
(`build_feature_snapshot` + `assess_availability`, both
`STRICT_PREMATCH`). Every input derives from pre-cutoff records through
`HistoricalFeatureRepository`. The envelope
`{match_id, cutoff, feature_version, model, features, availability,
provenance}` is canonically serialized (sorted keys, compact separators)
and SHA-256 hashed. Snapshots persist in `prediction_feature_snapshots`,
deduplicated by `(match_id, snapshot_hash)`.

Leakage protection (adversarially tested): post-cutoff results, odds,
events, lineups, and closing-market data never alter a `PRE_MATCH`
prediction — repeated execution at the same cutoff returns the identical
snapshot (`cache_hit: true`, hash unchanged).

## 5. Model Execution

The existing promoted `EnsembleModel.from_names(["elo", "poisson"])` is
invoked unmodified via `predict(db, match_id, cutoff, STRICT_PREMATCH)`.
Member names derive from the registered model id. Golden values preserved:
`P_home ≈ 0.60605`, `P_draw ≈ 0.22233`, `P_away ≈ 0.17161`,
`λ_home ≈ 1.7442`, `λ_away ≈ 0.1713`.

## 6. Output Validation

`validate_prediction_output()` rejects (with no persistence):
non-`valid` status, non-finite/NaN/infinite values, probabilities outside
`[0, 1]`, 1X2 sums outside `1.0 ± 1e-4`, negative lambdas, malformed score
grids, and inconsistent complementary markets (O/U, BTTS tolerance `1e-3`).

## 7. Immutable Snapshots, Idempotency, Hashing

`prematch_prediction_snapshots` rows are never updated. The deterministic
`execution_key` (hash of match + cutoff + model + feature hash) carries a
DB unique constraint: repeated identical execution returns the existing
row; any material change (cutoff, model, features) creates a new versioned
row while prior rows stay byte-identical. `prediction_hash` covers the
full payload including certificate binding; nondeterministic timestamps
live only in `provenance.executed_at`, outside the hash.

## 8. Match Intelligence

The execution service optionally attaches a read-only intelligence
document built by the existing `match_intelligence` service at the same
cutoff (`with_intelligence=True`). The intelligence layer itself is
unmodified; predictions and intelligence share cutoff, model, and
provenance rather than recomputation.

## 9. API

- `POST /api/v1/matches/{id}/predictions` `{cutoff, model_id?,
  certificate_id?, with_intelligence?}` → snapshot or
  `{blocked: true, code, reason, details}` (HTTP 200 envelope; 422 for
  malformed/missing cutoff).
- `GET /api/v1/matches/{id}/prediction-snapshots` → `{status:
  NOT_GENERATED|GENERATED|DEGRADED|BLOCKED, prediction_count, latest,
  snapshots[]}`.
- `GET /api/v1/prediction-snapshots/{prediction_id}` → full snapshot.
  (Distinct paths: `GET /matches/{id}/predictions` belongs to the
  lifecycle router; `GET /predictions/{id}` to the legacy predictions
  router.)

## 10. Scheduler

New job type `pre_match_prediction` (priority 40, 30-min interval).
The executor scans upcoming `SCHEDULED` matches, executes those whose
latest certificate is eligible and lack a bound snapshot, and skips
`BLOCKED`/uncertified matches without retry storms. Idempotency comes
from the execution layer; locks/backoff from the existing orchestrator.

## 11. Frontend

`MatchIntelligencePage` mounts `PredictionExecutionSection` showing
Not Generated / Generated / Degraded / Blocked plus model/version, mode,
cutoff, readiness, version, timestamp, hash, and 1X2 values. Typed client
methods + React-Query hooks (`usePredictionSnapshots`,
`usePredictionSnapshot`, `useExecutePrediction`) follow existing
conventions.

## 12. Database

Migration `0011_prediction_snapshots` (head) creates
`prediction_feature_snapshots` and `prematch_prediction_snapshots` with
FKs, unique constraints (`snapshot_id`, `prediction_id`,
`prediction_hash`, `execution_key`, `(match_id, snapshot_hash)`), and 22
indexes. Verified against real PostgreSQL 16.14: fresh upgrade, downgrade
to 0010, re-upgrade, idempotent re-run, and live end-to-end execution.

## 13. Observability

Execution results carry machine-readable `code` values
(`READINESS_BLOCKED`, `CERTIFICATE_*`, `CUTOFF_AT_OR_AFTER_KICKOFF`,
`UNSUPPORTED_MODEL`, `OUTPUT_VALIDATION_FAILED`, …) suitable for existing
request-ID logging and alerting. No secrets are logged.
