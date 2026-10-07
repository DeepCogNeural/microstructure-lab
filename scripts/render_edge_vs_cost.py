"""Render the edge-versus-cost figure from committed Q10/Q11 aggregate receipts.

Reads only public files under results/; no network, no private data. Output is
results/sequence_ml_q11_v1/figures/edge_vs_cost.png.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt'] = 'edge-vs-cost'
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.offsetbox import AnchoredOffsetbox, DrawingArea, HPacker, TextArea  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figure_style as style  # noqa: E402

SYMBOLS = ('KGHM', 'PEKAO', 'PKNORLEN', 'PKOBP', 'PZU')
MODE = 'Q10_source_only_transfer'
ARMS = (('B1_history_xgboost', 'XGBoost', style.BASELINE), ('S0_seed_mean', 'GRU (3-seed mean)', style.MODEL))
FOOTER = ('One share at visible quotes, fixed t+20 exit; no fills, fees, queue, impact or realized PnL. '
          'Pooled-selected means in a; one point per stock/day in b; equal stock/day means in c.')


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
    width = 0.62
    for block, (arm, label, color) in enumerate(ARMS):
        p = data[arm]['pooled']
        x0 = block * 5
        light = style.BASELINE_LIGHT if block == 0 else style.MODEL_LIGHT
        steps = [('gross\nmove', 0.0, p['gross_midpoint_bps'], color),
                 ('entry\nhalf-spread', p['gross_midpoint_bps'], -p['entry_half_spread_bps'], light),
                 ('exit\nhalf-spread', p['gross_midpoint_bps'] - p['entry_half_spread_bps'], -p['exit_half_spread_bps'], light),
                 ('net\ncrossed', 0.0, p['crossed_bps'], style.NET)]
        for k, (name, bottom, value, c) in enumerate(steps):
            x = x0 + k
            ax.bar(x, value, bottom=bottom, width=width, color=c, edgecolor='white')
            top = bottom + value
            ax.text(x, max(bottom, top) + 0.25, style.fmt_signed(value, 2), ha='center', va='bottom', fontsize=8, color=style.NET)
            if k < 3:
                ax.plot([x + width / 2, x + 1 - width / 2], [top, top], color=style.ZERO, lw=0.5, ls=':')
        ax.text(x0 + 1.5, 6.9, label, ha='center', fontsize=8, color=color)
        ax.text(x0 + 1.5, 5.2, f'IC {data[arm]["ic"]:.3f} · selected {data[arm]["selected"]:,} of {common:,}',
                ha='center', fontsize=8, color=style.MUTED)
    ax.axhline(0, color=style.ZERO, lw=0.5)
    ax.set_xticks([b * 5 + k for b in range(2) for k in range(4)],
                  ['gross\nmove', 'entry\nhalf-spread', 'exit\nhalf-spread', 'net\ncrossed'] * 2, fontsize=8)
    ax.set_ylim(-8.6, 8.6)
    ax.tick_params(axis='x', top=False)
    ax.set_yticks([-8, -4, 0])
    ax.set_xlim(-0.7, 8.7)
    ax.set_ylabel('bp per selected opportunity')
    ax.set_title(textwrap.fill('Gross edge minus entry and exit half-spreads, zero delay (pooled selected)', 82), loc='left', pad=14)
    style.panel_label(ax, 'a')


def scatter(ax, data):
    top = 0.0
    for arm, label, color in ARMS:
        rows = data[arm]['cells']
        x = [r['entry_half_spread_bps'] + r['exit_half_spread_bps'] for r in rows]
        y = [r['gross_midpoint_bps'] for r in rows]
        top = max(top, max(x))
        ax.scatter(x, y, s=5, alpha=0.5, color=color, label=f'{label} (315 stock/days)', linewidths=0)
    lim = top * 1.05
    ax.plot([0, lim], [0, lim], ls='--', color=style.INK, lw=0.75)
    ax.set_ylim(-1, 8)
    ax.axhline(0, color=style.ZERO, lw=0.5)
    ax.set_xlim(0, lim)
    ax.set_xlabel('entry + exit half-spread (bp)')
    ax.set_ylabel('gross midpoint move (bp)')
    ax.set_title('Both arms: all 315 stock/days below breakeven', loc='left', pad=14)
    ax.text(1.3, 1.85, 'breakeven: gross = cost',
            rotation=45, transform_rotates_text=True, rotation_mode='anchor',
            ha='left', va='bottom', fontsize=8, color=style.INK)
    style.panel_label(ax, 'b')


def delays(ax, data):
    for arm, label, color in ARMS:
        values = data[arm]['equal_by_delay']
        ax.plot([0, 1, 5], [values[d] for d in ('0', '1', '5')], marker='o', lw=1.2, markersize=4, color=color, label=label)
        dy = 9 if arm.startswith('B1') else -16
        for d, v in values.items():
            ax.annotate(f'{v:.2f}'.replace('-', '−'), (int(d), v), textcoords='offset points', xytext=(0, dy), ha='center', fontsize=8, color=color)
        ax.annotate(label, (5, values['5']), textcoords='offset points',
                    xytext=(-3, 24) if arm.startswith('B1') else (-30, -20),
                    ha='right', fontsize=8, color=color)
    ax.axhline(0, color=style.ZERO, lw=0.5)
    ax.set_xticks([0, 1, 5])
    ax.set_xlim(-0.45, 5.55)
    ax.set_xlabel('entry delay (original messages)')
    ax.set_ylabel('net crossed markout (bp)')
    ax.set_ylim(-11.5, 0.5)
    ax.set_title('Delay makes it worse', loc='left', pad=14)
    style.panel_label(ax, 'c')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', type=Path, default=Path('results'))
    ap.add_argument('--out', type=Path, default=Path('results/sequence_ml_q11_v1/figures/edge_vs_cost.png'))
    args = ap.parse_args()
    data, common = load(args.results)
    style.apply()
    fig = plt.figure(figsize=(style.WIDTH_DOUBLE, 6.0))
    grid = fig.add_gridspec(2, 2, left=0.09, right=0.975, bottom=0.19,
                           top=0.79, height_ratios=[1, 1.1], hspace=0.66, wspace=0.38)
    waterfall(fig.add_subplot(grid[0, :]), data, common)
    scatter(fig.add_subplot(grid[1, 0]), data)
    delays(fig.add_subplot(grid[1, 1]), data)
    fig.text(0.035, 0.965, 'Edge vs cost', ha='left', va='top',
             fontsize=10, weight='bold', color=style.INK)
    fig.text(0.035, 0.918,
             'Strict cross-stock forecasts · 2017 WSE · 20-message horizon · |prediction| > 1 bp',
             ha='left', va='top', fontsize=8, color=style.MUTED)
    key_entries = []
    for label, color in [('XGBoost baseline', style.BASELINE), ('GRU (3-seed mean)', style.MODEL)]:
        square = DrawingArea(6, 6, 0, 0)
        square.add_artist(Rectangle((0, 0), 6, 6, facecolor=color, edgecolor='none'))
        key_entries.append(HPacker(children=[
            square, TextArea(label, textprops={'color': color, 'size': 8}),
        ], align='center', pad=0, sep=4))
    key = HPacker(children=key_entries, align='center', pad=0, sep=22)
    fig.add_artist(AnchoredOffsetbox(loc='upper left', child=key, frameon=False,
                                    bbox_to_anchor=(0.035, 0.875),
                                    bbox_transform=fig.transFigure, borderpad=0, pad=0))
    fig.text(0.035, 0.065, textwrap.fill(FOOTER, 112), ha='left', va='top',
             fontsize=7, color=style.MUTED, linespacing=1.5)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=300, facecolor='white', metadata={'Software': None})
    plt.close(fig)
    print(json.dumps({'out': str(args.out),
                      'pooled_zero_delay': {arm: {k: round(v, 3) for k, v in data[arm]['pooled'].items()} for arm, _, _ in ARMS}}))


if __name__ == '__main__':
    main()
