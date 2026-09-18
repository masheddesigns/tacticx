# Phase 15 — Final Report: Prediction Intelligence & Decision-Support Layer

## Architecture

Read-only orchestration (`app/services/intelligence_v2/`) over the Phase 6
engine (composer/derived/analogues/scenarios/explanation reused, not
duplicated): production prediction → probabilities/goals/derived markets/
uncertainty/disagreement/quality/context/comparison/scenarios/explanation.
Nothing mutates predictions, models, snapshots, odds or history (snapshot
rows only).

## Intelligence snapshot

`intelligence_snapshots` rows (snapshot/match/prediction/versions/cutoff/
payload/hash); content-addressed reads; repeat builds dedupe by hash.

## Core prediction

Exposed unchanged as `core_prediction`; derived layers read it, never
recalculate it (except mathematically required grid derivations).

## Derived probabilities

1X2, double chance (identities checked), totals O/U 0.5–3.5 (sums to 1),
BTTS (joint + closed-form cross-check), team totals from marginals.

## Correct-score distribution

Full grid + configurable top_n + required-16 mass + tail mass; mode never
described as likely in absolute terms.

## Uncertainty

Entropy/margin/disagreement/completeness/availability/temporal, documented
and descriptive. Example (match 381): entropy 1.004, margin 0.285.

## Model disagreement

Elo/Poisson/Advanced/Ensemble per-outcome mean/std/min/max/range with
missing members reported, e.g. home mean 0.60 ± 0.03.

## Data completeness

Per-family measured fractions, separate from confidence.

## Temporal quality

Per-family strict/estimated/unknown; estimated never visually equal.

## Historical analogues

Cutoff-safe standardized-distance engine; target/future excluded (tested);
min-population gating; descriptive frequencies with "historical patterns,
not predictions" wording.

## Scenario engine

Whitelisted ±10% λ scenarios, baseline-first, baseline+delta output,
parameter validation, no mutation. Baseline reproduces grid distribution
deterministically.

## Market comparison

Pre-cutoff consensus only (closing excluded, partial books excluded);
bookmaker count/completeness/overround/timestamp exposed; small/moderate/
large labels from config thresholds, descriptive only.

## Explanation

Headlines state probabilities with uncertainty; factors cite actual inputs
(Elo/λ/xG status/features); contributions labeled model contribution;
no causal claims.

## Warnings

8 evidence-based codes firing only on measured conditions (verified live:
XG_UNAVAILABLE, CLOSING_ONLY, MARKET_THIN where applicable).

## API

7 GET (`/intelligence/{id}`, `/summary`, `/markets`, `/uncertainty`,
`/analogues`, `/scenarios`, `/explanation`) + snapshot read + whitelisted
scenario POST. All tested live.

## CLI

`tacticx intelligence <id> [--analogues --scenarios --json]` with concise
human output and complete-provenance JSON.

## Provenance

Every response carries match/cutoff/model/mode/versions/hash/snapshot_id.

## Leakage audit

See PHASE15_LEAKAGE_AUDIT.md — all adversarial tests pass.

## Real-data validation

15/15 matches × 5 leagues: predictions, markets, uncertainty, disagreement,
warnings, analogues, scenarios, explanations, provenance all green.
Timings: 1.2–14s (analogues dominate on big leagues; bounded).

## Production regression

5/5 stored predictions recompute identically; file-gate test; no writes
outside snapshot rows. changed = 0.

## Tests

Previous: 415. New: 16. Total: 431. Passed: 431. Failed: 0. Skipped: 0.

## Performance

Summary ~1.2s uncached (target <2s ✓); content-addressed cached reads
instant (memoized recompute not used — market data can append); analogues
1–14s (target partially missed on EPL, documented); scenarios ~10ms;
derived markets ~ms.

## Security

Validated match/mode/cutoff/model params; whitelisted scenario params
(ranges enforced, no code execution); ORM-only queries; no secrets in any
layer (audited).

## Limitations

- Analogue latency on large leagues; no memoization by design.
- Market coverage thin on older matches (unavailable honestly reported).
- xG/player families estimated-or-missing (warnings, not fills).
- MiroFish untouched (Phase 6 adapter persists separately).

## Commit

Phase 15 commit (see git log).

## Status: READY

The existing prediction is now transparent, traceable, consistent,
uncertainty-aware, cutoff-safe and reproducible — and still exactly a
probability estimate.
