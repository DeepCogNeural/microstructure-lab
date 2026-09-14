from __future__ import annotations

import numpy as np
import pandas as pd


def add_microstructure_features(
    frame: pd.DataFrame,
    *,
    bid_px_col: str = "bid_px_1",
    ask_px_col: str = "ask_px_1",
    bid_sz_col: str = "bid_sz_1",
    ask_sz_col: str = "ask_sz_1",
    bid_px_prev_col: str | None = None,
    ask_px_prev_col: str | None = None,
    bid_sz_prev_col: str | None = None,
    ask_sz_prev_col: str | None = None,
) -> pd.DataFrame:
    """Add causal top-of-book microprice and event-style OFI features.

    Inputs must be aligned to information known at the current decision time.
    When explicit previous-state columns are omitted, the function uses a
    one-row lag of the current top-of-book columns.
    """

    out = frame.copy()
    bid_px = out[bid_px_col].astype(float)
    ask_px = out[ask_px_col].astype(float)
    bid_sz = out[bid_sz_col].astype(float)
    ask_sz = out[ask_sz_col].astype(float)

    denom = bid_sz + ask_sz
    out["midpoint"] = (bid_px + ask_px) / 2.0
    out["spread"] = ask_px - bid_px
    out["microprice"] = np.where(
        denom > 0,
        (ask_px * bid_sz + bid_px * ask_sz) / denom,
        out["midpoint"],
    )
    out["microprice_minus_mid_bps"] = np.where(
        out["midpoint"] != 0,
        1e4 * (out["microprice"] - out["midpoint"]) / out["midpoint"],
        np.nan,
    )

    prev_bid_px = out[bid_px_prev_col].astype(float) if bid_px_prev_col else bid_px.shift(1)
    prev_ask_px = out[ask_px_prev_col].astype(float) if ask_px_prev_col else ask_px.shift(1)
    prev_bid_sz = out[bid_sz_prev_col].astype(float) if bid_sz_prev_col else bid_sz.shift(1)
    prev_ask_sz = out[ask_sz_prev_col].astype(float) if ask_sz_prev_col else ask_sz.shift(1)

    bid_flow = np.select(
        [bid_px > prev_bid_px, bid_px == prev_bid_px, bid_px < prev_bid_px],
        [bid_sz, bid_sz - prev_bid_sz, -prev_bid_sz],
        default=np.nan,
    )
    ask_flow = np.select(
        [ask_px < prev_ask_px, ask_px == prev_ask_px, ask_px > prev_ask_px],
        [ask_sz, ask_sz - prev_ask_sz, -prev_ask_sz],
        default=np.nan,
    )
    out["ofi_l1"] = bid_flow - ask_flow
    out["ofi_l1_norm"] = np.where(denom > 0, out["ofi_l1"] / denom, np.nan)
    return out


def add_rolling_activity_features(
    frame: pd.DataFrame,
    *,
    time_col: str = "local_ts",
    trade_sign_col: str = "trade_sign",
    trade_size_col: str = "trade_size",
    window: str = "5s",
) -> pd.DataFrame:
    """Add backward-looking trade-flow and event-intensity features."""

    out = frame.copy().sort_values(time_col)
    ts = pd.to_datetime(out[time_col], utc=True)
    signed_size = out[trade_sign_col].astype(float) * out[trade_size_col].astype(float)
    temp = pd.DataFrame(
        {
            time_col: ts,
            "signed_size": signed_size,
            "trade_size": out[trade_size_col].astype(float),
            "event": 1.0,
        },
        index=out.index,
    ).set_index(time_col)
    rolled = temp.rolling(window, closed="both")
    signed = rolled["signed_size"].sum().to_numpy()
    total = rolled["trade_size"].sum().to_numpy()
    out[f"trade_imbalance_{window}"] = np.where(total > 0, signed / total, 0.0)
    out[f"trade_intensity_{window}"] = rolled["event"].sum().to_numpy()
    return out


def add_causal_trade_activity_features(
    frame: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    time_col: str = "local_ts",
    symbol_col: str = "symbol",
    trade_time_col: str = "local_ts",
    trade_symbol_col: str = "symbol",
    trade_side_col: str = "side",
    trade_size_col: str = "size",
    window: str = "5s",
) -> pd.DataFrame:
    """Align backward-looking trade imbalance and intensity to decision rows."""

    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True)
    imbalance = pd.Series(0.0, index=out.index)
    intensity = pd.Series(0.0, index=out.index)
    if trades.empty:
        out[f"trade_imbalance_{window}"] = imbalance
        out[f"trade_intensity_{window}"] = intensity
        return out

    trade_frame = trades.copy()
    trade_frame[trade_time_col] = pd.to_datetime(trade_frame[trade_time_col], utc=True)
    trade_frame[trade_side_col] = trade_frame[trade_side_col].astype(str).str.lower()
    trade_frame[trade_size_col] = pd.to_numeric(trade_frame[trade_size_col], errors="coerce").fillna(0.0)
    window_delta = pd.Timedelta(window)

    for symbol, decision_group in out.groupby(symbol_col, sort=False):
        decisions = decision_group.sort_values(time_col, kind="stable")
        symbol_trades = trade_frame[trade_frame[trade_symbol_col] == symbol].sort_values(
            trade_time_col,
            kind="stable",
        )
        trade_times = symbol_trades[trade_time_col].tolist()
        trade_sides = symbol_trades[trade_side_col].tolist()
        trade_sizes = symbol_trades[trade_size_col].astype(float).tolist()
        left = 0
        right = 0
        buy_size = 0.0
        sell_size = 0.0
        for decision_index, decision_ts in decisions[time_col].items():
            while right < len(trade_times) and trade_times[right] <= decision_ts:
                if trade_sides[right] == "buy":
                    buy_size += trade_sizes[right]
                elif trade_sides[right] == "sell":
                    sell_size += trade_sizes[right]
                right += 1
            window_start = decision_ts - window_delta
            while left < right and trade_times[left] <= window_start:
                if trade_sides[left] == "buy":
                    buy_size -= trade_sizes[left]
                elif trade_sides[left] == "sell":
                    sell_size -= trade_sizes[left]
                left += 1
            total_size = buy_size + sell_size
            imbalance.loc[decision_index] = (buy_size - sell_size) / total_size if total_size > 0 else 0.0
            intensity.loc[decision_index] = float(right - left)

    out[f"trade_imbalance_{window}"] = imbalance
    out[f"trade_intensity_{window}"] = intensity
    return out
