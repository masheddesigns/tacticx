# Phase 34 Operations Guide

## Reading validation state

```bash
tacticx validation status                  # counts + champion, always safe
tacticx validation config [--config ID]    # versioned criteria + rationale
tacticx validation candidates              # artifacts with reports
tacticx validation show --validation VAL   # full report
tacticx validation rules --validation VAL  # per-rule PASS/BLOCKED/... + facts
```

API mirrors under `/candidate-validation/*`; frontend `/validation`.

## Running validation

```bash
tacticx validation run --candidate ART --snapshot SNAP [--config ID]
```

Requires a governed challenger artifact and a Phase 33 evidence
snapshot. Deterministic: repeats return the same report id/hash.
Writes one append-only row; touches nothing else.

## Refreshing evidence first

```bash
tacticx evidence refresh [--challenger ART]   # new snapshot if data changed
```

Validation binds a snapshot id; after new outcomes arrive, refresh
evidence, then run validation again (old reports stay immutable;
staleness flags the rest).

## Interpreting results

- INSUFFICIENT_DATA: gather real observations; do not lower thresholds
  to force eligibility.
- INCONCLUSIVE: evidence complete but not meeting policy (or neutral);
  human may still review via Phase 30, or wait for more data.
- BLOCKED: read `blocking_reasons` (rule ids); fix data/integrity/
  operational cause, then re-run (new report).
- VALIDATED_FOR_GOVERNANCE: candidate may enter Phase 30 human review.
  This is NOT approval — invoke promotion/approval explicitly there.

## Staleness

`.../staleness` (or CLI show): VALID → usable; STALE (champion
changed) → re-validate; SUPERSEDED (newer report) → use the newest.

## Safety rules

- Never hand-edit `candidate_validation_reports` rows.
- Never treat VALIDATED_FOR_GOVERNANCE as authorization to activate.
- Threshold changes require human/domain sign-off; record the reason
  with the config version in use.
