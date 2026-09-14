"""Explicit decision, order, fill and observable-outcome denominators."""
import numpy as np
import pandas as pd


def summarize(frame):
    n = len(frame)
    if not n:
        raise ValueError('empty decision block')
    placed = frame.direction != 0
    filled = placed & (frame.fill_time > 0)
    output = {'eligible_decisions': n, 'placed_orders': int(placed.sum()),
              'zero_signal_decisions': int((~placed).sum()), 'fills': int(filled.sum()),
              'fill_probability': float(filled.mean()), 'unfilled_fraction': float((placed & ~filled).mean()),
              'mean_fill_time': frame.loc[filled, 'fill_time'].mean(),
              'median_fill_time': frame.loc[filled, 'fill_time'].median(),
              'median_queue_ahead': frame.loc[placed, 'queue_ahead'].median(),
              'mean_queue_ahead': frame.loc[placed, 'queue_ahead'].mean(),
              'queue_ahead_p10': frame.loc[placed, 'queue_ahead'].quantile(.1),
              'queue_ahead_p90': frame.loc[placed, 'queue_ahead'].quantile(.9)}
    for key in ('fill_before_adverse', 'adverse_before_fill', 'simultaneous'):
        output[key] = float((placed & frame[key].astype(bool)).mean())
    output['no_event_fraction'] = 1-sum(output[k] for k in ('fill_before_adverse', 'adverse_before_fill', 'simultaneous'))
    for offset in (1, 5, 10, 'remaining'):
        for prefix in ('markout', 'spread'):
            key = f'{prefix}_{offset}'
            output[key] = frame.loc[filled, key].mean()
            output[key+'_observations'] = int(frame.loc[filled, key].notna().sum())
    return output


def deciles(frame, column):
    values = pd.qcut(frame[column], 10, labels=False, duplicates='drop')
    return [{'decile': int(decile)+1, **summarize(frame.loc[index])}
            for decile, index in values.groupby(values, dropna=True).groups.items()]


def paired_summary(blocks, symbols, months, seed=20260914):
    records = []
    primary = blocks[blocks.control_seed.isna()]
    for ident, part in primary.groupby(['interpretation', 'horizon', 'latency']):
        left = part[part.model == 'linear'].set_index(['symbol','month'])
        right = part[part.model == 'xgboost'].set_index(['symbol','month'])
        expected = pd.MultiIndex.from_product([symbols,months], names=['symbol','month'])
        if len(left)!=len(expected) or len(right)!=len(expected) or set(left.index)!=set(expected) or set(right.index)!=set(expected):
            raise ValueError('incomplete paired block denominator')
        left, right = left.reindex(expected), right.reindex(expected)
        if not np.array_equal(left.eligible_decisions, right.eligible_decisions):
            raise ValueError('unpaired eligible decisions')
        for metric in ('fill_probability','fill_before_adverse','markout_5','spread_5'):
            delta = right[metric]-left[metric]
            valid = delta.notna()
            base = dict(zip(['interpretation','horizon','latency'],ident))
            base.update(metric=metric, blocks=len(delta), defined_blocks=int(valid.sum()))
            if not valid.all():
                records.append(base)
                continue
            values=delta.to_numpy()
            bootstrap = np.random.default_rng(seed).choice(values, (10000,len(values)),replace=True).mean(axis=1)
            base.update(mean_delta=values.mean(),median_delta=np.median(values),wins=int((values>0).sum()),
                        ci_low=np.quantile(bootstrap,.025),ci_high=np.quantile(bootstrap,.975))
            for stock in symbols:base['without_'+stock]=delta[delta.index.get_level_values('symbol')!=stock].mean()
            for month in months:base['without_'+month]=delta[delta.index.get_level_values('month')!=month].mean()
            records.append(base)
    return pd.DataFrame(records)
