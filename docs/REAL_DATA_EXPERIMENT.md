# Licensed real-data experiment checklist

This checklist supersedes the earlier Coinbase ML instructions below. Coinbase
Market Data Terms (August 7, 2026), section 3.5, require written consent for ML
use, including validation and benchmarking. Do not rerun that experiment.
The selected replacement is WSELOB-2017 under CC BY 4.0;
see [license and selection evidence](WSELOB_LICENSE.md). FI-2010 was the first
candidate but unresolved normalization and stock-boundary semantics prevent
using it for this economic-markout experiment.

Use this checklist before promoting any empirical result to the README or a resume.

## Data

- Use licensed snapshots with documented stock, trading day and event order.
- Keep original files under `data/raw/` and do not commit them.
- For FI-2010 use decimal-preserved book levels, with verified stock/day boundaries.
- Do not infer missing stock boundaries from price jumps.

## Features

Build features strictly from information known at each decision timestamp. Recommended first comparison:

1. spread only;
2. spread + top/depth imbalance;
3. + L1 OFI;
4. + microprice displacement;
Omit trade-flow/activity when causally aligned trade messages are unavailable.

## Labels

Evaluate 10, 20 and 50 observation-event midpoint markouts, separately within
each stock/day. Never describe event horizons as seconds. Keep future columns
out of feature construction.

## Models

The generic entry point is:

```bash
python scripts/run_real_experiment.py --input data/processed/licensed_snapshots.parquet \
  --license-manifest data/processed/license_manifest.json \
  --out results/licensed_benchmark --horizons 10 20 50 --cost-bps 1 --random-seed 7
```

Input requires `symbol`, ISO `day` (YYYY-MM-DD), increasing `event_index` within
stock/day, and `bid_px_1..10`, `ask_px_1..10`, `bid_sz_1..10`, `ask_sz_1..10`.
Prices and sizes must preserve economically meaningful within-book ratios.
The license manifest requires `dataset`, `source_url`, `license`, `attribution`,
`boundary_evidence`, and true values for `ml_use_permitted` and
`aggregate_publication_permitted`. It records verified permission, not a license
grant. Stock/day identities must come from source documentation.

An optional `segment` field separates interruptions within a stock/day. Message
indices must be consecutive within each segment; features and labels never
cross segment boundaries. For the fixed WSELOB input:

```bash
pip install -e '.[dev,ml,data]'
python -m cloblab.wselob --input data/raw/wselob/PEKAO_lob_2017_zlib.h5 \
  --out data/processed/wselob
python scripts/run_real_experiment.py --input data/processed/wselob/snapshots.parquet \
  --license-manifest data/processed/wselob/license_manifest.json \
  --out results/wselob_pekao --horizons 10 20 50 --cost-bps 1 --random-seed 7
```

Run the existing linear baseline and `run_tree_baseline` with identical chronological folds and cost assumptions. Keep the shuffled-label control for each model family.

## Minimum report

For each model/horizon report:

- OOS Spearman IC;
- direction accuracy;
- cost coverage;
- mean signed markout after the stated simple cost threshold;
- negative-control values;
- number and time span of held-out observations.

Assign prediction quantiles within each held-out fold before aggregation, and
preserve fold counts. Also export feature ablation and per-day metrics. Report
the number of days as well as rows: overlapping labels are dependent and row
counts do not establish IID statistical significance. Avoid p-value claims.
Signed markout after an assumed cost threshold remains a midpoint diagnostic,
not realized execution or strategy PnL.

## Claim gate

A result is resume-ready only if it is produced from real captured data, out of sample, leakage-checked, and clearly labeled with the exact metric/horizon. Do not convert a midpoint-markout diagnostic into a realized-PnL or live-alpha claim.
