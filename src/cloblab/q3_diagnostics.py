"""Past-activity slices and exact visible crossing from feature-cache identities."""
from __future__ import annotations

import numpy as np


def crossed_from_features(markout_bps, entry_spread_bps, exit_spread_bps, direction):
    """Exact bid/ask crossing identity, denominator = entry midpoint."""
    markout = np.asarray(markout_bps, dtype=float)
    entry = np.asarray(entry_spread_bps, dtype=float)
    exit_ = np.asarray(exit_spread_bps, dtype=float)
    side = np.asarray(direction, dtype=float)
    if not np.isin(side, (-1, 1)).all():
        raise ValueError("direction must be +1 or -1")
    gross = side*markout
    entry_half = entry/2
    exit_half = exit_/2*(1+markout/10000)
    return gross-entry_half-exit_half


def future_positions(event_index, segment, endpoints, horizon=20):
    event = np.asarray(event_index, dtype=np.int64)
    group = np.asarray(segment, dtype=np.int64)
    ends = np.asarray(endpoints, dtype=np.int64)
    future = np.searchsorted(event, event[ends]+horizon)
    in_bounds = future < len(event)
    valid = np.zeros(len(ends), dtype=bool)
    valid[in_bounds] = ((event[future[in_bounds]] == event[ends[in_bounds]]+horizon) &
                        (group[future[in_bounds]] == group[ends[in_bounds]]))
    return future, valid
