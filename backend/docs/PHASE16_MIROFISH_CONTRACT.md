# Phase 16 — MiroFish Contract (`mirofish_contract_v1`)

## Request schema

Top-level fields only (whitelist enforced; anything else dropped):

`contract_version`, `match_id`, `competition`, `kickoff`, `cutoff`,
`home_team`, `away_team`, `core_prediction` ({home, draw, away}),
`derived_probabilities` (double_chance/totals/btts subsets),
`expected_goals` ({home_lambda, away_lambda, total_lambda}),
`uncertainty`, `model_disagreement`, `data_completeness`,
`temporal_quality`, `scenario` ({scenario_id, parameters{kind, home_mult,
away_mult, description}, baseline_hash, scenario_hash}),
`provenance`, `baseline_hashes` ({baseline_prediction,
intelligence_snapshot}).

Forbidden substrings (`result`, `closing`, `final_score`, `actual_*`) are
scrubbed even if present upstream. Serialization is canonical JSON (sorted
keys) so identical inputs hash identically.

## Scenario IDs

Reused verbatim from the Phase 15 engine: `baseline`, `home_strength_up`,
`home_strength_down`, `away_strength_up`, `away_strength_down`,
`high_scoring`, `low_scoring`. No custom parameters cross into MiroFish.

## Response schema

Required: `contract_version`, `match_id`, `cutoff`, `scenario_id`,
`scenario_hash`, `baseline_prediction_hash`, `intelligence_snapshot_hash`,
`provider`. Optional: `structured_observations[]` ({kind, statement,
detail}), `narrative` (verbatim, safety-scanned), `warnings[]`,
`provenance`. Scenario probabilities, when present, must be finite,
in [0,1], and sum to ~1; score distributions must sum to ~1.

## Identity verification

Match, cutoff, scenario, both hashes and contract version must echo the
request exactly; any mismatch rejects the response. Size-capped at
`MIROFISH_RESPONSE_MAX_BYTES`.

## Failure states

`provider_not_configured`, `provider_disabled`, `provider_timeout`,
`provider_error`, `provider_rate_limited`, `invalid_response`,
`contract_mismatch`, `response_too_large`. Client/contract errors are
never retried; 429/5xx retry bounded with backoff.

## Semantics

Output is scenario analysis / simulated evidence — never ground truth,
calibration, or a recommendation. Narrative is labeled simulated output;
certainty phrases are flagged, never rewritten or trusted. There is no
validated methodology for converting narrative into probabilities, so
MiroFish never modifies 1X2 probabilities.
