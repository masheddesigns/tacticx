# Football Prediction & Market Intelligence Engine — Backend (Phase 1)

Personal-use analysis system. It does **not** place bets, execute trades, log into
bookmaker accounts, or perform gambling actions. It collects football + permitted
market data, stores historical snapshots, and exposes a REST API for the dashboard.

**Phase 1 scope: data ingestion + database + API only.**
Prediction engine (Phase 2), odds-movement analytics depth (Phase 3), backtesting
runner (Phase 4), MiroFish scenarios (Phase 5), and live prediction (Phase 6) are
architecture stubs, not active systems.

## Quickstart (Docker — one command)

```bash
cp backend/.env.example backend/.env   # add FOOTBALL_API_KEY / ODDS_API_KEY
docker compose up -d
# API:     http://localhost:8000
# Swagger: http://localhost:8000/docs
```

Run migrations + seed leagues:

```bash
docker compose exec backend alembic upgrade head
docker compose exec -T postgres psql -U bet betpredictor < backend/scripts/seed_leagues.sql
```

Manual sync (no keys needed for structure; needs keys for real data):

```bash
docker compose exec backend python -m scripts.sync --leagues EPL
```

## Phase 1.5 — real provider validation

No prediction/ML/MiroFish changes. Prove the data foundation with real keys:

```bash
docker compose exec backend python -m scripts.diag_config          # safe: configured/missing only
docker compose exec backend python -m scripts.smoke_test_football  # /status + next=1 fixture
docker compose exec backend python -m scripts.smoke_test_odds --sport soccer_epl
docker compose exec backend python -m scripts.sync --leagues EPL --next 5 --with-details --check-idempotency
docker compose exec backend python -m scripts.sync --match-id <provider_id> --with-details
docker compose exec backend python -m scripts.sync --live-only --max-matches 1 --with-details --with-odds
docker compose exec backend python -m scripts.data_quality_report
```

Rules enforced by the scripts: small bounded requests only, odds linked to
matches by exact team-name match (unmatched odds are skipped and counted, never
guessed), missing optional fields stay NULL/absent, every provider request lands
in `provider_request_logs` including provider-reported quota (`quota_remaining`)
when headers carry it. pytest never touches live APIs
(`tests/test_phase15.py` is fully mocked).

## Local (no Docker)

Requires Python 3.12+.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
DATABASE_URL=sqlite:///./dev.db pytest -q
uvicorn app.main:app --reload
```

## Configuration

All tunables live in `backend/.env` (see `backend/.env.example`):
`DATABASE_URL`, `REDIS_URL`, `FOOTBALL_API_KEY`, `ODDS_API_KEY`,
`SUPPORTED_LEAGUES` (`CODE:provider_id:season` — add leagues without code changes),
cache TTLs (`TTL_*`), quota guards (`PROVIDER_MAX_REQUESTS_*`, retry settings),
market settings (`ODDS_CONSENSUS_METHOD`, `ODDS_CONSENSUS_TIME_WINDOW_MINUTES`,
`ODDS_CONSENSUS_MIN_BOOKMAKERS`, `ODDS_MOVEMENT_FLAT_TOLERANCE`,
`ODDS_MIN_VELOCITY_INTERVAL_SECONDS`, `MODEL_MARKET_NEUTRAL_THRESHOLD`,
`MODEL_MARKET_STRONG_THRESHOLD`).

## Architecture

- `app/services/base.py` — `FootballDataProvider` / `OddsProvider` interfaces.
- `app/services/football/api_football.py` — API-Football (api-sports) adapter.
- `app/services/odds/odds_api.py` — The-Odds-API adapter.
- `app/services/http_client.py` — rate-limit gate, cache-first, single-flight
  dedup, exponential-backoff retries, `Retry-After` on HTTP 429, per-request
  quota logging (`provider_request_logs`).
- `app/services/ingestion.py` — idempotent upserts keyed on
  `(provider, provider_*_id)`; odds stored append-only with `dedup_hash`.
- `app/services/predictions/base.py` — `PredictionProvider` + Phase-1 stub.
- `app/services/predictions/mirofish.py` — decoupled scenario-layer interface.
- `app/services/backtesting/service.py` — immutable prediction records with
  `input_snapshot`; resolution only from finished matches (no lookahead).
- `app/workers/` — Celery tasks scheduled by match lifecycle + config TTLs.

## API (dashboard contract — full schemas in `/docs`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health`, `/api/v1/ready` | liveness / DB+Redis readiness |
| GET | `/api/v1/matches` | filters: `league date team status`, `page page_size` |
| GET | `/api/v1/matches/upcoming?hours=24` | next-N-hours kickoffs |
| GET | `/api/v1/matches/live` | live + halftime |
| GET | `/api/v1/matches/{id}` | detail |
| GET | `/api/v1/matches/{id}/statistics` | shots, possession, xG… |
| GET | `/api/v1/matches/{id}/events` | goals, cards, subs… |
| GET | `/api/v1/matches/{id}/odds`, `…/odds/history` | current / full history |
| GET | `/api/v1/odds`, `/api/v1/odds/{id}`, `/api/v1/odds/{id}/history`, `/api/v1/odds/{id}/movement` | movement = opening/current/Δ/%/direction/velocity |
| GET | `/api/v1/leagues`, `/api/v1/teams` | catalog |
| GET | `/api/v1/predictions/{match_id}` | stored predictions (stub in Phase 1) |
| GET | `/api/v1/markets/{id}`, `…/history`, `…/movement`, `…/consensus`, `…/comparison` | market state, timeline, consensus, model-vs-market (all support `?cutoff=`) |
| GET | `/api/v1/sync/logs`, `/api/v1/sync/leagues` | ingestion visibility |

