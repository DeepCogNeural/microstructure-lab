# C++20 Replay / Queue Kernel Finalization

## Status

**Completed on 2026-09-14.** Full-domain byte parity passed for 85,846,918 messages and 604,837,896 virtual-order evaluations. Measured replay and queue speedups are 8.98× and 3.57×; see the [final engineering report](CXX20_REPLAY_QUEUE_REPORT.md) for workload and timing limits. Original specification follows.

This is the final engineering track for the project. The scientific work is frozen. The goal is to move only the performance-critical deterministic market-data replay and queue-state kernel from Python into modern C++20 while keeping Python as the research/orchestration layer.

**Do not change any published scientific result, feature definition, model, holdout, threshold, latency grid, queue assumption, or interpretation in order to improve a number.**

The current Python implementation is the reference oracle.

## Objective

Produce a small C++20 native kernel with exact, tested semantic parity to the existing Python implementation for:

1. WSELOB order-state replay;
2. visible price-level aggregation;
3. queue ordering / queue-ahead state used by the conditional passive-execution study;
4. virtual-order state transitions required by the existing queue diagnostics.

Expose the native kernel through a minimal Python binding so the existing research pipeline can invoke either backend.

The final public result should answer two questions:

- **Correctness:** does the C++ backend reproduce the Python reference exactly where exact parity is defined?
- **Engineering value:** how much replay/queue throughput improvement does the native kernel provide on the same input and semantics?

A speedup is not required for success. Correctness is mandatory; measured performance is reported as-is.

---

## Hard scope boundary

### Implement in C++20

- order identity/state maintenance;
- `A`, `Y`, `M`, `D`, `F` handling under the already-documented WSELOB semantics;
- omitted-field retention and price scaling required by the current replay;
- visible bid/ask aggregation;
- deterministic price/priority ordering needed by the current queue study;
- queue-ahead tracking for the existing `retain` and `reset/back-of-queue` sensitivity interpretations;
- the existing conditional virtual-order depletion/fill state machine where moving it into the kernel materially avoids Python per-event overhead;
- compact output sufficient for the current Python research layer to reconstruct the same public aggregate diagnostics.

### Keep in Python

- pandas/Parquet dataset preparation;
- feature construction already published;
- Linear / HistGB / XGBoost fitting and inference;
- bootstrap / paired robustness analysis;
- aggregation and report tables;
- plotting;
- experiment manifests and publication logic;
- high-level CLI orchestration.

### Explicit non-goals

Do **not** add:

- new alpha features;
- new ML models;
- hyperparameter search;
- new thresholds;
- new market data;
- live trading/network code;
- exchange gateway code;
- custom distributed framework;
- hardware-specific optimization that makes the code fragile;
- speculative AVX/CUDA work before the simple C++ implementation is correct.

This is a finalization track, not a new research direction.

---

## Required architecture

Prefer a small structure similar to:

```text
cpp/
  CMakeLists.txt
  replay_queue.cpp
  replay_queue.hpp
  bindings.cpp
src/cloblab/
  native.py              # thin backend selector / validation wrapper
```

Use **C++20** and a minimal binding layer such as **pybind11**. A standard CMake/scikit-build-core style build is preferred if it integrates cleanly with the existing package.

The Python-facing API must be narrow and documented. Do not mirror the entire Python object model into C++.

Suggested conceptual interfaces are batch-oriented rather than one Python call per message, for example:

```python
native_replay_day(records, symbol, day, options) -> compact replay result
native_queue_diagnostics(records, decisions, options) -> compact diagnostic result
```

Exact function names are not prescribed. Optimize API boundaries around correctness and avoiding Python event-loop overhead.

The native module must fail clearly when it is unavailable; pure-Python functionality must remain usable.

---

## Semantic parity requirements

The current Python implementation and published documentation define the behavior. C++ must not silently reinterpret the source.

At minimum preserve and test:

### Replay semantics

