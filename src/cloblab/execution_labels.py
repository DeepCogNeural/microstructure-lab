"""Visible crossed-book outcomes at exact original-message offsets."""
import numpy as np
import pandas as pd


def crossed_labels(snapshots, horizon, latency):
    if horizon <= 0 or latency < 0 or int(horizon) != horizon or int(latency) != latency:
        raise ValueError("require positive integer horizon and nonnegative integer latency")
    keys = ["symbol", "day", "segment"]
    identity = keys + ["event_index"]
    if snapshots.duplicated(identity).any():
        raise ValueError("duplicate quote identity")
    groups = snapshots.groupby(keys, sort=False)
    steps = groups.event_index.diff().dropna()
    if not steps.eq(1).all():
        raise ValueError("event gaps require separate segments")
    quotes = snapshots[["bid_px_1", "ask_px_1"]].to_numpy()
    if not np.isfinite(quotes).all() or (quotes[:, 0] <= 0).any() or (quotes[:, 1] <= quotes[:, 0]).any():
        raise ValueError("invalid visible book")
    entry = groups[["bid_px_1", "ask_px_1", "event_index"]].shift(-latency)
    future = groups[["bid_px_1", "ask_px_1", "event_index"]].shift(-(latency + horizon))
    valid = ((entry.event_index == snapshots.event_index + latency) &
             (future.event_index == snapshots.event_index + latency + horizon))
    mid = (entry.bid_px_1 + entry.ask_px_1) / 2
    out = snapshots[identity + ["timestamp_ns"]].copy()
    out["long_crossed_bps"] = (1e4 * (future.bid_px_1-entry.ask_px_1) / mid).where(valid)
    out["short_crossed_bps"] = (1e4 * (entry.bid_px_1-future.ask_px_1) / mid).where(valid)
    return out