## No fake data rule

If API keys are absent: adapters, mocked fixtures (`tests/fixtures/`), and docs
are provided. The system never invents matches, scores, or odds.

## Security

Input-validated routes, CORS allow-list, no keys/credentials in responses or git
(`.env` is git-ignored), no debug/admin endpoints in non-dev environments.

## Phase 1.6 — source-agnostic data layer

APIs are optional sources. The system is designed to operate primarily from
normalized historical/current datasets and permitted data-source adapters.

### 1. Architecture

```
            DATA SOURCES
                 |
  +--------------+--------------+
  |              |              |
  v              v              v
Scraper      Historical       APIs (fallback/
framework     datasets        validation only)
  |              |              |
  +--------------+--------------+
                 |
                 v
       Normalization layer      (Normalized* records + provenance)
                 |
                 v
            PostgreSQL          (canonical entities + raw_data_records)
                 |
      +----------+----------+
      |                     |
      v                     v
  Historical            Live/Current
    Data                   Data
```

Prediction code must never touch sources directly — the registry + pipeline is
the only path from raw sources to canonical entities.

### 2. Data source abstraction (`app/services/sources/`)

- `base.py` — `FootballDataSource`, `OddsDataSource`, `HistoricalDataSource`
  ABCs plus `SourceCapabilities` (each source declares what it really offers).
- `normalized.py` — `NormalizedMatch/Team/Player/MatchStatistics/Event/Lineup/
  Standing/OddsSnapshot/OddsSelection`. Provider parsing stays inside adapters;
  everything downstream sees only these.
- `registry.py` — `FootballSourceRegistry` / `OddsSourceRegistry` /
  `HistoricalSourceRegistry`; `football_source_chain()` / `odds_source_chain()`
  resolve primary→fallback from config.

### 3. Supported source types

| Name | Kind | Provides |
|---|---|---|
| `csv` | file datasets (.csv/.json/.jsonl/.parquet*) | fixtures, closing odds (h2h/totals), bulk history |
| `football_data_co_uk` | remote season CSVs (robots.txt verified permissive) | full-season results + closing odds |
| `api_football` | API wrapper (existing adapter, unchanged parsing) | fallback/validation only |
| `odds_api` | API wrapper (existing adapter, unchanged parsing) | fallback/validation only |

\* Parquet needs `pandas` + `pyarrow` installed, else a clean error.

### 4–5. Scraper rules & legal/technical constraints

`app/services/scraping/`: `PoliteFetcher` (min delay between same-host hits,
per-minute ceiling, timeout, caching, request logging, configurable
User-Agent) over the existing quota-protected HTTP layer; `robots_allowed()`
pre-check — disallowed sources raise `SourceDisallowed` and fail cleanly;
`BaseScraper` request→parse→validate→normalize→persist with versioned parsers
(`name@version` stored on every raw record). No CAPTCHA/auth/paywall/anti-bot/
rate-limit bypass exists anywhere; retries cover 429/5xx only (4xx fails fast
to protect quota).

### 6. Historical data import

```bash
python scripts/import_historical.py --file data/epl_2020_2025.csv --league EPL --season 2024
python scripts/import_historical.py --source football_data_co_uk --league EPL --season 2024
python scripts/import_historical.py --file data/x.json --league EPL --season 2024 --dry-run
```

Validates schema, normalizes teams/dates/competitions, resolves identities,
detects duplicates, preserves source + record IDs, upserts idempotently, and
prints the exact report (read/valid/inserted/updated/duplicates/invalid).
Malformed rows are listed and written to `<file>.rejected.jsonl` — never
silently discarded. Re-running is safe (resumable).

### 7. Team identity resolution (`app/services/identity/teams.py`)

`team_provider_mappings` + `TeamIdentityResolver`, priority: (1) known
(source, provider_team_id) mapping → (2) legacy provider columns → (3)
deterministic normalized-name match, alias-aware on BOTH sides
(order-independent) → (4) explicit `TEAM_ALIASES_JSON` dictionary → (5)
UNRESOLVED. No fuzzy matching. The alias map (e.g. `Dortmund` →
`Borussia Dortmund`, `Ein Frankfurt` → `Eintracht Frankfurt`) is curated from
real cross-source evidence; either variant resolves regardless of which was
stored first. Method labels (`mapping`, `legacy_provider_id`,
`normalized_name`, `alias`, `created`) persist on every mapping row.

### 8. Match identity resolution (`app/services/identity/matches.py`)

Canonical identity = (league, home team, away team, kickoff ±15 min).
`match_source_mappings` keeps source-native IDs; different providers pointing
at the same fixture resolve to ONE canonical row — never duplicates.

### 9. Odds snapshots

Append-only, per (match, bookmaker, market, timestamp); identical redeliveries
deduplicated by hash; genuine moves stored as new rows. Markets persisted only
when the source provides them (h2h/totals/asian_handicap family — never
invented). football-data.co.uk contributes BOTH opening (`B365:h2h`) and
closing (`B365C:h2h`) lines as separate snapshots. Implied probability/
overround/consensus/movement stay available via the existing
`/odds/{id}/movement` endpoint; not used for training yet.

