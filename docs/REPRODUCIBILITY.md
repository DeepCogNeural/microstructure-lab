# Reproducibility

The default demo is offline and deterministic. It does not require exchange
credentials or network access.

## Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
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
cloblab demo --offline --out data/sample --rows 120
```

Expected report files:

- `data/sample/reports/summary.json`
- `data/sample/reports/bucket_markouts.csv`
- `data/sample/reports/visible_depth_cost_sweep.csv`
- `data/sample/MANIFEST.json`

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
