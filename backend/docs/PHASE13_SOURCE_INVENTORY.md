# Phase 13 — Source Inventory (measured 2026-09-18)

## Accepted

### football_data_co_uk — VALIDATED → ACTIVE for historical backfill
- 10 season files per league HEAD-verified (1516–2425).
- Imported 37 missing seasons: EPL 1617–2122 (6), LA_LIGA 1617–2223 (7),
  SERIE_A/BUNDESLIGA/LIGUE_1 1516–2223 (8 each).
- Families: fixtures, results, statistics, shots, closing odds. No
  xG/events/lineups expected or found.
- Temporal: event dates only (D-level, unknown timing preserved).
- License: free personal/non-commercial; raw CSVs in /tmp only, never
  committed. Polite fetcher (UA, ≥2s spacing, retries).

## Tested, deferred

### api_football history — TESTED
- 1-match probe: 32 statistic rows + 12 events (subst/card/goal) retrieved.
- Bulk backfill deferred: ~3 calls/match × 13k matches exceeds quota
  budget without dedicated allocation.

## Rejected

### statsbomb_open_data — REJECTED (no incremental value)
- No new free seasons for our five leagues beyond stored 794 matches.
### odds_api_history — REJECTED (no historical depth; upcoming-only)
### aggressive_scraping — REJECTED (robots/terms/licensing incompatible)
