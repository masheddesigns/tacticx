# TACTICX PHASE 5 — Final Report: robustness + cross-league validation + probability quality

## 1. What was run (commands, scopes, temporal modes, seeds, dataset)

- Package: `backend/app/services/evaluation/` (`compare`, `calibration`,
  `uncertainty`, `sensitivity`, `subgroups`, `regimes`, `artifacts`).
- CLIs: `backend/scripts/phase5_validate.py --analysis baseline|sensitivity|mc|weights|advanced`,
  `backend/scripts/phase5_deepdive.py`.
- Dataset fingerprint `0b434d17` (sha256-8 of count + max updated_at + league/season
  census): 3272 matches, `BUNDESLIGA 2023: 306, EPL 2015/2022/2023/2024: 380 each,
  LA_LIGA 2015/2023: 380 each, LIGUE_1 2023: 306, SERIE_A 2023: 380`.
- Baseline commands (seed 7, `persist=False` throughout):
  `phase5_validate.py --analysis baseline --scope "EPL:2024,EPL:2023,LA_LIGA:2015,LA_LIGA:2023,SERIE_A:2023,BUNDESLIGA:2023"
  --models "baseline,elo,poisson,poisson-xg,montecarlo,ensemble" --with-market --label crossleague`
  (run `phase5_baseline_crossleague_0b434d17`).
- xG-estimated: `--scope "EPL:2015,LA_LIGA:2015" --models "elo,poisson,poisson-xg,ensemble"
  --temporal-mode historical_estimated --label xg_estimated`
  (run `phase5_baseline_xg_estimated_0b434d17`).
- Sensitivity / weights / MC (EPL:2024, strict, seed 7): runs
  `phase5_sensitivity_sens_epl24_0b434d17`, `phase5_weights_weights_epl24_0b434d17`,
  `phase5_mc_mc_epl24_0b434d17`.
- Advanced walk-forward (EPL train 2022 → validate 2023 → test 2024, strict):
  run `phase5_advanced_adv_epl_0b434d17` (train rows 365, dropped 15, validate N=364).
- Deep-dive (detail rows with goals/scores/grids): run `phase5_deepdive_v1_0b434d17`
  (`phase5_deepdive.py --label v1`).
- All artifacts under `backend/data/phase5/<run_id>/` with `metadata`
  (python/platform/git SHA/UTC timestamp/dataset fingerprint/seed/mode).

## 2. Identical-population comparisons (paired Brier / log-loss diffs + CIs)

Convention: diff = metric(A) − metric(B); positive favors B. Populations are
match-id intersections; N always stated. Reference = `ensemble_v1`.

| Scope | Pair (A vs B) | N common | dBrier (95% CI) | dLL |
|---|---|---|---|---|
| EPL 2024 | elo vs ensemble | 380 | +0.0067 (−0.0069, +0.0201) | +0.0090 |
| EPL 2024 | poisson vs ensemble | 375 | +0.0183 (+0.0047, +0.0315) | +0.0389 |
| EPL 2024 | baseline vs ensemble | 380 | +0.0652 (+0.0390, +0.0917) | +0.0917 |
| EPL 2023 | elo vs ensemble | 380 | +0.0032 (−0.0116, +0.0193) | +0.0048 |
| EPL 2023 | poisson vs ensemble | 364 | +0.0323 (+0.0157, +0.0490) | +0.0740 |
| LA_LIGA 2015 | elo vs ensemble | 380 | −0.0010 (−0.0207, +0.0193) | +0.0002 |
| LA_LIGA 2015 | poisson vs ensemble | 330 | +0.0708 (+0.0465, +0.0948) | +0.1853 |
| LA_LIGA 2023 | elo vs ensemble | 380 | −0.0009 (−0.0190, +0.0163) | +0.0022 |
| LA_LIGA 2023 | poisson vs ensemble | 352 | +0.0515 (+0.0303, +0.0733) | +0.1218 |
| SERIE_A 2023 | elo vs ensemble | 380 | +0.0014 (−0.0163, +0.0185) | +0.0053 |
| SERIE_A 2023 | poisson vs ensemble | 330 | +0.0481 (+0.0271, +0.0684) | +0.1166 |
| BUNDESLIGA 2023 | elo vs ensemble | 306 | +0.0032 (−0.0188, +0.0251) | +0.0084 |
| BUNDESLIGA 2023 | poisson vs ensemble | 261 | +0.0578 (+0.0322, +0.0831) | +0.1467 |

Ensemble_v1 beats poisson_v1 on Brier and log-loss in all 6 scopes (CIs exclude
zero). Ensemble_v1 vs elo_v1: all 6 CIs include zero — Elo is a live backbone,
the ensemble adds log-loss sharpness, not Brier separation from Elo.

## 3. Ablations (identical populations; paired diffs; what changed and what did not)

- **Temperature** (EPL test 2024, T=0.873 fit on validate 2023, N=377):
  advanced vs advanced+cal dBrier −0.0086 (CI −0.0132, −0.0042), dLL −0.0188.
  The validation-fit temperature HURT out-of-sample. Production stays uncalibrated.
