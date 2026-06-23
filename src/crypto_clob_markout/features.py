from __future__ import annotations

import pandas as pd


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def build_features(
    snapshots: pd.DataFrame,
    trades: pd.DataFrame | None = None,
    *,
    depth_levels: int = 3,
    recent_window: str | pd.Timedelta = "5s",
) -> pd.DataFrame:
    """Build no-lookahead book and trade features.

    `local_ts` is the decision timestamp. Every feature at that timestamp uses
    only the snapshot row and trades with `local_ts <= decision local_ts`.
    """

    _require_columns(
        snapshots,
        ["exchange_ts", "local_ts", "symbol", "bid_px_1", "bid_sz_1", "ask_px_1", "ask_sz_1"],
    )
    if depth_levels < 1:
        raise ValueError("depth_levels must be >= 1")

    book = snapshots.copy()
    book["exchange_ts"] = _to_utc(book["exchange_ts"])
    book["local_ts"] = _to_utc(book["local_ts"])
    book = book.sort_values(["symbol", "local_ts"]).reset_index(drop=True)

    for column in [c for c in book.columns if c.startswith(("bid_px_", "ask_px_", "bid_sz_", "ask_sz_"))]:
        book[column] = pd.to_numeric(book[column], errors="coerce")

    result = book[["exchange_ts", "local_ts", "symbol"]].copy()
    result["best_bid"] = book["bid_px_1"]
    result["best_ask"] = book["ask_px_1"]
    result["midprice"] = (book["bid_px_1"] + book["ask_px_1"]) / 2.0
    result["spread"] = book["ask_px_1"] - book["bid_px_1"]
    result["spread_bps"] = result["spread"] / result["midprice"] * 10_000.0
    result["top_imbalance"] = [
        _safe_ratio(bid - ask, bid + ask)
        for bid, ask in zip(book["bid_sz_1"].astype(float), book["ask_sz_1"].astype(float), strict=True)
    ]

    bid_depth = pd.Series(0.0, index=book.index)
    ask_depth = pd.Series(0.0, index=book.index)
    used_levels = 0
    for level in range(1, depth_levels + 1):
        bid_column = f"bid_sz_{level}"
        ask_column = f"ask_sz_{level}"
        if bid_column in book.columns and ask_column in book.columns:
            bid_depth = bid_depth + book[bid_column].fillna(0.0).astype(float)
            ask_depth = ask_depth + book[ask_column].fillna(0.0).astype(float)
            used_levels += 1
    if used_levels == 0:
        raise ValueError("no usable depth size columns found")

    result["bid_depth"] = bid_depth
    result["ask_depth"] = ask_depth
    result["depth_imbalance"] = [
        _safe_ratio(bid - ask, bid + ask)
        for bid, ask in zip(bid_depth.astype(float), ask_depth.astype(float), strict=True)
    ]

    buy_sizes, sell_sizes = _recent_trade_sizes(result, trades, recent_window)
    result["recent_trade_buy_size"] = buy_sizes
    result["recent_trade_sell_size"] = sell_sizes
    result["recent_trade_imbalance"] = [
        _safe_ratio(buy - sell, buy + sell)
        for buy, sell in zip(buy_sizes, sell_sizes, strict=True)
    ]
    return result


def _recent_trade_sizes(
    features: pd.DataFrame,
    trades: pd.DataFrame | None,
    recent_window: str | pd.Timedelta,
) -> tuple[list[float], list[float]]:
    if trades is None or trades.empty:
        return [0.0] * len(features), [0.0] * len(features)

    _require_columns(trades, ["local_ts", "symbol", "side", "size"])
    window = pd.Timedelta(recent_window)
    trade_frame = trades.copy()
    trade_frame["local_ts"] = _to_utc(trade_frame["local_ts"])
    trade_frame["side"] = trade_frame["side"].astype(str).str.lower()
    trade_frame["size"] = pd.to_numeric(trade_frame["size"], errors="coerce").fillna(0.0)

    buy_sizes: list[float] = []
    sell_sizes: list[float] = []
    for row in features[["local_ts", "symbol"]].itertuples(index=False):
        start = row.local_ts - window
        eligible = trade_frame[
            (trade_frame["symbol"] == row.symbol)
            & (trade_frame["local_ts"] <= row.local_ts)
            & (trade_frame["local_ts"] > start)
        ]
        buy_sizes.append(float(eligible.loc[eligible["side"] == "buy", "size"].sum()))
        sell_sizes.append(float(eligible.loc[eligible["side"] == "sell", "size"].sum()))
    return buy_sizes, sell_sizes

