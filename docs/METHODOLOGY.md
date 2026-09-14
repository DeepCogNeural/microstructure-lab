# Methodology

The benchmark asks one narrow question: given only information available at a decision timestamp, how does the future midpoint move over fixed horizons?

## Features

The base features are intentionally interpretable:

- `spread_bps`: current best ask minus best bid, divided by midpoint.
- `top_imbalance`: best-level bid size minus ask size, divided by total top size.
- `depth_imbalance`: the same imbalance over the first N displayed levels.
- `recent_trade_imbalance`: past-window buy/sell trade-size imbalance.

The extended microstructure set adds:

- `microprice_minus_mid_bps`: queue-size-weighted microprice displacement from midpoint;
- `ofi_l1`: event-style Level-1 order-flow imbalance from current and lagged top-of-book states;
- `ofi_l1_norm`: OFI normalized by current displayed top-level size;
- rolling signed trade-flow imbalance;
- rolling trade/event intensity.

All rolling features are backward-looking. No future midpoint, future book state, or future trade is available to the feature builder.

## Labels

For each feature row and horizon, the label builder finds the first midpoint timestamp at or after `local_ts + horizon`. It records:

- `future_ts_{horizon}s`
- `future_midprice_{horizon}s`
- `markout_{horizon}s`
- `markout_bps_{horizon}s`
- `direction_{horizon}s`

Future midpoint columns are labels only. They are not available to feature construction.

## Evaluation

The default evaluation uses anchored walk-forward splits:

- train on older rows;
- purge training rows whose future label timestamp reaches the test window;
- test on the next block of newer rows;
- never train on or after the test period.

Two model families are supported:

1. a standardized linear/ridge baseline for interpretability and sanity checking;
2. a histogram gradient-boosted tree baseline for nonlinear interactions.

The tree model is not allowed different data, features, or chronology than the linear model. Model comparisons should use the same horizon, folds, cost assumption, and test observations.

Reported metrics:

- IC: Spearman correlation between prediction and realized markout;
- direction accuracy: sign agreement for non-zero markouts;
- bucketed average markout: realized markout by prediction bucket;
- cost coverage: share of predictions whose absolute value clears the chosen cost threshold;
- mean signed markout after the simple cost threshold;
- shuffled-label negative control using the same model family.

## Signal Diagnostics

A real-data experiment should include at least two diagnostics beyond aggregate metrics:

### Prediction monotonicity

Rank out-of-sample predictions into quantiles and report realized future markout by quantile. A useful signal should show economically coherent ordering rather than a result driven by a few observations.

### Feature ablation

Add feature groups sequentially, for example:

1. spread;
2. + book imbalance;
3. + OFI;
4. + microprice displacement;
5. + trade-flow/activity.

This identifies where incremental predictive information actually enters the model.

## Cost Stress

`visible_depth_cost_sweep.csv` estimates the cost of crossing displayed depth. It uses visible L2 levels only. It does not model hidden liquidity, passive fills, queue priority, maker rebates, cancellations, latency races, or realized PnL.

Cost-aware markout metrics are therefore screening diagnostics rather than a claim of executable strategy PnL.

## Real-Data Reporting Rule

The committed deterministic sample is synthetic. No empirical market-performance number should be added to the README or resume until the experiment has been run on real captured data with the chronology, purging, and controls above. Raw venue data remain local; only provider-compliant derived results should be published.
