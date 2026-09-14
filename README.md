# Market Microstructure Lab

A research pipeline for short-horizon price prediction from limit-order-book data. The project emphasizes deterministic book reconstruction, causal feature construction, chronological out-of-sample evaluation, negative controls, reproducible experiment artifacts, and explicit limits on trading claims.

## Full-Year Five-Stock Benchmark

Using the CC BY 4.0 WSELOB-2017 dataset, the pipeline reconstructed **85,846,918 order messages** into **56,887,949 causal Level-2 feature rows** across five equities and 1,250 stock/day partitions.

The fixed experiment completed **152/152 preregistered tasks** with no missing real-data tasks or month substitutions. Linear and XGBoost use the same five features, horizons, and expanding monthly holdouts; XGBoost parameters were fixed before final-test inspection.

| Message horizon | Linear IC | XGBoost IC |
|---:|---:|---:|
| 10 | 0.2283 | **0.2367** |
| 20 | 0.2552 | **0.2616** |
| 50 | 0.2524 | **0.2585** |

The headline metric is equal-weight stock/month held-out Spearman IC across April, June, September, and November 2017. XGBoost modestly improves the point estimate at all three horizons; this is **not** a statistical-significance claim.

Matched June results show no universal model winner:

| Horizon | Linear | HistGB | XGBoost |
|---:|---:|---:|---:|
| 10 | 0.2357 | 0.2403 | **0.2422** |
| 20 | 0.2636 | 0.2673 | **0.2684** |
| 50 | 0.2595 | **0.2638** | 0.2635 |

Seed-7 shuffled-label XGBoost controls average **0.012 / 0.034 / 0.044 IC** at 10/20/50 messages, substantially below the primary results. Overlapping labels are dependent, so row counts are not treated as IID evidence.

[Scientific and engineering report](docs/XGBOOST_SCALE_ENGINEERING_REPORT.md) · [aggregate results](results/wselob_xgboost_application_v1)

## What the Model Uses

The primary feature set is deliberately small and interpretable:

- spread in basis points;
- top-of-book imbalance;
- ten-level depth imbalance;
- normalized Level-1 order-flow imbalance (OFI);
- microprice displacement from midpoint.

Across the primary XGBoost fits, normalized gain is dominated by top imbalance (~48–50%) and microprice displacement (~25–30%), with OFI providing additional information. Feature importance is descriptive, not causal attribution.

## Research Engineering

The project is designed so the experiment is reproducible rather than notebook-specific:

```text
licensed order messages
  -> deterministic L2 replay
  -> causal feature/label partitions by symbol/day
  -> immutable Parquet cache + hashes
  -> preregistered chronological tasks
  -> Linear / HistGB / XGBoost / shuffled controls
  -> resumable atomic artifacts
  -> denominator-checked aggregation
```

Implemented safeguards include deterministic task IDs, source/config/cache hashes, atomic writes, completed-task resume, explicit retry after failure, duplicate detection, and aggregation against the original task manifest.

A fixed CPU-versus-accelerator XGBoost comparison measured **17.26× faster training** and **9.07× faster end-to-end task execution**, while predictions remained numerically consistent (Spearman 0.99924; absolute IC drift 0.000084). A two-worker comparison improved independent-task throughput by **1.61×**. Only aggregate performance ratios are public; private infrastructure details are intentionally excluded.

## Earlier Ten-Day Benchmark

The earlier PEKAO-only benchmark remains as a smaller reproducibility check: 336,602 snapshots over ten trading days with nine strictly later-day test folds.

| Horizon | Linear IC | HistGB IC | Shuffled linear IC | Shuffled HistGB IC |
|---:|---:|---:|---:|---:|
| 10 | 0.2361 | 0.2312 | -0.0251 | -0.0104 |
| 20 | 0.2712 | 0.2584 | -0.0087 | -0.0024 |
| 50 | 0.2758 | 0.2606 | -0.0497 | -0.0422 |

The larger five-stock benchmark supersedes this as the main application result.

## Quickstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,ml,data,xgb]"
python -m pytest -q
cloblab demo --offline --out data/sample --rows 120
```

The offline demo is deterministic and synthetic. It validates the software path; it is not empirical alpha evidence.

## Licensed Data

WSELOB-2017 attribution:

> Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1, CC BY 4.0.

Raw licensed files are not committed. Public aggregates are derived research artifacts with attribution.

The repository also contains a Coinbase feed adapter for data-engineering demonstrations. Coinbase's Market Data Terms currently restrict AI/ML use without permission, so Coinbase captures are **not** used as empirical ML evidence in this project.

## Current Limits

The headline results rank **future midpoint moves**. They are not realized PnL and do not model:

- bid/ask crossing at entry and exit;
- passive queue position or fill probability;
- hidden liquidity;
- fees or rebates;
- latency before entry;
- inventory limits or market impact.

The next research priority is therefore **execution-aware robustness**, not adding more model libraries. See [Next Research Roadmap](docs/NEXT_RESEARCH_ROADMAP.md).

## Documentation

- [Scientific and engineering report](docs/XGBOOST_SCALE_ENGINEERING_REPORT.md)
- [Next research roadmap](docs/NEXT_RESEARCH_ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Methodology](docs/METHODOLOGY.md)
- [Data sources](docs/DATA_SOURCES.md)
- [Data terms](docs/DATA_TERMS.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Limitations](docs/LIMITATIONS.md)
- [WSELOB license evidence](docs/WSELOB_LICENSE.md)
- [Public contribution/privacy policy](CONTRIBUTING.md)

## Public Repository Policy

Do not commit hostnames, cluster/server names, hardware inventories, device UUIDs, scheduler job IDs, absolute home paths, environment dumps, credentials, or other private infrastructure metadata. Public engineering evidence should be limited to code, scientific configuration, aggregate results, and infrastructure-neutral performance summaries.
