# Public Crypto CLOB Markout Benchmark

This repo is an MVP scaffold for a reproducible crypto central-limit-order-book
markout benchmark.

It is not trading advice, not a live trading system, and not an alpha claim.
The goal is to show a clean market-microstructure research workflow:
public order-book/trade data, no-lookahead features, future midprice labels,
walk-forward validation, cost-aware reporting, and a shuffled-label negative
control.

## What It Measures

CLOB means central limit order book: the visible bid/ask queue for an exchange
product. Markout means the future midprice move after a decision timestamp, for
example 1s, 5s, 10s, or 60s later.

The MVP features are:

- top-of-book imbalance
- multi-level depth imbalance
- spread in basis points
- recent trade-size imbalance

Labels are future midprice changes. They are built after features and are not
available to the feature builder.

## Data Source

The default forward-collection source is Coinbase Exchange public market data:

- `level2_batch` WebSocket channel for batched Level 2 book updates
- `matches` WebSocket channel for trades
- REST `/products/{product_id}/book` and `/trades` as public fallback/reference endpoints

The collector accepts no API key, signature, wallet, account, or order-entry
input.

## Quickstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m unittest discover -s tests
clob-markout make-sample --out data/sample --rows 120
```

The deterministic sample pipeline writes:

- `data/sample/raw/snapshots.parquet`
- `data/sample/raw/trades.parquet`
- `data/sample/processed/features.parquet`
- `data/sample/processed/labels.parquet`
- `data/sample/reports/summary.json`
- `data/sample/reports/bucket_markouts.csv`

## Public Collection

Collect a short public WebSocket JSONL sample:

```bash
clob-markout collect-coinbase \
  --symbols BTC-USD ETH-USD \
  --seconds 30 \
  --out data/raw/coinbase/messages.jsonl
```

Raw collected market data can become large. The repo ignores `data/raw/` and
`data/processed/` by default.

## Schema

```bash
clob-markout schema --out data/schema.md
```

See `data/README.md` for the MVP table definitions.

## Current Limits

- The shipped sample is synthetic and deterministic; it proves the pipeline,
  not a market result.
- The WebSocket collector stores raw public JSONL. Production-grade book
  reconstruction and sequence-gap repair are future work.
- The baseline is intentionally simple linear regression plus binned markouts.
  More complex models should wait until data quality, costs, and negative
  controls are stronger.
- Coinbase trade `side` semantics are exchange-specific; downstream research
  must document exactly how trade direction is interpreted.

