# Architecture

This project is built as a small event-driven research pipeline.

```text
collector or fixture
  -> raw event storage
  -> normalized L2 events and trades
  -> deterministic book replay
  -> feature builder
  -> markout label builder
  -> walk-forward evaluation
  -> cost stress reports
```

## Design Rules

- Raw data is written before transformation.
- `exchange_ts` records the source event time when available.
- `local_ts` records local receipt or decision time.
- Features use only the current row and past rows.
- Future midpoint data is used only for labels.
- Evaluation uses walk-forward splits with label-time training purge, not
  random splits.
- Negative controls are part of the default benchmark.

## Modules

- `cloblab.collectors`: publicly accessible Coinbase Exchange WebSocket JSONL
  capture and side-semantics helpers.
- `cloblab.book`: deterministic aggregate L2 replay and book invariants.
- `cloblab.features`: no-lookahead feature construction.
- `cloblab.labels`: 1s/5s/10s/60s midpoint markout labels.
- `cloblab.splits`: anchored walk-forward split logic.
- `cloblab.evaluation`: simple linear baseline, label-time purge, and
  shuffled-label control.
- `cloblab.costs`: visible-depth sweep cost proxy.
- `cloblab.cli`: reproducible demo, schema rendering, and collection entrypoints.

## Non-Goals

- No private keys, wallets, exchange accounts, or live order entry.
- No live trading or production automation.
- No claim that a signal is tradable or profitable.
- No passive fill or queue-position claim from aggregate L2 data.
