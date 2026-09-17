# Phase 9 — Final Report: Player, Lineup & Event Intelligence Activation

## Architecture

canonical data → player/event/lineup repository (cutoff-gated, target
excluded) → player features (appearances, form, events) → team aggregation
(with contributors) → quality + availability gating → versioned snapshot
(player_features_v1, hashed, deterministic) → future experiments. Prediction
engine untouched; no new model; ensemble_v1 mathematics unchanged.

## Schema

Additive tables only: player_feature_snapshots (payload + hash + provenance),
player_team_memberships (validity ranges), player_feature_provenance
(per-feature source/IDs/quality). No historical row mutated.

## Player coverage

1690/1690 lineup provider IDs resolve to canonical players; 1130/1135 event
names and 1689/1695 lineup names intersect canonical players. Unresolved IDs
stay in their own lane (counted, never merged). Same-name cross-team merges
refused; transfers yield two membership rows.

## Event coverage

Registered (statsbomb, defined): goals, penalties_scored, own_goals,
yellow_cards, red_cards, substitute_appearances. NOT registered (no reliable
equivalent): shots, assists, passes, tackles, pressures, recoveries, carries,
minutes_played. Assists: 0 rows — unavailable, not zero.

## Lineup coverage

794 matches (EPL/LA_LIGA 2015 full seasons + Bundesliga 34); formation
present ~60%; is_starting splits starters/subs; all effective_at NULL.

## Strict coverage

0/250 sampled sides available across 5 leagues (unknown timing honestly
excluded). Estimated: EPL 36/50, LA_LIGA 42/50, Bundesliga 38/50 (low
quality, thin history), SERIE_A/LIGUE_1 0/50 (no data).

## Estimated coverage

See above. Every estimated value labeled; staleness exposed
(roster_staleness_days up to ~9.6y on 2024 targets reusing 2015 rows —
valid but stale, never capped silently).

## Feature missingness

Minutes: entirely absent (appearances used, per-appearance rates, no per-90).
Form gates: <3 apps → unavailable with reason. Team aggregates: no regulars
→ unavailable. Unavailable ≠ zero everywhere.

## Quality distribution

Estimated snapshots: mostly medium (temporal estimated caps the label);
components preserved (identity/source/definition high where resolved).
Strict snapshots: unavailable + reason.

## Real-data validation

5 leagues sampled (25 matches each, both modes, 27s). Example: Arsenal vs
Norwich Apr 2016 — 26/28 regulars, Sánchez/Giroud 12 goals each,
4231 vs 4411, continuity 0.53/0.47. CLI labels AVAILABLE/UNAVAILABLE/
ESTIMATED/UNKNOWN explicitly.

## Offline experiment

experimental_ensemble_player_v0 (continuity-differential logistic weight,
train-before-test, isolated script, no production writes): LA_LIGA train
159/test 393 weight 0.0 (no signal); EPL train 180/test 686 weight −0.3,
test dBrier +0.00021 CI [−0.0009, +0.0014] (null, immaterial). Features
available for evaluation; NOT activated. No promotion mechanism exists.

## Leakage audit

See PHASE9_LEAKAGE_AUDIT.md. Adversarial future/target injection leaves
output hashes byte-identical (tested). Cutoff equality excludes.
Side-attribution prevents opponent leakage.

## Prediction regression

See PHASE9_REGRESSION_REPORT.md. changed = 0 (9/9 like-for-like identical;
1 fitted-variant skip explained).

## Tests

Previous: 332. New: 18. Total: 350. Passed: 350. Failed: 0. Skipped: 0.

## Performance

Snapshot generation ~0.2s uncached (25× optimized from 5s via indexed
event fetch + batched identity resolution, hash-identical output);
persist-dedup by hash; API read-only.

## Security

No secrets in logs/payloads (grep-audited); provider keys stay in provider
constructors; API validates match/mode/cutoff; batch league queries bounded
(--limit); no raw SQL (ORM only).

## Limitations

- Strict mode yields nothing on this dataset (effective_at NULL everywhere).
- No minutes, assists, shots, defensive actions in source schema.
- Event attribution by within-side name equality (no event provider IDs).
- SERIE_A/LIGUE_1 have no player data at all.
- Stale-but-valid rows surface (flagged, not filtered).
- Current-season fixtures unavailable (unchanged).

## Commit

Phase 9 commit (see git log).

## Status: READY

READY requires temporal validity, reproducibility, provenance, and an
unaltered production engine — all evidenced above. No model was changed,
no promotion path was built, and every absence is labeled rather than filled.
