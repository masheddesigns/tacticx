# TacticX Phase 25 — Pre-Match Readiness Gate & Quality Protocol

Contract Version: `PREMATCH_CERTIFICATE_V1`

## 1. Overview & Architectural Intent

Phase 25 establishes a strict multi-stage validation gate between acquired current-season fixtures and downstream prediction/intelligence execution:

```
                      ┌────────────────────────────┐
                      │    Raw Acquired Fixture    │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │  Gate 1: Structural Audit  │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │ Gate 2: Cross-Source Recon │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │ Gate 3: Temporal / Cutoff  │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │ Gate 4: Feature / Leakage  │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │ Gate 5: Immutable Cert V1  │
                      └─────────────┬──────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
        PREDICTION_READY     READY_DEGRADED         BLOCKED
```

## 2. Readiness State Taxonomy

| State | Definition | Downstream Prediction Behavior |
| :--- | :--- | :--- |
| **`PREDICTION_READY`** | All Gates 1–4 passed with complete core and optional features. | Full prediction and match intelligence pipeline runs unconditionally. |
| **`READY_DEGRADED`** | Gates 1–3 passed; Gate 4 passed with missing optional features (e.g. lineups, market odds) or non-critical freshness warnings. | Prediction runs using core historical models. UI clearly displays degraded context notice. |
| **`BLOCKED`** | Any gate failed (structural defect, critical reconciliation conflict, duplicate collision, cutoff violation, stale fixture, or insufficient history). | Prediction is strictly refused. Audit reason is recorded and returned. |

## 3. The 5 Gates Detailed

### Gate 1: Structural Validity & Metadata Integrity
- **Mandatory Fields**: `match_id`, `competition`/`league_id`, `home_team_id`, `away_team_id`, `kickoff_at`.
- **Integrity Invariant**: `home_team_id != away_team_id`.
- **Identity Invariant**: Provider identification must be present either on the match (`provider` + `provider_match_id`) or via an associated `MatchSourceMapping`.

### Gate 2: Reconciliation & Cross-Source Identity
- **Conflict Assessment**: Queries `reconciliation_conflicts` for unresolved conflicts (`severity == "critical"` or fields `score_mismatch`, `team_mismatch`, `league_mismatch`, `duplicate_source_match`). Any matching row results in `CRITICAL_RECONCILIATION_CONFLICT`.
- **Duplicate Collision Detection**: Evaluates DB for any other match sharing `league_id`, `home_team_id`, `away_team_id`, with kickoff time within $\pm 24\text{ hours}$. Proximity match results in `DUPLICATE_SUSPICION_AWAITING_RECONCILIATION`.

### Gate 3: Temporal Validity & Cutoff Enforcement
- **Pre-Match Cutoff Rule**: When `mode == "PRE_MATCH"`, strictly enforces `cutoff < kickoff_at`. Evaluation with `cutoff >= kickoff_at` is refused with `CUTOFF_AT_OR_AFTER_KICKOFF`.
- **Stale Fixture Check**: Fixtures where `kickoff_at < now` while status remains `SCHEDULED` or `PRE_MATCH` are flagged with `STALE_FIXTURE_AWAITING_SYNC`.
- **Status Validation**: Postponed, cancelled, suspended, or abandoned matches are flagged with `FIXTURE_POSTPONED_OR_CANCELLED`.

### Gate 4: Feature Availability & Leakage Eligibility
- **Strict Leakage Guard**: Historical queries only evaluate observations before `cutoff` (`kickoff_at < cutoff`).
- **Core Requirement**: Both home and away teams must have at least 3 historical finished matches in the database prior to `cutoff`. Failure produces `INSUFFICIENT_HISTORICAL_MATCHES`.
- **Optional Degradation**: Missing `Lineup` or `OddsSnapshot` records degrade the status to `READY_DEGRADED` with warning notes, allowing the Poisson/ensemble model to execute while disclosing missing context.

### Gate 5: Immutable Certificate Generation
- **Contract Version**: `PREMATCH_CERTIFICATE_V1`.
- **Deterministic Canonical Hashing**: SHA-256 computed over alphabetically sorted keys, stripped whitespace JSON.
- **Append-Only Immutability**: Post-cutoff updates never overwrite certificates in-place. A re-evaluation or newly arrived observation creates a new certificate linked via `supersedes_certificate_id`.

## 4. Current-Season Telemetry Counters

The readiness summary strictly separates and preserves 9 distinct operational counters without collapse:
1. `season`: Canonical season code (e.g. `2026/27`).
2. `operational_mode`: `readiness_only` vs `operational`.
3. `provider_state`: e.g. `UNAVAILABLE`, `ACTIVE`.
4. `fixture_count`: Total current-season fixtures in database.
5. `reconciled_count`: Fixtures passing Gates 1 and 2.
6. `temporally_valid_count`: Fixtures passing Gate 3.
7. `quality_passed_count`: Fixtures passing Gate 4.
8. `prediction_ready_count`: Fixtures in `PREDICTION_READY`.
9. `ready_degraded_count`: Fixtures in `READY_DEGRADED`.
10. `blocked_count`: Fixtures in `BLOCKED`.
11. `blocking_reasons`: Detailed breakdown by reason code.
