"""Write a five-minute, evidence-bounded WSE sequence-ML research brief."""
from __future__ import annotations
import argparse,json
from pathlib import Path
def read(p):return json.loads(Path(p).read_text())
def fmt(v):return 'undefined' if v is None else f'{v:+.3f}'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('docs/SEQUENCE_ML_FINAL_RESEARCH_BRIEF.md'));a=ap.parse_args()
    if a.out.exists():raise ValueError('preserve existing final research brief')
    q2=read('results/sequence_ml_fq2_v1/fq2_summary.json');q3=read('results/sequence_ml_fq3_v1/fq3_summary.json')
    q4=read('results/sequence_ml_fq4_v1/fq4_summary.json');q8=read('results/sequence_ml_q8_v1/q8_summary.json')
    q10=read('results/sequence_ml_q10_v1/q10_summary.json');q11=read('results/sequence_ml_q11_v1/q11_summary.json')
    q5=read('results/sequence_ml_v1/q5_data_gate.json')
    alloc={s:read(f'results/sequence_ml_{s.lower()}_v1/{s.lower()}_gpu_allocation.json') for s in ('FQ2','FQ3','FQ4','Q8','Q10')}
    cpu=read('results/sequence_ml_q11_v1/q11_cpu_allocation.json')
    if q5['verdict']!='PENDING_INDEPENDENT_CONFIRMATION' or q5['outcomes_viewed']:raise ValueError('independent status changed')
    if any(x['stage']!=s for x,s in ((q4,'FQ4'),(q8,'Q8'),(q10,'Q10'),(q11,'Q11'))):raise ValueError('wrong stage')
    scale=[]
    for n in (50000,100000,200000):
        full=q2['levels'][str(n)]['full_denominator_result'];p=full['paired_vs_B1']['S0_seed_mean']
        scale.append(f"| {n//1000}k | {full['evaluation_mean_ic']['B1_history_xgboost']:.6f} | "
                     f"{sum(full['evaluation_mean_ic'][f'S0_history_gru_seed{s}'] for s in (7,17,29))/3:.6f} | "
                     f"{p['mean_delta_ic']:+.6f} | [{p['ci95_block5'][0]:+.6f}, {p['ci95_block5'][1]:+.6f}] |")
    f4=q4['evaluation']['full_denominator_result'];t=f4['S1_seed_mean_vs_S0_seed_mean']
    q8p=q8['evaluation']['128']['full_denominator_result'];q10p=q10['full_denominator_result']
    if q10p is None:raise ValueError('Q10 full denominator undefined')
    stock8=q8p['S0_seed_mean_vs_B1']['stock_delta_ic'];stock10=q10p['S0_seed_mean_vs_B1']['stock_delta_ic']
    execution=[]
    for mode,label in (('Q8_within_stock','within-stock Q8'),('Q10_source_only_transfer','source-only Q10')):
        for delay in (0,1,5):
            b=q11['execution'][mode]['B1_history_xgboost'][str(delay)]
            s=q11['execution'][mode]['S0_seed_mean'][str(delay)]
            execution.append(f"| {label} | {delay} | {b['common_opportunities_sum_across_cells']:,} | "
                             f"{b['selected_sum_across_cells']:,} / {s['selected_sum_across_cells']:,} | "
                             f"{fmt(b['pooled_selected_crossed_bps_descriptive'])} / {fmt(s['pooled_selected_crossed_bps_descriptive'])} | "
                             f"{len(b['undefined_cells'])} / {len(s['undefined_cells'])} |")
    both=q11['both_selected'];zero=q3['execution']
    total_gpu=sum(a['allocated_gpu_hours'] for a in alloc.values())
    text=f'''# Final WSELOB sequence-ML research brief

**Status:** formal historical research complete; independent confirmation **pending**. The 2017 WSE stocks and months used here were researcher-exposed. This brief does not claim unseen-stock or future-period generalization, actual fills or trading profit. The old Q2/Q3/Q6 20k/15-epoch work remains archived as a pilot; FQ2–FQ4, Q8, Q10 and Q11 are the final bounded retrospective record.

## Question and design

Can causal original-event limit-order-book history improve h20 midpoint-change ranking beyond a history-matched cheap baseline, and does a small Transformer add value beyond a sufficiently trained GRU? Five causal book features, fixed original-event endpoints, source hashes and public aggregate receipts bind the experiment. Jan–Mar trained models; April alone selected checkpoints/context; June, September and November supplied historical diagnostics. The cheap baseline is B1 history XGBoost, S0 is a one-layer GRU with seeds 7/17/29, and FQ4 S1 is a small Transformer on the unchanged context32 FQ2 cohort.

## Historical model evidence

| FQ2 train endpoints/stock | B1 history IC | S0 seed-specific IC mean | Paired S0−B1 IC | Five-day block interval |
|---|---:|---:|---:|---:|
{chr(10).join(scale)}

FQ4's fixed context32 Transformer lost to S0: S1−S0 **{t['mean_delta_ic']:+.6f}** IC, date-block interval **[{t['ci95_date_block5'][0]:+.6f},{t['ci95_date_block5'][1]:+.6f}]** on all 315 retrospective stock/day cells. All three seed and all five stock effects were negative. No post-result Transformer retuning was used.

Q8 tested 8/32/128 history states on **one common context128-eligible cohort**, with 200k train endpoints per stock, 90 April and 315 historical stock/day cells and exact same endpoints across contexts. April selected **{q8['selected_context_from_April_only']}**. On its historical evaluation, B1 IC **{q8p['mean_ic']['B1_history_xgboost']:.6f}**, S0 seed IC mean **{q8p['S0_seed_mean_ic']:.6f}**, paired difference **{q8p['S0_seed_mean_vs_B1']['mean_delta_ic']:+.6f}** [{q8p['S0_seed_mean_vs_B1']['ci95_date_block5'][0]:+.6f},{q8p['S0_seed_mean_vs_B1']['ci95_date_block5'][1]:+.6f}]. Q8's cohort is different from FQ2 and their scores are never pooled. PKNORLEN's within-stock S0−B1 difference was **{stock8['PKNORLEN']:+.6f}**, a retained negative effect.

Q10 was actual **train on four stocks → test the fifth** transfer, repeated for all five held-out stocks. Training, normalization, April context choice and checkpoints used only the four source stocks; each fold trained on 800k source endpoints. All folds selected 128 from source April scores, and the choice used GRU IC, favoring the neural arm. On 615,488 held-out historical rows/315 cells, B1 IC was **{q10p['mean_ic']['B1_history_xgboost']:.6f}** and S0 seed IC mean **{q10p['S0_seed_mean_ic']:.6f}**, paired difference **{q10p['S0_seed_mean_vs_B1']['mean_delta_ic']:+.6f}** [{q10p['S0_seed_mean_vs_B1']['ci95_date_block5'][0]:+.6f},{q10p['S0_seed_mean_vs_B1']['ci95_date_block5'][1]:+.6f}]. All five stock differences were positive; PKNORLEN was the smallest at **{stock10['PKNORLEN']:+.6f}**. FQ2's older leave-one-stock-out aggregate-sign check was not this transfer design. Averaging predictions before scoring IC is a distinct estimand, fully reported in Q10 receipts.

FQ3's fifteen rolling refits and fixed-model high/low prior-activity split remain in the public record. Newer training information and calendar conditions change together, so fixed-versus-updated differences are not causal decay estimates.

## Fixed visible-quote execution re-check

Q11 reused frozen Q8 and Q10 private predictions without fitting. At original event t, strict `abs(prediction)>1 bp` selected direction; entry was the visible ask/bid at t+0/1/5 messages and exit was the opposite quote at fixed t+20. Exact original-event, segment and valid-quote identities were required across all delays and both arms. The table uses **pooled selected descriptive** crossed bp because the arms can select different opportunities; full equal stock/day values and any undefined cells are in the public summary.

| Population | Entry delay | Common rows | B1 / S0 selected | B1 / S0 crossed bp | B1 / S0 undefined cells |
|---|---:|---:|---:|---:|---:|
{chr(10).join(execution)}

The both-selected subset is published separately. The prior FQ3 zero-delay historical B1/S0 visible crossing was **{zero['B1_history_xgboost']['equal_stock_day_crossed']['full_denominator_mean']:.3f} / {zero['S0_seed_mean']['equal_stock_day_crossed']['full_denominator_mean']:.3f} bp**, and remains in the record; it uses the different FQ2 cohort. Q11 is one-share quote arithmetic with no actual fills, fees, queue, impact, inventory or realized PnL. A positive ranking score does not imply executable profit.

## Cost, reproducibility and claim boundary

FQ2/FQ3/FQ4/Q8/Q10 used **{total_gpu:.3f} allocated GPU-hours** total; Q11 used **{cpu['allocated_cpu_core_hours']:.3f} allocated CPU core-hours**. These are scheduler allocations, not utilization. `results/sequence_ml_final_v1/` contains four figures, a cost table, public run/model/source/data hashes and an aggregate recomputation manifest. Licensed raw records, row predictions, weights and private scheduler logs stay outside Git.

The Q5 source audit found no legally usable, genuinely uninspected WSE original-event h20 cohort. Therefore `PENDING_INDEPENDENT_CONFIRMATION` remains the final boundary. A résumé-safe method description would require separate editing authorization; no résumé or PDF was changed by this research run. An independent performance or profit claim requires qualified new data and its own frozen protocol.
'''
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text)
    print(json.dumps({'characters':len(text),'lines':len(text.splitlines())}))
if __name__=='__main__':main()
