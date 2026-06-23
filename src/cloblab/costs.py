from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SweepCost:
    side: str
    requested_size: float
    filled_size: float
    average_price: float
    midprice: float
    spread_cost_bps: float
    depth_cost_bps: float
    fee_bps: float
    total_cost_bps: float
    assumption: str = "visible_depth_sweep_cost_proxy"


def sweep_visible_depth(snapshot: pd.Series | dict[str, object], *, side: str, size: float, fee_bps: float = 0.0) -> SweepCost:
    """Cost proxy for crossing visible L2 depth.

    This is not a passive-fill or queue-position model.
    """

    if size <= 0:
        raise ValueError("size must be positive")
    row = dict(snapshot)
    side_key = side.lower()
    if side_key not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")

    price_prefix = "ask_px_" if side_key == "buy" else "bid_px_"
    size_prefix = "ask_sz_" if side_key == "buy" else "bid_sz_"
    levels: list[tuple[float, float]] = []
    for level in range(1, 51):
        price = row.get(f"{price_prefix}{level}")
        level_size = row.get(f"{size_prefix}{level}")
        if price is None or level_size is None or pd.isna(price) or pd.isna(level_size):
            continue
        levels.append((float(price), float(level_size)))
    if side_key == "sell":
        levels = sorted(levels, key=lambda item: item[0], reverse=True)
    else:
        levels = sorted(levels, key=lambda item: item[0])

    remaining = float(size)
    notional = 0.0
    filled = 0.0
    for price, available in levels:
        take = min(remaining, available)
        if take <= 0:
            continue
        notional += take * price
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled < size:
        raise ValueError("insufficient visible depth")

    average_price = notional / filled
    best_bid = float(row["best_bid"])
    best_ask = float(row["best_ask"])
    midprice = (best_bid + best_ask) / 2.0
    signed_cost = average_price - midprice if side_key == "buy" else midprice - average_price
    total_cost_bps = signed_cost / midprice * 10_000.0 + fee_bps
    spread_cost_bps = (best_ask - best_bid) / midprice * 10_000.0 / 2.0
    depth_cost_bps = max(0.0, total_cost_bps - spread_cost_bps - fee_bps)
    return SweepCost(
        side=side_key,
        requested_size=float(size),
        filled_size=filled,
        average_price=average_price,
        midprice=midprice,
        spread_cost_bps=spread_cost_bps,
        depth_cost_bps=depth_cost_bps,
        fee_bps=float(fee_bps),
        total_cost_bps=total_cost_bps,
    )

