# Reproducibility

The default demo is offline and deterministic. It does not require exchange
credentials or network access.

## Licensed benchmark reproduction

The default demo below is synthetic. For the five-stock experiment, follow the preparation and task commands in the [scientific/engineering report](XGBOOST_SCALE_ENGINEERING_REPORT.md), then the receipt-reuse instructions in the [execution report](EXECUTION_AWARE_ROBUSTNESS_REPORT.md) and [queue report](QUEUE_AWARE_EXECUTION_REPORT.md). These require separately obtained licensed raw files and private caches/predictions; cloning this repository alone does not reproduce the full research run.

## Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,ml,data,xgb]"
```

## Tests

```bash
python -m pytest -q
```

The tests cover:

- no-lookahead recent trade features;
- markout label alignment;
- walk-forward split ordering;
- label-time purge before each test fold;
- L2 sequence-gap rejection;
- crossed-book and negative-size rejection;
- visible-depth cost reporting.

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

## Publicly Accessible Data Capture

```bash
cloblab collect-coinbase --symbols BTC-USD ETH-USD --seconds 30 --out data/raw/coinbase/messages.jsonl
```

Captured market data is local output from a publicly accessible feed. Review
venue terms before redistributing any captured data or derived analytics.
