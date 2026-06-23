from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_order_book(
    *,
    rows: int = 120,
    levels: int = 3,
    symbol: str = "BTC-USD",
    start: str = "2026-01-01T00:00:00Z",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create deterministic public-safe fixture data.

    The sample is for pipeline and test reproducibility only. It is not market
    evidence and must not be described as alpha.
    """

    if rows <= 0 or levels <= 0:
        raise ValueError("rows and levels must be positive")

    times = pd.date_range(start, periods=rows, freq="1s")
    snapshots: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []

    for i, timestamp in enumerate(times):
        wave = np.sin(i / 7.0)
        drift = i * 0.03
        mid = 50_000.0 + drift + 4.0 * np.sin(i / 11.0)
        spread = 1.0 + 0.1 * (i % 4)
        row: dict[str, object] = {
            "exchange_ts": timestamp,
            "local_ts": timestamp,
            "symbol": symbol,
        }
        for level in range(1, levels + 1):
            distance = spread / 2.0 + (level - 1) * 0.75
            row[f"bid_px_{level}"] = mid - distance
            row[f"ask_px_{level}"] = mid + distance
            row[f"bid_sz_{level}"] = 6.0 + level + max(wave, 0.0) * 3.0 + (i % 3) * 0.25
            row[f"ask_sz_{level}"] = 6.0 + level + max(-wave, 0.0) * 3.0 + ((i + 1) % 3) * 0.25
        snapshots.append(row)

        side = "buy" if wave >= 0 else "sell"
        trades.append(
            {
                "exchange_ts": timestamp,
                "local_ts": timestamp,
                "symbol": symbol,
                "trade_id": i + 1,
                "side": side,
                "price": row["ask_px_1"] if side == "buy" else row["bid_px_1"],
                "size": 0.1 + abs(wave) * 0.5,
            }
        )

    return pd.DataFrame(snapshots), pd.DataFrame(trades)

