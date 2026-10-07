"""Rebuild two archived decile figures from their committed aggregate tables only.

PEKAO repeats the plotting selection in licensed_experiment.py. The later figure
uses its printed contract: five-stock equal means, 20 messages, zero delay,
retain priority, with the all-dates aggregates and primary (unshuffled) models.
"""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import figure_style as style
from nature_legacy_layout import finish


def main():
    style.apply()
    root = Path('results/wselob_pekao')
    qframe = pd.read_csv(root/'prediction_quantiles.csv')
    symbols = sorted(qframe.symbol.unique())
    horizons = sorted(qframe.horizon_events.unique())
    fig, axes = plt.subplots(len(symbols), len(horizons), squeeze=False)
    for row, symbol in enumerate(symbols):
        for col, horizon in enumerate(horizons):
            ax = axes[row, col]
            subset = qframe[(qframe.symbol == symbol)&(qframe.horizon_events == horizon)]
            for model, group in subset.groupby('model'):
                ax.plot(group.prediction_quantile, group.avg_realized_markout_bps,
                        marker='o', label=model, color=style.LINEAR if model == 'linear' else style.HISTGB)
            ax.set_title(f'{symbol}: {horizon} events')
            ax.set_xlabel('Within-fold prediction quantile')
            ax.set_ylabel('Midpoint markout (bps)')
    out = root/'figures_nature'; out.mkdir(exist_ok=True)
    finish(fig, out/'prediction_quantile_markout.png'); plt.close(fig)
    root = Path('results/wselob_later_confirmation_v1')
    data = pd.read_csv(root/'passive_deciles.csv')
    data = data[(data.horizon == 20)&(data.latency == 0)&
                (data.interpretation == 'retain')&(data.day == 'all')&data.control_seed.isna()]
    assert len(data) == 100 and not data.duplicated(['model','symbol','bin']).any()
    fig, axes = plt.subplots(1, 2)
    for model, color in [('linear', style.LINEAR), ('xgboost', style.BASELINE)]:
        group = data[data.model == model].groupby('bin')
        assert (group.size() == 5).all()
        values = group[['fill_probability', 'markout_5']].mean()
        for ax, metric, scale in zip(axes, ['fill_probability','markout_5'], [100,1]):
            ax.plot(values.index, values[metric]*scale, marker='o', color=color, label=model)
            ax.set_xlabel('Prediction decile (ties preserved)')
    axes[0].set_ylabel('Conditional fill probability (%)')
    axes[1].set_ylabel('5-message post-fill markout (bp)')
    fig.suptitle('Later confirmation: 20 messages, zero delay\nFive-stock equal means; retain (reset aggregates identical)')
    out = root/'figures_nature'; out.mkdir(exist_ok=True)
    finish(fig, out/'passive_prediction_deciles.png'); plt.close(fig)


if __name__ == '__main__':
    main()
