# Phase 18 — Current Season (2026/27) Status

As of 2026-09-19, measured live against configured providers:

- **API-Football**: reachable. EPL season "2024" → 380 fixtures.
  Seasons "2025"/"2026" → 0 rows. The 2026/27 season is not published
  on this key. Status: **unavailable** for current-season fixtures.
- **Odds API**: reachable (cached 200). Upcoming events returned, but
  without league attribution they cannot enter the canonical universe.
  Status: **market observations only**.
- **football-data.co.uk**: no 2026/27 season file published yet.
  Status: **unavailable**.

Canonical 2026/27 match universe: **0 matches** (honestly empty, not
fabricated). The acquisition pipeline is validated end-to-end (mock
matrix + real historical-season run: 380 fetched, 0 created, 684
observations, idempotent rerun) and will populate the universe as soon
as any source publishes the season.
