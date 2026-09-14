"""Conditional depletion diagnostics, not identified historical fills.

Vectorized independent virtual orders join after their placement message. All
D removals and same-price M reductions are assumed executions in this scenario.
No execution is inferred from Y, repricing, or aggregate depth alone.
"""
import numpy as np


def passive_paths(events, placements, side, horizon, unit=1, tick=.01, decision_latency=0):
    if horizon not in (10, 20, 50) or unit != 1 or np.any(np.asarray(tick) <= 0) or side not in (1, 2):
        raise ValueError('unsupported frozen policy')
    p = np.asarray(placements, dtype=np.int64)
    n = len(events['valid'])
    if (p < 0).any() or (p >= n).any() or not events['valid'][p].all():
        raise ValueError('invalid placement')
    direction = 1 if side == 1 else -1
    price = events['bid' if side == 1 else 'ask'][p]
    ahead = events['bid_size' if side == 1 else 'ask_size'][p].astype(float).copy()
    initial = ahead.copy()
    orders = events['bid_orders' if side == 1 else 'ask_orders'][p]
    entry_mid = (events['bid'][p]+events['ask'][p])/2
    fill = np.full(len(p), -1, dtype=np.int64)
    adverse = np.full(len(p), -1, dtype=np.int64)
    alive = np.ones(len(p), bool)
    for offset in range(1, horizon+1):
        j = np.minimum(p+offset, n-1)
        same = (p+offset < n) & events['valid'][j] & (events['segment'][j] == events['segment'][p])
        alive &= same
        mid = (events['bid'][j]+events['ask'][j])/2
        hit = alive & (adverse < 0) & (direction*(mid-entry_mid) <= -tick+1e-10)
        adverse[hit] = offset
        active = alive & (fill < 0)
        old_here = (events['old_side'][j] == side) & (events['old_price'][j] == price)
        was_ahead = old_here & (events['old_entered'][j] <= p)
        # Only an assumed execution against an order BEHIND the virtual order
        # can supply the extra unit after all original ahead orders leave.
        executed = active & old_here & ~was_ahead & (ahead <= 0) & (events['execution'][j] >= unit)
        fill[executed] = offset
        old_quantity = np.where(was_ahead, events['old_quantity'][j], 0)
        still_ahead = (events['new_side'][j] == side) & (events['new_price'][j] == price) & (events['new_entered'][j] <= p)
        new_quantity = np.where(still_ahead, events['new_quantity'][j], 0)
        ahead += np.where(active, new_quantity-old_quantity, 0)
        if (ahead[active] < -1e-8).any():
            raise ValueError('negative virtual queue ahead')
    result = {'queue_ahead': initial, 'orders_ahead': orders, 'fill_time': fill,
              'adverse_time': adverse, 'placement_price': price,
              'fill_before_adverse': (fill > 0) & ((adverse < 0) | (fill < adverse)),
              'adverse_before_fill': (adverse > 0) & ((fill < 0) | (adverse < fill)),
              'simultaneous': (fill > 0) & (fill == adverse)}
    fi = np.minimum(p+np.maximum(fill, 0), n-1)
    fill_mid = (events['bid'][fi]+events['ask'][fi])/2
    for offset in (1, 5, 10, 'remaining'):
        future = p+horizon-decision_latency if offset == 'remaining' else fi+offset
        idx = np.minimum(future, n-1)
        valid = (fill > 0) & (future >= fi) & (future < n) & events['valid'][idx] & (events['segment'][idx] == events['segment'][p])
        mid = (events['bid'][idx]+events['ask'][idx])/2
        result[f'markout_{offset}'] = np.where(valid, direction*(mid-fill_mid)/fill_mid*1e4, np.nan)
        result[f'spread_{offset}'] = np.where(valid, 2*direction*(mid-price)/price*1e4, np.nan)
    return result
