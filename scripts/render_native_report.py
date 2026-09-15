"""Publish measured native engineering evidence from aggregate receipts only."""
from pathlib import Path
import json
import pandas as pd


def main():
    root=Path('results/cxx20_replay_queue_v1')
    parity=json.loads((root/'parity_summary.json').read_text())
    if not parity['complete'] or not parity['exact_bytes']:raise ValueError('full parity must pass before publication')
    table=pd.read_csv(root/'benchmark_summary.csv')
    lines=['| Workload | Backend | Units | Median kernel seconds | Units/s | Native speedup |',
           '| --- | --- | ---: | ---: | ---: | ---: |']
    for r in table.itertuples(index=False):
        lines.append(f'| {r.scope} | {r.backend} | {r.units:,} | {r.median_seconds:.3f} | {r.units_per_second:,.0f} | {r.native_speedup:.3f}× |')
    report=f'''# C++20 replay and queue engineering report

## Result and scope

The optional C++20/pybind11 backend passed exact value **and byte-hash parity** with the Python reference over **{parity['source_messages']:,} source messages in {parity['source_days']:,} stock/day partitions**, under both `retain` and `reset` priority interpretations. Queue parity covers **{parity['queue_days']} test-day partitions and {parity['queue_virtual_orders']:,} virtual-order evaluations**. Both sides are evaluated on every eligible row, covering all directions chosen by the frozen Linear/XGBoost/control predictions.

This is an engineering implementation result. It does not alter features, models, predictions, holdouts, latency offsets, queue assumptions or published scientific outcomes. Ambiguous WSELOB removals still prevent identified exact passive fills; positive conditional diagnostics are not trading profit.

## Architecture

```text
Python structured source records / existing decision indices
  → validated contiguous integer batch
  → C++20 order state / visible levels / ordered queues
  → compact event arrays and ten-level snapshots
  → C++20 conditional virtual-order paths
  → Python aggregation, statistics and figures
```

`cpp/replay_queue.cpp` owns the state machines; `cpp/bindings.cpp` exposes two batch functions. `src/cloblab/native.py` validates inputs and selects `python`, `native` or `auto`. The extension releases the Python GIL during native loops. There is no per-message Python/native call boundary, network code, model fitting, specialized hardware code or distributed framework.

Pandas, HDF5/Parquet preparation, features, model inference, bootstrap statistics, aggregate publication and plotting remain in Python. Moving those components would duplicate research logic without serving this track's replay/queue objective.

Input identities, timestamps, priority and quantity use 64-bit integers. Prices intentionally follow the reference's integer-to-double division rather than silently changing price semantics. Floating contraction is disabled; no fast-math flag is used. The full-domain byte check detects floating divergence as well as state differences.

## Parity methodology

Synthetic tests cover adds, retransmissions, omissions, price and quantity changes, resets, invalid updates, unpriced/crossed/shallow books, tied priority, both interpretations, queue depletion, later arrivals, conditional fills, expiry, latency, adverse/fill races, boundaries, fallback, malformed inputs, deterministic repeats and aggregate equality.

Every source day is replayed under both interpretations. Checked replay fields are the 16 event arrays, validity flags, segment IDs, live order counts, old/new priority timestamps, all ten bid/ask prices and sizes, and final ordered queues. Matching input identities plus identical old/new state traces also bind intermediate order changes; final queues verify deterministic ranking. Snapshot arrays include explicit NaNs for invalid states.

Across the full fixed April/June/September/November queue domain, both backends evaluate every eligible feature-row placement at 0/1/5-message latency, horizons 10/20/50 and both sides under both interpretations. All 16 existing passive-path outputs match: queue quantity/order count, placement price, fill/adverse times, three race indicators, four post-fill midpoint changes and four realized-spread diagnostics. These checks cover the current scientific outputs, not unmodeled actual exchange matching.

The original aggregate `wselob.reconstruct` supplies independent valid snapshot/index comparisons where a stored snapshot partition is unavailable. Consumed feature partitions are checked against the frozen manifest hashes; raw files are checked against depositor hashes. No model is retrained.

Exact means identical array values, dtypes, shapes and deterministic SHA256 byte encodings. Floating tolerance is **zero**. Each output must match before its timing can enter a published result; repeat-run hashes must agree. The aggregate [parity receipt](../results/cxx20_replay_queue_v1/parity_summary.json) retains complete denominators and combined checksums without row data or private execution metadata.

## Measured performance

'''+ '\n'.join(lines)+'''

Replay units are original messages. This benchmark covers all five licensed files and all 1,250 available source days, including engineering-only tail days; it does not change the scientific date cutoff. Timed replay uses `retain`; both interpretations are parity-checked.

Queue units are independent virtual orders. The fixed timing subset is all PEKAO June test days at the 20-message horizon, all three placement delays, both sides and both priority interpretations. Other horizons/stocks/months participate in full-domain correctness checks; they were not selected after seeing speedups.

Each timing uses three fixed passes with backend order alternated. Data are already resident; file reads, hash checks, garbage collection and report aggregation are outside both timed calls. Both replay timings include normalization, fresh state construction, output allocation and Python-boundary conversion. Both queue timings include the same wrapper and output schema. No backend alone receives an I/O exclusion.

The displayed seconds are the median of three **sums of per-day kernel wall times**, collected in bounded parallel day shards. They are not the elapsed time of a full parallel pipeline, and units/s must not be read as whole-machine aggregate throughput. Inputs and semantic work match within each pair. This is a measured workload comparison, not a speed guarantee on other systems. Peak memory was not isolated reliably across both backends; no comparative memory claim is made.

## Build and reproduce

A standard C++20 compiler and Python development headers are required. The normal Python install remains independent of the optional extension:

```bash
python -m pip install -e ".[dev,ml,data,xgb]"
python -m pytest -q
```

Build the optional extension into the source package:

```bash
python -m pip install -e ".[dev,ml,data,xgb,native]"
cmake -S cpp -B build/native \\
  -DPython_EXECUTABLE="$(command -v python)" \\
  -DCMAKE_BUILD_TYPE=Release \\
  -DCMAKE_LIBRARY_OUTPUT_DIRECTORY="$PWD/src/cloblab"
cmake --build build/native -j 2
python -c 'from cloblab.native import backend_module; backend_module("native")'
python -m pytest -q
```

`backend="native"` fails clearly if the extension is unavailable; `backend="auto"` falls back to Python. `replay_day(records, symbol, day, backend=..., interpretation=...)` returns event arrays, dense snapshots and ordered final state. `queue_paths(events, placements, side, horizon, backend=..., tick=..., decision_latency=...)` preserves the existing passive-path field names. Source arrays must remain unchanged during a native call.

The existing `scripts/run_queue_execution.py` accepts `--backend python|native|auto`; Python is the default. Select a separate private work directory when intentionally rerunning a backend. Existing completed checkpoints can skip computation, so they must not be used as evidence that a newly selected backend executed.

For the fixed engineering benchmark, use licensed files and the frozen cache:

```bash
PYTHONPATH=src python scripts/benchmark_native.py \\
  --raw "$RAW" --cache "$CACHE" --work "$PRIVATE_RECEIPTS" \\
  --out results/cxx20_replay_queue_v1
PYTHONPATH=src python scripts/benchmark_native.py \\
  --raw "$RAW" --cache "$CACHE" --work "$PRIVATE_RECEIPTS" \\
  --out results/cxx20_replay_queue_v1 --aggregate-only
python scripts/render_native_report.py
```

Independent workers may use `--shard N --shards K` with every shard exactly once and the same bound source/configuration. The one-shard command is the simplest reproduction, not a promise of the same parallel elapsed time. The full denominator must complete before aggregate publication.

The completed local suite passed 151 tests, including the published aggregate denominator and rate checks.

CI retains Python 3.10 and 3.12 fallback jobs and adds a Linux job that builds the extension, explicitly requires it and runs the full suite. Compiled modules and build directories remain ignored; no binary or compiler toolchain is committed.

## Interpretation

The project now includes a small native implementation with reproducible parity and measured throughput. It remains a historical research tool, not a production HFT engine, exchange matching engine or low-latency trading system. The [queue-identification limitation](WSELOB_QUEUE_SEMANTICS.md) and unfavorable execution evidence remain unchanged. No new model family or research tuning was added.

Source: Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1, [CC BY 4.0 dataset](https://data.mendeley.com/datasets/3g4mhdp899/1). Modifications: C++ replay/queue implementation and aggregate engineering measurements; no warranty or endorsement.
'''
    Path('docs/CXX20_REPLAY_QUEUE_REPORT.md').write_text(report)

if __name__=='__main__':main()
