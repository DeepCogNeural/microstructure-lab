"""Causal PM1A fixed-cadence opportunities from public token-book snapshots."""
from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timedelta
import math
from typing import Any, Mapping, Sequence

import numpy as np

from cloblab.polymarket_l2 import audit_snapshot

FEATURES = (
    'logit_midpoint', 'spread', 'best_bid_size', 'best_ask_size',
    'top_level_imbalance', 'five_level_bid_depth', 'five_level_ask_depth',
    'five_level_imbalance', 'log_total_visible_depth', 'log_seconds_to_close',
    'capture_age_seconds',
)


def _imbalance(bid: float, ask: float) -> float:
    return (bid - ask) / (bid + ask) if bid + ask > 0 else 0.0


def book_features(row: Mapping[str, Any], decision: datetime, market_end: datetime,
                  probability_clip: float = 1e-4) -> tuple[float, np.ndarray]:
    """Return current midpoint and eleven state/history features; reject invalid books."""
    if not audit_snapshot(row).valid_midpoint:
        raise ValueError('no valid two-sided midpoint')
    captured = row['captured_at']
    age = (decision - captured).total_seconds()
    remaining = (market_end - captured).total_seconds()
    if age < 0 or remaining <= 0:
        raise ValueError('future or post-close snapshot')
    bp, bs, ap, ass = (row[k] for k in ('bid_prices','bid_sizes','ask_prices','ask_sizes'))
    mid = (bp[0] + ap[0]) / 2
    p = min(1 - probability_clip, max(probability_clip, mid))
    b5, a5 = sum(bs[:5]), sum(ass[:5])
    vals = np.asarray([
        math.log(p / (1 - p)), ap[0] - bp[0], bs[0], ass[0],
        _imbalance(bs[0], ass[0]), b5, a5, _imbalance(b5, a5),
        math.log1p(sum(bs) + sum(ass)), math.log1p(remaining), age,
    ], dtype=np.float32)
    if not np.isfinite(vals).all():
        raise ValueError('nonfinite PM1A feature')
    return float(mid), vals


def select_opportunity(rows: Sequence[Mapping[str, Any]], times: Sequence[datetime],
                       decision: datetime, market_end: datetime,
                       *, history_length: int, max_age: float,
                       max_lookback: float, probability_clip: float) -> tuple[float, np.ndarray] | None:
    """Select the latest available capture and exactly the preceding distinct rows."""
    j = bisect_right(times, decision) - 1
    if j < history_length - 1 or (decision - times[j]).total_seconds() > max_age:
        return None
    start = j - history_length + 1
    if (decision - times[start]).total_seconds() > max_lookback:
        return None
    chosen = rows[start:j + 1]
    if any(not audit_snapshot(row).valid_midpoint for row in chosen):
        return None
    p, _ = book_features(chosen[-1], decision, market_end, probability_clip)
    history = np.stack([book_features(row, decision, market_end, probability_clip)[1]
                        for row in chosen])
    return p, history


def market_opportunities(rows: Sequence[Mapping[str, Any]], *, decision_step: int,
                         min_seconds_to_close: int, history_length: int,
                         max_age: float, max_lookback: float,
                         probability_clip: float) -> list[tuple[datetime, float, np.ndarray]]:
    if not rows:
        return []
    rows = sorted(rows, key=lambda row: row['captured_at'])
    times = [row['captured_at'] for row in rows]
    if len(set(times)) != len(times):
        raise ValueError('duplicate market/token capture')
    market_end = rows[0]['market_end_at']
    if any(row['market_end_at'] != market_end for row in rows):
        raise ValueError('inconsistent market end')
    max_steps = math.ceil((market_end - times[0]).total_seconds() / decision_step)
    out = []
    for step in range(math.ceil(min_seconds_to_close / decision_step), max_steps + 1):
        decision = market_end - timedelta(seconds=decision_step * step)
        if decision < times[0]:
            break
        selected = select_opportunity(rows, times, decision, market_end,
                                      history_length=history_length, max_age=max_age,
                                      max_lookback=max_lookback,
                                      probability_clip=probability_clip)
        if selected is not None:
            out.append((decision, *selected))
    return out
