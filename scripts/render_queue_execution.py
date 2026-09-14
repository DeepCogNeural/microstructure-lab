"""Render only public queue aggregates; never read licensed rows."""
from pathlib import Path
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',default='results/wselob_queue_execution_v1')
    args=parser.parse_args();root=Path(args.results)
    summary=pd.read_csv(root/'fill_summary.csv')
    prediction=pd.read_csv(root/'fill_by_prediction_decile.csv')
    queue=pd.read_csv(root/'fill_by_queue_decile.csv')
    for data,metric,title,name in [
      (prediction,'fill_probability','Conditional fill probability','fill_prediction_decile'),
      (prediction,'markout_5','Five-message post-fill midpoint movement (bp)','adverse_prediction_decile'),
      (queue,'fill_before_adverse','Fill before adverse move: conditional probability','race_queue_decile')]:
        fig,axes=plt.subplots(1,3,figsize=(12,3.5),sharey=True)
        for ax,h in zip(axes,(10,20,50)):
            for model in ('linear','xgboost'):
                for interpretation,style in [('retain','-'),('reset','--')]:
                    d=data[(data.horizon==h)&(data.model==model)&data.control_seed.isna()&(data.latency==0)&(data.interpretation==interpretation)]
                    ax.plot(d.decile,d[metric],style,label=f'{model}, {interpretation}')
            ax.set_title(f'{h}-message lifetime');ax.set_xlabel('Decile');ax.grid(alpha=.2)
        axes[0].set_ylabel(title);axes[-1].legend(fontsize=7)
        fig.suptitle('Conditional depletion scenario; equal-weight stock/month blocks',fontsize=11)
        fig.tight_layout();fig.savefig(root/(name+'.png'),dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,3.5))
    for ax,metric in zip(axes,('fill_probability','spread_5')):
        for model in ('linear','xgboost'):
            d=summary[(summary.horizon==20)&(summary.model==model)&summary.control_seed.isna()&(summary.interpretation=='retain')]
            ax.plot(d.latency,d[metric],'o-',label=model)
        ax.set_xlabel('Placement latency (messages)');ax.set_title(metric.replace('_',' '));ax.grid(alpha=.2);ax.legend()
    fig.suptitle('20-message lifetime; conditional scenario, not trading PnL')
    fig.tight_layout();fig.savefig(root/'model_comparison.png',dpi=150);plt.close(fig)
    table=summary[(summary.latency==0)&summary.control_seed.isna()][['interpretation','model','horizon','fill_probability','mean_fill_time','markout_5','spread_5','fill_before_adverse']]
    lines=['| '+' | '.join(table.columns)+' |','| '+' | '.join(['---']*len(table.columns))+' |']
    for row in table.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{v:.6f}' if isinstance(v,float) else str(v) for v in row)+' |')
    report='''# Queue-aware passive execution report

The order feed does not uniquely identify historical executions. **Y is retransmission**, and D does not distinguish cancellation from complete execution. Consequently, this experiment reports conditional depletion diagnostics and a zero identified lower fill bound. It does not establish an executable strategy.

## Frozen method

Read [source semantics](WSELOB_QUEUE_SEMANTICS.md) and the [preregistered roadmap](QUEUE_AWARE_EXECUTION_ROADMAP.md). Reuse all 137 original prediction tasks: 120 primary tasks and 17 shuffled-label controls. Five stocks, four fixed months, 10/20/50-message lifetimes, and 0/1/5-message placement latencies remain unchanged. Two priority interpretations produce 822 evaluation cells.

Each virtual order is independent, has one dataset-native displayed quantity unit, and joins the back of the visible best bid for a positive prediction or best ask for a negative prediction. Exactly zero predictions remain eligible but place no order. No repricing occurs. The queue ahead is tracked by individual order identity and entry state; new arrivals behind the virtual order cannot add queue ahead.

The conditional scenario treats D removals and same-price M quantity reductions as executions. A fill requires consumption of at least one unit from an order behind the virtual order after its ahead queue has cleared. Deleting the final ahead order alone cannot fill the virtual order. This is an explicit scenario, not a proven upper bound over every hidden matching process. The two modification interpretations retain ambiguous priority or move ambiguously modified orders behind existing orders. They are sensitivity checks, not two identified matching engines.

The adverse threshold is the smallest positive adjacent visible-price difference observed so far that day, using no later prices. Midpoint movement of at least that amount against the chosen direction triggers the adverse event. Simultaneous fill/adverse messages are reported separately; they are never counted as fill-before-adverse. A virtual order ends at fill, lifetime expiry, invalid state or segment boundary; Y retransmissions additionally break the diagnostic path.

Post-fill side-adjusted midpoint changes use offsets 1, 5 and 10 messages. The remaining-original-horizon outcome uses decision event plus prediction horizon, and is undefined if the fill occurs later. The realized-spread diagnostic is twice the side-adjusted difference between future midpoint and passive fill price, divided by fill price, in basis points. These are historical diagnostics, not realized trading PnL. Fees, rebates, hidden liquidity, impact, matching-phase uncertainty, inventory and competing virtual orders are not modeled.

## Zero-latency results

'''+ '\n'.join(lines)+'''

All headline means weight stock/month blocks equally. Tables expose eligible decisions, placed orders, fills, observable post-fill outcomes and the number of defined blocks. An undefined block prevents a strict headline mean; it is never silently assigned zero. Prediction and queue deciles preserve tied values and report the actual contributing block count. The identified zero-fill lower bound has undefined conditional markouts.

## Paired comparison and controls

`paired_model_differences.csv` reports XGBoost minus Linear means, medians, wins, leave-one-stock/month means and 10,000-resample paired block intervals. Intervals are descriptive; overlapping rows do not supply independent statistical evidence. Exact model eligibility is shared before selecting direction. Shuffled predictions use the identical scenario and output definitions; see `control_summary.csv`. No new fitting or parameter search is performed.

## Figures

![Fill probability](../results/wselob_queue_execution_v1/fill_prediction_decile.png)

![Post-fill midpoint movement](../results/wselob_queue_execution_v1/adverse_prediction_decile.png)

![Fill versus adverse race](../results/wselob_queue_execution_v1/race_queue_decile.png)

![Model comparison](../results/wselob_queue_execution_v1/model_comparison.png)

## Reproduction and provenance

Run `scripts/run_queue_execution.py` with the frozen config, original private raw files, frozen cache and original prediction receipt roots. `--symbol` and `--month` split independent work; `--aggregate-only` assembles all 20 completed stock/month checkpoints and rejects missing cells. Paths are runtime arguments and do not enter scientific identity. Run `scripts/render_queue_execution.py` on the public aggregates.

The manifest binds source code, scientific configuration, original cache and all prediction hashes. Original prediction timestamps, indices and outcomes must match cached rows. Source-file and partition hashes must match. Queue-derived ten-level snapshots are compared with every retained cached event; independent order/aggregate queue parity is checked every 1,000 original messages. Previous benchmark artifacts remain unchanged.

The optional C++ kernel is not implemented. Python remains the reference implementation; no C++ parity or acceleration claim is made.

## Attribution

Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1, [dataset](https://data.mendeley.com/datasets/3g4mhdp899/1), CC BY 4.0. Added queue reconstruction, conditional virtual-order diagnostics and aggregate figures. As-is; no warranty or endorsement.
'''
    Path('docs/QUEUE_AWARE_EXECUTION_REPORT.md').write_text(report)

if __name__=='__main__':main()
