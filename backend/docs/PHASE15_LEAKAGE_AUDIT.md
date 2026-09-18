# Phase 15 — Leakage Audit

## Invariants (tested in tests/test_phase15.py)

- Target exclusion: target match never appears in its own analogues
  (target id absent, deterministic ordering); target rows excluded from
  features by repository construction (Phase 6, preserved).
- Future analogue exclusion: post-cutoff finished matches never returned
  (adversarial future match inserted → absent).
- Future feature exclusion: post-cutoff event rows leave predictions
  byte-identical.
- Future market exclusion: post-cutoff + closing snapshots excluded from
  consensus (consensus values unchanged after injection).
- Scenario isolation: scenario runs leave prediction + core_prediction
  byte-identical.
- Explanation cutoff: explanations rebuild from cutoff-gated composer
  inputs only.
- Snapshot purity: snapshot payload derives solely from the objects above.

## Adversarial results

All three §27 scenarios pass (target-in-pool, future-match, post-cutoff
feature). Market injection (§28) leaves consensus unchanged. Baseline
scenario determinism verified (§29).

## Residual risks

- Analogue similarity uses estimated-mode features where configured; the
  mode travels in provenance and research-mode labels apply.
- Long-league analogue searches are slow (10–14s EPL) but bounded and
  deterministic.
