# Phase 15 — Intelligence Schema

Canonical response (`intelligence_v2.service.build_intelligence`):

- prediction: {home, draw, away} — production 1X2, sum validated = 1.
- goals: {home_lambda, away_lambda, total_lambda}.
- markets: totals (O/U 0.5–3.5, over+under = 1), btts (yes+no = 1, joint +
  closed-form consistent), double_chance (1X/X2/12 identities),
  team_totals, correct_scores (top_n + required-16 mass + tail mass),
  goal_distributions (marginals + joint + grid/tail mass), validation.
- score_distribution: full joint grid (≈1 with required-16 + tail = 1).
- uncertainty: predictive_entropy (nats, documented), top_probability,
  probability_margin = max − second_max, model_disagreement ref,
  data_completeness — descriptive, never correctness odds.
- model_disagreement: per-outcome mean/std/min/max/range + member
  statuses; labeled descriptive signal.
- data_quality: feature counts, strict flag, estimated fields, xG/event/
  lineup/market availability.
- market_comparison: market context (pre-cutoff consensus only) +
  interpretation (small/moderate/large from configurable thresholds,
  descriptive only).
- analogues: status, match list (id/distance/teams/result/vector/
  similarity), outcome distribution (descriptive), methodology.
- scenarios: baseline-first list with parameters, probabilities, goals,
  markets, top scores, difference_from_baseline; sensitivity labels.
- warnings: evidence-based codes (XG_UNAVAILABLE, PLAYER_DATA_UNAVAILABLE,
  TEMPORAL_QUALITY_UNKNOWN, MARKET_THIN, NO_MARKET, CLOSING_ONLY,
  HISTORICAL_DATA_SPARSE, MODEL_DISAGREEMENT_HIGH) with severity + detail.
- explanation: headline (probability stated, never certainty) + factors
  from actual inputs + Elo/Poisson/xG/feature blocks.
- core_prediction: untouched production output.
- provenance: match/cutoff/model/mode/versions/hash/snapshot_id.

No score is ever described as likely in absolute terms; divergences are
observations, never recommendations.