- **Learned vs equal weights** (ensemble_v2 0.5/0.2/0.3 vs ensemble_v1, N=380):
  dBrier −0.0053 (CI −0.0129, +0.0024), dLL −0.0075. No measured gain; equal
  weights stand.
- **Weight perturbations** (EPL 2024 vs equal): elo-heavy dBrier +0.0002
  (CI −0.0065, +0.0068); poisson-heavy +0.0060 (CI −0.0006, +0.0127);
  elo-only +0.0067; poisson-only +0.0183. Nothing beats equal weights.
- **xG, strict mode** (all 6 scopes): poisson-xg ≡ poisson_v1 exactly (d=0.0,
  identical N). Cause measured, not assumed: xG rows carry `effective_at=NULL`
  (imported 2026-09-16), and strict mode excludes unknown-timing records —
  the fallback is correct behavior.
- **xG, estimated mode** (parent-anchored, identical N=330): EPL 2015
  dBrier +0.0516 (CI +0.0341, +0.0696), dLL +0.1066, acc 0.476 vs 0.424;
  La Liga 2015 dBrier +0.0690 (CI +0.0494, +0.0886), dLL +0.1763,
  acc 0.536 vs 0.515. poisson-xg ≈ ensemble_v1 on both (diffs ~0, CIs include
  zero). Estimated-only finding, labeled as such.
- **Advanced vs Elo** (EPL test 2024, N=377): dBrier +0.0249
  (CI +0.0077, +0.0433), dLL +0.1020 — Elo beats the ML model here.
- **Advanced vs advanced-xg** (same-season split, LA_LIGA 2015 H2, estimated,
  N=190): dBrier +0.0052 (CI −0.0136, +0.0232), dLL −0.0118
  (CI −0.0455, +0.0207). No measurable xG lift for the ML model (unlike Poisson).
- Full-walk-forward advanced-xg is structurally impossible in this dataset
  (xG confined to single seasons per league; protocol needs 3 xG windows) —
  stated as a limitation, not worked around.

## 4. Calibration (ECE, reliability bins, sparse-bin handling)

- Ensemble_v1 home-win ECE: EPL24 0.052, EPL23 0.063, LaLiga15 0.050,
  LaLiga23 0.080, SerieA23 0.076, Bundesliga23 0.082. Poisson_v1 ECE is worse
  everywhere (0.09–0.21).
- Draw audit (EPL 2024 strict, N=380): ECE 0.039; predictions concentrate in
  0.18–0.31 (72 + 303 of 380 rows in two bins); outer bins flagged sparse.
  Estimated poisson-xg draw Brier 0.1825 vs pre-cutoff league baseline 0.1822 —
  draw skill ≈ baseline; the model does not overclaim draws.
- Bins with N<20 are reported with `sparse: true` and draw no conclusions.

## 5. Sensitivity (parameter perturbations; deltas vs baseline, same population)

- Elo (EPL 2024, N=380): K 18/22 and HFA 50/70 move Brier by ≤0.0021 and
  log-loss by ≤0.0032; max single-match probability shift <0.017. Robust.
- Poisson half-life 60/120/240/365d (N=375): Brier deltas ≤0.0063, but max
  single-match probability shifts reach 0.066/0.214/0.352/0.416 — outcome
  metrics are insensitive while individual probabilities move substantially at
  long half-lives. Documented, not tuned.

## 6. Monte Carlo convergence (seed 7; vs 25k reference, N=375 shared)

Max 1X2 probability difference: 1k → 0.0532; 5k → 0.0154; 10k → 0.0118.
Production default (10k) is within ~0.012 of 25k worst-case; the 1k backtest
default carries sampling noise up to ~0.05 — MC backtest numbers carry that
caveat. Seeds fixed; reruns are bit-identical.

## 7. Poisson truncation (measured tail; grid decision with evidence)

EPL 2024 strict lambdas (N=375): mean outside-0..10 mass 0.00036; 3 matches
above 1% (max 0.0329 at λ≈5.7, Tottenham–Ipswich Nov 2024); 5 above 0.5%.
Grid-12 variant widened and retested on the identical population: Brier Δ
−0.000015, log-loss Δ −0.000131 — fifth-decimal. Grid 0..10 stands on measured
evidence; the stale "negligible" comment now states the measured bound.

## 8. Market benchmark (independent; never an input)

EPL 2024 ensemble slice: N=284 with market (96 skipped_no_market, 0
skipped_no_prediction). Model Brier 0.5939 / LL 0.9961; closing-implied
(market_probability_v1) Brier 0.5683 / LL 0.9589. Market coverage in this
dataset is EPL-2024-only (other scopes: 0–1 matches with odds) — no
cross-league market claims are made. Closing lines remain sharper —
expected, stated descriptively, never a superiority claim and never an input.

## 9. Subgroups, extremes, goals, scores, drift