### 10. Data provenance

`raw_data_records` tracks every ingested record (source, entity, source ID,
payload hash, parser version, status: pending/processed/duplicate/
quarantined/failed/unresolved). Lineage columns (`source`, `source_record_id`,
`effective_at`, `source_event_id/market_id`) ride on statistics, events,
lineups, standings and snapshots, so backtests can reconstruct pre-kickoff
state. Retention via `RAW_RETENTION_DAYS` (0 = keep).

### 11. Data coverage report

```bash
python scripts/data_coverage.py --league EPL --season 2024
```

Per league/season: matches, with statistics/xG/events/lineups/odds/
historical-odds, teams, plus unresolved/quarantined/failed counts.

### 12. CLI commands

```bash
python scripts/collect_fixtures.py   --league EPL --season 2024 --from 2024-08-01 --to 2024-08-31 [--source csv --file data/x.csv] [--dry-run]
python scripts/collect_results.py    --league EPL --season 2024 --from ... --to ...
python scripts/collect_statistics.py --league EPL --season 2024 --from ... --to ... --max-matches 10
python scripts/collect_odds.py       --league EPL --season 2024 [--live]
python scripts/import_historical.py  --file ... --league EPL [--dry-run] [--no-create-teams] [--column-map '{...}']
python scripts/data_coverage.py      [--league EPL] [--season 2024] [--json]
```

All jobs support `--dry-run`, are bounded, and resume safely via idempotent
upserts. `--source` overrides the configured primary→fallback chain per run.

### 13. Configuration (.env)

`FOOTBALL_SOURCE_PRIMARY/FALLBACK`, `ODDS_SOURCE_PRIMARY/FALLBACK`,
`HISTORICAL_SOURCE`, `SOURCE_PRIORITY` (conflict reconciliation, first wins),
`SCRAPER_MIN_DELAY_SECONDS`, `SCRAPER_MAX_REQUESTS_PER_MINUTE`,
`SCRAPER_TIMEOUT_SECONDS`, `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_USER_AGENT`,
`DATASET_BASE_URL`, `STATSBOMB_BASE_URL`, `DATA_DIR`, `TEAM_ALIASES_JSON`,
`PLAYER_ALIASES_JSON`, `RAW_RETENTION_DAYS`. See
`.env.example`. Secrets still only in git-ignored `.env`, redacted from logs.

### 14. Testing

`tests/test_phase1.py` (20) + `test_phase15.py` (18) + `test_phase16.py` (48) +
`test_phase17.py` (32) + `test_phase18.py` (29) + `test_phase2.py` (37) +
`tests/test_phase3.py` (25), all mocked — no live network in pytest.
Phase 3 covers: implied/overround/no-vig, consensus (median/mean/trimmed),
movement/velocity incl. zero-interval and sub-minute guards, cutoff
reconstruction (future excluded), model comparison + agreement bands, closing
as benchmark-only, completeness handling, market API, market backtesting.
Full suite: 209 passed.

### 15. Known API limitations (unchanged)

Free plans: historical seasons 2022–2024 only, no current EPL, quotas limited
(100/day football, 500/mo odds), `?date=` restricted to ±1 day (code uses
equivalent from/to ranges), no BTTS market from the odds provider. APIs are
used selectively for validation/current data — never bulk history.

## Phase 1.7 — historical data acquisition

Goal: solve the stats/xG/events/lineups shortage with legitimate sources only.
No prediction modeling (no Elo/Poisson/ML/MiroFish/betting of any kind).

### 16. Source research (permitted access only)

| Source | URL | Data | Coverage | Format | License / status | Automated collection |
|---|---|---|---|---|---|---|
| football-data.co.uk | football-data.co.uk | results, HT, shots, SOT, corners, fouls, cards, open+close odds | 5 leagues, 1993→now | CSV | free, robots.txt permissive (verified) | YES — polite fetcher |
| StatsBomb Open Data | github.com/statsbomb/open-data | events+xG, lineups, matches | La Liga 04–21, EPL 03/04 (38 matches) + 15/16, Bundesliga 15/16 + 23/24 (34 each), Serie A 15/16, Ligue 1 15/16 + 21/22–22/23, UCL finals-only for listed seasons (verified per file, never assumed) | JSON | free for public research + attribution | YES — raw GitHub JSON |
| understat.com | understat.com | xG, stats | — | HTML/JSON | robots.txt `Disallow: /` | NO — disallowed |
| FBref | fbref.com | stats, xG, lineups | — | HTML | 403 to bots, ToS forbid scraping | NO — blocked |
| worldfootball.net | worldfootball.net | lineups, scores | — | HTML | 403 to bots | NO — blocked |
| Kaggle datasets | kaggle.com | varies | varies | varies | per-dataset, manual download | Only via generic CSV importer |

Rejected sources are documented, never scraped, never evaded.

### 17. New adapters (`app/services/sources/`)

- `football/statsbomb.py` — `StatsBombSource` (matches/lineups/events/xG;
  xG = summed shot xG incl. penalties; on-target = Goal+Saved; starters from
  Starting-XI tactics, the rest substitutes; unmapped event types skipped).
- `football/football_data_co_uk.py` — extended: full stat columns, closing
  (`B365C`) + asian-handicap markets, structured sids for detail fetching,
  local disk cache with content validation.
