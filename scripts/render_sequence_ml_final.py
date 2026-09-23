"""Render the final WSE historical research package from public aggregate receipts."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

BLUE='#3855a6';TEAL='#087f72';ORANGE='#c96b26';GRAY='#707784';RED='#aa4050'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(fig,p):fig.savefig(p,dpi=190,bbox_inches='tight',facecolor='white');plt.close(fig)
def style(ax,title,ylabel):
    ax.set_title(title,loc='left',fontsize=11,weight='bold');ax.set_ylabel(ylabel)
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('results/sequence_ml_final_v1'));a=ap.parse_args()
    if a.out.exists():raise ValueError('preserve existing final package')
    paths={s:Path(p) for s,p in {
        'FQ2':'results/sequence_ml_fq2_v1/fq2_summary.json','FQ3':'results/sequence_ml_fq3_v1/fq3_summary.json',
        'FQ4':'results/sequence_ml_fq4_v1/fq4_summary.json','Q8':'results/sequence_ml_q8_v1/q8_summary.json',
        'Q10':'results/sequence_ml_q10_v1/q10_summary.json','Q11':'results/sequence_ml_q11_v1/q11_summary.json'}.items()}
    d={k:read(p) for k,p in paths.items()}
    if (d['FQ2']['stage'],d['FQ4']['stage'],d['Q8']['stage'],d['Q10']['stage'],d['Q11']['stage'])!=('FQ2','FQ4','Q8','Q10','Q11'):
        raise ValueError('stage mismatch')
    if d['Q11']['stock_day_cells']!=315 or d['Q10']['cells_per_arm']!=315 or d['Q8']['evaluation']['128']['cells_per_arm']!=315:
        raise ValueError('full historical denominator unavailable')
    if d['Q10']['undefined_cells'] or d['Q8']['evaluation']['128']['undefined_cells']:
        raise ValueError('ranking IC undefined; final package requires explicit review')
    if d['Q11']['common_opportunities']<=0:raise ValueError('no common execution opportunities')
    a.out.mkdir(parents=True);figs=a.out/'figures';figs.mkdir();made=[]
    # Figure 1: two distinct historical cohorts, separated rather than pooled.
    fig,axes=plt.subplots(1,2,figsize=(11.4,4.5))
    sizes=(50000,100000,200000);q2=d['FQ2']
    delta=[q2['levels'][str(n)]['full_denominator_result']['paired_vs_B1']['S0_seed_mean']['mean_delta_ic'] for n in sizes]
    ci=[q2['levels'][str(n)]['full_denominator_result']['paired_vs_B1']['S0_seed_mean']['ci95_block5'] for n in sizes]
    axes[0].errorbar(range(3),delta,yerr=[[v-c[0] for v,c in zip(delta,ci)],[c[1]-v for v,c in zip(delta,ci)]],fmt='o-',color=TEAL,capsize=4)
    axes[0].axhline(0,color=GRAY,lw=.8);axes[0].set_xticks(range(3),['50k','100k','200k']);axes[0].set_xlabel('Training endpoints per stock')
    style(axes[0],'FQ2: context32 sample scaling','S0−B1 equal-cell IC')
    contexts=(8,32,128);q8=d['Q8'];b=[q8['evaluation'][str(c)]['full_denominator_result']['mean_ic']['B1_history_xgboost'] for c in contexts]
    s=[q8['evaluation'][str(c)]['full_denominator_result']['S0_seed_mean_ic'] for c in contexts]
    x=np.arange(3);axes[1].bar(x-.17,b,.34,label='B1 history XGBoost',color=BLUE);axes[1].bar(x+.17,s,.34,label='S0 GRU seed IC mean',color=TEAL)
    axes[1].set_xticks(x,[str(c) for c in contexts]);axes[1].set_xlabel('History states');axes[1].legend(frameon=False,fontsize=8)
    style(axes[1],'Q8: common 128-eligible rows','Equal-cell retrospective IC')
    fig.text(.01,-.015,'Both panels use exposed 2017 dates; Q8 eligibility differs from FQ2 and is never pooled with it.',fontsize=8,color=GRAY)
    p=figs/'01_history_and_sample_scale.png';save(fig,p);made.append(p)
    # Figure 2: fixed versus updated monthly IC; temporal composition changes with refit.
    months=('2017-06','2017-09','2017-11');q3=d['FQ3'];time=q3['time_fixed_vs_updated'];x=np.arange(3)
    b=[time[m]['B1_history_xgboost']['updated_minus_fixed_ic'] for m in months]
    s=[np.mean([time[m][f'S0_history_gru_seed{seed}']['updated_minus_fixed_ic'] for seed in (7,17,29)]) for m in months]
    fig,ax=plt.subplots(figsize=(8.8,4.5));ax.bar(x-.18,b,.36,color=BLUE,label='B1');ax.bar(x+.18,s,.36,color=TEAL,label='S0 three-seed mean')
    ax.axhline(0,color=GRAY,lw=.8);ax.set_xticks(x,['June','September','November']);ax.legend(frameon=False)
    style(ax,'FQ3: updated minus fixed model on exposed months','Equal-cell IC difference')
    fig.text(.02,-.015,'Refits add newer training information and change calendar conditions together; this is not a causal decay estimate.',fontsize=8,color=GRAY)
    p=figs/'02_time_and_update.png';save(fig,p);made.append(p)
    # Figure 3: all five stock effects for within-stock versus strict source-only fits, plus frozen state split.
    syms=d['Q10']['symbols'];within=q8['evaluation']['128']['full_denominator_result']['S0_seed_mean_vs_B1']['stock_delta_ic']
    transfer=d['Q10']['full_denominator_result']['S0_seed_mean_vs_B1']['stock_delta_ic'];state=q3['state']
    fig,axes=plt.subplots(1,2,figsize=(11.4,4.6),gridspec_kw={'width_ratios':[1.65,1]});x=np.arange(len(syms))
    axes[0].bar(x-.18,[within[s] for s in syms],.36,color=TEAL,label='Q8 within-stock')
    axes[0].bar(x+.18,[transfer[s] for s in syms],.36,color=BLUE,label='Q10 source-only 4→1')
    axes[0].set_xticks(x,syms,rotation=25);axes[0].axhline(0,color=GRAY,lw=.8);axes[0].legend(frameon=False,fontsize=8)
    style(axes[0],'Five stocks, complete denominator','S0 seed IC mean − B1 IC')
    keys=('high_activity','low_activity');vals=[state[k]['paired_delta_ic']['full_denominator_mean'] for k in keys]
    axes[1].bar(['High prior\nactivity','Low prior\nactivity'],vals,color=[TEAL,'#67a9a0']);axes[1].axhline(0,color=GRAY,lw=.8)
    style(axes[1],'FQ3 fixed prior-state split','IC of mean S0 prediction − B1')
    fig.text(.01,-.015,'Stock panel uses the Q8 common cohort; state panel uses the separate FQ2/FQ3 cohort and a different seed estimand.',fontsize=8,color=GRAY)
    p=figs/'03_stock_and_state.png';save(fig,p);made.append(p)
    # Figure 4: selected visible crossing at fixed t+20 exit, including coverage and both research populations.
    q11=d['Q11'];modes=('Q8_within_stock','Q10_source_only_transfer');arms=('B1_history_xgboost','S0_seed_mean');delays=(0,1,5)
    fig,axes=plt.subplots(2,2,figsize=(11.5,8.0),sharex='col')
    for row,mode in enumerate(modes):
        label='Within-stock Q8' if row==0 else 'Source-only Q10'
        for arm,shift,color in ((arms[0],-.18,BLUE),(arms[1],.18,TEAL)):
            cells=[q11['execution'][mode][arm][str(delay)] for delay in delays]
            mark=[cell['pooled_selected_crossed_bps_descriptive'] for cell in cells]
            coverage=[100*cell['selected_sum_across_cells']/cell['common_opportunities_sum_across_cells'] if cell['common_opportunities_sum_across_cells'] else np.nan for cell in cells]
            if any(v is None for v in mark):raise ValueError('no selected opportunities for a finalist')
            axes[row,0].bar(np.arange(3)+shift,mark,.36,color=color,label='B1' if arm==arms[0] else 'S0 mean')
            axes[row,1].bar(np.arange(3)+shift,coverage,.36,color=color,label='B1' if arm==arms[0] else 'S0 mean')
        axes[row,0].axhline(0,color=GRAY,lw=.8);axes[row,0].set_xticks(range(3),['0','1','5'])
        axes[row,1].set_xticks(range(3),['0','1','5'])
        style(axes[row,0],label+': visible crossing','Pooled selected crossed bp')
        style(axes[row,1],label+': selection coverage','Selected / common, %')
        axes[row,0].legend(frameon=False,fontsize=8)
    axes[1,0].set_xlabel('Entry delay, original messages');axes[1,1].set_xlabel('Entry delay, original messages')
    fig.text(.01,-.005,'One share at visible quotes, fixed t+20 exit; selected sets differ by arm. No fills, fees, queue, impact, inventory or realized PnL.',fontsize=8,color=GRAY)
    p=figs/'04_prediction_and_visible_execution.png';save(fig,p);made.append(p)
    # Allocation table: scheduler time is not GPU/CPU utilization.
    alloc={s:read(f'results/sequence_ml_{s.lower()}_v1/{s.lower()}_gpu_allocation.json') for s in ('FQ2','FQ3','FQ4','Q8','Q10')}
    cpu=read('results/sequence_ml_q11_v1/q11_cpu_allocation.json')
    table=a.out/'cost_table.csv'
    with table.open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['stage','tasks','allocated_gpu_hours','allocated_cpu_core_hours','allocated_cpu_wall_hours','interpretation'])
        for stage,v in alloc.items():w.writerow([stage,v['gpu_update_tasks'] if stage=='FQ3' else v['task_count'],f"{v['allocated_gpu_hours']:.6f}",'','','Allocation wall time including data/load; not GPU utilization'])
        w.writerow(['FQ3_CPU_DIAGNOSTIC',alloc['FQ3']['cpu_diagnostic_tasks'],'','',
                    f"{alloc['FQ3']['cpu_diagnostic_allocated_wall_hours']:.6f}",'Core count not recorded; wall time is not core-hours'])
        w.writerow(['Q11',cpu['task_count'],'',f"{cpu['allocated_cpu_core_hours']:.6f}",
                    f"{cpu['allocated_cpu_core_hours']/4:.6f}",'Four allocated CPU cores per task; not CPU utilization'])
    manifest={'stage':'FINAL_WSE_RETROSPECTIVE','retrospective_only':True,'input_aggregate_sha256':{k:sha(p) for k,p in paths.items()},
              'figure_sha256':{p.name:sha(p) for p in made},'cost_table_sha256':sha(table),
              'limits':'2017 historical/exposed evaluation only; no independent confirmation, actual fills or realized PnL.'}
    p=a.out/'render_manifest.json';p.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'figures':len(made),'render_manifest_sha256':sha(p)}))
if __name__=='__main__':main()
