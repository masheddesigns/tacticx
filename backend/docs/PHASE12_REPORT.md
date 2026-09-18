# Phase 12 — Final Report: Advanced Pre-Match Modeling & Walk-Forward Research

## Architecture

Versioned immutable datasets → family-gated features → chronological
splits/folds → deterministic candidates → train-only preprocessing →
validation-only calibration → identical-population evaluation → ablation →
bootstrap significance → promotion gate (evidence only). New
`app/services/model_research/` (11 modules) + `research_models` table.
Production code untouched; research writes only `data/research/` artifacts
and registry rows.

## Research dataset versions

`research_ds_<hash>` over (league, seasons, families, mode, N). One
chronological pass per league (Elo/form/rest/xG/shots/continuity from
bulk-prefetched rows, no N+1). Current/upcoming data excluded by
construction (FINISHED + scores only, strictly earlier matches).

## Chronological splits

EPL 2015+2022 → 2023 → 2024 (primary). LA_LIGA 2015 → 2023H1 → 2023H2 via
split-date firewall (2024-01-15). Single-season leagues via expanding folds
(train grows, 100-row validation tail, test block). Random splitting never
used; empty windows raise.

## Baseline results (EPL 2024, N=380/375)

ensemble_v1: acc 0.5237, LL 0.9905, Brier 0.5913, ECE 0.0516 (matches Phase 5
exactly — dataset labels validated). Elo inconclusive vs ensemble; Poisson
degradation (dBrier −0.0183, CI excludes zero).

## Candidate results

logreg_team primary (EPL): degradation on Brier and log-loss (CIs exclude
zero), accuracy inconclusive. xG/player/all variants on N=182: all
inconclusive. Cross-league logreg_team: LA_LIGA +0.0176 inconclusive;
SERIE_A/BUNDESLIGA/LIGUE_1 folds all inconclusive. Robustness: seed-invariant
(7 vs 42 identical), less training data worsens (expected).

## Feature coverage

team ~100% (post-warmup); xg/shots/player gated populations reported per
experiment (e.g. 182/375 EPL); missingness reports give eligible/missing/
coverage %; strict xG/player unavailable, estimated allowed in research
with labels. No imputation anywhere (complete-case + dropped counts).

## Player-feature results

Continuity differential: Phase 9 experiment weight 0.0 (no train signal);
Phase 12 team+player variant inconclusive on N=182. Coverage ≠ validity —
not promoted on a small estimated-only sample.

## Event-feature results

Registered-only features share the player gate; no unsupported categories
used. No measurable lift; inconclusive.

## xG results

Estimated-only xG variant inconclusive (dBrier +0.0019, CI wide on N=182).
Phase 5 strict rule preserved; no conversion to production-safe xG.

## Combined-model results

logreg_all (team+xg+shots+player, N=182): dBrier −0.0023 inconclusive;
calibration improves its ECE 0.1058 → 0.0664 but Brier stays flat.

## Calibration

Validation-fit temperatures (1.12 team, 1.74 xg-variant); raw vs -cal
versions reported separately; test labels never used.

## Ablation

Additive (team → +xg → +player → +all) and leave-one-out run with coverage
per plan; xG/player plans halve N (182 vs 375) — reported alongside, never
presented as generally superior.

## Cross-league validation

Per-league tables above (no pooled hiding); aggregate method: none applied
— leagues reported separately by policy.

## Robustness

Seeds identical; windows (2015+2022 vs 2022-only) both degradation;
regularization fixed per spec; randomness none (deterministic GD).

## Market comparison

EPL 2024 (N=284): model Brier 0.5939 vs market 0.5683 — market sharper,
benchmark-only, pre-cutoff observations only, never an input.

## Statistical significance

Paired ΔBrier/ΔLogLoss/ΔAccuracy + 95% bootstrap CIs, identical populations;
CI-includes-zero → inconclusive. Primary pre-declared; 10 candidates
counted; no cherry-picking (all leagues reported incl. poor ones).

## Leakage audit

See PHASE12_LEAKAGE_AUDIT.md. All adversarial tests pass.

## Reproducibility

Dataset/model/seed/version-keyed artifacts; byte-identical re-run enforced
(mismatch raises); coefficients + scaler + temperature stored.

## Production regression

changed = 0: file-level gate test over 11 service dirs + full suite green.
Research artifacts isolated (data/research/, registry rows only).

## Model registry

See PHASE12_MODEL_REGISTRY.md. 10 candidates, all research status.

## Tests

Previous: 380. New: 14. Total: 394. Passed: 394. Failed: 0. Skipped: 0.

## Performance

Season experiment ~1.6–2s (stored baselines; live fill counted, here 0);
full EPL matrix minutes first run; suite <5min target met (21s).

## Security

No new credentials/secrets; research reads production rows, writes only
artifacts/registry; no betting outputs (scenario CLI is diagnostic).

## Limitations

- Single test seasons per league; xG/player populations small (N≈182).
- Folds pools small (35–60/block) → wide CIs.
- No gradient-boosted trees (no sklearn in env; numpy-only policy kept).
- Baselines depend on stored prediction coverage (live fill otherwise).

## Promotion decision

NO PROMOTION. Primary hypothesis failed (degradation); exploratory all
null. ensemble_v1 retained. Registry records the distinction permanently.

## Commit

Phase 12 commit (see git log).

## Status: READY

Interesting signal distinguished from robust signal from production-ready
signal — with the registry preserving that distinction.
