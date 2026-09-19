# Phase 17 — Provenance

Every canonical response carries, under `provenance`:

- `match_id`, `cutoff`
- `prediction_snapshot`: `{prediction_id, hash}` (Phase 15 intelligence hash)
- `model_version`, `feature_version`, `dataset_version`
- `intelligence_snapshot`: `{snapshot_id, hash}`
- `scenario_version` (`phase15_scenarios_v1`)
- `mirofish_contract_version`, `mirofish_provider`
- `request_hash`: reserved for MiroFish-bound requests (`""` when the
  canonical build does not call a provider; the MiroFish run rows carry
  their own request hashes)
- `response_hash`: deterministic content hash (see below)
- `generated_at`: wall-clock build time, excluded from hashing

## Content hash contract

`content_hash` covers exactly: schema_version, match, cutoff,
core_prediction, derived_markets, expected_goals, correct_score,
uncertainty, model_disagreement, data_quality, temporal_quality, market,
analogues, scenarios, mirofish, explanation, warnings, and provenance
**minus** `response_hash` and `generated_at` (both set after hashing).
MiroFish narrative IS hashed: distinct provider runs hash distinctly.
Snapshot IDs derive from hashes (`intel_<16 hex>`), so identical builds
deduplicate to the same row.

Verification procedure (used by tests and the committed fixture): drop
`provenance.response_hash` and `provenance.generated_at`, recompute —
must equal the stored hash.
