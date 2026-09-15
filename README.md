# Market Microstructure Lab

A reproducible Level-2 (L2, depth-by-price) order-book research pipeline for short-horizon prediction, model comparison and execution-aware validation.

## At a glance

| Area | Measured result |
| --- | --- |
| Data scale | 85.8M licensed order messages → 56.9M causal L2 rows; five equities; 1,250 stock/day partitions |
| Research design | Frozen chronological holdouts; 10/20/50-message horizons; shuffled-label controls |
| Models | Linear, HistGradientBoosting and XGBoost, with matched comparison scopes |
| Held-out result | Modest XGBoost uplift over Linear at all three horizons; positive leave-one-stock/month mean differences |
| Engineering | Partitioned Parquet cache, deterministic task IDs, content hashes, atomic writes and resumable tasks |
| **Native engineering** | C++20/pybind11 backend with byte-exact Python parity across 85.8M messages and 604.8M virtual-order evaluations; 8.98× replay / 3.57× queue kernel speedups |
| Fixed-workload timing | 17.26× training / 9.07× end-to-end accelerator speedup; 1.606× two-worker throughput |
| Execution lesson | Predictive midpoint ranking did not yield positive crossed-book outcomes after spread and latency |

```text
licensed order messages → deterministic book replay → causal feature cache
  → chronological Linear / HistGB / XGBoost tasks → controls + paired robustness
  → spread / latency diagnostics → conditional passive-queue diagnostics
```

[Scientific + engineering report](docs/XGBOOST_SCALE_ENGINEERING_REPORT.md) · [Execution-aware robustness](docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md) · [C++20 parity and performance](docs/CXX20_REPLAY_QUEUE_REPORT.md)

## Held-out prediction result

IC means Spearman rank correlation between predictions and future midpoint changes. These are **equal-weight stock/month held-out** correlations over April, June, September and November 2017.

| Horizon | Linear IC | XGBoost IC | Paired XGBoost wins |
| --- | ---: | ---: | ---: |
| 10 messages | 0.228319 | 0.236688 | 20/20 |
| 20 messages | 0.255193 | 0.261639 | 18/20 |
| 50 messages | 0.252353 | 0.258527 | 18/20 |

The differences are modest. Leave-one-stock/month checks remain positive, but the block-bootstrap intervals are descriptive, not formal significance tests. HistGradientBoosting was evaluated on the matched June subset; these results do not establish a universal model winner.

![Paired held-out IC differences](results/wselob_execution_robustness_v1/paired_ic_delta.png)

XGBoost's midpoint-ranking uplift is broadly positive across the fixed stock/month blocks.

## Execution changes the interpretation

All 411 crossed-book cells reuse the original predictions. At zero delay, XGBoost's fixed 1 bp threshold-selected outcomes average **−5.00 / −5.36 / −7.07 bp** at 10/20/50 messages; 1- and 5-message delays worsen them. These are visible-quote diagnostics, not realized trading profit.

![Crossed-book prediction deciles](results/wselob_execution_robustness_v1/crossed_markout_deciles.png)

Paying the visible spread produces negative headline outcomes despite predictive midpoint rankings.

The completed [passive-queue study](docs/QUEUE_AWARE_EXECUTION_REPORT.md) adds 822 conditional execution cells. Stronger signal tails are harder to fill under the stated depletion scenario, and average five-message post-fill midpoint changes are adverse. Order deletions do not identify cancellation versus execution, so this is a **conditional diagnostic, not an exact historical fill simulator**. The separate 25-task held-out-stock transfer study retains comparable midpoint IC without overturning these execution limits.

## What this demonstrates

- Deterministic order replay and causal spread, imbalance, order-flow imbalance (OFI) and microprice features.
- Chronological model comparison with fixed parameters, negative controls and explicit task denominators.
- Restartable research over tens of millions of rows using hashes, caching and atomic artifacts.
- Measured fixed-workload CPU/accelerator comparisons, with numerical-drift checks.
- Research judgment about the difference between predictive ranking and executable returns.

## What this does not claim

- No live-trading, realized-profit or formal-significance claim.
- No identified exact passive fills, hidden-liquidity, inventory or market-impact model.
- A historical five-stock WSE sample, not universal cross-market evidence.

## Reproduce the software demo

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,ml,data,xgb]"
python -m pytest -q
cloblab demo --offline --out /tmp/microstructure-demo --rows 120
```

This quickstart runs a deterministic **synthetic** demo; it does not reproduce the 85.8M-message study. Licensed-file preparation, fixed experiment commands and receipt requirements are described in [reproducibility](docs/REPRODUCIBILITY.md) and the linked research reports. Raw data and row-level predictions are not committed.

## Data and scope

Source: [Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1](https://data.mendeley.com/datasets/3g4mhdp899/1), DOI 10.17632/3g4mhdp899.1, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Modifications: order replay, causal features, model evaluation and aggregate execution diagnostics. As-is; no warranty or endorsement.

The full-source engineering preparation covers all 250 available days per stock. The fixed scientific cache contains 1,235 stock/day partitions through December 24; 15 later partitions complete engineering coverage only. All 152 original scientific tasks completed without missing tasks or month substitutions.

The Coinbase adapter is retained for engineering demonstrations only. Its captures are not the empirical ML benchmark; see [data terms](docs/DATA_TERMS.md). The earlier single-stock study remains under [methodology](docs/METHODOLOGY.md).

See [public contribution and privacy policy](CONTRIBUTING.md). Further scientific work requires new data or a materially new preregistered question, rather than tuning these inspected holdouts.
