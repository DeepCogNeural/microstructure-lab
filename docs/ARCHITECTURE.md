# Architecture

The current research path keeps scientific definitions separate from execution placement and public aggregate reporting.

```text
licensed WSE order messages
  → order-level replay + valid ten-level snapshots
  → causal features / exact-message labels
  → immutable symbol/day Parquet partitions
  → fixed chronological model tasks
  → private predictions + hashed completion receipts
  → paired / crossed-book / transfer / conditional queue diagnostics
  → denominator-checked public tables and figures
```

## Main components

- `cloblab.wselob`: order-event replay and valid book segments.
- `cloblab.scale_cache`: compressed feature partitions and source/content manifests.
- `cloblab.scientific_identity`: scientific settings and input identity, excluding runtime device/path settings.
- `cloblab.scale_runner`: fixed task expansion, fitting, locks, atomic artifacts, resume/retry and complete aggregation.
- `cloblab.execution_labels` and `cloblab.robustness`: exact crossed quotes and paired block summaries.
- `cloblab.transfer`: held-out-stock training chronology.
- `cloblab.queue_book`, `passive_execution` and `queue_metrics`: visible order queues and conditional passive diagnostics.
- `scripts/run_*` and `scripts/render_*`: bounded research entrypoints and aggregate-only figures.

A completed task is reused only when its artifacts and identity match. Missing or conflicting tasks prevent complete aggregation. Raw files, predictions and compute metadata stay outside public Git; small aggregate artifacts retain the full planned denominator. The system uses local processes and partitioned files, not Dask/Ray or a production trading cluster.

## Engineering-only scaffold

`collectors` and `coinbase_normalize` support feed capture and normalization; `book` supports aggregate L2 replay. `features`, `labels`, `splits`, `evaluation`, `costs` and `cli` support the synthetic demo and clock-time research scaffold. Coinbase captures are not used for the licensed ML benchmark.

There is no live order-entry system, account integration or production execution claim. The Python queue engine is a reference diagnostic; no C++ acceleration result is claimed.
