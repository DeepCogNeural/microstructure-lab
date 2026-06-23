# Data Sources

## Default Publicly Accessible Source

The forward collector targets Coinbase Exchange WebSocket market data that is
publicly accessible but still subject to provider terms:

- `level2_batch` for batched Level 2 order-book updates;
- `matches` for public trade prints.

The collector stores raw JSONL records with a local receipt timestamp and the
raw message payload.

## Why Coinbase For The MVP

- Publicly accessible market-data endpoint.
- No API key, wallet, account, signature, or order-entry permission required
  for the public market-data connection.
- Common USD crypto pairs such as `BTC-USD` and `ETH-USD`.
- Good enough for a small reproducible forward-collection scaffold.

## What Is Not Included

- No paid data.
- No private account data.
- No licensed historical dataset.
- No live trading endpoint.
- No redistribution of captured venue data or derived real-data reports.

The committed demo uses deterministic synthetic data so the repository remains
safe to clone, test, and publish.
