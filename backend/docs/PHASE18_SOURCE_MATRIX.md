# Phase 18 — Current-Season Source Matrix (measured 2026-09-19)

Capabilities use measured | documented | unknown | unavailable.
Nothing below is claimed without an actual validating request.

| Source | Fixtures | Results | Stats | Events | Lineups | xG | Odds | Upcoming | Current season (2026/27) |
|---|---|---|---|---|---|---|---|---|---|
| api_football | measured (EPL 2024: 380) | measured | measured | measured | measured | unavailable | unavailable | measured (via season fetch + local window) | **unavailable** — seasons "2025"/"2026" return 0 rows; latest retrievable EPL season is "2024" |
| odds_api | unavailable (no league attribution; never guessed) | unavailable | unavailable | unavailable | unavailable | unavailable | measured (upcoming events) | measured (events only) | **unavailable as fixture source** — retained for market observations |
| football-data.co.uk | measured (historical CSVs) | measured | measured | unavailable | unavailable | unavailable | measured (closing) | unavailable | unavailable (no current-season file published yet) |

Request counts (quota-safe validation): api-football 4 requests
(EPL seasons 2026/2025/2024 + one season-windowed EPL 2024 fetch);
odds-api 1 cached request. No quota exhaustion, no repeated probing of
known-bad filters (Phase 7 date-filter finding reused, not re-tested).

Temporal quality: api-football fixtures carry kickoff timestamps
(event-time known); effective/retrieved timing unknown → strict gating
applies. Odds events carry commence times.

Source health: api-football healthy (200s observed); odds-api healthy
(cached 200). No authentication failures observed; no secrets logged.
