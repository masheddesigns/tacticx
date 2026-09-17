# Phase 8 — Final Report: multi-source reconciliation + data quality

## Reconciliation architecture

sources → normalization (existing normalized.py types, provenance preserved)
→ identity (Phase 1.6 resolvers + mapping records) → reconciliation
(per-field typed comparison) → conflict (severity + classification +
resolution status, persisted, never deleted) → quality (documented
dimensions/weights/thresholds) → canonical (versioned field resolvers) →
features/prediction (snapshots isolated; reconciliation has no import path
to prediction storage).

## Source matrix (measured from stored data)

| Source | Fixtures | Stats | Events | Lineups | xG | Odds | Upcoming |
|---|---|---|---|---|---|---|---|
| football_data_co_uk | ✓ | ✓ | – | – | – | ✓ | – |
| statsbomb | ✓ | ✓ | ✓ | ✓ | ✓ | – | – |

Temporal quality: fixtures/results verified (kickoff-gated); xG rows
effective_at NULL → unknown (strict-excluded, rule preserved); bulk odds
imports carry batch timestamps (pre-cutoff usable, closing labeled).
Registry capabilities + Phase 7 health joined in
`source_registry_view`; no theoretical capabilities claimed.

## Coverage

Canonical matches 3272; multi-source 414 (LA_LIGA 380, BUNDESLIGA 34);
single-source 2858; unresolved 0. Teams: 112 canonical + mappings;
players: resolved via ID/name+team evidence; matches: 6 api_football
mappings added during Phase 7 validation, 0 duplicates created.

## Identity

Team methods (mapping/legacy/normalized_name/alias/manual) with confidence;
ambiguous names queue as open (proven in tests). Player cross-team
name-only merges refused at the Phase 8 wrapper (transfers stay distinct).
Manual mappings versioned + mirrored into native tables; queue flips to
resolved.

## Conflicts (real data)

Total persisted on real data: 0 true cross-source field conflicts —
same-stat overlap between sources is 0 (disjoint coverage: fdcuk 2478
matches vs statsbomb 794, no shared (team, stat, period)). No duplicate
canonical rows (season-bucketed grouping; an unbucketed first pass produced
3562 cross-season false positives — caught and fixed, documented here).
Synthetic overlap validation: measurement/definition/unknown classified
correctly; same-source material gap persisted as true_conflict;
idempotent re-runs create nothing new. Severity policy: score critical,
kickoff high, definitions medium, formatting low (auto-merge only).

Breakdown by type on real data: score 0, kickoff 0, team 0, league 0,
statistics 0 true (all definition/measurement/unknown), events matched
where duplicated (8s-apart Bale goal matched; 6–8min-apart goals correctly
distinct), players 0, odds 0 (bookmakers already canonical, 7 rows, no
A/a-duplicates).

## Resolution

Automatically resolved: timezone renderings + name formatting (low-risk
only). Manually mapped: via CLI/API (versioned). Definition differences:
recorded as classification, values kept source-side. Not comparable:
undefined semantics. Unresolved: persistent queue (currently 0 open on
real data).

## Data quality

Dimensions/weights: identity .25, temporal .20, completeness .25,
agreement .15, provenance .15; high ≥ .75, medium ≥ .45. Real sample
(n=30): 30 high. Completeness by league measured; agreement penalizes only
unresolved high/critical; temporal stays separate from completeness.
Quality never converted to probability.

## Prediction impact

Proven: full EPL reconcile over 4388 stored predictions left every row
byte-identical (count + sampled payloads). Prediction snapshots ≠ canonical
records by construction. Gating integrated into readiness: critical
conflicts block, missing events/lineups/xG do not, unknown-timing
strict-exclusion preserved.

## Real-data validation

Scratch-copy runs: 5-league dry-run + write pass, stat/event/xG/odds
validation, CLI + API paths, idempotency (second runs: 0 new rows).
Synthetic second-source overlap (labeled) exercised classification,
matching, persistence. No production data altered (scratch only; dry-run
available: `--dry-run` detects/classifies/reports without writes).

## Dry run

`reconcile --dry-run`: 1520 EPL matches in 0.03s, 0 changes proposed,
0 applied. Write pass: same result, 0 applied (nothing to merge).

## Tests

Previous: 310. New: 22. Total: 332. Passed: 332. Failed: 0. Skipped: 0.

## Performance

League reconcile 0.1–0.6s (indexed groups, no O(n²)); stat pass over 414
matches 0.1s; memory bounded by batch limits.

## Security

Raw source strings returned as stored (no shell use, no secret fields);
no keys/tokens/headers in logs, API, tables, or CLI output (grep-audited);
manual mapping validates entity types and positive IDs.

## Limitations

- Same-stat cross-source overlap is 0 in this dataset (disjoint coverage).
- match_statistics uniqueness blocks co-storage (ingest-time reconciliation
  instead; no migration imposed).
- Current-season fixtures unavailable on tested plan; market overlap sparse.
- xG effective_at unknown (strict-excluded); events/lineups statsbomb-only.
- Player coverage thin outside event data.

## READY FOR PHASE 9

READY FOR PHASE 9. The canonical dataset represents the best-supported
interpretation of the evidence with every disagreement reconstructible —
and the validated core never touched.
