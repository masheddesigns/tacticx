# Phase 6 — Final Report: prediction intelligence + scenarios + MiroFish

## Prediction architecture

```
features (pre-cutoff snapshot, features_v1)
  → models (ensemble_v1 default; elo/poisson/advanced via registry)
  → composer (PredictionComposer: no training, no mutation)
  → distributions (goal marginals + joint grid, tail exposed)
  → derived markets (totals/BTTS/double-chance/team-totals/scores)
  → explanation (factual inputs only)
  → market (observed pre-cutoff context, never an input)
  → scenarios (deterministic sensitivity) + analogues (descriptive)
  → MiroFish (optional, separately labeled, failure-safe)
```

Statistical prediction ≠ market probability ≠ MiroFish scenario. No layer
overwrites another; every number traces to source + model version + cutoff +
calculation version.

## Unified prediction schema

`ComposedPrediction` (`app/services/intelligence/schemas.py`): match, cutoff,
model{version, selection}, status, probabilities{1X2 + validation}, goals,
markets{totals, btts, double_chance, team_totals, correct_scores,
goal_distributions, validation}, score_distribution, uncertainty, disagreement,
market, explanation, scenarios[], analogues, mirofish, data_quality,
core_prediction (untouched FullPrediction), provenance.

Real response (match 381, Bundesliga 2024-04-06): status=complete,
model=ensemble_v1-elo+poisson, 1X2 H=0.202 D=0.256 A=0.541 (sums to 1.0),
home_λ=0.779 away_λ=1.661, market=ok (4-book median consensus, closing excluded).

## Derived markets (all from the model's own distribution; nothing trained)

- O/U 0.5/1.5/2.5/3.5 from the joint grid; Over+Under=1 by construction
  (checked, `consistent: true`).
- BTTS from joint grid, cross-checked against closed form
  1−P(H=0)−P(A=0)+P(H=0,A=0) (test asserts agreement < 1e-6); plus
  `mc_crosscheck` helper for analytic-vs-Monte-Carlo comparison.
- Double chance: 1X=P(H)+P(D), X2=P(D)+P(A), 12=P(H)+P(A), identity-checked.
- Team totals (H/A over 0.5/1.5/2.5) from Poisson marginals.
- Correct scores: full grid + configurable top_n + required-16 coverage
  (match 381 tail mass disclosed).
- Invalid 1X2 vectors are rejected with reasons, never silently normalized.

## Model disagreement (actual example, match 1925)

home: elo/poisson/ensemble → mean 0.6035, std 0.0310, min 0.5655, max 0.6414,
range 0.0759, n=3 (advanced unfitted → reported missing, not zero-filled).
Labeled "model disagreement (descriptive, not a correctness signal)".

## Uncertainty (match 1925)

entropy 0.9377 nats, top 0.6035, margin 0.3638, data completeness
(home/away history + xg histories + xg_available=false). Probability,
uncertainty and data quality kept as distinct concepts.

## Explanation (actual)

"The ensemble_v1-elo+poisson model assigns AFC Bournemouth the highest
probability (60.3%; …). These are statistical estimates with uncertainty,
not certainties." Factors from real inputs: Elo ratings + history size,
Poisson λ vs league averages, xG unavailable (histories 0/0, never zero),
feature-row sufficiency. Advanced contributions available via
coef×standardized-feature when fitted (labeled "model contribution").

## Historical analogues

Methodology: standardized Euclidean distance (pool-standardized, common space)
over pre-match features (elo_diff, form_ppm_diff, goal_diff_diff, rest_diff,
total_goals_avg); candidates = finished league matches before target cutoff
evaluated at their own kickoff; target structurally excluded; min 20 or
`insufficient_sample`. Outcomes descriptive only. Example (match 381):
5 analogues, pool outcome distribution H 0.425/D 0.276/A 0.299 (n=221).
Coverage: works where league history ≥ ~20 eligible candidates; small leagues
report insufficient_sample honestly.

## Scenario engine

