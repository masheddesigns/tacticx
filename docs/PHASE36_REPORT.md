# PHASE 36 FINAL REPORT — Continuous Real-World Observation & Production Soak

## 1. Objective

Operate the existing system against genuine upcoming matches and
accumulate the first real paired observations. No new models, no
threshold changes, no governance changes.

## 2. Starting State

SYSTEM READY · MODEL ensemble_v1 · GOVERNANCE CONTROLLED · EVIDENCE
NO_DATA · VALIDATION INSUFFICIENT_DATA · REAL OBSERVATIONS 0.

## 3. Runtime

- Docker: unavailable → RUNTIME_BLOCKED recorded; no runtime claimed.
- Compose: statically valid (Phase 31/35, unchanged).
- PostgreSQL: 16.14 native — head 0017 verified via migrate/dump/restore.
- Redis: memory-fallback architecture unchanged.
- API: healthy; `/ready` reports migrations key.
- Scheduler: repeated `run-due` cycles verified (execute → nothing-due).
- Frontend: builds; Operations funnel section reused.

## 4. Provider Qualification (re-checked 2026-09-23)

| Provider | Competition | Season | Qualification | Activation | Fixtures | Results |
|---|---|---|---|---|---|---|
| api_football | EPL | 2026 | reachable, 0 rows | UNAVAILABLE | 0 | n/a |
| api_football | EPL | 2025 | reachable, 0 rows | UNAVAILABLE | 0 | n/a |
| api_football | EPL | 2024 | reachable, 380 rows | historical only | n/a | n/a |
| odds_api | soccer_epl | current | reachable, 1079 market rows | n/a (markets) | n/a | n/a |
| football-data.co.uk | E0/SP1 | 2627 | Level-A CSV | n/a (CSV) | 0 future | 50/69 played |

Reachability ≠ fixture availability (verified per provider).

## 5. Real Fixture Acquisition

- Total discovered: 0 upcoming (all sources).
- Total eligible: 0.
- Real 2026/27 results re-verified (50 EPL played, CSV); results-only
  source, no schedules.

## 6. Production Predictions

- Total: 0 genuine (no eligible fixtures).
- Champion: ensemble_v1 (unchanged, still resolved).
- Cutoff-valid: n/a (no predictions).

## 7. Shadow Predictions

- Total: 0 genuine. Scheduler without challenger reports clean
  `skipped`; NO_ELIGIBLE_MATCHES valid end-to-end (scan, API, CLI).

## 8. Outcomes

- Finished: 0 new real (no real predictions to resolve).
- Verified: 0 new. Supersession path covered by existing suites.

## 9. Evaluations

- Total: 0 new real. Verified-outcome linkage asserted on isolated
  lifecycle tests.

## 10. Genuine Paired Observations

- Total: 0.
- List: (none — no eligible real fixtures).
- Exclusions: n/a (nothing discovered to exclude).

## 11. Exclusions

No real matches discovered; exclusion ledger verified functional on
isolated fixtures (NO_READINESS for finished-without-cert).

## 12. Evidence

- Previous state: NO_DATA. Current state: NO_DATA.
- Real pair count: 0. Snapshot hash: n/a (no snapshot created).

## 13. Phase 34 Validation

- Validation state: INSUFFICIENT_DATA (by construction at zero pairs).
- Evidence snapshot: none. Candidate: none. Result: no run (nothing
  to validate; thresholds untouched).

## 14. Runtime/Restart

- Startup: N/A (no Docker); service-level startup verified via CLI +
  API probes.
- Scheduler: repeated cycles stable, no duplicates, locks recover
  (TTL expiry + cleanup + reacquire demonstrated live).
- Recovery: prediction/shadow/evaluation replay identity verified;
  backup→restore into isolated PostgreSQL (71/71 tables, head 0017).

## 15. Regression

- Backend: 1116 passed / 0 failed (full single-process run; the known
  Phase 18 failure did not trigger in this ordering — see §29).
- Frontend: 43/43 + build.
- Ruff: no new debt (tacticx.py count identical before/after).
- Golden: `0.60605/0.22233/0.17161`, `λ 1.7442/0.1713` unchanged.
- Phase 36 tests: 11/11 (config, no-fixture, exclusions, restart,
  migration head, golden).

## 16. Security

No `.env` tracked; no secret literals in changed files; log redaction
helper tested; existing guards untouched.

## 17. Changed Files

- `backend/scripts/tacticx.py`: system-status DB/migration split
  (reachable vs version probe separated; the only Phase 36 code fix).
- `backend/tests/test_phase36_soak.py`: 11 focused tests.
- `docs/PHASE36_REPORT.md`: this file.

## 18. Commit

c2371a5

## 19. Final Status

- OPERATIONAL STATUS: READY (Docker runtime pending).
- REAL-WORLD OBSERVATION STATUS: NO_ELIGIBLE_MATCHES.
- EVIDENCE STATUS: NO_DATA.
- VALIDATION STATUS: INSUFFICIENT_DATA.
- GOVERNANCE STATUS: UNCHANGED.
