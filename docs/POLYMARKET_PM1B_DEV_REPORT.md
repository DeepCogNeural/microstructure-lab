# PM1B train/dev repricing result — final target closed

Status: **DEV_ONLY_FINAL_CLOSED**. This is the separately frozen 15-second snapshot Up-midpoint repricing task. PM1A v1 terminal-outcome results remain separate, and this task is not an independent confirmation of WSELOB. The PolyOrderbooks v1.0.1 source, chronological whole-market split, PM1A decision opportunities and PM1B future-book validity/horizon are pinned in PM0/PM1B manifests. Train contained 392 markets/12,479 opportunities, dev 234/7,476; the private arrays matched their public SHA-256 manifests before fitting. PM1B final repricing values have not been built or viewed.

The pre-fit model config `configs/polymarket_pm1b_model_v1.json` (SHA-256 `9a1c1f23e1d6bdf3552606370ae860930c9cbf16dd2cad8c02ecdf1e6e881bca`) froze zero-change B0, current-state XGBoost B1, same-eight-book-history XGBoost B2, and same-history GRU B3 seeds 7/17/29. No model or horizon search used dev repricing values; April-style chronological dev market-equal MSE selected only GRU checkpoints. All arms used the same 7,476 dev opportunities and market weighting.

| Dev model | Equal-market MSE, probability points² |
|---|---:|
| B0 zero repricing | 0.01106069 |
| B1 current-state XGBoost | 0.01171174 |
| B2 same-history XGBoost | 0.01147291 |
| B3 GRU seed 7 | 0.01100201 |
| B3 GRU seed 17 | 0.01105701 |
| B3 GRU seed 29 | 0.01109084 |
| B3 three-seed prediction mean | 0.01103605 |

Primary B3 mean minus B2 paired market MSE was **−0.00043686**, 5,000-draw market-bootstrap 95% interval **[−0.00083516, −0.00006048]**; 143/234 markets favored B3 and 91 favored B2. B3 met the pre-frozen 1% relative dev improvement threshold versus B2. The simple zero-change baseline nonetheless beat both XGBoost arms: B2−B0 was **+0.00041222**, interval **[+0.00001880, +0.00083281]**, and B1−B0 **+0.00065105**, interval **[+0.00018026, +0.00113617]**. B3 mean−B0 was only **−0.00002464**, interval **[−0.00009294, +0.00004310]**. These negative/ambiguous simple-baseline comparisons are part of the main decision, not hidden by the B3−B2 contrast.

GRU seeds ran 10/14/12 epochs, best dev checkpoints 2/6/4; none hit the 60-epoch training-limit criterion. The complete model fit/dev run took 5.19 seconds local CPU process wall and 0 GPU-hours; peak process RSS was 510,885,888 bytes. Extraction wall time and CPU core-hours were not instrumented. Two targeted PM1B scoring/time-identity tests passed; model SHA-256 values and learning curves are in `results/polymarket_pm1b_v1/dev_result.json`. Private target arrays, predictions, fitted models and per-market scores stay outside Git.

The dev date is Aug 23 UTC only. Contract-length strata (5m/15m/4h) are descriptive and not selection strata. The market bootstrap conditions on this one date; it cannot establish durability. Sparse collector snapshots select which opportunities have valid future books, so coverage remains part of interpretation. Dev preference does not authorize a model-gain or trading claim. The frozen final scoring code must be pushed alongside this dev report and fitted-model hashes before the single final target build/read; all arms and seeds must be reported on final regardless of sign.
