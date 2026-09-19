# Phase 16 — Leakage Audit

## Invariants (tested in `tests/test_mirofish.py`)

- Future data injection (post-cutoff event + future finished match):
  MiroFish request hash byte-identical before/after.
- Future market injection (post-cutoff + closing snapshots): request hash
  byte-identical (market context is pre-cutoff non-closing by construction).
- Future analogue injection: analogues derive from the cutoff-gated
  composer path; target/future matches excluded (Phase 15 tests preserved).
- Scenario mutation (forged `scenario_hash`): rejected as mismatch.
- Cross-match response (wrong `match_id`): rejected.
- Cross-scenario response (wrong `scenario_id`): rejected.
- Invalid probabilities (negative, >1-sum, NaN, infinity, bad sums):
  all rejected; partial triplets range-checked.
- Narrative-only certainty ("guaranteed lock, sure win"): flagged in
  `narrative_safety`, stored verbatim, never converted to probabilities —
  the result carries no statistical probability fields of its own.
- Provider failure (timeout, 429/500-mapped, malformed JSON, wrong
  contract): unavailable state, core prediction path untouched.

## Determinism

Identical (match, cutoff, snapshot, scenario, contract) inputs hash
identically; changing the scenario changes the hash (tested).

## Residual risks

- A malicious provider returning *plausible but wrong* observations within
  a valid envelope cannot be detected by schema validation; observations
  are therefore labeled simulated evidence, never trusted as truth.
- Narrative safety is phrase-based flagging, not semantic understanding.
