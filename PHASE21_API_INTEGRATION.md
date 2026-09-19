# TacticX Phase 21 — API Integration Documentation

## 1. Centralized API Client Architecture

All network communication with the TacticX backend is centralized within [`frontend/src/api/client.ts`](file:///Users/sivek/Documents/Bet%20Predictor/frontend/src/api/client.ts). No raw `fetch()` calls or ad-hoc endpoint strings are scattered across components.

### Core Client Characteristics
- **Configurable Base URL**: Reads `import.meta.env.VITE_API_BASE_URL` with a default of `/api/v1`. During local development, the Vite dev server transparently proxies `/api` to `http://localhost:8000`.
- **Request Cancellation**: Every method accepts an optional `AbortSignal` passed directly from TanStack Query for automatic teardown on route transitions or component unmount.
- **Normalized Error Handling**: Converts backend HTTP error codes and JSON error objects into an `ApiError` instance with machine-readable codes.
- **Credential Protection**: The client never attaches, requests, or stores external API keys (API-Football, The Odds API, MiroFish) in client-side storage or cookies.

---

## 2. API Endpoint Mappings

| UI Feature Area | Backend Route | HTTP Method | Query / Payload Parameters | Response Type | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Engine Readiness** | `/ready` | `GET` | — | `ReadyProbeResponse` | Probes Postgres connection and Redis cache state. |
| **Supported Leagues** | `/leagues` | `GET` | — | `LeaguesResponse` | Supported league codes and canonical names. |
| **Match Explorer** | `/matches` | `GET` | `league`, `status`, `date`, `team`, `page`, `page_size` | `PaginatedMatchesResponse` | Lightweight match listing with metadata pagination. |
| **Current Universe** | `/matches/current` | `GET` | `competition`, `status`, `date`, `eligible`, `page`, `page_size` | `PaginatedMatchesResponse` | Returns current season universe (currently 0 fixtures for 2026/27). |
| **Match Detail** | `/matches/{match_id}` | `GET` | — | `MatchListItem` | Single match fallback metadata. |
| **Match Intelligence** | `/matches/{match_id}/intelligence` | `GET` | `mode`, `cutoff`, `model`, `seed`, `response_mode`, `mirofish_scenario` | `MatchIntelligence` | Full canonical intelligence document (`match_intelligence_v1`). |
| **Sources Registry** | `/sources` | `GET` | — | `SourcesResponse` | Registered providers, tier classifications, and capabilities. |
| **Source Status** | `/sources/{source_id}/status`| `GET` | — | `SourceEntry` | Granular adapter health and quota. |
| **Acquisition Telemetry**| `/acquisition/status` | `GET` | `source` | `AcquisitionStatusResponse` | Recent pipeline execution runs and season coverage audit. |
| **Scheduler Dashboard** | `/jobs/dashboard` | `GET` | — | `SchedulerDashboardResponse`| Real-time operational job summaries, locks, and competitions. |
| **Job Execution Logs** | `/jobs` | `GET` | `job_type`, `source`, `competition`, `status`, `limit` | `JobRecord[]` | Execution history, record counts, and failure tracking. |
| **Scheduler Alerts** | `/jobs/alerts` | `GET` | — | `any[]` | System alert conditions. |
| **Scheduler Anomalies** | `/jobs/anomalies` | `GET` | — | `any[]` | Cadence and drift anomalies. |
| **Scheduler Due Jobs** | `/jobs/due` | `GET` | — | `any[]` | Jobs due for next execution. |
| **Lock Cleanup** | `/jobs/locks/cleanup` | `POST` | — | `{"cleaned": number}` | Reclaims expired or orphaned scheduler locks safely. |

---

## 3. Data Contract Fidelity & Zero-Recalculation Guarantee

The frontend implements a strict read-only projection policy:

1. **1X2 Probabilities**: Rendered directly from `MatchIntelligence.core_prediction` (and `derived_markets.one_x_two`). The frontend merely multiplies the float by 100 for display (e.g. `0.202422` \(\to\) `20.2%`), preserving exact values in tooltips.
2. **Expected Goals (\(\lambda\))**: Rendered from `MatchIntelligence.expected_goals` (`home_lambda`, `away_lambda`, `total_lambda`).
3. **Derived Markets**: Double Chance (`1x`, `x2`, `12`), Totals (`over_0_5` through `under_3_5`), BTTS, and Team Totals are consumed directly from `MatchIntelligence.derived_markets`.
4. **Correct Scores**: Consumed from `MatchIntelligence.correct_score.distribution` and `MatchIntelligence.correct_score.top_n`. The scoreline with highest mass is labeled *"Highest-probability scoreline"*, never *"Predicted score"*.
5. **Model Agreement**: Members (`elo`, `poisson`, `advanced`, `ensemble`) and statistical distribution parameters (`mean`, `std`, `min`, `max`, `range`) are extracted directly from `MatchIntelligence.model_disagreement`.
6. **Market Comparison**: Market consensus and divergence are mapped from `MatchIntelligence.market`. No betting recommendations, expected profits, or staking algorithms exist.

---

## 4. Server State Caching Strategy

TanStack Query (`@tanstack/react-query`) is configured with tiered stale times tailored to the data volatility:

- **Canonical Match Intelligence** (`/matches/:id/intelligence`):
  - `staleTime: 5 minutes`
  - Finished matches in the backend are cached indefinitely by SHA-256 content hash; the frontend query respects this immutability.
- **Match Explorer List** (`/matches`):
  - `staleTime: 30 seconds`
  - Refetches on filter adjustments with automatic request cancellation.
- **Provider & Source Health** (`/sources`, `/acquisition/status`):
  - `staleTime: 20–30 seconds`
- **Scheduler & Operations Dashboard** (`/jobs/dashboard`, `/jobs`):
  - `staleTime: 15 seconds`
- **Engine Readiness Probe** (`/ready`):
  - `staleTime: 15 seconds`

---

## 5. Error Shielding & Security Review

Backend errors are mapped to friendly presentation states by [`frontend/src/components/common/ErrorCard.tsx`](file:///Users/sivek/Documents/Bet%20Predictor/frontend/src/components/common/ErrorCard.tsx):
- `match_not_found` \(\to\) *"Match Not Found"*
- `prediction_unavailable` \(\to\) *"Prediction Unavailable: Insufficient historical sample"*
- `intelligence_unavailable` \(\to\) *"Match Intelligence Unavailable"*
- `provider_unavailable` \(\to\) *"Data Provider Unavailable"*
- `temporal_data_unavailable` \(\to\) *"Temporal Data Unavailable: Missing kickoff or cutoff"*

**Security Measures**:
- Raw database exceptions, psycopg2 traces, and Python file paths are stripped before rendering.
- MiroFish simulation narratives are rendered as escaped plain text (`whitespace-pre-wrap`), preventing XSS injection.
- Zero credentials or tokens are embedded into the client bundle, verified by automated regex auditing.
