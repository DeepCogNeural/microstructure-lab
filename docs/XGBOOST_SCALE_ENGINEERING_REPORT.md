# WSELOB application benchmark: scientific and engineering results

## Scope

This benchmark asks whether causal limit-order-book features rank short-horizon future midpoint moves out of sample, and whether the research workflow remains reproducible at full-year scale.

The frozen scientific experiment uses:

- five WSE equities from WSELOB-2017;
- five causal features: spread, top imbalance, depth imbalance, normalized L1 OFI, and microprice displacement;
- 10/20/50-message horizons;
- expanding monthly training windows with at least 40 strictly earlier trading days;
- fixed test months: April, June, September, and November 2017;
- Linear and XGBoost on all stock/month/horizon blocks;
- HistGradientBoosting on the matched June subset;
- within-training-day shuffled-label controls;
- no hyperparameter search or outcome-based exclusions.

Horizons are message counts, not seconds. Labels remain within uninterrupted stock/day/book segments.

## Scientific results

All **152/152 preregistered tasks** completed with no missing tasks, failed real-data tasks, or month substitutions.

### Equal-weight stock/month Spearman IC

| Horizon (messages) | Linear | XGBoost |
|---:|---:|---:|
| 10 | 0.228319 | **0.236688** |
| 20 | 0.255193 | **0.261639** |
| 50 | 0.252353 | **0.258527** |

XGBoost modestly exceeds Linear at all three horizons in these point estimates. This is not a significance claim.

### Matched June comparison

| Horizon | Linear | HistGB | XGBoost |
|---:|---:|---:|---:|
| 10 | 0.235724 | 0.240338 | **0.242180** |
| 20 | 0.263589 | 0.267323 | **0.268427** |
| 50 | 0.259510 | **0.263819** | 0.263545 |

The experiment does not establish a universal XGBoost advantage. The main conclusion is that nonlinear tree models add modest incremental predictive value over a strong linear microstructure baseline.

### Cross-stock 20-message results

Four fixed test months are averaged equally within each stock.

| Stock | Linear IC | XGBoost IC |
|---|---:|---:|
| KGHM | 0.269627 | **0.275594** |
| PEKAO | 0.254365 | **0.262476** |
| PKNORLEN | 0.282781 | **0.293281** |
| PKOBP | 0.250009 | **0.252760** |
| PZU | 0.219183 | **0.224085** |

The XGBoost point estimate is higher for all five stocks at the 20-message horizon, and the completed [paired stock/month robustness study](EXECUTION_AWARE_ROBUSTNESS_REPORT.md) reports descriptive uncertainty without inferring significance from row count.

## Negative controls

Seed-7 shuffled-label XGBoost controls average IC:

- 10 messages: **0.011982**
- 20 messages: **0.034216**
- 50 messages: **0.044124**

An extra PEKAO June/20 check gave:

| Shuffle seed | IC |
|---:|---:|
| 7 | 0.010898 |
| 17 | -0.004559 |
| 29 | 0.052781 |

These are sanity controls, not an IID sampling distribution. Overlapping message-horizon labels are dependent, so row counts are not used for p-values.

## Feature importance

Normalized XGBoost gain, averaged across the 20 primary stock/month fits at each horizon, is dominated by top-of-book imbalance and microprice displacement.

Approximate ranges across 10/20/50-message horizons:

- top imbalance: **47.8%–49.5%**;
- microprice displacement: **25.3%–30.0%**;
- normalized OFI: **13.3%–15.5%**;
- spread: **4.9%–6.4%**;
- depth imbalance: **3.2%–4.1%**.

Under shuffled labels, importance becomes much flatter, which is a useful sanity comparison but not causal attribution.

## Coverage

The full-year data preparation covered:

- **85,846,918** licensed order messages;
- **56,887,949** retained ten-level causal feature rows;
- **1,250** stock/day partitions;
- five equities across all 250 available 2017 source days per stock.

The fixed scientific experiment uses the preregistered date range through December 24. The final source days through December 29 were prepared only to verify full-source engineering coverage and were not used to change scientific tasks.

## Research engineering

The workflow is designed to make large historical experiments repeatable rather than notebook-specific.

Implemented components include:

- deterministic order-level L2 reconstruction;
- immutable `symbol/day` Parquet feature partitions with Zstd compression;
- source, code, config, cache, and artifact hashing;
- deterministic task IDs;
- atomic result writes and file locks;
- explicit failed-task retry;
- completed-task resume with artifact validation;
- cross-run duplicate detection;
- aggregation against the preregistered task denominator;
- separate row-level local artifacts and small public aggregate artifacts.

The bounded benchmark measured a **17.26× training-time improvement** and **9.07× end-to-end task-wall improvement** for one fixed XGBoost CPU-versus-accelerator comparison. Predictions remained numerically consistent (Spearman 0.999242; absolute IC drift 0.000084). Two independent accelerator workers improved paired-task throughput by **1.606×** relative to serial execution.

Only aggregate performance ratios are public. Private hostnames, hardware inventory, device identifiers, scheduler details, environment dumps, and filesystem locations are intentionally excluded.

## Interpretation limits

The benchmark predicts future midpoint moves. It does **not** establish realized trading PnL.

In particular, the current headline does not model:

- crossing the bid/ask at both entry and exit;
- queue position or passive fill probability;
- hidden liquidity;
- fees and rebates;
- latency before entry;
- inventory constraints;
- market impact.

The subsequent [execution-aware robustness study](EXECUTION_AWARE_ROBUSTNESS_REPORT.md) and [conditional queue study](QUEUE_AWARE_EXECUTION_REPORT.md) are complete. The exclusions above describe this original midpoint benchmark, not a list of unstarted work. See the [completed roadmap](NEXT_RESEARCH_ROADMAP.md).

## Reproduction

WSELOB-2017 attribution:

> Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1, CC BY 4.0.

The public experiment definition is in `configs/wselob_xgboost_application_v1.json`. Private infrastructure-only orchestration fields were removed from that public config after the completed run; dataset, feature, model, split, horizon, and negative-control settings are preserved. Therefore the public JSON digest intentionally differs from the archived run digest recorded in the result manifests.

Representative commands:

```bash
python scripts/remote/download_sources.py configs/wselob_sources_v1.json data/raw
python -m cloblab.scale_cache \
  --config configs/wselob_xgboost_application_v1.json \
  --sources configs/wselob_sources_v1.json \
  --raw data/raw --out data/cache --workers 4

python -m cloblab.scale_runner \
  --config configs/wselob_xgboost_application_v1.json \
  --cache data/cache --out runs/scientific --plan-only
```

Raw licensed files, row-level feature caches, predictions, model binaries, private infrastructure metadata, and large runtime logs are not committed.

## Public artifacts

Scientific aggregates are under `results/wselob_xgboost_application_v1/`, including:

- `model_metrics_overall.csv`;
- `model_metrics_by_symbol.csv`;
- `model_metrics_by_symbol_month.csv`;
- `model_metrics_common_month.csv`;
- `negative_control_summary.csv`;
- `prediction_deciles.csv`;
- `xgboost_feature_importance_summary.csv`;
- `preparation_summary.json`;
- `performance_summary.json`;
- `run_manifest.json`.

Public repository policy forbids committing private compute infrastructure or personally identifying execution metadata; see `CONTRIBUTING.md`.