Scenarios: baseline (always first), home/away_strength_up/down (±10% λ),
high/low_scoring (±10% both). Parameters whitelisted to [0.50, 2.00];
configuration is data, never code. Output per scenario: 1X2, goals, O1.5/
O2.5/O3.5, BTTS, top scores + difference_from_baseline vs caller baseline.
Example (match 381): high_scoring moves O2.5 0.441→0.502, BTTS 0.438→0.483.
Baseline row exposes the ensemble-blend vs pure-grid recomputation gap
(H −0.029) explicitly — auditable, not hidden.

## MiroFish

Integration status: **adapter complete, no external service bound**.
Adapter: explicit context (observed/derived/estimated/scenario labels),
cutoff-after-kickoff refusal, configurable timeout (default 30s), output
validation (0≤p≤1, 1X2≈1), any failure → `status=unavailable` with core
untouched (tested: success/timeout/invalid/disabled/core-untouched).
No successful MiroFish run is claimed — none occurred; the CLI/API return
honest `unavailable` ("MiroFish not configured"). Nothing fabricated.

## APIs

GET /api/v1/predictions/{id}/full[?include=scenarios,analogues],
explanation, distribution[?top_n], scenarios[?names], analogues[?top_k],
models; POST .../scenarios (records ScenarioRun, core untouched);
POST .../mirofish (records MiroFishRun, failure-safe; timeout ∈ [1,300]).

## CLI

`python scripts/tacticx.py predict|explain|scenarios|analogues|mirofish
<match_id>` (+ --model/--temporal-mode/--cutoff/--seed/--json). All backed by
real data; verified on matches 381/1925/2314.

## Tests

Previous: 258. New: 30 (composer, validation, distributions, BTTS,
double-chance, disagreement, explanation, analogues, scenarios, MiroFish,
temporal safety, API). Total: 288. Passed: 288. Failed: 0. Skipped: 0.

## Temporal audit

Checks: target exclusion (analogues), future-result exclusion (all repo reads
kickoff<cutoff), future-xG exclusion (strict mode, Phase 5), future-event/
standings exclusion (inherited snapshot design), future-market exclusion
(post-cutoff snapshots ignored; closing excluded even when pre-cutoff —
tested with mixed snapshot fixtures). Issues found & fixed: partial-book
prices entering consensus (now complete-books only); per-pair analogue
standardization (now pool-standardized); cutoff==kickoff MiroFish refusal
(now only cutoff>kickoff refused). Remaining risk: market coverage is thin
(34 matches with pre-kickoff snapshots) → context often honestly unavailable.

## Probability audit

Checks: 1X2 sums (rejection on violation), grid sums (≈1, tail exposed),
BTTS joint vs closed-form agreement, totals Over+Under=1, double-chance
identities. Issues found & fixed: double-chance tolerance vs 9-decimal
rounding (1e-12 → 1e-9 on two checks). No remaining failures.

## Performance

compose 0.4–1.2s, analogues 0.8–11.7s (pool-size dependent; Elo cache +
2000-candidate bound), scenarios ~0.01s, MiroFish adapter ~0.00s overhead
(no service bound). No repeated historical scans beyond existing repository
memoization; analogue search is the only heavy path and is bounded.

## Limitations

- xG coverage: strict mode excludes xG (effective_at=NULL); explanations
  report unavailable, never zero.
- Events/lineups collected but not consumed by v1 math (reported in data quality).
- Market coverage thin → context often unavailable; closing never used as context.
- Analogues need ≥20 eligible candidates; large-league searches take seconds.
- Scenarios are ±10% λ sensitivity analyses with labeled assumptions.
- MiroFish: adapter only; nondeterministic outputs would store seed/version/
  input snapshot when a service is bound.
- Advanced member missing from disagreement unless fitted (no silent fallback).

## PHASE 7 READINESS

READY FOR PHASE 7. The intelligence layer is complete, tested (288 green),
audited, and documented with the validated statistical core untouched and
ensemble_v1 still the default.
