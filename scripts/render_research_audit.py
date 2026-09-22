"""Render the audit only from published aggregate tables; no fitting or row input."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cloblab.research_audit import strict_stats
from cloblab.scale_common import atomic_json,file_hash
from cloblab.later_confirmation import clean


def summarize(frame,keys,metric,expected):
 rows=[]
 for ident,g in frame.groupby(keys,dropna=False,sort=True):
  if not isinstance(ident,tuple):ident=(ident,)
  rows.append(dict(zip(keys,ident),metric=metric,**strict_stats(g[metric],expected)))
 return pd.DataFrame(rows)


def main():
 p=argparse.ArgumentParser();p.add_argument('--out',default='results/wselob_research_audit_v1');a=p.parse_args();out=Path(a.out)
 ab=pd.read_csv(out/'ablation_blocks.csv');control=pd.read_csv(out/'control_blocks.csv');ex=pd.read_csv(out/'execution_decomposition.csv');fx=pd.read_csv(out/'fixed_exit_latency.csv');pa=pd.read_csv(out/'passive_accounting.csv');tm=pd.read_csv(out/'event_time_summary.csv');st=pd.read_csv(out/'state_diagnostics.csv')
 summaries=[]
 for metric in ['ic','daily_ic']:
  q=summarize(ab,['model','feature_group'],metric,20);summaries.append(q)
 af=pd.concat(summaries);af.to_csv(out/'ablation_level_summary.csv',index=False)
 cs=[]
 for metric in ['ic','daily_ic']:
  seed=summarize(control,['scope','shuffle','seed'],metric,5);seed['level']='five_stock_mean'
  for (scope,shuffle),g in seed.groupby(['scope','shuffle']):cs.append(dict(scope=scope,shuffle=shuffle,metric=metric,level='five_seed_distribution',**strict_stats(g['mean'],5),min_seed_mean=g['mean'].min(),max_seed_mean=g['mean'].max()))
  cs.extend(seed.to_dict('records'))
 pd.DataFrame(cs).to_csv(out/'control_cohort_summary.csv',index=False)
 stock_seeds=[]
 for (scope,symbol,method),g in control.groupby(['scope','symbol','shuffle']):
  for metric in ['ic','daily_ic']:
   stock_seeds.append(dict(scope=scope,symbol=symbol,shuffle=method,metric=metric,**strict_stats(g[metric],5),min=g[metric].min(),max=g[metric].max(),std=g[metric].std(ddof=0)))
 pd.DataFrame(stock_seeds).to_csv(out/'control_stock_seed_distribution.csv',index=False)
 # Main references remain the archived primary experiments, not new fits.
 monthly=pd.read_csv('results/wselob_xgboost_application_v1/model_metrics_by_symbol_month.csv')
 transfer=pd.read_csv('results/wselob_execution_robustness_v1/transfer_block_metrics.csv')
 later_primary=pd.read_csv('results/wselob_later_confirmation_v1/primary_prediction.csv')
 references=[]
 for scope,frame in [('own_june',monthly),('transfer_june',transfer)]:
  selected=frame[(frame.month=='2017-06')&(frame.horizon==20)&frame.control_seed.isna()&frame.model.str.startswith('xgboost')]
  assert len(selected)==5
  references.extend(dict(scope=scope,symbol=r.symbol,ic=r.ic,origin='archived_primary',expected=5) for r in selected.itertuples())
 references.extend(dict(scope='later',symbol=r.symbol,ic=r.xgboost,origin='archived_primary',expected=5) for r in later_primary.itertuples())
 pd.DataFrame(references).to_csv(out/'control_main_reference.csv',index=False)
 mean_day=[]
 for (scope,method),g in control.groupby(['scope','shuffle']):
  mean_day.append(dict(scope=scope,shuffle=method,metric='correlation_of_daily_means',**strict_stats(g.mean_day_prediction_label_ic,25),prediction_std_min_bps=g.prediction_std_bps.min(),prediction_std_max_bps=g.prediction_std_bps.max()))
 pd.DataFrame(mean_day).to_csv(out/'control_daily_mean_diagnostics.csv',index=False)
 state=[]
 for (i,j),part in st.groupby(['spread_bin','imbalance_bin']):
  for model,g in part.groupby('model'):
   pivot=g.pivot(index=['symbol','period'],columns='feature_group',values='ic')
   for hi,lo in [('F2','F1'),('F3','F2'),('F4','F2'),('F5','F3'),('F5','F4')]:state.append(dict(spread_bin=i,imbalance_bin=j,model=model,contrast=hi+'-'+lo,**strict_stats(pivot[hi]-pivot[lo],20)))
  for feature,g in part.groupby('feature_group'):
   pivot=g.pivot(index=['symbol','period'],columns='model',values='ic');state.append(dict(spread_bin=i,imbalance_bin=j,model='xgboost-linear',contrast=feature,**strict_stats(pivot.xgboost-pivot.linear,20)))
 pd.DataFrame(state).to_csv(out/'state_paired_summary.csv',index=False)
 missing=st[['task_id','symbol','period','model','feature_group','spread_bin','imbalance_bin','rows','ic']].copy()
 missing['undefined_reason']=np.where(missing.ic.notna(),'',np.where(missing.rows<2,'insufficient_rows','constant_prediction_or_label'))
 missing.to_csv(out/'state_metric_validity.csv',index=False)
 e=[]
 for cohort,n in [('monthly',20),('later',5)]:
  for table,mode in [(ex,'moving_exit'),(fx,'fixed_exit')]:
   for metric in ['gross_midpoint_bps','entry_half_spread_bps','exit_half_spread_bps','crossed_bps','coverage']:
    s=summarize(table[(table.cohort==cohort)&table.control_seed.isna()],['model','horizon','latency'],metric,n);s['cohort']=cohort;s['mode']=mode;e.append(s)
 ef=pd.concat(e);ef.to_csv(out/'execution_summary.csv',index=False)
 psummary=[]
 for cohort,n in [('monthly',20),('later',5)]:
  sub=pa[(pa.cohort==cohort)&pa.control_seed.isna()]
  for metric in ['fill_probability','mean_fill_time','markout_5','spread_5','passive_price_markout_5_bps']:
   g=summarize(sub,['model','horizon','latency','interpretation'],metric,n);g['cohort']=cohort;psummary.append(g)
 pd.concat(psummary).to_csv(out/'passive_accounting_summary.csv',index=False)
 matched=[]
 for cohort in ['monthly','later']:
  sub=pa[(pa.cohort==cohort)&(pa.horizon==20)&(pa.latency==0)&(pa.model=='xgboost')]
  if cohort=='monthly':sub=sub[sub.month=='2017-06']
  for interpretation in ['retain','reset']:
   for label,seed in [('primary',None),('control_seed7',7)]:
    q=sub[(sub.interpretation==interpretation)&(sub.control_seed.isna() if seed is None else sub.control_seed.eq(seed))]
    for metric in ['fill_probability','mean_fill_time','markout_5','passive_price_markout_5_bps']:
     matched.append(dict(cohort=cohort,interpretation=interpretation,model='xgboost',group=label,metric=metric,**strict_stats(q[metric],5)))
 pd.DataFrame(matched).to_csv(out/'passive_matched_controls.csv',index=False)
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
 fig,ax=plt.subplots(figsize=(8.4,4.5))
 for model,color in [('linear','#326a9c'),('xgboost','#c86b2c')]:
  s=af[(af.model==model)&(af.metric=='ic')].sort_values('feature_group');ax.plot(s.feature_group,s['mean'],marker='o',label=model,color=color)
 ax.set(xlabel='Frozen feature group (same eligible rows)',ylabel='Equal-weight stock/month Spearman IC',title='2017 WSE · 5 stocks × Apr/Jun/Sep/Nov · 20 messages');ax.legend();ax.grid(alpha=.2);fig.text(.5,.01,'F1: spread/top imbalance · F2: +microprice · F3: +OFI · F4: F2+depth · F5: all',ha='center',fontsize=8);fig.tight_layout(rect=(0,.04,1,1));fig.savefig(out/'signal_sources.png');plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(10,4.5),sharey=True)
 for ax,cohort,title in zip(axes,['monthly','later'],['Four fixed months','Dec 27–29 (3 shared dates)']):
  sub=ef[(ef.cohort==cohort)&(ef['mode']=='moving_exit')&(ef.horizon==20)&(ef.latency==0)].pivot(index='model',columns='metric',values='mean')
  x=np.arange(2);width=.2
  for j,(metric,label,color) in enumerate([('gross_midpoint_bps','Gross midpoint','#326a9c'),('entry_half_spread_bps','Entry half-spread','#d6a13d'),('exit_half_spread_bps','Exit half-spread','#c86b2c'),('crossed_bps','Crossed markout','#923a3a')]):
   y=sub.reindex(['linear','xgboost'])[metric].to_numpy();y=-y if 'half_spread' in metric else y
   ax.bar(x+(j-1.5)*width,y,width,label=label,color=color)
  ax.axhline(0,color='black',lw=.7);ax.set_xticks(x,['Linear','XGBoost']);ax.set_title(title)
 axes[0].set_ylabel('bp, equal-weight stock/period means');axes[1].legend(fontsize=8);fig.suptitle('2017 WSE · 20 messages, zero delay, strict |prediction| > 1 bp');fig.tight_layout();fig.savefig(out/'visible_costs.png');plt.close(fig)
 old=pd.read_csv('results/wselob_queue_execution_v1/block_fill_by_prediction_decile.csv');later=pd.read_csv('results/wselob_later_confirmation_v1/passive_deciles.csv')
 fig,axes=plt.subplots(1,3,figsize=(12,4.5))
 for cohort,data,n,bincol in [('monthly',old,20,'decile'),('later',later,5,'bin')]:
  s=data[(data.model=='xgboost')&data.control_seed.isna()&(data.horizon==20)&(data.latency==0)&(data.interpretation=='retain')]
  if 'day' in s:s=s[s.day=='all']
  for ax,metric,label,scale in zip(axes,['fill_probability','markout_5','spread_5'],['Conditional fill (%)','Post-fill midpoint (bp)','Passive price → midpoint (bp)'],[100,1,.5]):
   summary=summarize(s,[bincol],metric,n);ax.plot(summary[bincol],summary['mean']*scale,marker='o',label='Apr/Jun/Sep/Nov' if cohort=='monthly' else 'Dec 27–29 (3 dates)');ax.set(xlabel='Prediction decile',ylabel=label);ax.axhline(0,color='gray',lw=.7)
 axes[0].legend(fontsize=8);fig.suptitle('2017 WSE · XGBoost · 20-message lifetime · five-message post-fill outcomes');fig.text(.5,.01,'Zero delay · retain priority · equal stock/period means · conditional diagnostics, not actual fills or profit',ha='center',fontsize=9);fig.tight_layout(rect=(0,.05,1,1));fig.savefig(out/'conditional_execution.png');plt.close(fig)
 fig,axes=plt.subplots(1,3,figsize=(11,4),sharey=True)
 for ax,scope in zip(axes,['own_june','transfer_june','later']):
  for j,method in enumerate(['S0','S1']):
   sub=control[(control.scope==scope)&(control.shuffle==method)]
   for k,metric in enumerate(['ic','daily_ic']):
    v=summarize(sub,['seed'],metric,5)['mean'];ax.scatter(np.full(len(v),j+(k-.5)*.18),v,label=['Block IC','Daily IC'][k] if j==0 else None,marker=['o','x'][k],color=['#326a9c','#c86b2c'][k])
  ax.axhline(0,color='gray',lw=.6);ax.set_xticks([0,1],['S0: within day','S1: across days']);ax.set_title({'own_june':'Own-stock June','transfer_june':'Held-out-stock June','later':'Dec 27–29'}[scope])
 axes[0].set_ylabel('Five-stock mean IC per shuffle seed');axes[0].legend();fig.suptitle('2017 WSE · five frozen seeds; sensitivity, not a p-value distribution');fig.tight_layout();fig.savefig(out/'shuffle_controls.png');plt.close(fig)
 fig,ax=plt.subplots(figsize=(9,4.5));s=tm[(tm.day=='all')&(tm.offset_events==20)].copy();s['label']=s.symbol+' / '+s.period.replace({'later':'Dec 27–29'})
 x=np.arange(len(s));ax.plot(x,s.p50,'o',label='median');ax.vlines(x,s.p10,s.p90,color='#326a9c',alpha=.6,label='p10–p90');ax.set_xticks(x,s.label,rotation=90,fontsize=7);ax.set_yscale('log');ax.set_ylim(s.p10.min()/1.4,s.p90.max()*1.4);ax.set_ylabel('Elapsed event seconds (log scale)');ax.set_title('2017 WSE · exactly 20 original messages within valid segments');ax.legend();fig.tight_layout();fig.savefig(out/'event_time.png');plt.close(fig)
 atomic_json(out/'render_manifest.json',clean(dict(source='aggregate CSVs only',figures={p.name:file_hash(p) for p in out.glob('*.png')},input_csv_hashes={p.name:file_hash(p) for p in out.glob('*.csv')})))

if __name__=='__main__':main()
