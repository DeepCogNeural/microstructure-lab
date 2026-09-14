from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

import pandas as pd
from sortedcontainers import SortedDict


@dataclass(frozen=True)
class ReplayResult:
    snapshots: pd.DataFrame


class L2Book:
    """Deterministic aggregate L2 book keyed by integer ticks and lots."""

    def __init__(self, *, symbol: str, tick_size: str = "0.01", lot_size: str = "0.00000001") -> None:
        self.symbol = symbol
        self.tick_size = Decimal(tick_size)
        self.lot_size = Decimal(lot_size)
        self.bids: SortedDict[int, int] = SortedDict()
        self.asks: SortedDict[int, int] = SortedDict()

    def apply_level(self, side: str, price: str | float, size: str | float) -> None:
        self.apply_levels([(side, price, size)])

    def apply_levels(self, levels: Iterable[tuple[str, str | float, str | float]]) -> None:
        """Apply one source message atomically, then validate the resulting book."""

        for side, price, size in levels:
            self._apply_level_unchecked(side, price, size)
        self._validate_uncrossed()

    def _apply_level_unchecked(self, side: str, price: str | float, size: str | float) -> None:
        side_key = _normalize_side(side)
        price_ticks = _to_units(price, self.tick_size)
        size_lots = _to_units(size, self.lot_size)
        if size_lots < 0:
            raise ValueError("negative book level size")

        book_side = self.bids if side_key == "bid" else self.asks
        if size_lots == 0:
            book_side.pop(price_ticks, None)
        else:
            book_side[price_ticks] = size_lots

    def best_bid_ticks(self) -> int | None:
        return self.bids.peekitem(-1)[0] if self.bids else None

    def best_ask_ticks(self) -> int | None:
        return self.asks.peekitem(0)[0] if self.asks else None

    def to_snapshot_row(self, *, include_state_hash: bool = True) -> dict[str, object]:
        best_bid = self.best_bid_ticks()
        best_ask = self.best_ask_ticks()
        row: dict[str, object] = {
            "symbol": self.symbol,
            "best_bid": _from_units(best_bid, self.tick_size) if best_bid is not None else None,
            "best_ask": _from_units(best_ask, self.tick_size) if best_ask is not None else None,
        }
        if include_state_hash:
            row["state_hash"] = self.state_hash()
        bid_levels = (self.bids.peekitem(-offset) for offset in range(1, min(10, len(self.bids)) + 1))
        ask_levels = (self.asks.peekitem(offset) for offset in range(min(10, len(self.asks))))
        for level, (price_ticks, size_lots) in enumerate(bid_levels, start=1):
            row[f"bid_px_{level}"] = _from_units(price_ticks, self.tick_size)
            row[f"bid_sz_{level}"] = _from_units(size_lots, self.lot_size)
        for level, (price_ticks, size_lots) in enumerate(ask_levels, start=1):
            row[f"ask_px_{level}"] = _from_units(price_ticks, self.tick_size)
            row[f"ask_sz_{level}"] = _from_units(size_lots, self.lot_size)
        return row

    def state_hash(self) -> str:
        encoded = repr((list(self.bids.items()), list(self.asks.items()))).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_uncrossed(self) -> None:
        best_bid = self.best_bid_ticks()
        best_ask = self.best_ask_ticks()
        if best_bid is not None and best_ask is not None and best_bid >= best_ask:
            raise ValueError("crossed book")


def replay_l2_events(
    events: pd.DataFrame,
    *,
    tick_size: str = "0.01",
    lot_size: str = "0.00000001",
) -> ReplayResult:
    required = {"exchange_ts", "local_ts", "symbol", "sequence", "side", "price", "size"}
    missing = sorted(required.difference(events.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    ordered = events.copy()
    ordered["exchange_ts"] = pd.to_datetime(ordered["exchange_ts"], utc=True)
    ordered["local_ts"] = pd.to_datetime(ordered["local_ts"], utc=True)
    ordered = ordered.sort_values(["symbol", "sequence", "local_ts"]).reset_index(drop=True)

    books: dict[str, L2Book] = {}
    last_sequence: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    for receive_index, row in enumerate(ordered.itertuples(index=False), start=1):
        symbol = str(row.symbol)
        sequence = int(row.sequence)
        previous = last_sequence.get(symbol)
        if previous is not None and sequence != previous + 1:
            raise ValueError(f"sequence gap for {symbol}: expected {previous + 1}, got {sequence}")
        last_sequence[symbol] = sequence

        book = books.setdefault(symbol, L2Book(symbol=symbol, tick_size=tick_size, lot_size=lot_size))
        book.apply_level(str(row.side), row.price, row.size)
        snapshot = book.to_snapshot_row()
        snapshot.update(
            {
                "exchange_ts": row.exchange_ts,
                "local_ts": row.local_ts,
                "local_receive_index": receive_index,
                "sequence": sequence,
            }
        )
        rows.append(snapshot)
    return ReplayResult(snapshots=pd.DataFrame(rows))


def _normalize_side(side: str) -> str:
    value = side.lower()
    if value in {"bid", "buy", "bids"}:
        return "bid"
    if value in {"ask", "sell", "asks"}:
        return "ask"
    raise ValueError(f"unknown side: {side}")


def _to_units(value: str | float | int | Decimal, quantum: Decimal) -> int:
    decimal_value = Decimal(str(value))
    return int((decimal_value / quantum).to_integral_value(rounding=ROUND_HALF_UP))


def _from_units(units: int | None, quantum: Decimal) -> float | None:
    if units is None:
        return None
    return float(Decimal(units) * quantum)
