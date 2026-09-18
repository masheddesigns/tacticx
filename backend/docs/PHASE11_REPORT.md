# Phase 11 — Final Report: Production Match Universe & Acquisition Pipeline

## Architecture

Registry → discovery → raw observation → normalization → identity →
canonical resolution → validation → append-only observation → universe →
eligibility → prediction. New `app/services/acquisition/` (universe,
workflow, activation, snapshot) + tables (acquisition_runs,
source_activations, acquisition_jobs; match_observations from Phase 10).

## Match Universe

Explicit read view (no table dup): EPL 1520, LA_LIGA 760, SERIE_A 380,
BUNDESLIGA 306, LIGUE_1 306 entries with lifecycle/confidence/quality.
Lifecycle derived (rescheduled/live/finished/…); confidence evidence-based.

## Source matrix

Unchanged from Phase 10 (measured): fdcuk fixtures/results/stats/odds;
statsbomb fixtures/results/stats/events/lineups/xG; declared-only adapters
show MEASURED: none in-store.

## Current-season coverage

2026/27 UNAVAILABLE all leagues (provider_plan_or_source_limit). Live
acquisition attempt logged as `empty`/`provider_empty` (run recorded, not
proof of no fixtures). No new adapter: no environment source qualifies
(documented decision, not a workaround).

## Historical coverage

Per-season slots: EPL 2015 (full incl. events/lineups/xG) + 2022–24
(stats/odds); LA_LIGA 2015 full + 2023 partial; SERIE_A/LIGUE_1/BUNDESLIGA
2023 stats/odds (+34 Bundesliga event/lineup/xG rows).

## Acquisition runs

Append-only log (run/source/job/times/status/scope/counts/errors, no
payloads/credentials). Partial success persists; retries idempotent
(content-hash + sync dedup verified: 0 new on re-run).

## Fixture observations

Kickoff/status/venue changes append immutable rows (3-observation chain
tested); canonical row advances only via validated sync; rescheduled
lifecycle derived from observation count.

## Source health

Phase 7 extended: healthy/degraded/rate_limited/authentication_failed/
unavailable/schema_error + consecutive failures + per-run records/latency.
Single failures never auto-disable.

## Reconciliation

Cross-source agreement measured over open match conflicts (0 true on real
data); formatting/timezone/expected-difference classes separated;
ambiguous candidates quarantine via existing resolvers.

## Production snapshot

`universe_<hash>` descriptor (matches/sources/observations/versions);
deterministic under ordering; answers "which exact universe was used".

## Prediction readiness

`tacticx readiness` per match: fixture/identity/historical/player/xG/
market/eligibility/mode + warnings. Data only, never a recommendation.
Cutoff integration reuses Phase 10 gates with explicit refusal reasons.

## Historical integrity

4388 predictions untouched by construction (tested); boundaries enforced
and adversarially tested (future/event/source-removal/kickoff cases).

## Leakage audit

No acquisition path reaches prediction storage; observations are
pre/post-neutral records, eligibility is cutoff-gated; market age filters
snapshots ≤ cutoff (Phase 10 fix preserved).

## Tests

Previous: 350. New: 16. Total: 366. Passed: 366. Failed: 0. Skipped: 0.

## Performance

Universe 5 leagues 5.7s; readiness per match ~ms–s; discovery <2s cached;
indexed queries, bounded limits. Targets met.

## Security

Secret scans in validation gate + stored-payload scan (6/6 PASS);
acquisition runs exclude payloads/credentials; raw strings never executed.

## Limitations

- Current season unavailable; date filter dead on key; no qualifying new
  source in environment.
- 45k+ rows lack effective_at (strict player/xG unavailable).
- Market overlap sparse; 2 leagues lack player data.
- Scheduler is a registry (external scheduler out of scope).

## Commit

Phase 11 commit (see git log).

## Status: READY

Can TacticX reliably discover and maintain its match set? Yes — with
measured coverage, idempotent runs, and honest unavailable states. Can a
prediction be traced to its exact universe and cutoff-safe snapshot? Yes —
snapshot descriptors + immutable versions + boundary tests prove it.
