# Phase 33 Operations Guide

## Reading evidence

```bash
tacticx evidence status                    # NO_DATA / INSUFFICIENT / AVAILABLE
tacticx evidence cohorts                   # defined populations
tacticx evidence generate [--challenger A] # compute + persist snapshot
tacticx evidence compare --challenger A    # pure read, no writes
tacticx evidence breakdown --challenger A  # competition/season groups
tacticx evidence show --snapshot S         # full snapshot
tacticx evidence refresh [--challenger A]  # new version (append-only)
```

API mirrors: `GET /evidence/{status,cohorts,cohorts/{id},snapshots,
snapshots/{id},compare/{challenger},breakdown/{challenger},
uncertainty/{snapshot}}`, `POST /evidence/{cohorts,refresh}` (guarded).
Frontend: `/evidence` (status, snapshots, paired differences).

## Interpreting states

- NO_DATA: nothing evaluated anywhere — expected before any
  predictions/outcomes exist.
- INSUFFICIENT_REAL_DATA: records exist but zero valid pairs — check
  exclusions (`excluded_by_code`) for the reason (often FILTER_EXCLUDED
  or missing outcomes).
- DESCRIPTIVE_ONLY: measurements present, n < 20 — quote numbers with
  sample sizes, draw no comparisons.
- INCONCLUSIVE / SUPPORTED_DIFFERENCE / CONFLICTING_EVIDENCE: read the
  CIs, not just the point differences.
- INVALID: temporal violation found — investigate data pipeline, do not
  use the snapshot.

## Scheduler refresh

`performance_evidence_refresh` runs every 6h when a challenger is
configured (`challenger_artifact_id`, else clean `skipped`). Verify via
`jobs status`; reruns are no-ops when data is unchanged.

## Failure response

- Empty evidence: normal before real accumulation; do not fabricate.
- Exclusion spikes: inspect `excluded_by_code` (OUTCOME_MISSING after
  corrections is expected until re-evaluation).
- Refresh failures: executor records the error; source rows untouched;
  retry via CLI refresh.

## No-governance guarantee

Evidence operations cannot create promotion requests, approvals,
activations, or rollbacks (asserted in tests). If a governance
transition is desired, use the Phase 30 flow explicitly with a human
actor.
