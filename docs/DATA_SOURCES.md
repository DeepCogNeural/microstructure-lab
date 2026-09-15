# Data Sources

## Headline licensed research

The empirical benchmark uses [WSELOB-2017 V1](https://data.mendeley.com/datasets/3g4mhdp899/1), covering five WSE equities in 2017. Its CC BY 4.0 attribution and file identities are documented in [license evidence](WSELOB_LICENSE.md) and `configs/wselob_sources_v1.json`. Public results are aggregate research artifacts; raw files and predictions remain uncommitted.

The sections below describe the separate engineering-only Coinbase scaffold.

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

## Coinbase scaffold scope

- No paid data.
- No private account data.
- No licensed Coinbase historical dataset.
- No live trading endpoint.
- No redistribution of Coinbase captures or their derived real-data reports.

The committed demo uses deterministic synthetic data so the repository remains
safe to clone, test, and publish.
