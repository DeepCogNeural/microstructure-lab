# Data Model

The pipeline separates raw market-data events, reconstructed book state,
features, labels, and reports. This keeps feature construction auditable and
makes future-data leakage easier to detect.

## Timestamps

- `exchange_ts`: timestamp supplied by the exchange or source message when it
  exists.
- `local_ts`: local receipt or decision timestamp. This is the causal boundary
  for features.
- `local_receive_index`: monotonic local event order used when events share the
  same timestamp.

## Core Tables

- `order_book_deltas`: price-level updates with `side`, `price`, `size`, and
  optional `sequence`.
- `l2_replay_snapshots`: deterministic book state after each accepted delta,
  including `state_hash`.
- `order_book_snapshots`: top N bid/ask prices and displayed sizes.
- `trades`: public trade prints. Feature code expects normalized aggressor
  side in `side`; raw venue side should be stored separately when ingesting
  real data.
- `features`: current midpoint, spread, order-book imbalance, and recent
  trade imbalance known at `local_ts`.
- `labels`: future midpoint markouts for fixed horizons.
- `visible_depth_cost_sweeps`: simple crossing-cost stress results.

## Price And Size Representation

Book replay converts prices to integer ticks and sizes to integer lots before
updating state. This avoids floating-point key drift in the book map. Output
tables are written as ordinary numeric columns for ease of use with pandas,
DuckDB, and Parquet.

## Sample Manifest

`data/sample/MANIFEST.json` marks committed sample artifacts as synthetic. It
does not grant rights to any third-party market data.

## Schema

Run:

```bash
cloblab schema --out data/schema.md
```

The generated schema is committed at `data/schema.md`.
