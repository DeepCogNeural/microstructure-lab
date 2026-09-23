# PM1A public prediction-market terminal calibration pilot

Date: 2026-09-23. Source: pinned PolyOrderbooks Zenodo v1.0.1, version DOI 10.5281/zenodo.22084977, CC BY 4.0. PM0 fixed data identity, validity rules and whole-market UTC split. The full PM1A model/feature/score code and dev result were pushed at scientific commit `e1c0e1c2c23b7ba21ba95430c53f62bf69a1d7ac` **before** the final block was opened. The final was scored once with unchanged fitted models and hyperparameters. A later secondary calibration pass recomputed identical primary scores and did not alter the models.

## Exact scope

Train: 405 eligible markets and 16,947 opportunities; dev: 236 and 8,749; final: **122 and 4,621**. All splits use disjoint whole markets. The final covers only the first half of 2026-08-24 UTC within a sampled four-day source. Each opportunity is one Up-token decision on a close-anchored 30-second grid, with a valid causal book and eight-state recent history. Market-equal fitting weights and equal-market score means prevent 4-hour markets' denser snapshots from dominating the headline. Outcomes are terminal; current market midpoint probability P0 is always the reference.

## Final result

| Frozen arm | Final market-mean log loss ↓ | Final market-mean Brier ↓ | Paired log-loss difference vs P0 ↓ |
| --- | ---: | ---: | ---: |
| P0 raw midpoint | 0.495170 | 0.165157 | reference |
| P1 calibrated midpoint/time | **0.488214** | **0.162378** | −0.006955 [market-bootstrap 95%: −0.023161,+0.008625] |
| P2 current-state XGBoost | 0.514803 | 0.172271 | +0.019633 [−0.007413,+0.046225] |
| P3 same-history XGBoost | 0.503169 | 0.167131 | +0.007999 [−0.019118,+0.035320] |
| P4 GRU seed 7 | 0.500293 | 0.165917 | see aggregate |
| P4 GRU seed 17 | 0.505676 | 0.168176 | see aggregate |
| P4 GRU seed 29 | 0.498407 | 0.165491 | see aggregate |
| P4 three-seed probability mean | 0.499466 | 0.165640 | +0.004297 [−0.016237,+0.026458] |

The primary P4 seed-mean minus P3 same-information paired difference was **−0.003702 log loss**, market-bootstrap 95% interval **[−0.023146,+0.014673]**; 61 markets favored P4 and 61 favored P3. This does not establish a sequence-architecture gain. P4 was also worse than raw price P0 in final point estimate. P1 simple calibration had the best point estimate, but its interval versus P0 crossed zero, and it improved 59 of 122 markets while worsening 63. On dev, raw P0 had beaten all fitted arms. The current-state P2 and history P3 did not improve on raw price in the final point estimate. Every null, simple-baseline win and negative result is retained.

## Secondary calibration and interpretation

The prespecified secondary file `results/polymarket_pm1a_v1/final_calibration.json` gives 10-bin market-weighted reliability tables, ECE, and descriptive final calibration slopes/intercepts for every arm. P0 slope/intercept were 1.116/+0.089 and P1 were 1.153/−0.073; market-weighted ECE was 0.0395 for P0 and 0.0344 for P1. These are descriptive fits on the final block, not new calibrated predictors. ECE can rank arms differently from proper log loss and is not used for model selection. Private per-market scores and row predictions are retained outside Git; public results show market-level counts, paired uncertainty and all arm aggregates.

The final contains one partial UTC date, so market bootstrap intervals describe within-date market variation and cannot test date transfer. The dataset's sampled market coverage, sparse changed-book collector snapshots and short date span limit external validity. PM1A is an external-domain method pilot, not independent confirmation of the WSELOB equity result. It supports no claim of tradable edge, passive fills, or realized P&L. The strongest defensible finding is that extra L2 state/history and the GRU failed to show stable incremental terminal information beyond the market price in this narrow public sample.

Machine results and source hashes are inventoried in `results/polymarket_pm1a_v1/publication_manifest.json`. Raw public-source Parquet, private train/dev/final arrays, model weights, per-market scores and row predictions are excluded from Git. No résumé/PDF edits follow automatically.
