# Phase 17 — API Schema (`match_intelligence_v1`)

Canonical endpoint: `GET /api/v1/matches/{match_id}/intelligence`
(lightweight: `/summary`; sections: `/markets`, `/uncertainty`,
`/scenarios`, `/analogues`, `/mirofish`). Query params: `mode`
(`strict_prematch` | `historical_estimated`), `cutoff` (ISO),
`model`, `seed`, `response_mode` (`standard` | `compact`),
`mirofish_scenario` (whitelisted ID).

## Top-level sections

`schema_version`, `match` (ids, canonical team names, competition code,
season, kickoff, status, source mappings; venue null unless stored),
`cutoff` (timestamp, policy text, prediction/market-as-of, temporal
quality, estimated/unknown flags), `core_prediction` (1X2, expected goals,
model version, mode, calibration state, dataset/feature versions,
prediction snapshot id+hash), `derived_markets` (1X2, double chance,
totals, BTTS, team totals), `expected_goals`, `correct_score`
(distribution, top-8, required-16 mass, tail mass, probability sum),
`uncertainty`, `model_disagreement`, `data_quality` (completeness,
coverage, source count, missing families, conflicts), `temporal_quality`
(strict/estimated/unknown family lists), `market` (markets, bookmaker
count, consensus, model probabilities, divergence, movement, timing,
closing_used=false), `analogues`, `scenarios`, `mirofish` (status,
provider, contract version, scenarios, provenance, reason),
`explanation`, `warnings[]` ({code, severity, message, evidence}),
`provenance` (all §17 fields).

## Modes

`standard`: full document. `compact`: strict presentation subset
(1X2/goals/totals-2.5/BTTS/top-3 scores/uncertainty/disagreement/quality/
temporal/consensus+divergence/analogue status/empty scenarios list/
mirofish status/headline/major warnings/provenance). Same underlying
values in both modes (tested).

## Errors (machine-readable `{code, message}`)

`match_not_found` (404), `intelligence_unavailable` (400/500),
`prediction_unavailable` (400), `invalid_snapshot` (400),
`temporal_data_unavailable` (400), `provider_unavailable` (MiroFish only,
200 payload — never a 500). No stack traces, no secrets.

## Semantic rules (encoded in tests)

Probabilities stay probabilities; disagreement/divergence stay
descriptive; MiroFish stays simulated scenario evidence; analogues stay
non-causal; completeness is not confidence; unknown timing is never
upgraded; closing stays benchmark-only; no betting/staking automation
exists anywhere in this surface.
