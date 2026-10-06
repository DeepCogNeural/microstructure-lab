# Reproducibility

The default demo is offline and deterministic. It does not require exchange
credentials or network access.

## Licensed benchmark reproduction

The default demo below is synthetic. For the five-stock experiment, follow the preparation and task commands in the [scientific/engineering report](XGBOOST_SCALE_ENGINEERING_REPORT.md), then the receipt-reuse instructions in the [execution report](EXECUTION_AWARE_ROBUSTNESS_REPORT.md) and [queue report](QUEUE_AWARE_EXECUTION_REPORT.md). These require separately obtained licensed raw files and private caches/predictions; cloning this repository alone does not reproduce the full research run.

The optional C++20 build, backend selection and full-domain parity/performance reproduction are documented in the [native report](CXX20_REPLAY_QUEUE_REPORT.md). Python remains the default; compiled binaries are not committed.

## Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,ml,data,xgb,sequence]"
```

Add the `polars` extra (`pip install -e ".[dev,polars]"`) to enable the optional polars engine for `cloblab cache-summary`; its parity tests skip without it.

## Tests

```bash
python -m pytest -q
```

The tests (`tests/`) cover:

- WSELOB replay, queue semantics and later-period confirmation: `test_wselob.py`, `test_queue_execution.py`, `test_later_confirmation.py`;
- licensed-experiment and scale pipeline: `test_licensed_experiment.py`, `test_scale_pipeline.py`, `test_data_artifacts.py`;
- features, labels, splits, replay and costs: `test_features_labels_splits.py`, `test_l2_replay_and_costs.py`, `test_advanced_features.py`;
- execution robustness and research audit: `test_execution_robustness.py`, `test_research_audit.py`;
- tree models: `test_tree_model.py`, `test_tree_evaluation.py`;
- sequence ML: `test_sequence_ml.py`, `test_sequence_model.py`, `test_sequence_transformer.py`, `test_sequence_ml_fq4_gate.py`, `test_q3_diagnostics.py`;
- native C++20 backend parity: `test_native.py`;
- engineering scaffold: `test_collectors.py`, `test_coinbase_normalize.py`.

## Offline Demo

```bash
cloblab demo --offline --out /tmp/microstructure-demo --rows 120
```

Expected report files:

- `/tmp/microstructure-demo/reports/summary.json`
- `/tmp/microstructure-demo/reports/bucket_markouts.csv`
- `/tmp/microstructure-demo/reports/visible_depth_cost_sweep.csv`
- `/tmp/microstructure-demo/MANIFEST.json`

## Regenerate Schema

```bash
cloblab schema --out data/schema.md
```

## Engineering scaffold (not part of the WSE study)

### Publicly accessible data capture

```bash
cloblab collect-coinbase --symbols BTC-USD ETH-USD --seconds 30 --out data/raw/coinbase/messages.jsonl
```

Captured market data is local output from a publicly accessible feed. Review
venue terms before redistributing any captured data or derived analytics.
