# Data Schema

## order_book_snapshots

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | exchange or source timestamp for the book observation |
| `local_ts` | `timestamp[ns, UTC]` | local receipt or sample timestamp used as the decision time |
| `symbol` | `string` | exchange product id such as BTC-USD |
| `bid_px_1..N` | `float64` | bid price by book level; level 1 is best bid |
| `bid_sz_1..N` | `float64` | bid displayed size by book level |
| `ask_px_1..N` | `float64` | ask price by book level; level 1 is best ask |
| `ask_sz_1..N` | `float64` | ask displayed size by book level |

## l2_replay_snapshots

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | exchange/source timestamp carried from the accepted delta |
| `local_ts` | `timestamp[ns, UTC]` | local receipt timestamp carried from the accepted delta |
| `local_receive_index` | `int64` | monotonic local replay order |
| `sequence` | `int64` | source sequence accepted by the replay engine |
| `symbol` | `string` | exchange product id |
| `best_bid` | `float64` | best bid after applying the delta |
| `best_ask` | `float64` | best ask after applying the delta |
| `bid_px_1..N` | `float64` | replayed bid price by level |
| `bid_sz_1..N` | `float64` | replayed bid displayed size by level |
| `ask_px_1..N` | `float64` | replayed ask price by level |
| `ask_sz_1..N` | `float64` | replayed ask displayed size by level |
| `state_hash` | `string` | stable hash of full replayed aggregate book state |

## order_book_deltas

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | exchange event timestamp when provided |
| `local_ts` | `timestamp[ns, UTC]` | local receipt timestamp |
| `symbol` | `string` | exchange product id |
| `sequence` | `int64` | source sequence number when provided; Coinbase L2 messages do not provide one |
| `side` | `string` | bid/buy or ask/sell side from the source event |
| `price` | `float64` | price level being updated |
| `size` | `float64` | new displayed size at that price level; zero means remove |
| `source_channel` | `string` | for example level2_batch |

## trades

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | exchange trade timestamp |
| `local_ts` | `timestamp[ns, UTC]` | local receipt timestamp |
| `symbol` | `string` | exchange product id |
| `trade_id` | `string` | source trade id if provided |
| `side` | `string` | normalized aggressor side when used for features |
| `source_side` | `string` | optional raw venue side field |
| `price` | `float64` | trade price |
| `size` | `float64` | trade size in base asset units |

## midprices

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | source timestamp carried from snapshot |
| `local_ts` | `timestamp[ns, UTC]` | decision timestamp |
| `symbol` | `string` | exchange product id |
| `best_bid` | `float64` | best bid price |
| `best_ask` | `float64` | best ask price |
| `midprice` | `float64` | (best_bid + best_ask) / 2 |
| `spread` | `float64` | best_ask - best_bid |
| `spread_bps` | `float64` | spread divided by midprice, in basis points |

## features

| Column | Type | Meaning |
| --- | --- | --- |
| `exchange_ts` | `timestamp[ns, UTC]` | source timestamp carried from snapshot |
| `local_ts` | `timestamp[ns, UTC]` | decision timestamp |
| `symbol` | `string` | exchange product id |
| `midprice` | `float64` | current midprice, included for label construction and diagnostics |
| `spread_bps` | `float64` | current spread in basis points |
| `top_imbalance` | `float64` | (best_bid_size - best_ask_size) / total top size |
| `depth_imbalance` | `float64` | same imbalance over configured depth levels |
| `recent_trade_imbalance` | `float64` | past-window buy/sell trade-size imbalance |

## labels

| Column | Type | Meaning |
| --- | --- | --- |
| `local_ts` | `timestamp[ns, UTC]` | decision timestamp; joins to feature row |
| `symbol` | `string` | exchange product id |
| `future_ts_{horizon}s` | `timestamp[ns, UTC]` | first midprice timestamp at or after local_ts + horizon |
| `future_midprice_{horizon}s` | `float64` | future midprice used only as the supervised label |
| `markout_{horizon}s` | `float64` | future_midprice - current_midprice |
| `markout_bps_{horizon}s` | `float64` | markout divided by current midprice, in basis points |
| `direction_{horizon}s` | `float64` | sign of the markout |

## visible_depth_cost_sweeps

| Column | Type | Meaning |
| --- | --- | --- |
| `side` | `string` | buy or sell crossing direction |
| `requested_size` | `float64` | base asset size requested for the sweep |
| `filled_size` | `float64` | size covered by visible depth |
| `average_price` | `float64` | volume-weighted crossing price over visible levels |
| `midprice` | `float64` | snapshot midpoint before the sweep |
| `spread_cost_bps` | `float64` | half-spread component in basis points |
| `depth_cost_bps` | `float64` | additional depth component in basis points |
| `fee_bps` | `float64` | user-supplied fee assumption |
| `total_cost_bps` | `float64` | spread plus depth plus fee cost proxy |
| `assumption` | `string` | explicitly labels this as a visible-depth sweep cost proxy |
