# Methodology

The benchmark asks one narrow question: given only information available at a
decision timestamp, how does the future midpoint move over fixed horizons?

## Features

The MVP features are intentionally simple:

- `spread_bps`: current best ask minus best bid, divided by midpoint.
- `top_imbalance`: best-level bid size minus ask size, divided by total top
  size.
- `depth_imbalance`: same imbalance over the first N displayed levels.
- `recent_trade_imbalance`: past-window buy/sell trade-size imbalance.

These are microstructure diagnostics, not a claim of alpha.

## Labels

For each feature row and horizon, the label builder finds the first midpoint
timestamp at or after `local_ts + horizon`. It records:

- `future_ts_{horizon}s`
- `future_midprice_{horizon}s`
- `markout_{horizon}s`
- `markout_bps_{horizon}s`
- `direction_{horizon}s`

Future midpoint columns are labels only. They are not available to the feature
builder.

## Evaluation

The default baseline uses anchored walk-forward splits:

- train on older rows;
- purge training rows whose future label timestamp reaches the test window;
- test on the next block of newer rows;
- never train on or after the test period.

Reported metrics:

- IC: Spearman correlation between prediction and realized markout.
- Direction accuracy: sign agreement for non-zero markouts.
- Bucketed average markout: average realized markout by prediction bucket.
- Cost coverage: share of predictions whose absolute value clears the chosen
  cost threshold.
- Negative control: same model with shuffled training labels.

## Cost Stress

`visible_depth_cost_sweep.csv` estimates the cost of crossing displayed depth.
It uses visible L2 levels only. It does not model hidden liquidity, passive
fills, queue priority, maker rebates, cancellations, latency races, or realized
PnL.
