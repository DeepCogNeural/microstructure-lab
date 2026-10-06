# Technology stack

This page lists the languages, libraries and engineering practices in the repository, and where each one lives. Counts describe the current tree.

## 1. Languages

| Language | Where | Size |
|---|---|---|
| Python 3.10 or newer | `src/cloblab/` (35 modules plus `__init__.py`), `scripts/` (45 scripts), `tests/` | 4,092 lines in `src/cloblab` |
| C++20 | `cpp/replay_queue.cpp`, `cpp/replay_queue.hpp`, `cpp/bindings.cpp` | 191 lines |
| Shell (bash) | `scripts/remote/run_bounded.sh` | one script |

- Python is the reference implementation. The package name is `cloblab`; the command-line entry point is `cloblab.cli:main`.
- C++20 implements two batch kernels: order-level book replay (`replay`) and conditional passive-order paths (`paths`).
- `bindings.cpp` exposes both kernels to Python with pybind11 as the module `_replay_queue`. It releases the GIL during the native loops.
- `cpp/CMakeLists.txt` builds the module with CMake 3.20 or newer. It sets `-ffp-contract=off` (GCC and Clang) or `/fp:strict` (MSVC), so floating-point results do not change with fused multiply-add.
- `run_bounded.sh` runs one command with a time limit, single-thread math settings, and separate log and exit-code files.

## 2. Libraries

| Library | Used in | Role |
|---|---|---|
| numpy | most modules and scripts | Arrays, replay buffers, statistics |
| pandas | most modules and scripts | Tables, time handling, aggregation |
| pyarrow | through `to_parquet` / `read_parquet` in `scale_cache.py`, `io.py`, `wselob.py`, `scale_runner.py` | Parquet files (Zstd compression) |
| h5py | `wselob.py`, `scale_cache.py`, `later_confirmation.py`, `research_diagnostics.py`, `benchmark_native.py`, `run_queue_execution.py` | Reads HDF5 source files (extra `data`) |
| sortedcontainers | `book.py`, `queue_book.py`, `wselob.py` | Sorted price levels and order queues |
| scikit-learn | `models.py`, `scale_runner.py`, `run_sequence_ml_v1.py` | Ridge regression and metrics (extra `ml`) |
| xgboost | `scale_runner.py`, `later_confirmation.py`, `research_audit.py`, `run_transfer_robustness.py` | Gradient-boosted trees (extra `xgb`) |
| torch | `sequence_model.py` (GRU), `sequence_transformer.py` (Transformer), `run_sequence_ml_fq2.py`, `run_sequence_ml_fq4.py`, `run_sequence_ml_q8.py` | Sequence models (extra `sequence`; CPU build in CI) |
| matplotlib | `render_*.py` scripts, `licensed_experiment.py` | Aggregate figures (extra `ml`) |
| websockets | `collectors.py` | Coinbase feed collector (engineering-only) |
| pybind11, cmake | `cpp/bindings.cpp`, `cpp/CMakeLists.txt` | C++ to Python binding and build (extra `native`) |
| pytest | `tests/` | Test runner (extra `dev`) |
| polars (optional) | `src/cloblab/polars_cache.py`, `cloblab cache-summary --engine polars`, extra `polars` | Lazy scan of the symbol/day Parquet feature cache; parity-tested against the pandas reference in `tests/test_polars_cache.py`. pandas stays the default. |

## 3. Data engineering

The pipeline turns licensed HDF5 order messages into immutable Parquet partitions, one per symbol and day. Every file is hashed. A task runner reads the partitions and writes one result per task. Each task has an ID built only from scientific settings, so it does not change when paths or devices change. Finished tasks are reused after an interrupt. Missing or conflicting tasks block final aggregation.

1. Read HDF5 source files (`wselob.py`, `scale_cache.py`).
2. Replay order messages into valid ten-level book snapshots.
3. Compute causal features and exact-message labels (`features.py`, `labels.py`).
4. Write symbol/day Parquet partitions with Zstd compression (`scale_cache.py`).
5. Record SHA-256 hashes of sources and partitions in manifests (`scale_common.py`).
6. Build the scientific identity and task ID (`scientific_identity.py`).
7. Fit and evaluate tasks with locks, atomic writes, resume and retry (`scale_runner.py`).
8. Aggregate all tasks and publish only aggregate tables and figures.

## 4. Scientific computing and ML

| Area | Modules |
|---|---|
| Causal features | `features.py`, `advanced_features.py` |
| Labels and chronological splits | `labels.py`, `splits.py` |
| Ridge and XGBoost | `models.py`, `tree_evaluation.py`, `scale_runner.py` |
| GRU and Transformer | `sequence_model.py`, `sequence_transformer.py`, `sequence_ml.py` |
| Evaluation statistics | `evaluation.py`, `robustness.py`, `research_audit.py` |
| Execution diagnostics | `costs.py`, `execution_labels.py`, `passive_execution.py`, `queue_book.py`, `queue_metrics.py` |
| Transfer and later-period checks | `transfer.py`, `later_confirmation.py`, `q3_diagnostics.py` |

