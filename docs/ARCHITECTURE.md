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

The optional C++20/pybind11 batch backend in cloblab.native and cpp/ implements replay and conditional queue transitions, releasing the GIL during native loops. It has byte-exact parity across 85.8M messages and 604.8M virtual-order evaluations, with measured 8.98× replay and 3.57× queue kernel speedups. See the [native report](CXX20_REPLAY_QUEUE_REPORT.md) for timing scope and build instructions.

## Optional polars engine for cache scans

`cloblab.polars_cache` summarizes the immutable `symbol=*/day=*/features.parquet` partitions: per partition it reports total rows, rows whose five primary features are all finite, and the max/mean absolute error of the identity `microprice_minus_mid_bps = 0.5 × spread_bps × top_imbalance` on those rows. This is the per-partition algebra check from `cloblab.research_diagnostics`, extracted as a standalone function.

- The pandas engine is the default reference. It reads each partition with `pd.read_parquet` in a Python loop, like the other cache readers.
- The optional polars engine builds one lazy query over all selected partitions with `pl.scan_parquet` and collects it once. Only the seven needed columns are read (projection pushdown), each file is cast to an explicit schema before concatenation, and the aggregation runs in the multi-threaded engine. This fits a cache of many small columnar files.
- Both engines take partitions from the manifest, check `features_sha256` when present, raise `FileNotFoundError` for a missing partition and keep an empty partition as a zero-row result, so no partition leaves the denominator.
- `tests/test_polars_cache.py` builds a multi-partition fixture from the synthetic order book and the cache feature definition, injects non-finite features and an empty partition, and requires identical integer counts and `np.allclose` floats from both engines.

Run it with `cloblab cache-summary --root <cache> --engine {pandas,polars}`. The engine choice does not change any feature, label, model or reported result.

## Engineering-only scaffold

`collectors` and `coinbase_normalize` support feed capture and normalization; `book` supports aggregate L2 replay. `features`, `labels`, `splits`, `evaluation`, `costs` and `cli` support the synthetic demo and clock-time research scaffold. Coinbase captures are not used for the licensed ML benchmark.

There is no live order-entry system, account integration or production execution claim. Python remains the default reference.