- `historical/csv_source.py` — `match_stats_from_row()`, closing/AH snapshots,
  `row:{idx}` sids for detail fetching.
- Wrappers: API-Football now captures formation, player IDs, stoppage minutes,
  assists; stat names normalized centrally (`sources/stats_schema.py`).
- Identity: `PlayerIdentityResolver` + `player_provider_mappings`; alias-aware
  (order-independent) matching for teams and players.
- Quality: `validate_xg`, `validate_minute`, `assess_temporal_quality()`
  (verified/estimated/unknown); stat divergences across sources open
  tolerance-gated conflicts (first value stays canonical, both preserved).
- Provenance: `temporal_quality` + `source_url` on every raw record.

### 18. New/changed CLI

```bash
python scripts/import_historical.py --source football_data_co_uk --league EPL --from-season 2022 --to-season 2024
python scripts/import_historical.py --source statsbomb --league LA_LIGA --season 2015 --with-details --max-matches 10
python scripts/import_historical.py --source csv --file data/E0_{season}.csv --league EPL --from-season 2020 --to-season 2024
python scripts/prune_raw.py --dry-run | --apply [--days N]
python scripts/data_coverage.py --all [--league EPL] [--season 2024] [--json]
python scripts/data_quality_report.py [--json]
```

Season files cache to `data/.cache/` (`--refresh` to re-download); ranges loop
seasons with per-season reports; every job is idempotent/resumable.

### 19. Real coverage achieved (nothing fabricated)

fdco: EPL 2022–24 (1,140) + La Liga/Serie A 2023 (760) + Bundesliga/Ligue 1
2023 (612) with results, full stats, closing odds. StatsBomb: La Liga 2015/16
(380) + EPL 2015/16 (380) + Bundesliga 2023/24 (34 — genuinely partial
upstream) with matches; events/xG/lineups for bounded samples (18 matches).
Total ≈ 3,300 canonical matches, 0 duplicates, 0 invalid values.

### 20. Phase 2 gate (objective)

NOT READY for full statistical modeling: possession is 0% everywhere (no
permitted bulk source found), xG covers ~1% of matches (15), events/lineups
~1%. READY only for results+shots/corners/cards/closing-odds modeling on the
fdco-covered seasons. Next data: a permitted possession source (none found —
Understat/FBref forbidden), and broader xG (expand StatsBomb detail collection:
La Liga has 16 more seasons available; each full season ≈ 380 event-file
downloads, resumable per match).

## Phase 1.8 — StatsBomb expansion + readiness gate

### 21. StatsBomb source (attribution required)

Data: StatsBomb Open Data (github.com/statsbomb/open-data), free for public
research use — any published analysis must credit StatsBomb. Raw GitHub JSON
over the polite fetcher (robots pre-check, delays, per-minute ceiling,
disk cache in `data/.cache/`, request logging). No auth, no protections,
none bypassed. Validated competitions: La Liga 2004/05–2020/21 (season IDs
resolved live from `competitions.json`), Bundesliga 2015/16 + 2023/24 (34
matches — partial upstream), Serie A 2015/16, Ligue 1 2015/16 + 2021/22–22/23,
EPL 2003/04 + 2015/16, UCL 1999/2000–2018/19. Claim only what was imported.

Enrichment over 1.7: events carry second/period/outcome; xG sums source xG
only (shots lacking it counted in transparent `shots_missing_xg`, never
zero-filled); lineups carry jersey numbers; formations stored as sourced stat
rows; captaincy stays 0 (not published — documented absence).

### 22. Inventory, manifest, collection

```bash
python scripts/statsbomb_inventory.py --all [--league LA_LIGA] [--season 2015] [--manifest] [--probe --max-probe 20] [--json]
python scripts/import_statsbomb.py --competition "La Liga" --season 2015 --with-details [--max-matches 50] [--refresh] [--resume|--no-resume] [--dry-run]
```

Inventory derives a per-match manifest (IMPORTED/PARTIAL/AVAILABLE/
NOT_AVAILABLE/FAILED/UNKNOWN) from DB state + cache + raw attempt records —
no extra table; 404s are sticky and never retried blindly. Detail collection
is bounded, resumable per match (DB presence + 404 memory), and skips
re-downloads via cache. Bulk pace (~1 req/s via env override) stays
rate-conscious against a static CDN; defaults remain conservative.

### 23. Cross-source reconciliation (proven on real data)

760 fdco + StatsBomb rows for La Liga 2015/16 → **380 canonical matches**,
20 unified teams (alias-curated variants: `Ein Frankfurt`, `Sp Gijon`,
`M'gladbach`…), **12 genuine stat conflicts** preserved with both
observations (shots 16.0 vs 17.0 — definitional, not errors; zero score
conflicts). Wall-clock skew across sources (fdco 19:30 vs StatsBomb 21:30)
merges via same-day fallback guarded by unique-pairing + score agreement.

### 24. Temporal discipline + leakage audit

Bulk history is `estimated` (event dates known, publication unknown);
live API pulls are `verified`. `audit_leakage()` flags any feature record
newer than kickoff or of unknown timing as `LEAKAGE_RISK` in
`data_quality_report` (counts + examples) — flagged, never deleted. Closing
odds stamped at kickoff are flagged (cannot prove pre-kickoff availability);
date-only evidence is never stamped with false precision.

