# Phase 25.1 PostgreSQL Verification Report

**Date**: September 22, 2026
**Commit**: `fbaf96a`
**PostgreSQL Version**: 16.14 (Homebrew) on aarch64-apple-darwin25.4.0

---

## Verification Results

| Step | Description | Result |
|------|-------------|--------|
| 1 | Fresh PostgreSQL database + alembic upgrade head | **PASS** |
| 2 | Migration structure (revision, down_revision) | **PASS** |
| 3 | Schema verification (table, columns, indexes) | **PASS** |
| 4 | Existing-schema upgrade (0009 -> 0010) | **PASS** |
| 5 | Downgrade from 0010 | **PASS** |
| 6 | Re-upgrade to head | **PASS** |
| 7 | Migration idempotency/safety | **PASS** |
| 8 | Phase 25.1 migration tests (8/8) | **PASS** |
| 9 | Backend regression test suite (673 passed, 1 pre-existing) | **PASS** |

---

## Detailed Results

### Step 1: Fresh Database Upgrade
- Created fresh `tacticx_pg_verify` database
- Ran `alembic upgrade head` from empty
- All 10 migrations applied cleanly (0001 through 0010)
- No errors, no warnings

### Step 2: Migration Structure
- Alembic head: `0010_prematch_readiness`
- down_revision: `0009_production_schema_complete`
- branch_labels: None

### Step 3: Schema Verification
- **Table**: `prematch_readiness_certificates` exists
- **Columns**: 28 columns, all PostgreSQL-native types (TIMESTAMPTZ, JSON, VARCHAR, INTEGER)
- **Indexes**: 11 indexes (1 PK, 2 UNIQUE, 8 B-tree, including 2 composite)
- **Foreign keys**: 3 (match_id -> matches.id, home_team_id -> teams.id, away_team_id -> teams.id)
- **Nullable fields**: provider, provider_match_id, activation_state, provider_qualification_version, prediction_config, model_version, prediction_mode, required_features, available_features, missing_required_features, missing_optional_features, supersedes_certificate_id — all correctly nullable
- **JSON columns**: gate_verdicts, blocking_reasons, warnings, prediction_config, required_features, available_features, missing_required_features, missing_optional_features — all native PostgreSQL JSON type

### Step 4: Existing-Schema Upgrade
- Database at migration 0009 (all prior tables)
- Ran upgrade to head
- 0010_prematch_readiness applied cleanly
- prematch_readiness_certificates table created with all columns, indexes, and constraints

### Step 5: Downgrade
- Ran `alembic downgrade -1`
- Version rolled back to `0009_production_schema_complete`
- prematch_readiness_certificates table removed
- All indexes removed
- Confirmed: `\dt prematch_readiness_certificates` returns "Did not find any relation"

### Step 6: Re-upgrade
- Ran `alembic upgrade head`
- 0010_prematch_readiness applied again cleanly
- Table recreated with full schema
- Version = `0010_prematch_readiness`

### Step 7: Idempotency
- Ran `alembic upgrade head` on already-migrated database
- No errors, no re-execution, no side effects
- Phase 23 safe migration conventions confirmed working on PostgreSQL

### Step 8: Migration Tests
- 8/8 tests pass (tests run against PostgreSQL connection; tests 5-7 internally create SQLite DBs for structural verification)
- No new warnings beyond existing SADeprecationWarning

### Step 9: Backend Regression
- **Passed**: 673
- **Failed**: 1 (pre-existing: `test_phase18_current_season.py::test_readiness_splits_not_fixture_only`)
- **Skipped**: 0
- Pre-existing failure is unrelated to Phase 25.1

---

## Schema Drift Check

| Column | Migration | Model | Match |
|--------|-----------|-------|-------|
| id | INTEGER PK | Integer PK | Yes |
| certificate_id | VARCHAR(64) UNIQUE | String(64) | Yes |
| certificate_version | VARCHAR(32) | String(32) | Yes |
| readiness_contract_version | VARCHAR(32) | String(32) | Yes |
| match_id | INTEGER FK | ForeignKey | Yes |
| competition | VARCHAR(32) | String(32) | Yes |
| season | VARCHAR(32) | String(32) | Yes |
| home_team_id | INTEGER FK | ForeignKey | Yes |
| away_team_id | INTEGER FK | ForeignKey | Yes |
| kickoff_at | TIMESTAMPTZ | DateTime(tz) | Yes |
| cutoff | TIMESTAMPTZ | DateTime(tz) | Yes |
| readiness_state | VARCHAR(32) | String(32) | Yes |
| gate_verdicts | JSON | JSON | Yes |
| blocking_reasons | JSON | JSON | Yes |
| warnings | JSON | JSON | Yes |
| payload_hash | VARCHAR(64) | String(64) | Yes |
| supersedes_certificate_id | VARCHAR(64) | String(64) | Yes |
| provider | VARCHAR(64) | String(64) | Yes |
| provider_match_id | VARCHAR(128) | String(128) | Yes |
| activation_state | VARCHAR(32) | String(32) | Yes |
| provider_qualification_version | VARCHAR(64) | String(64) | Yes |
| prediction_config | JSON | JSON | Yes |
| model_version | VARCHAR(64) | String(64) | Yes |
| prediction_mode | VARCHAR(32) | String(32) | Yes |
| required_features | JSON | JSON | Yes |
| available_features | JSON | JSON | Yes |
| missing_required_features | JSON | JSON | Yes |
| missing_optional_features | JSON | JSON | Yes |
| created_at | TIMESTAMPTZ | DateTime(tz) | Yes |

No schema drift detected.

---

## Final Status

- **PostgreSQL verification**: PASS
- **Alembic upgrade**: PASS
- **Downgrade**: PASS
- **Re-upgrade**: PASS
- **Schema verification**: PASS
- **Backend tests**: 673 passed / 1 failed / 0 skipped
- **Pre-existing failure**: Phase 18 `test_readiness_splits_not_fixture_only` (unrelated)
- **Phase 25.1 release gate**: CLOSED
- **Phase 26**: MAY BEGIN
