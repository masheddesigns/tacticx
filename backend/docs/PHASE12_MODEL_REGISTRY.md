# Phase 12 — Model Registry (measured 2026-09-18)

Registered research candidates (status research unless noted).
Promotion requires an explicit human decision; none performed in Phase 12.

| model_id | version | test | N | Brier | ΔBrier vs ensemble_v1 [95% CI] | verdict |
|---|---|---|---|---|---|---|
| logreg_team@EPL | research_v1 | EPL 2024 | 375 | 0.6085 | −0.0180 [−0.0339, −0.0029] | degradation |
| logreg_team_xg@EPL | research_v1 | EPL 2024 | 182 | 0.5590 | +0.0019 [−0.0253, +0.0288] | inconclusive |
| logreg_team_player@EPL | research_v1 | EPL 2024 | 182 | 0.5573 | +0.0036 [−0.0209, +0.0272] | inconclusive |
| logreg_all@EPL | research_v1 | EPL 2024 | 182 | 0.5632 | −0.0023 [−0.0338, +0.0299] | inconclusive |
| logreg_team@LA_LIGA | research_v1 | 2023 H2 | 183 | 0.5813 | +0.0176 [−0.0173, +0.0514] | inconclusive |
| logreg_team@SERIE_A | research_v1 | folds | 120 | 0.6600 | −0.0263 [−0.0898, +0.0315] | inconclusive |
| logreg_team@BUNDESLIGA | research_v1 | folds | 70 | 0.5992 | +0.0073 [−0.0324, +0.0494] | inconclusive |
| logreg_team@LIGUE_1 | research_v1 | folds | 70 | 0.6872 | −0.0198 [−0.0610, +0.0241] | inconclusive |
| baseline_elo@EPL | elo_v1 | EPL 2024 | 380 | 0.5979 | −0.0067 [−0.0201, +0.0069] | inconclusive |
| baseline_poisson@EPL | poisson_v1 | EPL 2024 | 375 | 0.6089 | −0.0183 [−0.0315, −0.0047] | degradation |

Primary hypothesis (logreg_team, EPL): degradation — retained ensemble_v1.
Exploratory: 0 improvements, 2 degradations, rest inconclusive.
Tested candidates this phase: 10. Automatic promotion: none exists.
