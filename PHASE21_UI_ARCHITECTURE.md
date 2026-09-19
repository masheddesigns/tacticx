# TacticX Phase 21 — UI Architecture Documentation

## 1. Overview & Principles

TacticX Phase 21 introduces an independently deployable, production-quality user interface (`/frontend`) providing transparent, auditable access to the canonical football intelligence engine and operational scheduler.

The design philosophy adheres to that of a **deterministic sports analytics and probability intelligence platform**, explicitly rejecting sportsbook, gambling, or casino design patterns.

### Core Architectural Axioms
1. **Zero Client-Side Recalculation**: All 1X2 probabilities, expected goal rates (\(\lambda\)), derived market distributions, correct score distributions, uncertainty metrics, and divergence statistics are authored solely by the backend engine. The frontend serves strictly as an auditable presentation layer.
2. **Absolute Data Honesty**: Where fixture data is unavailable—such as the 2026/27 current campaign having 0 validated Level-A fixtures—the UI clearly and prominently communicates this state ("Current-season fixture source unavailable") rather than synthesizing or mocking data.
3. **No Betting Terminology**: The UI never uses terminology such as "lock", "sure bet", "safe", "guaranteed", "value bet", "stake", or "ROI". Model outputs are neutrally designated as "Model probability" and "Model-estimated expected goals".
4. **MiroFish Simulation Isolation**: MiroFish scenario outputs are explicitly labeled "SIMULATED SCENARIO EVIDENCE" and visually separated from statistical models, preventing qualitative hypotheses from masquerading as mathematical predictions.
5. **No Secret Leakage**: Zero backend API keys, credentials, or internal connection strings exist in client bundles or environment configurations.

---

## 2. Technology Stack

- **Core Framework**: React 18.3 (`react`, `react-dom`)
- **Language**: TypeScript 5.6 (strict mode enabled)
- **Build Tooling & Dev Server**: Vite 5.4 with HTTP proxying to backend (`/api/v1`)
- **Routing**: React Router DOM 6.27 (declarative client-side routing)
- **Server State & Caching**: TanStack React Query 5.59 (declarative caching, background refetching, deduping)
- **Design System & Styling**: Tailwind CSS 3.4 with custom dark analytical palette (slate/zinc neutrals, emerald accents)
- **Iconography**: Lucide React
- **Testing**: Vitest 2.1 + React Testing Library 16.0 + jsdom

---

## 3. Directory Structure

