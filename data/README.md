# Data

Large raw data is not committed. Keep only small deterministic samples, schemas,
or derived examples that are safe to publish.

## Tables

### `order_book_snapshots`

One row per observed book snapshot.

- `exchange_ts`: exchange/source timestamp.
- `local_ts`: local receipt or sampling timestamp; this is the decision time.
- `symbol`: product id, for example `BTC-USD`.
- `bid_px_1..N`, `bid_sz_1..N`: bid prices and displayed sizes by level.
- `ask_px_1..N`, `ask_sz_1..N`: ask prices and displayed sizes by level.

### `order_book_deltas`

One row per price-level update when using a streaming source.

- `exchange_ts`, `local_ts`, `symbol`.
- `sequence`: source sequence number when available.
- `side`: bid/buy or ask/sell side from the source event.
- `price`: updated price level.
- `size`: new displayed size at that level; zero means remove.
- `source_channel`: for example `level2_batch`.

### `trades`

One row per trade.

- `exchange_ts`, `local_ts`, `symbol`.
- `trade_id`: source id when available.
- `side`: raw source side field; interpretation must be documented per exchange.
- `price`: trade price.
- `size`: trade size in base asset units.

### `features`

One row per decision timestamp. Every field must be known at `local_ts`.

- `midprice`: current `(best_bid + best_ask) / 2`.
- `spread_bps`: spread divided by midprice, in basis points.
- `top_imbalance`: best-level size imbalance.
- `depth_imbalance`: multi-level size imbalance.
- `recent_trade_imbalance`: buy/sell trade-size imbalance using only trades at
  or before `local_ts`.

### `labels`

Future midprice labels joined to feature rows after feature construction.

- `future_ts_{horizon}s`: first midprice timestamp at or after the horizon.
- `future_midprice_{horizon}s`: future midprice.
- `markout_{horizon}s`: future midprice minus current midprice.
- `markout_bps_{horizon}s`: markout in basis points.
- `direction_{horizon}s`: sign of markout.