## 5. Performance engineering

- The C++20 kernels cover book replay and conditional queue paths.
- `src/cloblab/native.py` selects the backend: `backend` is `python`, `native` or `auto`. `auto` falls back to Python if the extension is missing.
- Python stays the semantic reference. `tests/test_native.py` compares native and Python outputs array by array, including malformed inputs and queue race cases.
- `scripts/benchmark_native.py` times fixed workloads and hashes every output (SHA-256 over dtype, shape and bytes).
- `scripts/render_native_report.py` writes the aggregate table. See `docs/CXX20_REPLAY_QUEUE_REPORT.md` for ratios and timing scope.

## 6. Testing and CI

- `tests/` has 21 files and 112 `def test_` functions. Parametrized tests run more cases.
- CI (`.github/workflows/ci.yml`) has two jobs.
  - `test`: Python 3.10 and 3.12 on Ubuntu, CPU torch, extras `dev,ml,data,xgb,sequence`, then `pytest -q`.
  - `native`: Python 3.12, builds the C++20 module with CMake, asserts the native backend loads, runs `pytest -q`.
- Both jobs run `scripts/check_public_privacy.py`. It scans for hostnames, hardware inventory, scheduler IDs, home paths and SSH targets.

## 7. Reproducibility practices

- Fixed protocols are written before the runs (`docs/*_PROTOCOL.md`). Reports state limits and failed or missing tasks.
- Outputs carry SHA-256 hashes and manifests.
- Render and verify scripts come in pairs. Verify scripts check that published tables match their hashes and denominators.
  - `render_research_audit.py` and `verify_research_audit.py`
  - `render_sequence_ml_final.py` and `verify_sequence_ml_final.py` (also `verify_sequence_ml_package.py`)
- Public: source, tests, scientific settings, aggregate CSV/JSON, small figures, hashes.
- Withheld: raw licensed data, row-level features and predictions, model binaries, run logs, host and scheduler details.

## 8. Question, code and report

| Stage | Run | Aggregate / render | Results | Report |
|---|---|---|---|---|
| Five-stock benchmark | `scale_runner.py`, `run_application_benchmarks.py` | `render_research_audit.py` | `results/wselob_xgboost_application_v1` | `docs/XGBOOST_SCALE_ENGINEERING_REPORT.md` |
| Execution-aware robustness | `run_execution_robustness.py`, `run_transfer_robustness.py` | `render_execution_robustness.py` | `results/wselob_execution_robustness_v1` | `docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md` |
| Queue-aware diagnostics | `run_queue_execution.py` | `render_queue_execution.py` | `results/wselob_queue_execution_v1` | `docs/QUEUE_AWARE_EXECUTION_REPORT.md` |
| C++20 kernels | `benchmark_native.py` | `render_native_report.py` | `results/cxx20_replay_queue_v1` | `docs/CXX20_REPLAY_QUEUE_REPORT.md` |
| Later-period confirmation | `python -m cloblab.later_confirmation` | same module (`--aggregate-only`) | `results/wselob_later_confirmation_v1` | `docs/LATER_PARTITIONS_CONFIRMATION_REPORT.md` |
| Sequence ML FQ2 | `run_sequence_ml_fq2.py` | `aggregate_sequence_ml_fq2.py` | `results/sequence_ml_fq2_v1` | `docs/SEQUENCE_ML_FQ2_REPORT.md` |
| Sequence ML FQ3 / FQ4 | `run_sequence_ml_fq3_update.py`, `run_sequence_ml_fq4.py` | `aggregate_sequence_ml_fq3.py`, `aggregate_sequence_ml_fq4.py` | `results/sequence_ml_fq3_v1`, `results/sequence_ml_fq4_v1` | `docs/SEQUENCE_ML_FQ3_REPORT.md`, `docs/SEQUENCE_ML_FQ4_REPORT.md` |
| Sequence ML Q8 / Q10 / Q11 | `run_sequence_ml_q8.py`, `run_sequence_ml_q10.py`, `run_sequence_ml_q11.py` | `aggregate_sequence_ml_q8.py`, `aggregate_sequence_ml_q10.py`, `aggregate_sequence_ml_q11.py` | `results/sequence_ml_q8_v1`, `_q10_v1`, `_q11_v1` | `docs/SEQUENCE_ML_Q8_REPORT.md`, `_Q10_REPORT.md`, `_Q11_REPORT.md` |
| Formal sequence-ML package | `recompute_sequence_ml_final.py` | `render_sequence_ml_final.py` | `results/sequence_ml_final_v1` | `docs/SEQUENCE_ML_FINAL_PACKAGE.md` |
| Research audit | `research_audit.py` | `render_research_audit.py`, `verify_research_audit.py` | `results/wselob_research_audit_v1` | `docs/RESEARCH_AUDIT_PROTOCOL.md` |
