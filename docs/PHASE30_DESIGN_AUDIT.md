# Phase 30 Design Audit — Model Governance Control Points

**Date**: 2026-09-23 · **Baseline**: `ad9f72e` (Phase 29 CLOSED/READY) ·
Branch `main`, clean tree. Alembic head: `0013_research_registry`.

## 1. Existing identity fields

| Concept | Identity | Location |
|---|---|---|
| Production model | `model_name="ensemble"`, `MODEL_VERSION="ensemble_v1"`, runtime `model_version="ensemble_v1-elo+poisson"` (members joined) | `predictions/ensemble.py:34-35,79-80` |
| Readiness config | `model_id == model_version == "ensemble_v1-elo+poisson"`, single-entry registry | `readiness_gate.py:101-127` |
| Phase 26 snapshot | `execution_key` (match+cutoff+model+feature hash), `prediction_hash` (UNIQUE) | `prediction_execution/contracts.py:43-57` |
| Phase 29 candidate | `candidate_id=cand_{hex12}`, `code_hash`, declared inputs | `research/candidates.py` |
| Phase 29 dataset | `dataset_id=ds_{hex12}`, `dataset_hash` (UNIQUE) | `research/datasets.py` |
| Phase 29 experiment | `experiment_id=exp_{hex12}`, `result_hash` (UNIQUE), evidence state | `research/experiments.py` |
| Phase 27 evaluation | `evaluation_key` (prediction+outcome, UNIQUE) | `prediction_evaluation` |

## 2. Champion representation today

**None exists.** No `champion/current_model/active_model` concept anywhere
in backend or frontend. The de-facto champion is a constellation of
defaults: `PredictionComposer.default_model="ensemble"`,
`DEFAULT_MODEL_ID`, `SUPPORTED_MODEL_IDS`, scheduler executors calling
execution without `model_id`. Lifecycle `PredictionVersion` records
`model_version` per row but selects nothing global.

## 3. Where model selection currently occurs

1. `intelligence/composer.py:78-93` — explicit request or regime map.
2. `lifecycle/versions.py:148-171` — passthrough (`None` = regime default).
3. `UpcomingPredictionService(model=None)` — passthrough.
4. CLI `--model` flags (default `None`) — per-call override.
5. API: lifecycle `PredictRequest.model`, legacy `GenerateRequest.model`,
   Phase 26 `ExecutePredictionRequest.model_id` (allowlisted).
6. Scheduler executors — no model param (always default).
7. `readiness_gate.get_prediction_config` — silent default fallback.

## 4. Production control points (accidental-change surface)

1. **Any caller passing a non-default model** (lifecycle, legacy
   predictions API, CLI flags). Only Phase 26 is allowlisted.
2. **Silent config fallback** (`get_prediction_config` returns
   `model_id="default"` on unknown input).
3. **Weight-blind version string**: `ensemble_v1-elo+poisson` covers both
   50/50 and 60/40 math. → Phase 30 artifact identity MUST include
   weights/config fingerprint (spec §2).
4. **Mutable module globals** (`MODEL_REGISTRY`, `DEFAULT_JOBS`,
   `READINESS_CONFIG_REGISTRY`) — source edits change production.
5. **Scheduler executor calling execution without `model_id`** — adding a
   param there silently re-targets all scheduled predictions.
6. **Research registration accepts free-form members/weights** — contained
   by the `predict_with_candidate` allowlist; legacy
   `model_research/promotion.py` candidate→production statuses are inert
   (nothing in prod reads that table).
7. **`model_config` JSON on legacy `Prediction` rows** — write-only today.

## 5. Auth / guards

No authentication exists (`get_db` yields sessions; actor is
self-asserted, e.g. `actor="api_operator"` default). Operational guard:
`settings.operational_endpoints_enabled` → 403 (research create/rerun,
jobs run/cleanup, activation). Prediction write paths (lifecycle,
Phase 26 POST, legacy generate, readiness persist) are unguarded.
Per spec §9: `required_approval_count` defaults to 1; actor strings are
recorded as asserted, never invented.

## 6. Design consequences for Phase 30

- **New authority, no rewiring**: governance owns a `model_registry`
  champion binding + `resolve_active_model_id(scope)`; default execution
  paths stay pinned to `ensemble_v1-elo+poisson`. Activation changes
  authority, never prediction code. (Future traffic-switch wiring is
  explicitly out of scope and documented.)
- **Artifact identity includes weights** (closes control point 3).
- **No scheduler integration** (control point 5 stays untouched; §25).
- **No changes to composer/lifecycle/legacy paths** (control point 1
  stays as-is; governance neither widens nor narrows them).
- **CLI `model` command** follows the `jobs` subcommand pattern.
- **Migration 0014** adds 7 governance tables; no FKs into production
  tables (string linkage only).
- **Monitoring as evidence only** (§26): canary checklist reads anomaly
  state; no auto-transitions.
