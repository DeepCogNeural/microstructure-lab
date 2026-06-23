from __future__ import annotations

TABLE_SCHEMAS: dict[str, list[tuple[str, str, str]]] = {
    "order_book_snapshots": [
        ("exchange_ts", "timestamp[ns, UTC]", "exchange or source timestamp for the book observation"),
        ("local_ts", "timestamp[ns, UTC]", "local receipt or sample timestamp used as the decision time"),
        ("symbol", "string", "exchange product id such as BTC-USD"),
        ("bid_px_1..N", "float64", "bid price by book level; level 1 is best bid"),
        ("bid_sz_1..N", "float64", "bid displayed size by book level"),
        ("ask_px_1..N", "float64", "ask price by book level; level 1 is best ask"),
        ("ask_sz_1..N", "float64", "ask displayed size by book level"),
    ],
    "order_book_deltas": [
        ("exchange_ts", "timestamp[ns, UTC]", "exchange event timestamp when provided"),
        ("local_ts", "timestamp[ns, UTC]", "local receipt timestamp"),
        ("symbol", "string", "exchange product id"),
        ("sequence", "int64", "exchange sequence number when provided"),
        ("side", "string", "bid/buy or ask/sell side from the source event"),
        ("price", "float64", "price level being updated"),
        ("size", "float64", "new displayed size at that price level; zero means remove"),
        ("source_channel", "string", "for example level2_batch"),
    ],
    "trades": [
        ("exchange_ts", "timestamp[ns, UTC]", "exchange trade timestamp"),
        ("local_ts", "timestamp[ns, UTC]", "local receipt timestamp"),
        ("symbol", "string", "exchange product id"),
        ("trade_id", "string", "source trade id if provided"),
        ("side", "string", "source trade side field; interpretation is exchange-specific"),
        ("price", "float64", "trade price"),
        ("size", "float64", "trade size in base asset units"),
    ],
    "midprices": [
        ("exchange_ts", "timestamp[ns, UTC]", "source timestamp carried from snapshot"),
        ("local_ts", "timestamp[ns, UTC]", "decision timestamp"),
        ("symbol", "string", "exchange product id"),
        ("best_bid", "float64", "best bid price"),
        ("best_ask", "float64", "best ask price"),
        ("midprice", "float64", "(best_bid + best_ask) / 2"),
        ("spread", "float64", "best_ask - best_bid"),
        ("spread_bps", "float64", "spread divided by midprice, in basis points"),
    ],
    "features": [
        ("exchange_ts", "timestamp[ns, UTC]", "source timestamp carried from snapshot"),
        ("local_ts", "timestamp[ns, UTC]", "decision timestamp"),
        ("symbol", "string", "exchange product id"),
        ("midprice", "float64", "current midprice, included for label construction and diagnostics"),
        ("spread_bps", "float64", "current spread in basis points"),
        ("top_imbalance", "float64", "(best_bid_size - best_ask_size) / total top size"),
        ("depth_imbalance", "float64", "same imbalance over configured depth levels"),
        ("recent_trade_imbalance", "float64", "past-window buy/sell trade-size imbalance"),
    ],
    "labels": [
        ("local_ts", "timestamp[ns, UTC]", "decision timestamp; joins to feature row"),
        ("symbol", "string", "exchange product id"),
        ("future_ts_{horizon}s", "timestamp[ns, UTC]", "first midprice timestamp at or after local_ts + horizon"),
        ("future_midprice_{horizon}s", "float64", "future midprice used only as the supervised label"),
        ("markout_{horizon}s", "float64", "future_midprice - current_midprice"),
        ("markout_bps_{horizon}s", "float64", "markout divided by current midprice, in basis points"),
        ("direction_{horizon}s", "float64", "sign of the markout"),
    ],
}


def render_schema_markdown() -> str:
    lines = ["# Data Schema", ""]
    for table_name, columns in TABLE_SCHEMAS.items():
        lines.extend([f"## {table_name}", "", "| Column | Type | Meaning |", "| --- | --- | --- |"])
        for column, dtype, meaning in columns:
            lines.append(f"| `{column}` | `{dtype}` | {meaning} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