### 25. Final coverage (measured, not claimed)

3,272 canonical matches (EPL 1,520 / La Liga 760 / Serie A 380 / Bundesliga
306 / Ligue 1 306); xG 794 matches (24%); events 10,411 rows; lineups 28,706
(1,690 players, formations where published); stats 45,184; odds 36,870
snapshots; duplicates 0; invalid 0; unresolved 0; possession 0% everywhere.

### 26. Phase 2 gate

NOT READY FOR PHASE 2 for full modeling (possession unavailable by design;
xG/events at 24%, below a comfortable modeling threshold; 444 open
definitional conflicts need no action but are unaudited at scale). READY
today: results/shots/corners/cards/closing-odds modeling on fdco seasons,
and xG/event-based modeling strictly within the 794 fully-detailed matches.
Next data if wanted: more StatsBomb detail seasons (mechanical from here),
a permitted possession source (none exists among evaluated sources).

## Phase 2 — Statistical prediction engine

Models (`app/services/predictions/`): **Elo** (chronological ratings + home
edge + empirical draw prior), **Poisson** (venue-split attack/defense, recency
weights, league context, optional xG blend), **Monte Carlo** (seeded sampling
of Poisson lambdas), **Ensemble** (configurable weights, registry for future
xG/ML/Market/MiroFish members), **Baseline** (pre-cutoff empirical
distribution). All outputs: 1X2 (sums to 1), expected goals, O/U 1.5/2.5/3.5,
BTTS, score grid, audit trail. No guarantees language anywhere.

Temporal safety: `HistoricalFeatureRepository` (cutoff + strict/estimated
modes) is the only read path for models; unknown-timing records excluded in
strict mode; backtests default to strict and walk forward chronologically
(train = all before cutoff, test = next match).

```bash
python scripts/predict.py --match-id ID --model ensemble [--seed 7] [--json]
python scripts/backtest.py --league EPL --season 2024 [--model poisson] [--temporal-mode strict_prematch] [--json]
```

Real validation (strict, EPL 2024/La Liga 2015): ensemble ≥ poisson ≥ Elo >
baseline on accuracy/log-loss/Brier; xG blend active only where eligible
(`xg_used` recorded). Poisson/ensemble backtests are slow on full seasons
(O(n²) history scans) — bound with `--from-date/--to-date` for iteration.

## Phase 3 — Market intelligence + odds analysis

Separate analytical layer over bookmaker prices. The statistical ensemble
never consumes odds; the market never overwrites model probabilities.

### Market architecture

```
Observed snapshots (append-only, per match/bookmaker/market/timestamp)
        │
        ▼
Implied probability (1/price) → overround check (complete markets only)
        │
        ▼
No-vig normalization → per-bookmaker fair probabilities
        │
        ▼
Consensus (median/mean/trimmed-mean across books, configurable minimum)
        │
        ▼
Model-vs-market comparison (differences + agreement bands, thresholds in .env)
```

### Implied probability, overround, no-vig

`raw = 1/price` per selection. Overround = Σraw over a **complete** market
(h2h needs home+draw+away; totals grouped by line) — never computed from
partial markets. No-vig = raw/Σraw, kept alongside raw (never overwriting).
Calculation version: `market_probability_v1`.

### Consensus methodology

Probabilities (not decimal odds) are aggregated: median by default (robust to
one stale book), mean or trimmed-mean configurable via
`ODDS_CONSENSUS_METHOD`. Consensus requires
`ODDS_CONSENSUS_MIN_BOOKMAKERS` (default 2) complete books. Best/worst prices
only compare snapshots inside `ODDS_CONSENSUS_TIME_WINDOW_MINUTES` (default
5). Version: `market_consensus_v1`.

### Movement methodology

Per (bookmaker, market, selection) timeline: consecutive equal prices
collapse; moves below `ODDS_MOVEMENT_FLAT_TOLERANCE` are noise; velocity is
percentage-points-per-hour, `None` on zero/duplicate timestamps or intervals
below `ODDS_MIN_VELOCITY_INTERVAL_SECONDS` (bulk imports stamp batches
milliseconds apart — recorded, never annualized). Version: `movement_v1`.

### Cutoff reconstruction

`get_market_state(match_id, cutoff, market)` returns the latest snapshot per
bookmaker with timestamp ≤ cutoff — future odds are unreachable by
construction. Completeness: complete (≥1 full book) / partial /
insufficient. Closing lines (C-suffixed source market IDs) are a benchmark
only, never a pre-closing input.

### Model-market comparison

Per-outcome absolute/relative differences plus agreement bands from
`MODEL_MARKET_NEUTRAL_THRESHOLD` (0.03) / `MODEL_MARKET_STRONG_THRESHOLD`
(0.08): same top outcome within neutral → strong agreement, and so on.
Descriptors only — never recommendations, never "sharp/insider" narratives.

### Limitations

- Bulk historical timestamps are import-time (or kickoff-stamped estimates):
  pre-kickoff reconstruction works only for live-polled data; closing lines
  are the historical benchmark.
- Only h2h/totals/asian_handicap observed so far; BTTS and others appear only
  if a source supplies them.
- 7 bookmakers via football-data.co.uk; live coverage depends on provider.
- Consensus needs ≥2 complete books; single-book states report completeness
  without consensus.
- TacticX market probabilities are analytical transformations of observed
  bookmaker prices and are not guaranteed probabilities of the actual outcome.

