# Phase 14 — Dataset Comparison (Phase 12 vs Phase 14)

| Dimension | Phase 12 | Phase 14 |
|---|---|---|
| Matches | 3,272 | 16,639 (+13,367) |
| EPL seasons | 2015, 2022–2024 | 2015–2024 contiguous |
| LA_LIGA seasons | 2015, 2023 | 2015–2023 contiguous |
| Other leagues | 2023 only | 2015–2023 |
| Research dataset (EPL) | research_ds_c544a413d044 (preserved) | team-family research_ds_4d82b61d92db; full-family versions per experiment (old intact) |
| Team-feature coverage (EPL test) | ~100% | ~98% |
| xG population (EPL test) | 182 | 182 (same source, wider train history) |
| Shots population | partial | full post-warmup |
| Strict temporal rule | unknown excluded | unchanged |
| Baseline EPL 2024 | 0.5237 / 0.9905 / 0.5913 | reproduced exactly |

Old dataset versions remain accessible (artifacts + builder determinism);
new versions never overwrite old ones.
