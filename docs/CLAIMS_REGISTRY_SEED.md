# Verified Claims Registry — Application Packaging Seed

Purpose: provide one conservative source of truth for recruiter-facing README edits, resume bullets, cover letters, and interview preparation. Every numeric claim must remain traceable to committed aggregate artifacts/reports. Do not upgrade any claim beyond the wording below without new independent evidence.

## Approved quantitative claims

### Scale / data engineering

- Processed **85,846,918** licensed order messages from WSELOB-2017.
- Retained **56,887,949** ten-level causal feature rows.
- Produced **1,250** stock/day partitions.
- Covered **five equities** and all **250 available 2017 source days per stock** in the engineering preparation.
- The application benchmark completed **152/152 preregistered tasks** with no missing real-data tasks.

Primary evidence: `docs/XGBOOST_SCALE_ENGINEERING_REPORT.md` and `results/wselob_xgboost_application_v1/`.

### Predictive research

Equal-weight stock/month held-out Spearman IC:

| Horizon | Linear | XGBoost | XGBoost - Linear |
|---:|---:|---:|---:|
| 10 messages | 0.228319 | 0.236688 | +0.008369 |
| 20 messages | 0.255193 | 0.261639 | +0.006446 |
| 50 messages | 0.252353 | 0.258527 | +0.006174 |

Paired stock/month block robustness:

- 10-message: XGBoost wins **20/20** paired blocks.
- 20-message: XGBoost wins **18/20** paired blocks.
- 50-message: XGBoost wins **18/20** paired blocks.
- Leave-one-stock and leave-one-month mean XGBoost-minus-Linear IC deltas remain positive at all three horizons.

Primary evidence: `docs/XGBOOST_SCALE_ENGINEERING_REPORT.md` and `docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md`.

### Engineering / systems

Measured on a fixed representative XGBoost workload:

- **17.26x** training-time improvement for accelerator vs CPU.
- **9.07x** end-to-end task-wall improvement for the same fixed comparison.
- **1.606x** throughput improvement from two independent accelerator workers vs serial paired-task execution.
- CPU/accelerator predictions remained numerically aligned: prediction Spearman **0.999242**, absolute IC drift **0.000084**.

Public claims should use the aggregate ratios only. Do not disclose private hostnames, hardware inventory, device IDs, scheduler details, or filesystem paths.

Primary evidence: `docs/XGBOOST_SCALE_ENGINEERING_REPORT.md`.

### Research-engineering capabilities that are directly supported

Safe capability phrases:

- deterministic order-level L2 reconstruction;
- causal order-book feature engineering (spread, top/depth imbalance, normalized L1 OFI, microprice displacement);
- chronological expanding-window evaluation;
- Linear / sklearn HistGradientBoosting / XGBoost comparison;
- shuffled-label negative controls;
- partitioned Parquet caching with Zstd;
- deterministic task IDs, artifact hashing, atomic writes, file locking, failed-task retry and resumable execution;
- execution-aware crossed-book diagnostics with fixed latency offsets;
- leave-one-stock-out transfer evaluation;
- CPU/GPU workload benchmarking and multi-worker scheduling.

## Execution-aware result: wording gate

The project **does not establish executable profitability**.

The fixed execution-aware robustness extension found that the primary crossed-book headline diagnostics were negative after paying the visible spread, and modest message-event latency worsened those outcomes.

Safe interview wording:

> The midpoint-ranking signal was robust, but it did not survive a deliberately conservative crossed-book execution test. That distinction was useful: it showed why predictive IC and tradable edge are not the same object.

Do not turn this into a positive PnL claim. Do not hide it if asked about execution realism.

Primary evidence: `docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md`.

## Prohibited / unsupported claims

Do **not** say any of the following:

- profitable strategy / positive trading PnL;
- live-trading alpha;
- statistically significant edge unless the exact statement is supported by a valid analysis (current block bootstrap is descriptive, not formal significance);
- HFT production system;
- realistic queue-position or passive-fill simulator;
- market impact model;
- low-latency production trading engine;
- universal cross-market generalization;
- modern US-equity or crypto profitability;
- XGBoost is universally better than Linear or HistGB;
- billions of observations;
- full distributed cluster / Dask / Ray / Kubernetes system;
- any private compute hardware details in public materials.

## Preferred headline interpretation

The strongest defensible story is:

> Built a reproducible large-scale market-microstructure research pipeline over ~86M order messages / ~57M causal L2 rows, compared linear and boosted-tree models under frozen chronological holdouts and negative controls, measured a modest but robust XGBoost uplift in midpoint ranking, and then showed that the same predictive signal did not automatically translate into executable crossed-book returns.

This combines research, engineering, model judgment, and execution realism without overstating the result.
