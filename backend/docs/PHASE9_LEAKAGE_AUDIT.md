# Phase 9 — Leakage Audit

## Rule

Every feature must answer: "could this value have been known immediately
before the target match kickoff?" Cutoff = target kickoff. Target match
contributes zero. Unknown effective_at is never assumed available.

## Per-family audit

| Family | Source | Cutoff rule | effective_at rule | Target exclusion | Future exclusion | Strict | Estimated | Limits |
|---|---|---|---|---|---|---|---|---|
| Appearances | lineups/statsbomb | parent kickoff < cutoff, FINISHED only | required; NULL → excluded | structural (match id) | kickoff ≥ cutoff excluded | unavailable (all NULL) | parent-anchored, labeled estimated | minutes absent; side via match |
| Player events | match_events/statsbomb | as above | as above | structural | as above | unavailable | estimated; side-attributed; name-equality within side | no provider IDs on events; unresolved unattributed |
| Player form | derived | chronological windows 3/5/10 | inherits inputs | inherits | inherits | unavailable | estimated; gates ≥3 apps | per-appearance (no per-90) |
| Team aggregates | derived | as above | as above | as above | as above | unavailable | estimated; regulars ≥3 apps | staleness exposed, not capped |
| Lineup continuity | lineups | as above | as above | as above | as above | unavailable | estimated | formation ~60% present |
| Formation | lineups | as above | as above | as above | as above | unavailable | estimated, descriptive only | no causal claims |
| Memberships | lineups | kickoff-ordered ranges | estimated anchor | n/a (spans) | valid_from > cutoff excluded | none built | built, labeled | last-seen ≠ contract end |
| xG | unchanged | Phase 5 rule | unknown → strict-excluded | unchanged | unchanged | excluded | parent-anchored only | partial coverage |

## Adversarial tests (all passing in tests/test_phase9.py)

- Target poisoning (own lineup + goal rows on target): output hash unchanged;
  repository excluded_target counts the rows.
- Future injection (match + rows 16 days after cutoff, post-match
  "corrections"): snapshot hash byte-identical before/after.
- Cutoff equality (match kicking off exactly at cutoff): excluded
  (strict `<` boundary).
- Unknown timing: strict excludes, estimated admits with label.
- Strict suite on real data: 0/250 sides available (no silent upgrades).

## Known limitations

- Name-equality event attribution within a side (no event provider IDs);
  same-name teammates would collide (documented, unobserved in dataset).
- Stale-but-valid rows allowed (staleness exposed via
  roster_staleness_days, up to ~9.6y on 2024 targets).
- Opponent events never attribute (side filter, tested).
