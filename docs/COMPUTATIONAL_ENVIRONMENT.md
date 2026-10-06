# Computational environment

This page records the software, hardware class and resource use behind the completed WSE research. Every number below is copied from a committed public file, named next to it. Hostnames, usernames, filesystem paths and scheduler identifiers are withheld by the [public privacy policy](../CONTRIBUTING.md). Exact CPU/GPU model inventory is also withheld under that policy.

## Software

| Component | Recorded value | Source |
| --- | --- | --- |
| Python (formal GPU stages) | 3.11.10 | `software` field in `results/sequence_ml_fq2_v1/*.json`, `results/sequence_ml_fq3_v1/fq3_update_*.json`, `results/sequence_ml_fq4_v1/fq4_transformer_*.json`, `results/sequence_ml_q8_v1/*.json` |
| PyTorch (formal GPU stages) | 2.6.0+cu124 | same `software` field |
| XGBoost | `xgboost>=3.0,<3.1` | `pyproject.toml` extra `xgb`; the exact installed patch version is not recorded in result files |
| Supported Python for this package | `>=3.10`; CI tests 3.10 and 3.12 | `pyproject.toml`, `.github/workflows/ci.yml` |
| C++ extension build | C++20, CMake `>=3.20`, pybind11 `>=2.13,<4`, `-ffp-contract=off` (MSVC: `/fp:strict`), no fast-math | `cpp/CMakeLists.txt`, `pyproject.toml` extra `native`, `docs/CXX20_REPLAY_QUEUE_REPORT.md` |

The Q10 and Q11 task receipts do not contain a `software` field. Their software versions are not recorded in public files.

## Hardware class

| Work | Hardware class | Host |
| --- | --- | --- |
| Formal GRU/XGBoost/Transformer stages FQ2, FQ3 updates, FQ4, Q8, Q10 | one NVIDIA CUDA GPU allocated per task; device model withheld by policy | not published |
| Q11 visible-crossing re-check | desktop-class x86-64 workstation; four CPU cores allocated per task (`results/sequence_ml_q11_v1/q11_cpu_allocation.json`) | host not recorded |
| FQ3 CPU diagnostics | CPU only; core count not recorded (`results/sequence_ml_final_v1/cost_table.csv`) | host not recorded |
| C++20 replay/queue benchmark | desktop-class x86-64 workstation; kernel timings are same-host ratios, not absolute throughput | host not recorded |
| Full-year data preparation | desktop-class x86-64 workstation | host not recorded |

Peak framework GPU memory allocation across the formal stages was under 0.4 GB, so results do not depend on a large-memory accelerator. The largest `gpu_peak_allocated_bytes` over all 165 recorded GRU/Transformer fits is 306,970,624 bytes (Q10, `results/sequence_ml_q10_v1/q10_transfer_PKNORLEN.json`); the largest framework reservation, `gpu_peak_reserved_bytes`, is 400,556,032 bytes (Q8 and Q10 context-128 fits).

## What "allocated" means

Allocated time is the start-to-completion wall time of a task that held the resource. It includes data loading and the XGBoost baseline. It is not GPU or CPU utilization (`limits` field in `results/sequence_ml_fq2_v1/fq2_gpu_allocation.json`, `results/sequence_ml_q11_v1/q11_cpu_allocation.json`). Allocated GPU-hours sum one GPU times each task's allocated wall hours. Allocated CPU core-hours for Q11 sum four cores times each task's allocated wall hours.

## Allocated resources per stage

From `results/sequence_ml_final_v1/cost_table.csv`:

| Stage | Tasks | Allocated GPU-hours | Allocated CPU core-hours | Allocated CPU wall hours |
| --- | ---: | ---: | ---: | ---: |
| FQ2 | 15 | 0.956667 | | |
| FQ3 | 15 | 1.391111 | | |
| FQ4 | 5 | 1.926111 | | |
| Q8 | 15 | 1.520556 | | |
| Q10 | 5 | 2.117222 | | |
| FQ3 CPU diagnostic | 5 | | not recorded | 0.016111 |
| Q11 | 5 | | 1.264444 | 0.316111 |

