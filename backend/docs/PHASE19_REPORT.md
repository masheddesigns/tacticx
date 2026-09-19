# Phase 19 — Final Report: Provider Qualification & Acquisition Reliability

## Architecture

`app/services/provider_qualification/` (capabilities, qualification,
registry, authority, fallback, plans, health_ext, freshness, snapshots)
extends — never duplicates — the Phase 1.6 registry, Phase 7 health/
retries, Phase 8 reconciliation, Phase 10 freshness/eligibility and
Phase 11/18 acquisition. Prediction/intelligence code paths untouched.

## Provider registry

Declarative entries (adapter, capabilities, competitions/seasons, field
authority, rate limit, priority, enabled, qualification status) with
deterministic priority ordering. Core depends on the abstract contract.

## Provider capability model

Tri-state evidence markers (measured/documented/unknown/unavailable)
across 20 dimensions; declared adapter support seeds DOCUMENTED, only
observed responses earn MEASURED.

## Qualification framework

Bounded probing (≤5 requests), structured verdicts, repeatability
refetch, levels A–D, append-only evidence. Empty ≠ proof-of-absence;
auth failures fail fast without retry storms.

## Sources evaluated

api-football, odds_api, football_data_co_uk (+ theoretical adapters
explicitly not built).

## Source qualification results

- api-football/EPL/2026: **rejected** (authentication_failure, HTTP 403;
  0 rows; repeatability n/a).
- odds_api/EPL/2026: **rejected** for fixtures (authentication_failure,
  HTTP 401); Level C market role retained in principle.
- football_data_co_uk: Level A standing (Phase 13 bulk evidence).

## EPL / La Liga / Serie A / Bundesliga / Ligue 1

Five-league orchestration verified by mock matrix; real run reports
2026/27 unavailable everywhere with evidence. No league fabricated.

## Current-season coverage

0 canonical 2026/27 fixtures from any source (measured, not fatal).

## Field authority

Per-field table persisted per plan; no global ranking; documented.

## Fallback strategy

Classified outcomes; eligible fallbacks only; empty gated by policy;
auth/unsupported halt the chain; previous observations immutable.

## Acquisition plans

Deterministic, hashed; supplementary never promotes; verified identical
across reruns.

## Source health

Extended telemetry; new states; backoff without auto-disable.

## Freshness

Configured intervals or honest unknown; per source/competition.

## Rate limiting

Provider-specific limits (unknown → conservative defaults); bounded
retries with backoff; 429 honored; quota never deliberately exhausted
(6+1 live requests total this phase).

## Pagination

Bounded collector tested (repeat/empty/malformed termination, page cap).

## Identity resolution

Existing resolvers; ambiguity quarantines (tested); no fuzzy matcher.

## Reconciliation

Existing Phase 8 paths; reruns create no duplicate conflicts (tested).

## Temporal audit

Unknown stays unknown; post-cutoff excluded; closing benchmark-only.

## CLI

`sources list/qualify/status/coverage/freshness/validate`,
`acquire --explain` (plan, reasons, coverage, identity). No secrets shown.

## API

`GET /api/v1/sources`, `/status`, `/qualification`, `POST qualify`
(bounded, registry-resolved adapters only); extended acquisition status
(qualification/freshness/coverage). OpenAPI validated (85 paths).

## Security

Fixed a real secret leak: httpx URL-object log args bypassed redaction —
now covered, verified 0 occurrences + 0 unredacted DB rows. Trusted
endpoints only; allowlisted CLI sources; bounded pagination/retries;
ORM-only; no raw payload storage.

## Performance

Status <500ms cached; qualification 2s cached; 1k-record normalization
and identity well under 1s; idempotent reruns faster; no extra source
calls.

## Tests

Previous: 482. New: 33. Total: 515. Passed: 515. Failed: 0. Skipped: 0.

## Production regression

Prediction/model/feature/odds/history byte-identical (the one
`lifecycle/sync.py` status-map addition is acquisition-layer only and
covered). No model code modified, nothing retrained, no promotions.

## Documentation

PHASE19_REPORT.md, PHASE19_PROVIDER_QUALIFICATION.md,
PHASE19_SOURCE_MATRIX.md, PHASE19_ACQUISITION_STRATEGY.md + README.

## Limitations

- No live Level-A source (both API keys restricted/expired).
- fdcuk has no current-season file yet.
- Odds unattributable without league context (by design).
- Qualification DB is append-only (growth is inherent to evidence).

## Commit

(Reported after push.)

## Status: READY
