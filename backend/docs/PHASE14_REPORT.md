# Phase 14 — Final Report: Expanded-Dataset Model Validation

## Dataset

16,639 matches (Phase 13 expansion) across 5 leagues; new immutable
versions per (league, families, mode) — e.g. EPL team-family
research_ds_4d82b61d92db. Old versions intact. See
PHASE14_DATASET_COMPARISON.md.

## Dataset comparison / historical coverage

46 season-slots; EPL contiguous 2015–2024; others 2015–2023 (LA_LIGA) and
2015–2023/2023-only mixes. Team ~98%, shots full post-warmup, xG/player
gated populations (EPL test: 182).

## Strict / estimated / unknown temporal

Strict excludes unknown timing (unchanged); xG/player estimated-only in
research with labels; new rows unknown-timing preserved.

## Baseline

EPL 2024 reproduced exactly: acc 0.5237, LL 0.9905, Brier 0.5913 (N=380).
Baseline never redefined.

## Team candidate

EPL season-by-season logreg_team: degradation persists on aggregate;
per-season all inconclusive-or-degradation. Larger N did not rescue it.

## Shots candidate (primary: team+shots)

EPL by season (N≈365–375): 2017 +0.0058 inc; 2018 +0.0123 inc; 2019
−0.0030 inc; 2020 −0.0094 inc; 2021 +0.0151 inc (CI touches zero);
2022 +0.0086 inc; 2023 +0.0182 improvement (CI barely excludes zero);
2024 −0.0022 inc. Cross-league: LA_LIGA +0.0144/+0.0136 inc; SERIE_A
folds −0.0319 degradation; BUNDESLIGA inc; LIGUE_1 inc. Verdict: NO
ROBUST IMPROVEMENT (single marginal season out of 8 + 4 leagues).

## XG / player / combined candidates

xg variant (N=182): inconclusive. player variant (N=182): inconclusive.
logreg_all (N=182): inconclusive. Coverage ≠ validity; small estimated
samples not promoted.

## Season-by-season / cross-league

Tables above; no pooled hiding. Aggregate method: none — reported
separately by policy.

## Calibration

Validation-fit temperatures per experiment (e.g. 1.12 team, 1.74
xg-variant); raw vs -cal reported; test labels never used. Calibration
helps ECE, not Brier.

## Robustness

Seeds 7/42 identical; train windows (2015+2022 vs 2022-only) both
degradation-or-worse; fixed regularization; deterministic GD.

## Learning curve (EPL team+shots, test 2024)

20%→LL 1.0152/ECE 0.105 → 100%→LL 0.9904/ECE 0.051, monotone with
diminishing returns, plateau at 80–100%. More data reduced uncertainty
(CI widths narrowed vs Phase 12), not superiority (still ≈ ensemble).

## Market benchmark

EPL 2024 (N=284): model 0.5939 vs market 0.5683. EPL 2019: no stored
overlap (N=0, reported not filled). Benchmark-only, pre-cutoff only.

## Statistical significance

Paired ΔBrier/ΔLL/ΔAcc + 95% CIs, identical populations; 10 comparisons
counted (primary team+shots EPL + secondaries); no cherry-picking —
poor seasons/leagues reported.

## Leakage audit

See PHASE14_LEAKAGE_AUDIT.md (framework invariants + new split-date guard).

## Reproducibility

dataset/model/seed/split-keyed artifacts; byte-identical re-run enforced
(mismatch raises — triggered once during Phase 14 dev, fixed by keying).

## Production regression

changed = 0: 5/5 stored predictions recompute identically on untouched
production DB; file gate test; full suite green. New history changes
future recomputation legitimately (more pre-cutoff data) without mutating
any stored row.

## Model registry

10 Phase 14 experiments registered (research status); counts queryable via
CLI. No status changes beyond research.

## Tests

Previous: 407. New: 8. Total: 415. Passed: 415. Failed: 0. Skipped: 0.

## Performance

Season experiment ~2s (stored baselines); folds runs slower on
no-coverage leagues (live fill counted); full matrix ~1hcompute;
suite 21s. Phase 14 suite target met for the framework (<5min for
standard runs; bulk matrix is batch work, documented).

## Security

No credentials/secrets; research reads production rows, writes only
artifacts/registry; no betting outputs.

## Limitations

Single test seasons per league; xG/player N≈182; fold pools 35–60;
numpy-only (no sklearn); stored-coverage-dependent baselines; market
overlap 2024-only.

## Promotion decision

NO PROMOTION. Primary failed to show robustness (1 marginal season of 8,
degradation elsewhere, null cross-league). ensemble_v1 retained.

## Commit

Phase 14 commit (see git log).

## Status: READY

INCONCLUSIVE/NO ROBUST IMPROVEMENT — the additional data narrowed
uncertainty without overturning the Phase 12 conclusion.