## Phase 4 — Advanced features + walk-forward validation

Feature pipeline (`app/services/features/engineered.py`, version
`features_v1`): rolling form last 3/5/10 (W/D/L, GF/GA, GD, points, PPM),
venue splits, half-life recency weights (`FORM/XG_DECAY_HALF_LIFE_DAYS`),
goal differentials, xG/shots rolling (source values only), rest days +
congestion (finished matches only; missing = unavailable, never zero),
season context, chronologically reconstructed standings (current season only,
never the final table), descriptive H2H (min sample gate), Elo-based
strength of schedule. Every leaf carries
`{value, available, source, as_of, quality}`; missing data is flagged, never
invented. Target match never contributes to its own features (cutoff-gated,
tested).

Models: `advanced_v1` (numpy softmax regression, deterministic full-batch
GD, L2, train-standardized), `advanced_v1-xg` (+xG diff, xG-eligible rows
only), `advanced_goal_v1` (Poisson + shrinkage toward league mean for thin
histories), `ensemble_v2` (walk-forward learned weights), `calibration_v1`
(temperature scaling, train-window only, `-cal` version suffix). Confidence
derives from probability margin (+ entropy/disagreement notes), labeled as
uncertainty basis, never correctness.

```bash
python scripts/features.py --match-id ID [--cutoff ... --json]
python scripts/walkforward.py --league EPL --train 2015,2022 --validate 2023 --test 2024 [--use-xg]
python scripts/backtest.py --model advanced --league EPL --season 2024
```

Walk-forward: train → validate (weights + temperature) → test, expanding
windows, no shuffling. Purge/embargo analysis: no embargo needed — features
aggregate completed matches strictly before cutoff; same-day earlier matches
are legitimately usable; the target is structurally excluded.

Validated (EPL test 2024, strict): ensemble_v1 ≥ poisson ≥ Elo > baseline on
log-loss/Brier; learned v2 weights and calibration did not improve
out-of-sample here (reported, not hidden). Poisson-xg beats poisson on the
La Liga 2015 ablation (identical N=330). Market slice (n=284): market ahead
of Elo descriptively; paired bootstrap CI excludes zero but closing lines
inform the market side — stated, not a superiority claim.

## Phase 5 — Robustness + cross-league validation + probability quality

Evaluation package (`app/services/evaluation/`): identical-population
comparisons (`compare.py`: match-id intersection, paired per-match Brier /
log-loss diffs, deterministic bootstrap CIs), per-class calibration with
sparse-bin flags (`calibration.py`), descriptive uncertainty — entropy,
probability margin, member disagreement (`uncertainty.py`; never correctness
claims), parameter sensitivity + Monte Carlo convergence + Poisson
truncation audit (`sensitivity.py`), availability-based model regimes +
model status registry (`regimes.py`), subgroup / extreme-probability / draw /
goal-distribution / correct-score / drift analyses (`subgroups.py`), and
deterministic run artifacts with dataset fingerprint + environment metadata
(`artifacts.py`, `data/phase5/<run_id>/`).

```bash
python scripts/phase5_validate.py --analysis baseline --scope "EPL:2024,LA_LIGA:2015" --models "elo,poisson,ensemble" [--with-market]
python scripts/phase5_validate.py --analysis sensitivity|mc|weights|advanced --scope "EPL:2024"
python scripts/phase5_deepdive.py --label v1
```

Validated: ensemble_v1 (equal weights) is the production default across 6
league-seasons (EPL 2024/2023, La Liga 2015/2023, Serie A 2023, Bundesliga
2023) — learned v2 weights and validation-fit temperature did not transfer
out-of-sample (measured, CIs reported). xG pathway: xG rows carry unknown
timing, so strict mode correctly excludes them (poisson-xg ≡ poisson_v1);
under parent-anchored estimated mode poisson-xg beats poisson_v1 decisively
on identical populations (EPL 2015 dBrier +0.052, La Liga 2015 +0.069, CIs
exclude zero) — estimated, never a strict claim. Monte Carlo: 10k draws are
within ~0.012 of 25k worst-case (seed 7); 1k backtest draws carry sampling
noise up to ~0.05. Poisson 0..10 grid retained on evidence (grid-12 retest:
Brier Δ 0.000015). Closing lines remain the sharper benchmark (EPL 2024
market Brier 0.568 vs model 0.594, N=284) and are never a model input.

Read-only artifacts API: `GET /api/v1/validation/phase5/runs`,
`/runs/{run_id}/{artifact}`, `/model-registry`, `/disclaimer`.

## Phase 6 — Prediction intelligence + scenarios + MiroFish

Intelligence layer (`app/services/intelligence/`): `PredictionComposer`
(snapshot → regime-selected core model → derived markets → uncertainty →
disagreement → market context → explanation; never trains, never mutates),
pure derived-markets math (`derived.py`: O/U 0.5–3.5, BTTS joint +
closed-form cross-check, double chance identities, team totals, correct
scores with required-16 coverage, grid/tail mass exposure, 1X2 rejection of
invalid vectors), factual explanation service (Elo ratings, Poisson
strengths/lambdas, xG status never-zero-filled, advanced coef×feature
contributions labeled "model contribution"), cutoff-safe historical
analogues (standardized distance, target excluded, min-sample gate,
descriptive outcome frequencies), deterministic scenario engine
(baseline always first, baseline+scenario+difference output), and an
optional MiroFish adapter (labeled context, output validation, timeout,
failure → `unavailable`, never touches core probabilities).

