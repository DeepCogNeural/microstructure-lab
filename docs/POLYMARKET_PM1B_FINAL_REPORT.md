# PM1B 15-second snapshot repricing — one-time final result

Status: **FINAL_SCORED_ONCE**. The frozen train/dev-fitted models and 15-second target protocol were used once on 120 final markets and 4,104 common opportunities (Aug 24 UTC, one partial date). Final target and fit-input hashes matched the public manifests; final markets did not overlap train/dev. No model was refit or selected using final values.

Primary metric is equal-market mean squared error (probability points²); lower is better. Market bootstrap used 5,000 paired resamples, conditional on the single final date.

| Frozen arm | Final equal-market MSE | Delta versus B0 (95% market CI) |
|---|---:|---:|
| B0 zero repricing | 0.01018973 | reference |
| B1 current XGBoost | 0.01105769 | +0.00086796 [+0.00000777, +0.00181051] |
| B2 history XGBoost | 0.01042236 | +0.00023263 [-0.00037003, +0.00077971] |
| B3 GRU seed 7 | 0.01014746 | -0.00004226 [-0.00018741, +0.00008329] |
| B3 GRU seed 17 | 0.01023078 | +0.00004105 [-0.00016848, +0.00022330] |
| B3 GRU seed 29 | 0.01019127 | +0.00000154 [-0.00019506, +0.00015294] |
| B3 three-seed prediction mean | 0.01017392 | -0.00001581 [-0.00018632, +0.00012459] |

B3 mean minus B2 was -0.00024844, 95% CI [-0.00076645, +0.00025191]. The predeclared dev preference for B3 over B2 did **not** establish a final improvement: this interval crosses zero. B3 mean minus the simpler zero-change B0 was -0.00001581, CI [-0.00018632, +0.00012459]; this also crosses zero. B1 was worse than B0 with a positive interval. B2 was worse in point estimate, with an interval crossing zero. All negative and null comparisons are retained.

Private target SHA-256: `6759f649c565f170af684bad677b46c5dbb3a4d89a1a534754b1fca8b17e2057`; final result SHA-256: `330678f2b976e49fc5304ae81ea5b27376791b725be02fddc26ac6aa90426376`. The public final build manifest reports 120 eligible markets/4,104 opportunities and future-book exclusions; no row arrays, predictions, model weights, or per-market scores are published.

This is sparse sampled-book **snapshot repricing**, not terminal-outcome information, exact fills, realized PnL, or independent confirmation of WSELOB. Aug 24 is one partial UTC date. The market bootstrap cannot establish date durability; capture availability determines valid future-book coverage. PM1A terminal results and PM1B repricing must remain separate. Contract-length and coin splits are descriptive only. No résumé/PDF claim follows from this result.
