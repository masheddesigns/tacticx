# Phase 16 — Final Report: MiroFish Scenario Intelligence Integration

## Architecture

Cutoff-gated composer → whitelisted Phase 15 scenario → deterministic
contract request → provider interface → strict validation → identity
verification → append-only run → structured result. New
`app/services/mirofish/` (contracts, errors, config, scenario/request
builders, adapter, validation, response parser, provenance, service) +
`mirofish_scenario_runs` table. Phase 6 primitives reused, never duplicated.

## MiroFish contract

`mirofish_contract_v1`: whitelisted fields, canonical-JSON determinism,
forbidden-substring scrubbing, identity echo requirements. See
PHASE16_MIROFISH_CONTRACT.md.

## Scenario integration

Phase 15 scenario IDs reused verbatim (7 IDs); custom parameters never
cross into MiroFish; baseline + scenario hashes travel with every request.

## Request schema

§3 minimum payload + baseline_hashes; byte-identical for identical inputs
(tested), hash-sensitive to scenario changes (tested).

## Response schema

Identity envelope + structured observations + verbatim narrative +
warnings + provenance + hashes. Invalid probabilities (negative, >1-sum,
NaN, infinity, bad sums) rejected, never repaired.

## Provider implementation

`MiroFishProvider` ABC; `DisabledProvider` (honest unavailability);
`HttpProvider` (config-trusted endpoint, bounded timeout/retries, no retry
on 4xx, 429/5xx mapped). No live provider is bound in this repository.

## Unavailable-provider behavior

Machine-readable states (8 codes); core prediction latency unaffected
(0.5s worst case measured, prediction path never raises on provider
failure); deterministic Phase 15 scenarios remain available independently.

## Persistence

Append-only `mirofish_scenario_runs` (ids, hashes, provider, timings,
payload, error codes); history never overwritten; identical requests share
hashes but append rows.

## API

GET latest/specific scenario, POST run, POST batch (bounded, ordered,
partial success) under `/api/v1/intelligence/{match_id}/mirofish*`.
Provider failure → 200 unavailable payload, never 500; unknown scenario →
400; unknown match → 404.

## CLI

`tacticx intelligence <id> --mirofish [--scenario ID]` with config
diagnostics and clean status output; secrets never printed.

## Provenance

11 required fields enforced at assembly; missing provenance invalidates.

## Determinism

Request-hash equality/difference tested; artifact hashes stable.

## Leakage audit

See PHASE16_LEAKAGE_AUDIT.md — all adversarial tests pass (future data/
market/analogues, mutation, cross-match/scenario, invalid probabilities,
narrative certainty, provider failures).

## Production isolation

Prediction/feature/odds/history rows byte-identical before/after runs
(tested); model versions, snapshots, calibration, backtests untouched.

## Five-league validation

EPL/LA_LIGA/SERIE_A/BUNDESLIGA/LIGUE_1: unavailable mode clean +
mocked mode ok + predictions unchanged (12.1s total).

## Mock-provider validation

Deterministic fake: requests generated, hashes stable, results parsed,
provenance complete, scenarios isolated. Clearly labeled mock — no real
performance claimed.

## Real-provider validation

None configured (MIROFISH_ENABLED=false, no endpoint). Honestly reported
as unavailable; fresh clones run all normal functionality.

## Performance

Request construction 0.9ms; validation ~0ms; persistence single-insert;
provider timeout bounded by config; batch bounded. External latency
reported, never hidden.

## Security

Secrets wire-only, presence-only diagnostics; endpoint from trusted config
(SSRF-guarded); whitelisted scenarios; size caps both directions;
bounded retries/backoff; no secret leakage in logs/API/CLI/tables
(audited); ORM-only queries.

## Tests

Previous: 431. New: 17. Total: 448. Passed: 448. Failed: 0. Skipped: 0.
Existing tests untouched (no deletions/weakenings).

## Limitations

- No live provider bound; all ok-path evidence is mocked.
- Plausible-but-wrong observations undetectable by schema (labeled
  simulated evidence, never truth).
- Narrative safety is phrase-flagging, not semantic understanding.
- Analogue latency from Phase 15 dominates end-to-end timing.

## Commit

Phase 16 commit (see git log).

## Status: READY

MiroFish is an isolated, deterministic, cutoff-safe, provenance-complete
scenario layer; production prediction remains byte-identical. MiroFish is
NOT in the statistical ensemble; no weights tuned; no betting outputs.