Default core model unchanged: ensemble_v1 (Phase 5 evidence stands).

```bash
python scripts/tacticx.py predict <match_id> [--model ensemble --json]
python scripts/tacticx.py explain <match_id>
python scripts/tacticx.py scenarios <match_id> [--names baseline,high_scoring]
python scripts/tacticx.py analogues <match_id> [--top-k 10]
python scripts/tacticx.py mirofish <match_id>
```

API: `GET /api/v1/predictions/{id}/full|explanation|distribution|scenarios|analogues|models`,
`POST .../scenarios` (recorded, core untouched), `POST .../mirofish`
(optional, failure-safe). Storage reuses `predictions.input_snapshot`;
new audit tables (`prediction_explanations`, `scenario_runs`,
`analogue_results`, `mirofish_runs`) carry prediction/model/cutoff/version/
input-reference/status columns via the established `create_all` pattern.

Validated: 288 tests green (258 prior + 30 new); integration over real
Bundesliga/EPL/La Liga matches with probability + temporal audits;
MiroFish adapter ready with no external service bound (honest
`unavailable`, never fabricated).

## Phase 7 — Live pipeline + prediction lifecycle

Lifecycle layer (`app/services/lifecycle/`): source-agnostic upcoming
discovery (`upcoming.py`; API-Football season fetch + local windowing, odds
events with unresolved league left unset), idempotent canonical sync
(`sync.py` via Phase 1.6 resolvers; metadata may advance, predictions never
touched), versioned predictions (`versions.py`: generated → refreshed →
superseded → locked → evaluated; readiness gate; input-reference cache;
neutral diffs; kickoff lock), append-only odds refresh + current market state
(`odds_refresh.py`; closing reported separately, never merged), source health
with bounded retries and fail-fast auth (`health.py`), post-match evaluation
(`evaluate.py`; finished-only, idempotent, never mutates predictions),
descriptive monitoring (`monitoring.py`; rolling metrics, drift bands,
data drift — never switches models or retrains), and
`UpcomingPredictionService` (readiness-gated single + isolated batch).

```bash
python scripts/tacticx.py sync-upcoming [--league EPL --hours 168]
python scripts/tacticx.py predict-upcoming [--league EPL --hours 48]
python scripts/tacticx.py refresh <match_id>
python scripts/tacticx.py evaluate [--limit 500]
```

API: `GET /api/v1/matches/{id}/predictions|prediction/latest|prediction/diff`,
`POST .../predict|refresh`, `GET /api/v1/sources/health|status`,
`POST /api/v1/lifecycle/evaluate`, `GET .../monitoring`, `POST .../lock`.
New tables (`prediction_versions`, `prediction_diffs`, `source_health`,
`prediction_evaluations`) via the established `create_all` pattern with
lifecycle indexes; sync logging reuses `data_sync_logs`.

Validated: 310 tests green (288 prior + 22 new); full v1→v2→lock→evaluate
chain on real + controlled fixtures; real-provider check (5 football + 1 odds
request: 380-season pull works, date filter dead on this key, 20 upcoming odds
events resolve to zero canonical matches — correctly unmatched, never guessed).

## Phase 8 — Multi-source reconciliation + data quality

Reconciliation layer (`app/services/reconciliation/`): source envelopes with
raw references (`records.py`), typed match comparison with kickoff tolerance
+ season buckets (`matches.py`), team/player identity with unresolved queue
and versioned manual mappings (`identities.py`), event matching within
`EVENT_TIME_TOLERANCE_SECONDS` (`events.py`), semantic statistic
classification with a definition registry (`statistics.py`), bookmaker/market
selection canonicalization (`odds_norm.py`), per-field canonical resolvers
with version history (`canonical.py`), documented quality scoring
(`quality.py`), measured source matrix (`matrix.py`), and prediction gating
(`gating.py`: critical identity conflicts block, irrelevant gaps do not;
temporal gates never weakened).

```bash
python scripts/tacticx.py reconcile --match 1 [--dry-run]
python scripts/tacticx.py reconcile --league EPL [--all --limit 500]
python scripts/tacticx.py data-quality [--league EPL]
python scripts/tacticx.py mapping team <source> <source_id> <canonical_id> [--dry-run]
```

API: `GET /api/v1/data-quality[/{entity}]`,
`/matches/{id}/sources|conflicts|provenance`,
`/reconciliation/queue`, `POST /reconciliation/mappings`.
New tables (`reconciliation_conflicts`, `canonical_field_versions`,
`unresolved_records`, `manual_mappings`, `stat_definitions`) via `create_all`;
legacy `source_conflicts` untouched. Field authority is explicit
(`FIELD_SOURCE_PRIORITY`: score/status/kickoff → api_football, xG →
statsbomb, odds → odds_api, closing → football_data_co_uk).

Validated: 332 tests green (310 prior + 22 new); real-data run over 5 leagues
(3272 matches, 414 multi-source, 0 unresolved; same-stat cross-source overlap
is 0 — disjoint coverage, honestly reported); synthetic overlap proves
classification, event matching (8s-apart duplicate matched), idempotency, and
prediction isolation (4388 prediction rows byte-identical after reconcile).

## Phase 9 — Player, lineup & event intelligence (additive feature layer)

