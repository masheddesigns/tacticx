# Phase 17 — Final Report: Intelligence Product Surface & Canonical API

## Architecture

`app/services/match_intelligence/` (schemas + orchestrator) projects
Phase 15 intelligence and Phase 16 MiroFish runs into the versioned
`match_intelligence_v1` document. Read-only; the only writes are the
pre-existing intelligence-snapshot and MiroFish-run rows.

## Canonical schema

18 top-level sections per §2 (see PHASE17_API_SCHEMA.md). Pydantic
`MatchIntelligence` validates every canonical response (OpenAPI derives
from it; 83 paths served).

## Core prediction preservation

Byte-compared against composer output in tests; model version
`ensemble_v1-elo+poisson` surfaces unchanged with snapshot id+hash.

## Derived markets

Reused engine; 1X2/DC/BTTS/totals identities asserted per response.

## Correct-score distribution

Full grid + top-8 + required-16/tail masses + probability sum; top
scoreline labeled highest-probability, never "predicted score".

## Uncertainty

Entropy/margin/disagreement/completeness/temporal, descriptive only —
no safe/risky/lock language exists anywhere in the surface.

## Model disagreement

Mean/std/min/max/range per outcome + missing-model reporting; no winner
chosen.

## Data quality

Completeness/coverage/source-count/missing-families/conflicts kept
separate; missing/unavailable/estimated/known/conflicting preserved.

## Temporal quality

Per-family strict/estimated/unknown lists from measured flags; cutoff
section exposes policy, as-of timestamps, and estimated/unknown booleans.

## Market intelligence

Consensus/model/divergence/movement/timing/overround; closing_used=false
always; no bet/stake/return language.

## Historical analogues

Cutoff-safe engine output with methodology; descriptive wording preserved.

## Scenarios

Whitelisted deterministic set with baseline hash + per-scenario hashes;
baseline always exposed separately; execution cannot mutate it.

## MiroFish

Status/provider/contract/scenarios/provenance/reason; unavailable (with
`provider_not_configured`) when unconfigured; mocked ok-path verified;
output labeled simulated scenario evidence, never probability.

## Explanation

Headline + input-cited factors + limitations; no causal claims (tested:
no definitely/certainly/guaranteed/will-happen language).

## Warnings

8 evidence-bearing codes (XG_UNAVAILABLE … MODEL_DISAGREEMENT_HIGH),
machine-readable {code, severity, message, evidence}.

## Provenance

§17 field set + deterministic hash contract (see PHASE17_PROVENANCE.md).

## Caching

Finished matches: snapshot payload reused indefinitely (immutable).
Scheduled/live: 60s memo keyed by full request identity. Memo hits are
hash-identical (tested). No stale data can masquerade as current:
cutoff/mode/model/seed/mode-flags all participate in the key.

## API

Canonical + summary + 5 section endpoints, response_mode standard/compact,
machine-readable errors, OpenAPI-validated (83 paths).

## OpenAPI

Derives from `MatchIntelligence` response_model; prediction vs
simulation vs market description kept distinct in summaries.

## Compact mode

Strict subset transformation; values identical to standard (tested
field-by-field); scenarios list emptied, analogues reduced to status,
explanation reduced to headline, warnings reduced to major.

## Error handling

Stable codes, no stack traces, no secrets, MiroFish failure contained.

## Security

Typed match IDs, validated mode/cutoff/model params, whitelisted
scenarios, ORM-only access, no raw rows (MatchOut-style projections),
no credentials/provider internals, in-process cache keyed by identity
(no poisoning vector beyond the process).

## Performance

Measured on scratch DB, match 381: uncached build 1.69s (<2s ✓),
memo hit ~0ms (<300ms ✓); analogues dominate fresh builds. External
MiroFish latency reported separately, never blocks prediction endpoints.

## Tests

Previous: 448. New: 14 (`test_phase17b_match_intelligence.py`;
`test_phase17.py` Phase-1.7 suite untouched). Total: 462. All green
(verified below before commit).

## Production regression

Prediction/model/feature/odds/history rows byte-identical around
canonical builds (tested); MiroFish runs append their own rows only.

## Documentation

PHASE17_REPORT.md (this file), PHASE17_API_SCHEMA.md,
PHASE17_PROVENANCE.md, plus deterministic example fixture
`tests/fixtures/match_intelligence_example.json` (schema-validated,
hash-verified).

## Limitations

- Analogue latency on large leagues (bounded, unmemoized by design).
- Market coverage thin on older matches (reported unavailable).
- xG/player families estimated-or-missing (warnings, not fills).
- Fresh-clone MiroFish unavailable by default (honest, documented).

## Commit

(Reported after push.)

## Status: READY
