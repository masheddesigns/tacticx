# Phase 10 — Source Matrix (measured 2026-09-18, /tmp/p17.db)

Capabilities use measured | documented | unknown | unavailable.
No theoretical claims are presented as coverage.

| Source | Fixtures | Results | Stats | Events | Lineups | xG | Odds | Upcoming | Current season | Historical |
|---|---|---|---|---|---|---|---|---|---|---|
| football_data_co_uk | measured (2478) | measured | measured (38832) | unavailable | unavailable | unavailable | measured (36870) | unavailable | unavailable | measured |
| statsbomb | measured (794) | measured | measured (6352) | measured (10411) | measured (28706) | measured (1588) | unavailable | unavailable | unavailable | measured |

Notes:
- Declared-only adapters (api_football, csv, odds_api) show MEASURED: none
  in this store; their live behavior was validated separately (Phase 7:
  season pull works, date filter dead on key, 20 upcoming odds events).
- Effective-time quality: UNAVAILABLE for stats/events/lineups/xG
  (0/45k+ rows carry effective_at); retrieved-time DOCUMENTED (server
  recorded_at). This is the binding constraint on strict eligibility.
- Upcoming: no SCHEDULED rows in store for any source.
- Current season (2026/27): all leagues UNAVAILABLE with reason
  provider_plan_or_source_limit.
- Odds: 7 canonical bookmakers, no display-name duplicates; selections
  already canonical; markets h2h/totals/asian_handicap.
- xG: statsbomb-only, 1588 rows, effective_at NULL throughout.