Player intelligence (`app/services/player_intelligence/`): cutoff-safe
repository (target contributes zero; unknown timing strict-excluded),
appearance histories (starts/subs; minutes honestly unavailable), registered
event features (goals/penalties/cards/subs with source definitions — no
shots/passes/tackles invented), per-appearance form with sample gates,
transparent team aggregates with contributors, lineup continuity + formation
frequency/entropy/stability, versioned memberships, availability boundary
(unknown, never injury-inferred), 5-dimension quality, hashed versioned
snapshots (`player_features_v1`).

```bash
python scripts/tacticx.py player-features --match-id 702 --mode estimated
python scripts/player_experiment.py --league LA_LIGA  # isolated, descriptive
```

API: `GET /api/v1/features/player/{id}[/availability|contributors|quality]`
(inspection only). No prediction model modified; offline experiment showed
no activatable signal (weights 0.0 / null CI); strict mode yields nothing
on current data (effective_at NULL) — reported, not worked around.
Docs: `PHASE9_REPORT.md`, `PHASE9_LEAKAGE_AUDIT.md`, `PHASE9_REGRESSION_REPORT.md`
(changed = 0).

## Phase 10 — Production coverage, freshness & temporal provenance

Freshness layer (`app/services/freshness/`): four-timestamp provenance
(event/effective/retrieved/created, never conflated), deterministic status
classifier, per-family freshness policies (standings/form/membership/lineup/
odds/xG), measured-only capability registry, current-season audit, append-only
fixture observations, match + feature-family eligibility gates
(`production_strict` vs `estimated`, explicit degraded mode), staleness/xG/
player audits. New table `match_observations` via `create_all`.

```bash
python scripts/tacticx.py sources status|coverage|freshness|validate [--league EPL]
```

Eligibility verdict: `{eligible, reasons, warnings, degraded_mode,
data_quality, temporal_quality, freshness}`. Production strict demands known
timing, resolved identity, no critical conflicts; estimated research stays
visibly labeled. Docs: `PHASE10_REPORT.md`, `PHASE10_TEMPORAL_PROVENANCE.md`,
`PHASE10_SOURCE_MATRIX.md`. All 364 tests green; models unchanged.

## Phase 11 — Production match universe & acquisition pipeline

Acquisition layer (`app/services/acquisition/`): explicit match universe
view (lifecycle + evidence confidence), idempotent workflow with classified
failures and partial-success safety, source activation gate (10 checks),
scheduler job registry, capability-checked enrichment, deterministic
production snapshots, per-match readiness reports, explicit dataset
boundaries (historical/validation/test/production). Tables:
`acquisition_runs`, `source_activations`, `acquisition_jobs` via `create_all`.

```bash
python scripts/tacticx.py sync-fixtures [--league EPL]
python scripts/tacticx.py readiness [--match-id 1 --league EPL --limit 20]
```

Current-season acquisition honestly records empty/unavailable (no qualifying
source in environment — documented, no workaround). Docs:
`PHASE11_REPORT.md`, `PHASE11_ACQUISITION.md`, `PHASE11_DATA_BOUNDARIES.md`.
All 366 tests green; models unchanged.

## Phase 12 — Advanced pre-match modeling & walk-forward research

Research framework (`app/services/model_research/`): versioned immutable
datasets (one chronological pass, bulk prefetch), season splits + expanding
folds (never random), family-gated features with missingness reports (no
imputation), deterministic numpy candidates (softmax logreg + production
baselines), train-only preprocessing, validation-only calibration as `-cal`
versions, identical-population paired evaluation with bootstrap CIs,
additive/leave-one-out ablation, evidence-only promotion gate (no
auto-promote; human decision required with reason), hashed artifacts +
`research_models` registry.

```bash
python scripts/tacticx.py research run --league EPL --candidate logreg_team --train 2015,2022 --validate 2023 --test 2024 [--split-date ...] [--folds N]
python scripts/tacticx.py research ablate --league EPL [...]
python scripts/tacticx.py research registry|promote-check --model-id ...
```

Result: primary hypothesis failed (logreg_team degradation vs ensemble_v1);
all exploratory null; NO PROMOTION, ensemble_v1 retained. Docs:
`PHASE12_REPORT.md`, `PHASE12_MODEL_REGISTRY.md`, `PHASE12_LEAKAGE_AUDIT.md`.
All 394 tests green; production predictions unchanged (changed = 0).

## Phase 13 — Historical data expansion & feature coverage

Data expansion (`app/services/data_expansion/`): measured inventory,
candidate registry (validated/tested/rejected with reasons), polite
acquisition, row validation, backfill through the proven pipeline
(identity + reconciliation + idempotency), temporal checks, quality gates,
coverage deltas, deterministic dedup keys.

```bash
python scripts/tacticx.py data coverage [--league EPL]
python scripts/tacticx.py data backfill --league EPL --season 1617 [--dry-run]
python scripts/tacticx.py data candidates
```

Result: 3,272 → 16,639 matches (+13,367) across 37 new season-slots;
EPL contiguous 2015–2024. Pipeline odds idempotency fixed along the way.
No model, weight, calibration, or registry change. Docs:
`PHASE13_REPORT.md`, `PHASE13_SOURCE_INVENTORY.md`,
`PHASE13_COVERAGE_DELTA.md`, `PHASE13_LEAKAGE_AUDIT.md`.
All 407 tests green.