- order key identity;
- `F` reset behavior;
- duplicate `A` rejection;
- unknown `M` / `D` rejection;
- `Y` as retransmission/state recovery, **not a trade**;
- previous-value retention for omitted fields;
- side normalization already used by the Python implementation;
- integer-price scaling by `10 ** price_level`;
- unpriced-order handling;
- nonnegative reconstructed visible depth;
- deterministic ten-level snapshot ordering;
- invalid shallow/locked/crossed state treatment;
- original event index preservation;
- valid-segment boundaries.

### Queue-study semantics

Preserve the two already-published priority sensitivity interpretations. Do not upgrade either interpretation into a claim of identified exchange matching rules.

Preserve:

- virtual order placed at back of current visible best-price queue;
- one dataset-native displayed quantity unit;
- no repricing;
- later arrivals do not increase queue ahead;
- exact lifetime/placement-latency message offsets;
- queue-ahead depletion logic;
- conditional execution assumption already used for `D` removals and same-price quantity reductions;
- requirement for additional same-price execution-assumed quantity to consume the virtual unit after queue ahead reaches zero;
- simultaneous fill/adverse handling;
- segment/reset invalidation;
- post-fill offset logic;
- both priority interpretations;
- zero identified lower fill bound remains a scientific limitation outside the native implementation.

Read and obey:

- `docs/WSELOB_QUEUE_SEMANTICS.md`
- `docs/QUEUE_AWARE_EXECUTION_REPORT.md`
- existing Python replay/queue implementation and tests.

If the Python implementation and prose appear inconsistent, **stop and resolve the inconsistency explicitly** rather than choosing the result that produces better performance or nicer numbers.

---

## Correctness gate: Python is the oracle

No benchmark is publishable until parity passes.

### Unit parity

Create hand-checkable synthetic sequences covering at least:

1. add / modify / delete;
2. retransmission;
3. omitted modification fields;
4. price change;
5. quantity increase/decrease;
6. same-price ambiguous modification under both priority interpretations;
7. reset;
8. duplicate and unknown-order failures;
9. unpriced order;
10. tied priority timestamps / deterministic tie behavior;
11. queue-ahead depletion;
12. new order arriving behind virtual order;
13. queue ahead clearing without enough subsequent quantity to fill virtual order;
14. actual conditional virtual fill;
15. lifetime expiry;
16. placement latency;
17. adverse-before-fill;
18. fill-before-adverse;
19. simultaneous fill/adverse;
20. segment boundary invalidation.

### Real-data parity

Use real licensed WSELOB inputs locally and compare Python vs C++ on deterministic subsets before any full run.

Required comparisons where applicable:

- live order count;
- aggregate price-level depth;
- ten-level snapshot values;
- valid snapshot indices;
- segment IDs;
- queue-ahead values;
- virtual-order terminal state;
- conditional fill indicator;
- fill event index / fill time;
- post-fill diagnostic inputs.

Prefer exact equality for integer/state fields. For prices, avoid unnecessary floating-point divergence; integer/fixed-point internal price representation is preferred, converting to floating point only at the public Python boundary if practical.

### Full-run parity receipt

For the full benchmark domain, generate deterministic hashes/checksums of compact Python and C++ outputs and verify agreement for every scientifically relevant field.

The final report must state exactly which fields are bit/exact-parity checked and, if any floating output requires tolerance, the tolerance and reason.

**If material parity fails, do not publish a speedup claim.**

---

## Performance benchmark

Only after parity succeeds, benchmark Python vs native C++ on identical inputs.

### Benchmark A — replay kernel

Measure the order-replay / visible-book path on the largest practical full licensed dataset already used by this project.

Report public-safe aggregate metrics only:

- messages processed;
- wall-clock time;
- messages/second;
- native/Python speedup;
- peak process memory if measured reliably.

Do not publish hostnames, CPU model, server/cluster names, core counts tied to private machines, scheduler IDs, filesystem paths, or device inventory.

### Benchmark B — queue diagnostic kernel

Benchmark the queue-aware event loop on the existing frozen queue-study workload or a clearly defined representative full subset, identical across backends.

Report:

- decisions / virtual orders evaluated;
- source messages scanned;
- wall time;
- throughput;
- speedup;
- output parity receipt.

### Benchmark hygiene

