# Changelog

## 0.2.0

- Added optional polars engine (`cloblab.polars_cache`, `cloblab cache-summary --engine {pandas,polars}`) for feature-cache partition summaries, with pandas as the default reference and parity tests on a synthetic multi-partition fixture; no scientific definitions or results changed.
- Added `docs/TECH_STACK.md`; removed the unused `duckdb` dependency.

Dates are given where the linked documents record them.

- WSELOB-2017 five-stock study: 85.8M order messages from five 2017 Warsaw Stock Exchange equities replayed into ten-level books; Linear/XGBoost midpoint forecasts over four fixed months (HistGradientBoosting on June only) ([report](docs/XGBOOST_SCALE_ENGINEERING_REPORT.md)).
- Execution-aware robustness: paired block evidence, spread/latency cells and stock-transfer tasks ([report](docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md)).
- Queue-aware passive diagnostics: 822 conditional virtual-order cells with identification limits ([report](docs/QUEUE_AWARE_EXECUTION_REPORT.md)).
- C++20/pybind11 replay and queue kernels with byte-exact Python parity, completed 2026-09-14 ([report](docs/CXX20_REPLAY_QUEUE_REPORT.md)).
- Preregistered later-period check on December 27–29, 2017, protocol dated 2026-09-21 ([report](docs/LATER_PARTITIONS_CONFIRMATION_REPORT.md)).
- Post-inspection signal and execution research audit, 2026-09-22 ([report](docs/SIGNAL_EXECUTION_DIAGNOSTICS_REPORT.md)).
- Formal retrospective sequence-ML package (FQ2–FQ4, Q8, Q10, Q11), FQ2 dated 2026-09-23 ([package](docs/SEQUENCE_ML_FINAL_PACKAGE.md)).
- Computational-environment record and README "Read this first" summary ([environment](docs/COMPUTATIONAL_ENVIRONMENT.md)).

## 0.1.0

- Added offline deterministic market-microstructure demo.
- Added publicly accessible Coinbase Exchange JSONL collector.
- Added aggregate L2 replay with sequence-gap, crossed-book, and stable-hash
  checks.
- Added no-lookahead features, markout labels, label-time-purged walk-forward
  baseline, negative control, and visible-depth cost sweep.
- Added public documentation for architecture, methodology, data model,
  reproducibility, data terms, and limitations.
