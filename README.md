# Crypto Market Microstructure Lab

Deterministic publicly accessible feed capture, aggregate Level 2
reconstruction, chronological future-midpoint evaluation, and visible-depth
crossing-cost diagnostics for crypto central limit order book research.

This is a research scaffold, not trading advice, not a live trading system,
and not an alpha or profit claim. It is designed to make the hard parts of
market microstructure research visible: timestamp causality, order-book
invariants, feature/label separation, label-time purging, walk-forward
validation, negative controls, and explicit cost assumptions.

```text
public feed or synthetic fixture
  -> raw events
  -> deterministic L2 replay
  -> features known at decision time
  -> future midpoint markout labels
  -> walk-forward baseline + negative controls
  -> visible-depth cost stress report
```

## Core Concepts

CLOB means central limit order book: the visible bid and ask queues for a
traded product. A markout is the future midpoint price change after a decision
timestamp, for example 1s, 5s, 10s, or 60s later. In this repo, future midpoint
data is used only as a label, never as an input feature.

## Quickstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
cloblab demo --offline --out data/sample --rows 120
```

The offline demo writes only deterministic synthetic fixtures:

- `data/sample/raw/snapshots.parquet`
- `data/sample/raw/trades.parquet`
- `data/sample/raw/l2_events.parquet`
- `data/sample/processed/features.parquet`
- `data/sample/processed/labels.parquet`
- `data/sample/processed/l2_replay_snapshots.parquet`
- `data/sample/reports/summary.json`
- `data/sample/reports/bucket_markouts.csv`
- `data/sample/reports/visible_depth_cost_sweep.csv`
- `data/sample/MANIFEST.json`

## What Is Implemented

- Coinbase Exchange publicly accessible WebSocket collector for raw JSONL
  capture, subject to provider terms.
- Deterministic synthetic ingestion path for offline reproducibility.
- Aggregate L2 replay with integer tick/lot normalization, sequence-gap checks,
  crossed-book rejection, and stable state hashes.
- No-lookahead features: top-of-book imbalance, multi-level depth imbalance,
  spread in basis points, midpoint, and recent trade-size imbalance.
- 1s/5s/10s/60s midpoint markout labels built after feature construction.
- Label-time-purged walk-forward linear baseline with IC, direction accuracy,
  binned markouts, cost-threshold coverage, and shuffled-label negative
  control.
- Visible-depth sweep cost proxy for crossing the book. It is not a passive
  fill, queue-position, or PnL model.

## Public Collection

Collect a short Coinbase Exchange publicly accessible WebSocket JSONL sample:

```bash
cloblab collect-coinbase \
  --symbols BTC-USD ETH-USD \
  --seconds 30 \
  --out data/raw/coinbase/messages.jsonl
```

Raw collected market data can become large and may be subject to provider
redistribution limits. The repo ignores `data/raw/` and `data/processed/` by
default.

The collector accepts no API key, signature, wallet, account, or order-entry
input.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Methodology](docs/METHODOLOGY.md)
- [Data sources](docs/DATA_SOURCES.md)
- [Data terms](docs/DATA_TERMS.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Limitations](docs/LIMITATIONS.md)
- [Schema](data/schema.md)

## Current Limits

- The shipped sample is synthetic and deterministic; it proves the pipeline,
  not a market result.
- Publicly accessible feed capture is forward-only. The repo does not
  redistribute captured venue data or derived real-data reports.
- L2 data cannot prove hidden liquidity, true queue position, or passive-fill
  probability.
- The baseline is intentionally simple. More complex models should wait until
  data quality, costs, and negative controls are stronger.
- Coinbase `match.side` is maker side; aggressor-side features must invert it
  before using trade direction.