```
frontend/
├── dist/                      # Production build output
├── public/                    # Static public assets
├── src/
│   ├── api/
│   │   ├── client.ts          # Centralized typed fetch client with normalized error codes
│   │   ├── queries.ts         # TanStack Query custom hooks with fine-grained TTLs
│   │   └── types.ts           # Canonical TypeScript interfaces matching Pydantic backend models
│   ├── components/
│   │   ├── common/
│   │   │   ├── Badge.tsx      # Semantic status and severity badges
│   │   │   ├── ErrorCard.tsx  # Error boundary display without leaking stack traces
│   │   │   └── LoadingSpinner.tsx
│   │   ├── dashboard/
│   │   │   ├── CompetitionCards.tsx   # Per-league fixture coverage summary
│   │   │   └── CurrentSeasonBanner.tsx # Honest zero-fixture notice for 2026/27
│   │   ├── intelligence/
│   │   │   ├── CorrectScoreGrid.tsx    # Discrete scoreline heatmap + ranked table
│   │   │   ├── CorePredictionCard.tsx  # 1X2 model probability display
│   │   │   ├── DataQualitySection.tsx  # Feature completeness & temporal audits
│   │   │   ├── DerivedMarketsCard.tsx  # Double chance, Over/Under, BTTS, team totals
│   │   │   ├── ExpectedGoalsCard.tsx   # Poisson lambda scoring intensities
│   │   │   ├── ExplanationSection.tsx  # Backend factor breakdown
│   │   │   ├── HistoricalAnaloguesCard.tsx # Euclidean similarity matches + disclosure
│   │   │   ├── MarketComparisonCard.tsx # Model vs bookmaker consensus divergence
│   │   │   ├── MatchHeader.tsx         # Hero match header with teams & cutoff
│   │   │   ├── MiroFishSection.tsx     # Qualitative simulation evidence
│   │   │   ├── ModelAgreementTable.tsx # Elo vs Poisson vs Ensemble comparison
│   │   │   ├── ProbabilityBar.tsx      # 1X2 horizontal probability visual
│   │   │   ├── ProvenanceSection.tsx   # Hash audit panel + Copy JSON
│   │   │   ├── ScenarioAnalysisCard.tsx # Interactive lambda perturbation
│   │   │   └── WarningsSection.tsx     # Backend audit codes & evidence
│   │   ├── layout/
│   │   │   ├── Footer.tsx              # Disclaimer and build metadata
│   │   │   └── Navbar.tsx              # Responsive navigation & engine readiness indicator
│   │   └── matches/
│   │       ├── MatchFilters.tsx        # Filter controls for Explorer
│   │       └── MatchRow.tsx            # Lightweight match row with intelligence link
│   ├── lib/
│   │   └── utils.ts           # Percentage formatting, date/time UTC formatters, clipboard
│   ├── pages/
│   │   ├── DashboardPage.tsx          # Route: /
│   │   ├── MatchExplorerPage.tsx      # Route: /matches
│   │   ├── MatchIntelligencePage.tsx  # Route: /matches/:matchId
│   │   ├── OperationsPage.tsx         # Route: /operations
│   │   └── SystemStatusPage.tsx       # Route: /system
│   ├── test/
│   │   ├── apiClient.test.ts          # Network, error normalization & cancellation tests
│   │   ├── dashboardAndExplorer.test.tsx # Honesty & filtering tests
│   │   ├── fixture.ts / mockMatchIntelligence.json # Canonical mock data
│   │   ├── intelligenceComponents.test.tsx # Component fidelity & integrity tests
│   │   └── setup.ts                   # Testing library setup
│   ├── App.tsx                        # Application shell and route provider
│   ├── index.css                      # Tailwind stylesheet & custom scrollbars
│   ├── main.tsx                       # React DOM root entrypoint
│   └── vite-env.d.ts                  # Vite client type references
├── index.html
├── package.json
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

---

## 4. Routes & Screen Breakdown

### Route 1: Dashboard (`/`)
- **Purpose**: System landing page communicating live engine status.
- **Components**:
  - System readiness indicator (Database connection, Redis cache probe).
  - High-level KPIs: Total fixtures, current-season coverage (0), registered sources, active jobs.
  - Mandatory Current-Season Fixture Banner: Highlights that no Level-A source supplies 2026/27 fixtures.
  - Competition Cards: Breakdowns for EPL, La Liga, Serie A, Bundesliga, and Ligue 1.
  - Upcoming and Recent Fixtures carousels.

### Route 2: Match Explorer (`/matches`)
- **Purpose**: High-density searchable and filterable match browser.
- **Components**:
  - Filter controls: Competition code, status (FINISHED, SCHEDULED, LIVE, PRE_MATCH), date (UTC), team name.
  - Match Row: Displays Home vs Away, score, status, kickoff date/time (UTC), intelligence availability badge, and navigation action.
  - Pagination Controls: Supports configurable `page_size` and page navigation.

### Route 3: Canonical Match Intelligence (`/matches/:matchId`)
- **Purpose**: Primary product screen showcasing the full `match_intelligence_v1` canonical document.
- **Section Progression**:
  1. Match Header: Competition, season, home/away names, kickoff timestamp, venue, ingested sources.
  2. Warnings: Prominent display of backend audit codes (`XG_UNAVAILABLE`, `CLOSING_ONLY`, etc.) with evidentiary attributes.
  3. Core Prediction & Probability Visualization: Home/Draw/Away model probabilities rendered as numbers and horizontal distribution bar.
  4. Expected Goals (\(\lambda\)): Continuous Poisson scoring rate intensities with visual meters.
  5. Derived Markets: Double Chance (1X, X2, 12), Over/Under totals (0.5 to 3.5), BTTS, and individual team totals.
  6. Correct Score Heatmap & Rankings: 4x4 matrix distribution, top scorelines ranking, required 16-score mass, and tail mass. Highest value labeled "Highest-probability scoreline".
  7. Uncertainty Diagnostics: Predictive entropy, margin, sample completeness, temporal audit classification.
  8. Model Agreement Matrix: Unranked comparison across Elo, Poisson, Advanced, and Ensemble models with mean, standard deviation, and range.
  9. Market Comparison: Divergence between statistical models and bookmaker consensus; closing odds preserved as benchmark-only.
  10. Scenario Sensitivity Analysis: Interactive parameter selector testing mathematical elasticity (Home/Away/Both \(\lambda \pm 10\%\)) while preserving baseline.
  11. Historical Analogues: Pre-cutoff finished matches with Euclidean similarity distance and methodology disclosure.
  12. MiroFish Simulation: Qualitative agentic evidence; displays "MiroFish provider is not configured" when unconfigured, or structured narrative when available.
  13. Explanation: Objective model factor statements (Elo, scoring rates, xG availability, form).
  14. Data Quality & Temporal Quality: Strict/estimated/unknown timestamps and feature family completeness.
  15. Cryptographic Provenance: Collapsible panel displaying model/feature/dataset versions, request/response hashes, and one-click Copy JSON.

### Route 4: System & Sources (`/system`)
- **Purpose**: Real-time provider qualification, health, and freshness monitoring.
- **Components**:
  - Core engine readiness probe.
  - Provider registry cards (API-Football, The-Odds-API, StatsBomb, Football-Data.co.uk) showing tier, qualification status, health state, consecutive failures, and remaining quota.
  - Recent ingestion run logs from the acquisition pipeline.

### Route 5: Job Operations (`/operations`)
- **Purpose**: Scheduler telemetry, execution audit, and operational safety.
- **Components**:
  - Scheduler lock monitor (active vs stale locks) with safe stale-lock cleanup mutation.
  - Active operational alerts and anomaly detection monitors.
  - Execution log audit table filtering by job status and type.

---

## 5. Responsive Design & Priority Order

The interface is engineered with a mobile-first responsive layout that adapts gracefully without horizontal scrollbars.

### Mobile Priority Hierarchy
On small viewports (mobile), components stack according to analytical priority:
1. Match Header (Hero)
2. 1X2 Model Probabilities & Visual Bar
3. Expected Goals (\(\lambda\)) Estimates
4. Key Derived Probabilities (Double Chance, Totals)
5. Uncertainty & Entropy Diagnostics
6. Market Comparison & Divergence
7. Scenario Sensitivity Analysis
8. Historical Analogues
9. MiroFish Simulated Evidence
10. Explanation, Data Quality, and Provenance

---

## 6. Accessibility (a11y) Standards

- **Semantic Headings**: Full `<h1>` through `<h3>` hierarchy across all pages.
- **ARIA Attributes**: Progress bars declare `role="progressbar"`, `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, and descriptive `aria-label`s. Error cards declare `role="alert"`.
- **Non-Color Indicators**: Every outcome probability segment is accompanied by text labels, percentage numbers, and exact floating-point readouts. Status badges pair icons with distinct labels.
- **Contrast**: Neutral surfaces (`#090d16`, `#111827`, `#1f293d`) exceed WCAG 2.1 AA contrast requirements against text (`#e2e8f0`, `#f8fafc`).
