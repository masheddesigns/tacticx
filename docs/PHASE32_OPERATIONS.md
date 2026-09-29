# Phase 32 Operations Guide

## Eligibility scan

```bash
tacticx shadow matches [--competition EPL]
tacticx shadow status
```
`NO_ELIGIBLE_MATCHES` with `eligible: []` is valid — do not fabricate
fixtures to clear it.

## Running shadow

```bash
# Single match (explicit):
tacticx shadow run --match <id> --challenger <artifact_id>
# Scheduled (uses configured challenger_artifact_id; empty ⇒ skipped):
tacticx jobs run shadow_prediction
tacticx jobs run-due
```

Challenger prerequisites (Phase 30 flow): validate → promotion-request
→ approve → shadow-start. `shadow run` refuses anything else with a
machine-readable code.

## Evaluating

```bash
tacticx shadow evaluate --shadow <shadow_id>   # after the match finishes
tacticx shadow compare --challenger <artifact_id>
tacticx shadow audit --shadow <shadow_id>       # pair validation
```

## Reading evidence

API: `/shadow/summary`, `/shadow/comparison/{challenger}`,
`/shadow/evaluations`, `/shadow/matches[/{id}]`. Frontend: `/shadow`
(challenger select, status cards, factual comparison table).
Monitoring: shadow coverage + evaluation rate via summary endpoint.

## Scheduler

`shadow_prediction` every 30m (config), `challenger_artifact_id` empty
by default ⇒ job reports `skipped` until an operator configures a
challenger. The job never activates, requests, or promotes.

## Failure response

- `NO_CHAMPION_PREDICTION`: wait — shadow follows the champion (§18A).
- `READINESS_BLOCKED` / `CERTIFICATE_*`: fix data/readiness, never bypass.
- `INCOMPATIBLE` / output errors: challenger-side issue; champion unaffected.
- Stale locks / failed jobs: same Phase 31 procedures (TTL, cleanup, rerun).

## Docker / soak notes

Docker unavailable on the build machine: Compose startup/restart and
multi-day soak remain outstanding operational acceptance tests (Phase 31
boundary, unchanged). Real-data soak currently yields
eligible = 0 / executed = 0 (no upcoming 2026/27 fixtures at measured
sources) — an acceptable, honest result.
