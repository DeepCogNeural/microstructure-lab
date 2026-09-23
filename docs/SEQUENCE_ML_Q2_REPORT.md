# Q2 retrospective five-arm comparison

Protocol: `configs/sequence_ml_v1.json` and `docs/SEQUENCE_ML_PROTOCOL.md`, frozen before fitting. Scientific runner commit: `1f26e52d1d6ee09939de2f243f4f30a5b042d230`. Source: WSELOB-2017 V1, CC BY 4.0; the cached manifest SHA-256 and per-partition feature hashes are bound in `results/sequence_ml_v1/q2_summary.json` and five per-stock receipts. All 2017 outcomes had prior research exposure. These are retrospective/exploratory comparisons, not new independent confirmation.

## Data and model selection

All five stocks completed, with **20,000 selected Jan–Mar training endpoints per stock** (100,000 stock/endpoints total, not independent dates). The shared April dev set has **18 shared dates × 5 stocks = 90 stock/day cells**, 210,290 scored rows per arm. June/September/November have **63 shared dates × 5 stocks = 315 cells**, 625,118 scored rows per arm. Every declared cell had defined Spearman IC; no failure was dropped. Same 32-state eligible endpoints, original h20 labels, and original-index stride-20 scoring were used across arms. No raw row predictions or model weights are published.

April selected B1 historical XGBoost over B0 historical Ridge: equal-stock/date mean IC **0.267537 vs 0.253370**. On historical evaluation dates:

| Arm | Mean stock/day IC |
| --- | ---: |
| A0 current Ridge | 0.257563 |
| A1 current XGBoost | 0.248309 |
| B0 history Ridge | 0.252810 |
| B1 history XGBoost (B*) | 0.267719 |
| S0 GRU seed 7 | 0.272845 |
| S0 GRU seed 17 | 0.274811 |
| S0 GRU seed 29 | 0.273829 |

History helps the boosted-tree arm under this fixed budget, while history Ridge trails current Ridge. The current XGBoost arm also trails current Ridge. These negative comparisons remain in the full receipts. The GRU seed-mean minus B* paired difference is **+0.006110 IC**; paired five-trading-day within-month block bootstrap 95% interval **[+0.005099, +0.007378]**, with 3-day sensitivity **[+0.004902, +0.007345]** and 10-day sensitivity **[+0.005610, +0.007089]**. These intervals describe date variation for the fitted historical models; they are not an independent-final confidence statement. The three seed-specific paired means are +0.005126, +0.007092, +0.006110, all positive.

The seed-mean month differences versus B* are June **+0.008086**, September **+0.003682**, November **+0.006561**. Stock differences are KGHM +0.006691, PEKAO +0.005890, PKNORLEN +0.007525, PKOBP +0.011233 and **PZU −0.000791**. Removing any one stock leaves a positive aggregate mean, but the PZU negative result limits any across-stock generalization. These dates and stocks are not new market samples.

## Training and cost

Five per-stock runs took **400.41 seconds total wall time** on the local CPU, with four configured compute threads per run; actual CPU core-hours were not measured and must not be inferred by multiplying wall time by four. There were **0 GPU-hours**. Aggregate fit time across five stocks was 0.036 s current Ridge, 0.689 s current XGBoost, 0.095 s historical Ridge, 3.190 s historical XGBoost, and 98.57/116.01/103.90 s for GRU seeds 7/17/29. These are model-fit times, distinct from data loading, inference and total run wall time. Per-model inference time, model SHA-256, per-seed learning curves and peak process RSS are retained in the five aggregate JSON receipts.

The KGHM GRU seeds 17 and 29 reached the protocol's 15-epoch cap with their best dev MSE at the last epoch; their receipts flag `training_limited=true`. Other seed/stock tasks stopped with earlier best epochs. This prevents a blanket claim that GRU optimization was adequate in all stocks. A single **post-fit pipeline diagnostic** permuted PEKAO B1 training labels within each training day at seed 7, without selecting a model or threshold; its mean day IC was −0.000234 on April dev and −0.019308 on historical evaluation dates. This negative control is retained as observed, not forced to zero or treated as a complete leakage proof. A prior local import of XGBoost failed because its OpenMP dynamic library was not found; the run used the already bundled PyTorch `libomp.dylib` through a process-local library path. No scientific result was produced by that failed import. No protocol threshold, horizon, feature set or model grid was changed in response to outcomes.

## Verdict and continuation

The fixed retrospective data show a GRU advantage over the dev-selected equally informed boosted-tree baseline, with a PZU exception and two KGHM capped training curves. The magnitude exceeds the *planning* ΔIC 0.005 in this exposed sample; **`PREDICTIVE_GAIN_CONFIRMED` is unavailable without Q5-qualified new data**. The cost difference is large under local CPU conditions. Q3 must keep B* and S0 only, inspect the planned temporal/state/execution questions on paired opportunities, and preserve the KGHM training limitation. Q4's Transformer gate is not decided until Q3; a positive historical IC alone cannot trigger it.
