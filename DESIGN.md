# DESIGN.md — TacticX (FotMob Match Intelligence)

## 1. Visual Philosophy & North Star
TacticX is a **high-density, dark-first football & betting intelligence terminal** inspired by FotMob and institutional sports-analytics dashboards.

- **Clarity over decoration:** Every surface, border, and color carries semantic meaning (live status, model confidence, market edge, or data provenance).
- **Scannable hierarchy:** Team names, scores, kickoff times, and probabilities must be readable at a glance without competing gradients, glassmorphism, or decorative animations.
- **Data-first restraint:** Avoid generic "AI slop" (purple-to-blue gradients, nested cards-inside-cards, low-contrast gray-on-dark text, or perpetual pulsing badges).

---

## 2. Color System & Semantic Tokens

Use the Tailwind theme tokens defined in `frontend/tailwind.config.js` rather than raw hex values or ad-hoc `slate-*` / `emerald-*` utilities.

### Surfaces & Borders
| Role | Token / Class | Hex | Usage |
|---|---|---|---|
| **Canvas Base** | `bg-surface-base` / `bg-fotmob-bg` | `#0e1015` | Page background, sticky header backdrop |
| **Primary Card** | `bg-surface-card` / `bg-fotmob-card` | `#161922` | Match groups, intelligence cards, filter bars |
| **Elevated / Nested** | `bg-surface-cardMuted` / `bg-fotmob-cardLight` | `#1e222e` | Active tabs, hover rows, secondary chips, inputs |
| **Subtle Border** | `border-surface-border` / `border-fotmob-border` | `#242938` | Card outlines, section dividers, table rules |
| **Hover Border** | `border-surface-borderLight` | `#32394d` | Interactive card/button hover states |

### Brand & Semantic Accents
| Role | Token / Class | Hex | Usage |
|---|---|---|---|
| **Primary Accent** | `text-fotmob-green` / `bg-brand-500` | `#21e786` | Active nav/tabs, primary CTA, positive edge, healthy status |
| **Accent Hover** | `bg-fotmob-greenHover` | `#1cd378` | Primary button hover |
| **Live / Danger** | `text-fotmob-red` | `#ff4b4b` | Live in-play status, negative delta, errors |
| **Warning / AI** | `text-fotmob-amber` | `#f59e0b` | Degraded status, qualitative AI / MiroFish highlights |
| **Info / Neutral** | `text-fotmob-blue` | `#3b82f6` | Informational badges, neutral comparison metrics |
| **Muted Text** | `text-fotmob-textMuted` | `#94a3b8` | Secondary labels, timestamps, metadata |

> **Rule:** Never introduce uncalibrated accent colors (e.g., `purple-400`, `emerald-600`, `slate-900`) when a `surface-*` or `fotmob-*` token exists.

---

## 3. Typography & Numeric Alignment

Defined in `frontend/src/index.css` and `frontend/tailwind.config.js`:

- **Display & UI Sans:** `Plus Jakarta Sans` (`font-sans`)
  - Page titles (`h1`): `text-2xl font-extrabold tracking-tight text-white`
  - Section headers (`h2`/`h3`): `text-sm` to `text-base font-bold text-white`
  - Body / labels: `text-xs` to `text-sm text-slate-100` / `text-fotmob-textMuted`
- **Data, Odds & Telemetry:** `Roboto Mono` (`font-mono`)
  - Always pair `font-mono` with **`tabular-nums`** on scores, kickoff times, probabilities, xG values, odds, and KPI counters so columns align vertically and do not jitter during 10-second live polling.

---

## 4. Layout, Spacing & Component Grammar

- **Container:** `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`
- **Vertical Rhythm:** `py-6 space-y-6` (detail pages) or `space-y-8` (dashboard)
- **Border Radius:**
  - Primary cards & panels: `rounded-2xl`
  - Inputs, buttons, nav items: `rounded-lg` or `rounded-xl`
  - Status pills / count badges: `rounded-md` or `rounded-full`
- **Interactive States:**
  - Keep transitions crisp (`transition-colors` / `transition-all duration-150`).
  - Use subtle border shifts (`hover:border-surface-borderLight` or `hover:border-fotmob-green/50`) instead of heavy drop shadows or scale-up jumps.

---

## 5. Motion & Animation Rules

- **Functional motion only:** Use CSS/Tailwind transitions for tabs, drawers, modals, and live-data updates.
- **No competing perpetual animations:** At most one subtle live indicator (e.g., a steady or slow-pulsing dot on the **Live In-Play** badge when `liveCount > 0`). Do not stack `animate-ping` and `animate-pulse` in the same header bar.
- **Avoid heavy JS animation engines** (GSAP / Anime.js) for standard UI; reserve SVG/path animation strictly for custom tactical pitch visualizations if needed.

---

## 6. Anti-Patterns to Flag During UI Reviews
1. Mixing raw hex literals (`#161922`, `#242938`), `slate-900`/`emerald-600`, and `surface-*`/`fotmob-*` tokens in the same component.
2. Numeric columns or live counters missing `tabular-nums`.
3. Duplicate domain constants (e.g., `LEAGUE_PRIORITY` defined in multiple pages instead of one shared helper).
4. Unreadable low-contrast text below `#94a3b8` (`slate-400`) on `#161922` / `#1e222e` surfaces.
