"""Render the edge-versus-cost figure from committed Q10/Q11 aggregate receipts.

Reads only public files under results/; no network, no private data. Output is
results/sequence_ml_q11_v1/figures/edge_vs_cost.png.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt'] = 'edge-vs-cost'
from matplotlib import pyplot as plt  # noqa: E402

SYMBOLS = ('KGHM', 'PEKAO', 'PKNORLEN', 'PKOBP', 'PZU')
MODE = 'Q10_source_only_transfer'
ARMS = (('B1_history_xgboost', 'XGBoost', '#3855a6'), ('S0_seed_mean', 'GRU (3-seed mean)', '#c96b26'))
GREEN, RED, GRAY = '#2e7d4f', '#aa4050', '#707784'
FOOTER = ('One share at visible quotes, fixed t+20 exit; no fills, fees, queue, impact or realized PnL. '
          'Pooled-selected means in A; one point per stock/day in B; equal stock/day means in C.')


def read(path: Path):
    return json.loads(path.read_text())


def load(root: Path):
    q10 = read(root / 'sequence_ml_q10_v1' / 'q10_summary.json')['full_denominator_result']
    q11 = read(root / 'sequence_ml_q11_v1' / 'q11_summary.json')
    cells = []
    for symbol in SYMBOLS:
        receipt = read(root / 'sequence_ml_q11_v1' / f'q11_execution_{symbol}.json')
        cells += [r for r in receipt['execution'] if r['mode'] == MODE and r['delay_events'] == 0]
    out = {}
    for arm, _, _ in ARMS:
        rows = [r for r in cells if r['arm'] == arm]
        if len(rows) != 315 or any(r['undefined_reason'] for r in rows):
            raise ValueError(f'{arm}: expected 315 defined stock/day cells')
        n = sum(r['selected'] for r in rows)
        pooled = {k: sum(r['selected'] * r[k] for r in rows) / n
                  for k in ('gross_midpoint_bps', 'entry_half_spread_bps', 'exit_half_spread_bps', 'crossed_bps')}
        summary = q11['execution'][MODE][arm]
        if n != summary['0']['selected_sum_across_cells']:
            raise ValueError(f'{arm}: selected count differs from q11_summary.json')
        if abs(pooled['crossed_bps'] - summary['0']['pooled_selected_crossed_bps_descriptive']) > 1e-9:
            raise ValueError(f'{arm}: pooled crossed markout differs from q11_summary.json')
        out[arm] = {
            'ic': q10['mean_ic']['B1_history_xgboost'] if arm.startswith('B1') else q10['S0_seed_mean_ic'],
            'selected': n,
            'pooled': pooled,
            'cells': rows,
            'equal_by_delay': {d: summary[d]['equal_stock_day_crossed_bps'] for d in ('0', '1', '5')},
        }
    return out, q11['common_opportunities']


def waterfall(ax, data, common):
    width = 0.8
    for block, (arm, label, color) in enumerate(ARMS):
        p = data[arm]['pooled']
        x0 = block * 5
        steps = [('gross\nmove', 0.0, p['gross_midpoint_bps'], GREEN),
                 ('entry\nhalf-spread', p['gross_midpoint_bps'], -p['entry_half_spread_bps'], RED),
                 ('exit\nhalf-spread', p['gross_midpoint_bps'] - p['entry_half_spread_bps'], -p['exit_half_spread_bps'], RED),
                 ('net\ncrossed', 0.0, p['crossed_bps'], '#3a3f4b')]
        for k, (name, bottom, value, c) in enumerate(steps):
            x = x0 + k
            ax.bar(x, value, bottom=bottom, width=width, color=c, edgecolor='white')
            top = bottom + value
            ax.text(x, max(bottom, top) + 0.25, f'{value:+.2f}', ha='center', va='bottom', fontsize=9.5, weight='bold', color=c)
            if k < 3:
                ax.plot([x + width / 2, x + 1 - width / 2], [top, top], color=GRAY, lw=0.8, ls=':')
        ax.text(x0 + 1.5, 5.0, label, ha='center', fontsize=11, weight='bold', color=color)
        ax.text(x0 + 1.5, 4.25, f'IC {data[arm]["ic"]:.3f} · selected {data[arm]["selected"]:,} of {common:,}',
                ha='center', fontsize=8.5, color=GRAY)
    ax.axhline(0, color='black', lw=0.8)
    ax.set_xticks([b * 5 + k for b in range(2) for k in range(4)],
                  ['gross\nmove', 'entry\nhalf-spread', 'exit\nhalf-spread', 'net\ncrossed'] * 2, fontsize=8.5)
    ax.set_ylim(-8.6, 5.9)
    ax.set_xlim(-0.7, 8.7)
    ax.set_ylabel('bp per selected opportunity')
    ax.set_title('A. Gross edge minus entry and exit half-spreads, zero delay (pooled selected)', loc='left', fontsize=11, weight='bold')
    ax.spines[['top', 'right']].set_visible(False)


def scatter(ax, data):
    top = 0.0
    for arm, label, color in ARMS:
        rows = data[arm]['cells']
        x = [r['entry_half_spread_bps'] + r['exit_half_spread_bps'] for r in rows]
        y = [r['gross_midpoint_bps'] for r in rows]
        top = max(top, max(x))
        ax.scatter(x, y, s=12, alpha=0.55, color=color, label=f'{label} (315 stock/days)', linewidths=0)
    lim = top * 1.05
    ax.plot([0, lim], [0, lim], ls='--', color='black', lw=1, label='breakeven: gross = cost')
    ax.set_ylim(-1, 8)
    ax.axhline(0, color=GRAY, lw=0.6)
    ax.set_xlim(0, lim)
    ax.set_xlabel('entry + exit half-spread (bp)')
    ax.set_ylabel('gross midpoint move (bp)')
    ax.set_title('B. Both arms: all 315 stock/days below breakeven', loc='left', fontsize=11, weight='bold')
    ax.legend(fontsize=8, loc='upper left', frameon=False)
    ax.spines[['top', 'right']].set_visible(False)


def delays(ax, data):
    for arm, label, color in ARMS:
        values = data[arm]['equal_by_delay']
        ax.plot([0, 1, 5], [values[d] for d in ('0', '1', '5')], marker='o', color=color, label=label)
        dy = 7 if arm.startswith('B1') else -13
        for d, v in values.items():
            ax.annotate(f'{v:.2f}', (int(d), v), textcoords='offset points', xytext=(4, dy), fontsize=8, color=color)
    ax.axhline(0, color='black', lw=0.8)
    ax.set_xticks([0, 1, 5])
    ax.set_xlabel('entry delay (original messages)')
    ax.set_ylabel('net crossed markout (bp)')
    ax.set_ylim(-9.5, 0.5)
    ax.set_title('C. Delay makes it worse', loc='left', fontsize=11, weight='bold')
    ax.legend(fontsize=8, loc='center right', frameon=False)
    ax.spines[['top', 'right']].set_visible(False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', type=Path, default=Path('results'))
    ap.add_argument('--out', type=Path, default=Path('results/sequence_ml_q11_v1/figures/edge_vs_cost.png'))
    args = ap.parse_args()
    data, common = load(args.results)
    fig = plt.figure(figsize=(12, 7.2))
    grid = fig.add_gridspec(2, 2, height_ratios=[1, 1.25], hspace=0.45, wspace=0.25)
    waterfall(fig.add_subplot(grid[0, :]), data, common)
    scatter(fig.add_subplot(grid[1, 0]), data)
    delays(fig.add_subplot(grid[1, 1]), data)
    fig.suptitle('Edge vs cost: strict cross-stock forecasts, 2017 WSE, 20-message horizon, |prediction| > 1 bp',
                 x=0.01, ha='left', fontsize=12.5, weight='bold')
    fig.text(0.01, 0.005, FOOTER, fontsize=8.5, color=GRAY)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200, bbox_inches='tight', facecolor='white', metadata={'Software': None})
    plt.close(fig)
    print(json.dumps({'out': str(args.out),
                      'pooled_zero_delay': {arm: {k: round(v, 3) for k, v in data[arm]['pooled'].items()} for arm, _, _ in ARMS}}))


if __name__ == '__main__':
    main()
