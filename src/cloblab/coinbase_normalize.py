from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from cloblab.book import L2Book, ReplayResult


BOOK_COLUMNS = [
    "event_ts",
    "exchange_ts",
    "local_ts",
    "product_id",
    "symbol",
    "sequence",
    "local_receive_index",
    "event_change_index",
    "event_type",
    "side",
    "price",
    "size",
    "source_channel",
]
TRADE_COLUMNS = [
    "event_ts",
    "exchange_ts",
    "local_ts",
    "product_id",
    "symbol",
    "sequence",
    "local_receive_index",
    "trade_id",
    "price",
    "size",
    "maker_side",
    "source_side",
    "aggressor_sign",
    "side",
]


def normalize_coinbase_jsonl(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize Coinbase Exchange level2/match JSONL captured by the collector.

    Returns `(book_events, trades)`. Unknown/control messages are ignored.
    Sequence is preserved when supplied by the venue. Timestamps are parsed as
    UTC; no future information is introduced.
    """

    with Path(path).open("r", encoding="utf-8") as handle:
        return normalize_coinbase_messages(json.loads(line) for line in handle if line.strip())


def normalize_coinbase_messages(messages: Iterable[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    book_rows: list[dict] = []
    trade_rows: list[dict] = []

    for receive_index, record in enumerate(messages, start=1):
        msg, local_ts = _unwrap_capture_record(record)
        typ = msg.get("type")
        product = msg.get("product_id")
        ts = msg.get("time")
        seq = msg.get("sequence")

        if typ == "snapshot":
            change_index = 0
            for side_name, levels in (("buy", msg.get("bids", [])), ("sell", msg.get("asks", []))):
                for price, size, *_ in levels:
                    change_index += 1
                    book_rows.append(
                        {
                            "event_ts": ts,
                            "exchange_ts": ts,
                            "local_ts": local_ts or ts,
                            "product_id": product,
                            "symbol": product,
                            "sequence": seq,
                            "local_receive_index": receive_index,
                            "event_change_index": change_index,
                            "event_type": "snapshot",
                            "side": side_name,
                            "price": float(price),
                            "size": float(size),
                            "source_channel": "level2_batch",
                        }
                    )
        elif typ == "l2update":
            for change_index, (side_name, price, size, *_) in enumerate(msg.get("changes", []), start=1):
                book_rows.append(
                    {
                        "event_ts": ts,
                        "exchange_ts": ts,
                        "local_ts": local_ts or ts,
                        "product_id": product,
                        "symbol": product,
                        "sequence": seq,
                        "local_receive_index": receive_index,
                        "event_change_index": change_index,
                        "event_type": "l2update",
                        "side": side_name,
                        "price": float(price),
                        "size": float(size),
                        "source_channel": "level2_batch",
                    }
                )
        elif typ == "match":
            maker_side = msg.get("side")
            aggressor_sign = 1 if maker_side == "sell" else -1 if maker_side == "buy" else 0
            aggressor_side = "buy" if aggressor_sign == 1 else "sell" if aggressor_sign == -1 else None
            trade_rows.append(
                {
                    "event_ts": ts,
                    "exchange_ts": ts,
                    "local_ts": local_ts or ts,
                    "product_id": product,
                    "symbol": product,
                    "sequence": seq,
                    "local_receive_index": receive_index,
                    "trade_id": msg.get("trade_id"),
                    "price": float(msg["price"]),
                    "size": float(msg["size"]),
                    "maker_side": maker_side,
                    "source_side": maker_side,
                    "aggressor_sign": aggressor_sign,
                    "side": aggressor_side,
                }
            )

    books = pd.DataFrame(book_rows, columns=BOOK_COLUMNS)
    trades = pd.DataFrame(trade_rows, columns=TRADE_COLUMNS)
    for frame in (books, trades):
        if not frame.empty:
            for time_col in ("event_ts", "exchange_ts", "local_ts"):
                frame[time_col] = pd.to_datetime(frame[time_col], utc=True)
            sort_cols = ["local_receive_index"]
            if "event_change_index" in frame.columns:
                sort_cols.append("event_change_index")
            frame.sort_values(sort_cols, inplace=True)
            frame.reset_index(drop=True, inplace=True)
    return books, trades


def replay_coinbase_book_events(
    events: pd.DataFrame,
    *,
    tick_size: str = "0.01",
    lot_size: str = "0.00000001",
) -> ReplayResult:
    """Replay normalized Coinbase L2 batches in local receipt order.

    Coinbase's level2_batch messages do not carry a usable sequence number.
    Each message is therefore applied atomically in captured receipt order.
    A fresh snapshot is required before updates for every symbol.
    """

    required = {
        "exchange_ts",
        "local_ts",
        "symbol",
        "local_receive_index",
        "event_change_index",
        "event_type",
        "side",
        "price",
        "size",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if events.empty:
        return ReplayResult(snapshots=pd.DataFrame())

    ordered = events.copy()
    ordered["exchange_ts"] = pd.to_datetime(ordered["exchange_ts"], utc=True)
    ordered["local_ts"] = pd.to_datetime(ordered["local_ts"], utc=True)
    ordered = ordered.sort_values(
        ["symbol", "local_receive_index", "event_change_index"],
        kind="stable",
    )
    rows: list[dict[str, object]] = []
    for symbol, symbol_events in ordered.groupby("symbol", sort=False):
        book: L2Book | None = None
        previous_receive_index: int | None = None
        grouped = symbol_events.groupby("local_receive_index", sort=True)
        for receive_index, message_events in grouped:
            current_receive_index = int(receive_index)
            if previous_receive_index is not None and current_receive_index <= previous_receive_index:
                raise ValueError(f"non-monotonic local receipt order for {symbol}")
            previous_receive_index = current_receive_index

            event_types = set(message_events["event_type"].astype(str))
            if len(event_types) != 1:
                raise ValueError(f"mixed Coinbase event types at receipt index {current_receive_index}")
            event_type = next(iter(event_types))
            if event_type == "snapshot":
                book = L2Book(symbol=str(symbol), tick_size=tick_size, lot_size=lot_size)
            elif book is None:
                raise ValueError(f"Coinbase update before snapshot for {symbol}")

            assert book is not None
            book.apply_levels(
                (str(row.side), row.price, row.size)
                for row in message_events.itertuples(index=False)
            )
            snapshot = book.to_snapshot_row(include_state_hash=False)
            first = message_events.iloc[0]
            snapshot.update(
                {
                    "exchange_ts": first["exchange_ts"],
                    "local_ts": first["local_ts"],
                    "local_receive_index": current_receive_index,
                    "sequence": first.get("sequence"),
                    "source_event_type": event_type,
                }
            )
            rows.append(snapshot)
    snapshots = pd.DataFrame(rows).sort_values(["symbol", "local_receive_index"], kind="stable")
    snapshots.reset_index(drop=True, inplace=True)
    return ReplayResult(snapshots=snapshots)


def _unwrap_capture_record(record: dict) -> tuple[dict, object | None]:
    message = record.get("message")
    if isinstance(message, dict):
        return message, record.get("local_ts")
    return record, record.get("local_ts") or record.get("time")
