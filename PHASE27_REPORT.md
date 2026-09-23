# TacticX Phase 27 — Prediction Evaluation Report

**Date**: September 23, 2026
**Baseline**: `0574c8c` (Phase 26 READY/CLOSED)
**Status**: READY

---

## 1. Implementation

- **Outcome snapshot** (`outcomes.py`): verified := `FINISHED` + recorded
  scores; canonical SHA-256 payload; idempotent per (match, hash);
  corrected scores supersede explicitly (`supersedes_outcome_id`).
- **Evaluation** (`service.py` + `metrics.py`): per-snapshot 1X2 accuracy /
  log loss / Brier, goal MAE + squared errors, O/U 1.5/2.5/3.5 and BTTS
  accuracy/log-loss/Brier, exact-score hit — all reusing Phase 2
  primitive definitions, no new scoring methodology. Prediction hash
  re-verified before scoring; failures never persist.
- **Metrics/immutability**: `evaluation_key` (prediction_id +
  outcome_hash) unique; repeats return existing record; corrected
  outcomes create new versions; old records byte-identical.
- **Temporal safety**: separate tables, read-only snapshot access,
  adversarial tests (post-match odds can't enter PRE_MATCH features,
  payload/hash stable after evaluation).
- **Aggregation** (`aggregation.py`): read-only means + RMSE-from-SE over
  model/version/competition/season/mode/date filters, with period.
- **Calibration** (`calibration.py`): deterministic per-outcome
  reliability + ECE (Phase 2 definition); measure only.
- **Drift** (`drift.py`): trailing window vs baseline with sample sizes;
  `< 20` flagged insufficient; no auto-verdicts.
- **API** (read-only): `GET /matches/{id}/evaluation`,
  `GET /prediction-snapshots/{pid}/evaluation`,
  `GET /evaluations/summary|/calibration|/drift`.
- **Scheduler**: `post_match_evaluation` (priority 45, hourly); due =
  finished scored matches with unevaluated snapshots; incomplete matches
  never evaluated.
- **Frontend**: `EvaluationSection` (match page, completed matches) +
  `ModelPerformanceSection` (system page: aggregates, calibration,
  drift). No model rankings.

## 2. Temporal safety

- Prediction payload/hash byte-identical after evaluation (tested).
- Post-match odds/events/results cannot alter PRE_MATCH snapshots.
- Evaluation allowed only post-completion; generation path untouched.

## 3. Database

- Migration `0012_evaluation_records` (head; down `0011`):
  `match_outcome_snapshots` (14 cols) +
  `prediction_evaluation_records` (22 cols), unique keys, 25 indexes.
- **PostgreSQL 16.14**: fresh upgrade PASS, downgrade to 0011 PASS
  (tables removed), re-upgrade PASS, idempotent re-run PASS, live
  predict→finish→evaluate PASS (hash stable, summary/calibration/drift
  served). No schema drift.

## 4. Tests

- **Phase 27**: 41 new tests pass (eligibility, outcomes, metrics,
  immutability, idempotency, temporal safety, calibration, drift,
  aggregation, API, scheduler, migration chain, golden).
- **Backend full suite**: 761 passed / 1 failed / 0 skipped.
- **Frontend**: 25 passed (22 + 3 new); `tsc && vite build` passes.
- **Golden regression**: `0.60605 / 0.22233 / 0.17161`,
  `λ 1.7442 / 0.1713` unchanged.
- **Ruff**: only convention-matching flags remain in new code
  (UP/I001/RUF013/B008/S110/BLE001 shared with baseline files).

## 5. Known pre-existing failures

- Phase 18 `test_readiness_splits_not_fixture_only` — pre-existing,
  unrelated, untouched (not counted as regression).
- Phase 20 `test_all_job_types` count 7 → 8 (Phase 27 adds the 8th job
  type per §12); Phase 26 chain test now asserts linkage not headship.

## 6. Files changed

- New: `app/services/prediction_evaluation/` (8 files),
  `app/db/models/evaluation_records.py`,
  `app/api/routes/prediction_evaluation.py`,
  `migrations/versions/0012_evaluation_records.py`,
  `tests/test_phase27_evaluation.py`,
  `frontend/.../EvaluationSection.tsx`,
  `frontend/.../ModelPerformanceSection.tsx`,
  `PHASE27_EVALUATION.md`, `PHASE27_REPORT.md`.
- Modified: `app/db/models/__init__.py`, `app/main.py`,
  `app/services/scheduler/{config,executors}.py`,
  `tests/{test_phase20_scheduler,test_phase26_prediction_execution}.py`,
  frontend `api/{client,queries,types}.ts`,
  `pages/{MatchIntelligencePage,SystemStatusPage}.tsx`,
  `test/apiClient.test.ts`.

## 7. Final decision

**PHASE 27 READY.** Phase 28 not started.