- warm/cold distinctions must be explicit if relevant;
- I/O must not be mixed into one backend and excluded from the other;
- compare the same semantic work;
- avoid cherry-picking a small subset that exaggerates native speedup;
- repeat enough times to detect gross timing noise, but do not build a large benchmarking framework;
- report the median of a small fixed number of repeated timings if repetitions are used;
- do not tune implementation or benchmark selection based on the desired resume number.

---

## Packaging / CI

The repository should remain easy to install and test.

Required:

- Python fallback remains functional when the native extension is absent;
- native-extra/build instructions are concise;
- CI continues to cover current Python 3.10 and 3.12 tests;
- add at least one CI path that actually builds the native extension on Linux and runs native parity tests;
- do not require specialized hardware;
- no vendored compiler toolchains or binary blobs;
- no committed build directories.

If extending the default CI matrix would make every push unnecessarily expensive, use a separate native job while retaining the existing Python jobs.

---

## Required tests

In addition to the semantic cases above, add tests for:

- backend selection / graceful Python fallback;
- malformed input rejection;
- stable exception mapping at the Python boundary;
- repeat-run determinism;
- both queue-priority interpretations;
- exact task/output row ordering where downstream code depends on it;
- aggregate queue metrics reproduced from C++ outputs matching Python reference values on a fixed fixture;
- privacy gate remains green.

All pre-existing tests must remain green.

---

## Public outputs

Create a final engineering report:

`docs/CXX20_REPLAY_QUEUE_REPORT.md`

It should contain:

1. scope and architecture;
2. what stayed in Python and why;
3. parity methodology;
4. real-data parity results;
5. replay benchmark;
6. queue-kernel benchmark;
7. limitations;
8. exact build/reproduction commands that contain no private paths;
9. concise interpretation for a quant/HFT engineering audience.

Small public-safe aggregate benchmark data may live under:

`results/cxx20_replay_queue_v1/`

Suggested files:

- `parity_summary.json`
- `benchmark_summary.csv`
- optional one small figure comparing throughput

Do **not** commit raw licensed data, row-level data, private execution receipts, environment dumps, hardware inventory, local paths, or private server metadata.

Update `README.md` only after measured results exist. The README should present this as an engineering implementation result, not a new alpha result.

---

## Claim rules

Allowed only if measured:

- "Implemented a C++20/pybind11 replay and queue kernel with exact Python parity on X fields."
- "Processed N messages at Y messages/s versus Z for Python, a Kx measured speedup."
- "Preserved identical queue diagnostic outputs under the frozen assumptions."

Not allowed:

- "production HFT engine";
- "exchange-grade matching engine";
- "nanosecond trading system";
- "exact passive fills";
- "profitable strategy" based on these queue diagnostics;
- any latency/throughput number not produced by a controlled benchmark;
- any claim that C++ changes the scientific conclusion.

The data-identification limitation discovered in the queue study remains unchanged: WSELOB does not uniquely identify historical executions from `D`/`M` events, so nonzero passive fills remain conditional diagnostics.

---

## Repository/privacy rules

`CONTRIBUTING.md` remains a hard gate.

Do not commit:

- host/server/cluster names;
- CPU/GPU inventory;
- private hardware counts;
- device IDs;
- scheduler details;
- absolute home paths;
- environment dumps;
- credentials;
- internal application notes;
- agent handoff/completion notes.

This document is a public engineering specification, not a private infrastructure handoff.

---

## Definition of done

The C++ finalization is complete only when all are true:

1. native C++20 kernel is small and scoped to replay/queue hot paths;
2. Python remains the research/orchestration layer;
3. native extension builds reproducibly;
4. synthetic semantic parity suite passes;
5. real-data subset parity passes;
6. full-domain parity/checksum gate passes for all scientifically relevant outputs used in the benchmark;
7. replay benchmark is completed on identical work;
8. queue-kernel benchmark is completed on identical work;
9. all existing and new tests pass;
10. CI including native build/parity is green;
11. privacy check is green;
12. final report and small aggregate performance artifacts are published;
13. README is updated only with measured facts;
14. no scientific models/results/thresholds were changed;
15. the existing queue-identification caveat remains explicit.

After these conditions are met, stop development on this project except for bug fixes or genuine external-data replication. Do not add another model family merely to extend the repository.
