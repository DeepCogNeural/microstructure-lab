"""Causal, event-identity-preserving windows for the WSELOB sequence study.

The input is the unfiltered per-day feature cache. A future markout never
participates in choosing historical tokens; it only makes an endpoint scorable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FEATURES = (
    "spread_bps", "top_imbalance", "depth_imbalance", "ofi_l1_norm",
    "microprice_minus_mid_bps",
)
IDENTITY = ("symbol", "day", "segment", "event_index", "timestamp_ns")
CONTEXT = 32


@dataclass(frozen=True)
class WindowIndex:
    """Indices into one immutable, original-order stock/day frame."""

    endpoints: np.ndarray
    scorable: np.ndarray
    counts: dict[str, int]


def index_day(frame: pd.DataFrame, context: int = CONTEXT) -> WindowIndex:
    if context < 1:
        raise ValueError("context must be positive")
    required = set(IDENTITY) | set(FEATURES) | {"markout_20"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    n = len(frame)
    if n == 0:
        return WindowIndex(np.empty(0, dtype=np.int64), np.empty(0, dtype=bool),
                           {"states": 0, "valid_windows": 0, "scorable": 0,
                            "short_or_broken": 0, "nonfinite_window": 0,
                            "unscorable_label": 0})
    if frame.symbol.nunique() != 1 or frame.day.nunique() != 1:
        raise ValueError("index one stock/day at a time")
    identity = frame[list(IDENTITY)]
    if identity.isna().any().any() or identity.duplicated(["symbol", "day", "event_index"]).any():
        raise ValueError("missing or duplicate event identity")
    event = frame.event_index.to_numpy(dtype=np.int64)
    segment = frame.segment.to_numpy(dtype=np.int64)
    timestamp = frame.timestamp_ns.to_numpy(dtype=np.int64)
    if np.any(np.diff(event) <= 0) or np.any(np.diff(timestamp) < 0):
        raise ValueError("source order or timestamps are not monotonic")
    features = frame[list(FEATURES)].to_numpy(dtype=np.float64)
    finite = np.isfinite(features).all(axis=1)
    # A run ends at an event gap, a segment boundary, or a nonfinite state.
    run = np.zeros(n, dtype=np.int64)
    for i in range(n):
        if finite[i]:
            if i and finite[i-1] and segment[i] == segment[i-1] and event[i] == event[i-1]+1:
                run[i] = run[i-1]+1
            else:
                run[i] = 1
    all_candidates = np.arange(n, dtype=np.int64)
    structural = np.zeros(n, dtype=bool)
    structural[context-1:] = True
    valid = run >= context
    endpoints = all_candidates[valid]
    labels = frame.markout_20.to_numpy(dtype=np.float64)
    scorable = np.isfinite(labels[endpoints])
    counts = {"states": n, "valid_windows": len(endpoints), "scorable": int(scorable.sum()),
              "short_or_broken": int((~structural).sum() + (structural & (run < context) & finite).sum()),
              "nonfinite_window": int((structural & (run < context) & ~finite).sum()),
              "unscorable_label": int((~scorable).sum())}
    return WindowIndex(endpoints, scorable, counts)


def window(frame: pd.DataFrame, endpoint: int, context: int = CONTEXT) -> np.ndarray:
    if endpoint < context-1 or endpoint >= len(frame):
        raise IndexError("endpoint has no complete context")
    return frame.iloc[endpoint-context+1:endpoint+1][list(FEATURES)].to_numpy(dtype=np.float32, copy=True)


def scoring_endpoints(frame: pd.DataFrame, index: WindowIndex, stride: int = 20) -> np.ndarray:
    if stride < 1:
        raise ValueError("stride must be positive")
    endpoints = index.endpoints[index.scorable]
    return endpoints[frame.event_index.to_numpy(dtype=np.int64)[endpoints] % stride == 0]
