# Phase 19 — Acquisition Strategy

## Source selection

1. Qualify each candidate (bounded requests, recorded evidence).
2. Map qualification status → level (A/B/C/D).
3. Build the deterministic plan: lowest-priority Level-A source supporting
   the competition becomes canonical; the rest are ordered fallbacks.
4. Execute with per-league isolation and partial-success semantics.
5. Reconcile multi-source observations; persist conflicts; gate eligibility.

## Current posture (2026/27)

No Level-A source is qualified (api-football 403, odds unattributable,
fdcuk historical-only). Canonical 2026/27 fixtures: honestly zero.
The pipeline is validated and waiting — acquisition runs record empty
with evidence rather than fabricating coverage.

## When a source qualifies

Flip its registry entry, re-run qualification, and acquire. No code
changes are needed: the plan builder picks it up deterministically.
Supplementary sources attach without ever becoming fixture authority.
