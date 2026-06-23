from __future__ import annotations

import numpy as np
import pandas as pd


def build_markout_labels(
    features: pd.DataFrame,
    *,
    horizons_seconds: tuple[int, ...] = (1, 5, 10, 60),
    time_col: str = "local_ts",
    price_col: str = "midprice",
) -> pd.DataFrame:
    """Attach future-midprice markout labels.

    Future midprice is used only as the supervised label. It is not used by
    `build_features`.
    """

    required = {"symbol", time_col, price_col}
    missing = sorted(required.difference(features.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    output = features.copy()
    output[time_col] = pd.to_datetime(output[time_col], utc=True)
    output = output.sort_values(["symbol", time_col]).reset_index(drop=True)

    for horizon in horizons_seconds:
        output[f"future_ts_{horizon}s"] = pd.Series(pd.NaT, index=output.index, dtype="datetime64[ns, UTC]")
        output[f"future_midprice_{horizon}s"] = np.nan
        output[f"markout_{horizon}s"] = np.nan
        output[f"markout_bps_{horizon}s"] = np.nan
        output[f"direction_{horizon}s"] = np.nan

    for _, group in output.groupby("symbol", sort=False):
        positions = group.index.to_numpy()
        times = group[time_col].to_numpy(dtype="datetime64[ns]")
        prices = group[price_col].astype(float).to_numpy()
        for horizon in horizons_seconds:
            target_times = (group[time_col] + pd.Timedelta(seconds=horizon)).to_numpy(dtype="datetime64[ns]")
            future_positions = np.searchsorted(times, target_times, side="left")
            valid = future_positions < len(group)
            future_prices = np.full(len(group), np.nan)
            future_times = np.full(len(group), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
            future_prices[valid] = prices[future_positions[valid]]
            future_times[valid] = times[future_positions[valid]]

            markout = future_prices - prices
            markout_bps = markout / prices * 10_000.0
            output.loc[positions, f"future_midprice_{horizon}s"] = future_prices
            output.loc[positions, f"markout_{horizon}s"] = markout
            output.loc[positions, f"markout_bps_{horizon}s"] = markout_bps
            output.loc[positions, f"direction_{horizon}s"] = np.sign(markout)
            output.loc[positions[valid], f"future_ts_{horizon}s"] = pd.to_datetime(
                future_times[valid],
                utc=True,
            )

    return output
