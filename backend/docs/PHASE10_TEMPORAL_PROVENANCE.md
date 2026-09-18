# Phase 10 — Temporal Provenance Semantics

## The four timestamps

| Field | Meaning | Source |
|---|---|---|
| event_time | when the football event occurred (kickoff, match minute) | fixture/event record |
| effective_at | when the information became knowable/valid for prediction | source contract or NULL |
| retrieved_at | when TacticX acquired the record | acquisition path (≈ recorded_at) |
| created_at | when TacticX persisted the record | server default |

These are never interchangeable. In particular, effective_at is NEVER
inferred from event_time: a match played Saturday does not imply its
lineup was knowable beforehand unless the source contract says so. All
lineup/event/xG rows in this dataset carry effective_at NULL and are
therefore temporally unknown — strict-excluded, estimated only when
parent-anchored.

## Temporal status

Derived deterministically (`freshness/provenance.classify`):

- effective_at <= cutoff → known_pre_cutoff
- effective_at > cutoff → known_post_cutoff
- effective_at NULL → unknown, unless the caller explicitly allows
  estimation AND the parent anchor predates cutoff → estimated_pre_cutoff
  (or estimated_post_cutoff when it does not)

Estimated timing is never presented as known timing: labels, API fields
and reports carry the estimated flag end to end.

## Freshness policies

Per-family (fresh/stale/expired day bounds + rationale) in
`freshness/policies.FRESHNESS_POLICIES`: standings 7/30, team_form 14/90,
player_form 30/365, squad_membership 90/365, lineup 30/365, odds 1/7,
xg 30/365. Unknown effective_at is always state unknown, never fresh.

## Modes

- production_strict: strict data access + no unknown timing, no estimation,
  no unresolved identity, no critical conflicts, freshness reported.
  Suitable for eventual live predictions; never weakened for coverage.
- estimated: historical research with visible estimated labels; never
  consumed by production.