- Favorite buckets (EPL 2024 ensemble): favorite 0.60–0.75 acc 0.635 (N=96);
  lean 0.45–0.60 acc 0.500 (N=164); tossup <0.45 acc 0.410 (N=105).
  Directional calibration holds; strong-favorite N=15 → insufficient_sample.
- Extreme probabilities: only 15 matches ≥0.75 (3 ≥0.80, 0 ≥0.90) — all buckets
  flagged insufficient; no overconfidence conclusions drawn.
- Goals (strict poisson, N=375): MAE 1.008/match, RMSE 1.300, distributional
  log score 1.970, total-goals MAE 1.435. Estimated poisson-xg (N=330): MAE
  0.935, RMSE 1.223, log score 1.857.
- Correct scores (N=375): mean log-probability of actual score −3.144;
  required-16 mass 0.799, tail 0.201 — the tail is disclosed, not hidden.
- Drift EPL23→EPL24 (ensemble): home rate 0.4605→0.4079, draw 0.2158→0.2447,
  mean entropy 0.968→0.981. Diagnostic context only.

## 10. Regime policy and defaults (unchanged unless evidence forced a change)

- Policy (`regimes.select_model`, availability-only, fixed before evaluation):
  no goal history → `baseline_v1`; xG-eligible → `poisson_v1-xg`;
  advanced fitted → `advanced_v1`; else `ensemble_v1`. Market stays an
  independent benchmark.
- Production default UNCHANGED: `ensemble_v1` (equal weights, uncalibrated,
  grid 0..10, MC 10k). Nothing in Phase 5 earned a default change; the
  temperature and learned-weight pathways stay experimental with measured
  negative/neutral results on record.

## 11. Leakage audit (probes a–g, concrete outcomes)

- (a) Target in features: structurally excluded — repository never queries the
  target match (Phase 2/4 tested; untouched).
- (b) Future matches in history: all reads via kickoff < cutoff
  (`finished_before`); no violations observed.
- (c) Unknown-timing records: xG rows (`effective_at=NULL`, recorded
  2026-09-16) EXCLUDED under strict (measured: xg ≡ base in 6 scopes).
- (d) Standings: chronological current-season reconstruction (Phase 4; untouched).
- (e) H2H: descriptive, min-sample gated (Phase 4; untouched).
- (f) Strict-vs-estimated: non-xG models are mode-INVARIANT (elo/poisson
  metrics identical both modes on EPL15/LaLiga15) — the mode switch moves
  nothing except the xG pathway, which is the point of the two modes.
- (g) No test outcomes in selection: weights/temperature fit on validate-2023
  only; regime policy reads availability, never test performance.

## 12. Reproducibility (run ids, artifacts, how to rerun)

- Runs: `phase5_baseline_crossleague_0b434d17`,
  `phase5_baseline_xg_estimated_0b434d17`, `phase5_sensitivity_sens_epl24_0b434d17`,
  `phase5_weights_weights_epl24_0b434d17`, `phase5_mc_mc_epl24_0b434d17`,
  `phase5_advanced_adv_epl_0b434d17`, `phase5_deepdive_v1_0b434d17`
  under `backend/data/phase5/<run_id>/{baseline,sensitivity,mc,weights,advanced,deepdive}_report.json`.
- Determinism: seeds fixed (7; bootstrap seeds 7/8); MC seeded; numpy present,
  scipy present, sklearn absent (unused — softmax is numpy).
- Rerun: `DATABASE_URL=sqlite:////tmp/p17.db python scripts/phase5_validate.py
  --analysis <kind> --scope "<LEAGUE:SEASON>,..." [--models ...] [--with-market]
  [--temporal-mode ...]`; `python scripts/phase5_deepdive.py --label <name>`.
- Read-only API: `/api/v1/validation/phase5/runs`, `/runs/{id}/{artifact}`,
  `/model-registry`, `/disclaimer`.

## 13. Limitations and follow-ups (no new claims)

- xG evidence is estimated-mode only (unknown timing); strict-mode xG skill is
  unmeasured by construction, not zero by proof.
- Extreme-probability calibration is unmeasurable here (N=15 above 0.75).
- Strong-favorite subgroup ungated (N=15).
- Advanced-xg lacks a 3-window walk-forward (single-season xG coverage).
- Bundesliga 2023 (N=261) is the smallest cross-league scope; Ligue_1/EPL
  2015/2022 not covered beyond what is reported.
- No defaults changed; temperature/learned-weights stay experimental.

## 14. Verdict

Phase 5 confirms the Phase 4 hierarchy on 6 league-seasons with paired
uncertainty: ensemble_v1 (equal) ≥ elo_v1 ≈ on Brier, > poisson_v1 everywhere,
and ≫ baseline. Complexity (learned weights, validation-fit temperature, ML
features) did not transfer out-of-sample on the measured populations. xG is a
real Poisson lift where its timing is anchored (estimated mode), and correctly
unavailable where it is not (strict mode). Probability quality is reported with
bounds, sparse bins, and disclosed tails — no certainty language, no betting
content, no test-set tuning.
