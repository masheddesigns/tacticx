# Phase 11 — Acquisition Architecture

## Pipeline

source registry → fixture discovery → raw observation → normalization →
identity resolution (Phase 1.6/8 resolvers only) → canonical match
resolution → validation → append-only observation → match universe →
feature eligibility → prediction.

Prediction never triggers acquisition. The engine consumes validated
canonical snapshots; acquisition only maintains the universe.

## Match universe

Read view (no duplicate table): match_id, competition, season, teams,
scheduled kickoff, status, derived lifecycle, source count, first/last
seen (observations), temporal + data quality, evidence-based confidence
(high/medium/low/unresolved — never a probability of occurrence).

Lifecycle derivation: rescheduled (>1 distinct observed kickoff),
otherwise direct status map; abandoned is a CANCELLED-family detail from
observations; unknown when status/kickoff missing. Never inferred from
scores alone.

## Source boundary (§6 decision)

Environment check 2026-09-18: api-football returns no 2026/27 fixtures on
this key (season pull works for 2024 and earlier); odds-api returns events
without league attribution (uncanonicalizable — guessing leagues is
forbidden). No source in the environment can provide current-season
fixtures with competition identity, so NO new adapter was built. Adding
one would be code without data; the architecture accepts any
FootballDataSource implementation when such a source validates.

## Activation gate

candidate → validated → active (all 10 checks: identity, fixture,
timestamp, duplicate, season, status, idempotency, secret scan, rate
limit, failure path); degraded/disabled states; decision rows persisted.

## Failure handling

401/403/429/5xx/timeout/invalid/schema/empty/partial classify explicitly;
partial success persists (18-of-19 keeps the 18); empty responses are
recorded as provider_empty, never as proof of no fixtures; one failure
never auto-disables a source.

## Observations vs canonical rows

Observations record source truth immutably; the canonical Match row
advances only through the validated sync path (Phase 7). Reconciliation
conflicts from disagreement go through the Phase 8 conflict table, never
UPDATE-old-value.

## Dataset boundaries

historical (<2024) / validation (2024) / test (2025–now) / production
(future), labeled per kickoff with explicit cutoffs. Backtests use
historical scopes; upcoming data belongs to readiness reports.