Total formal GPU allocation was 7.912 GPU-hours. Q11 used 1.264 allocated CPU core-hours (`docs/SEQUENCE_ML_FINAL_PACKAGE.md`). Every task returned an explicit zero exit and empty stderr, except one FQ2 task that has a completion marker but no explicit exit-code line (`missing_explicit_exit_count` in `results/sequence_ml_fq2_v1/fq2_gpu_allocation.json`).

## Per-task examples

Wall time and peak process resident memory (RSS) for one stock, KGHM, from the task receipts:

| Task | Wall seconds | Peak process RSS (bytes) | Source |
| --- | ---: | ---: | --- |
| FQ2, 200k endpoints | 402.54 | 1,859,952,640 | `results/sequence_ml_fq2_v1/fq2_200000_KGHM_a1.json` |
| FQ3, June 2017 update | 339.07 | 1,776,254,976 | `results/sequence_ml_fq3_v1/fq3_update_2017-06_KGHM.json` |
| FQ4, Transformer | 1,711.23 | 1,932,406,784 | `results/sequence_ml_fq4_v1/fq4_transformer_KGHM.json` |
| Q8, context 128 | 443.25 | 3,508,842,496 | `results/sequence_ml_q8_v1/q8_context128_KGHM.json` |
| Q10, KGHM held out | 1,547.36 | 9,174,040,576 | `results/sequence_ml_q10_v1/q10_transfer_KGHM.json` |
| Q11, KGHM | 239 allocated CPU seconds (four cores) | not recorded | `results/sequence_ml_q11_v1/q11_cpu_allocation.json` |

## Full-year data preparation

From `results/wselob_xgboost_application_v1/preparation_summary.json`:

- 1,250 source stock/days and 85,846,918 raw order messages produced 56,887,949 feature rows.
- Total preparation time was 244.5 seconds (`preparation_seconds_total` 244.50541062932462).
- Maximum worker peak RSS was 1,729,668 KiB, about 1.65 GiB.
- The source HDF5 files total 1,313,242,927 bytes. The derived Parquet store holds 964,616,714 bytes of snapshots and 1,187,614,304 bytes of features (2,152,231,018 bytes together).

The derived store is larger than the source. It is not compression. It is a partitioned, immutable, query-ready derived store with SHA-256 manifests (one `symbol/day` partition per stock/day; see `docs/XGBOOST_SCALE_ENGINEERING_REPORT.md`). The worker count for this run is not recorded in the summary file.

## C++20 benchmark threading

C++20 kernels are single-threaded; the benchmark ran day partitions as bounded parallel shards, and the reported 8.984× / 3.571× are per-kernel wall-time ratios on the same host.

- The C++ replay and queue kernels are single-threaded. `cpp/replay_queue.cpp` contains no thread, OpenMP or async code. `cpp/bindings.cpp` releases the Python GIL during each native call.
- Each timing is the median of three sums of per-day kernel wall times (`results/cxx20_replay_queue_v1/benchmark_summary.csv`). Days ran in bounded parallel shards (`--shard N --shards K` in `scripts/benchmark_native.py`). The shard count is not recorded in public files.
- Replay: Python 4192.595 s versus native 466.656 s over 85,846,918 messages, an 8.984× ratio. Queue: Python 5.099 s versus native 1.428 s over 7,889,736 virtual orders, a 3.571× ratio (`docs/CXX20_REPLAY_QUEUE_REPORT.md`).
- These are same-host kernel ratios with file I/O excluded. They are not end-to-end pipeline speed or live latency.

## Not published

Raw licensed WSE rows, row-level predictions, model weights, scheduler logs, hostnames, usernames, filesystem paths and scheduler job identifiers stay outside this repository.
