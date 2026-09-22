"""Verify new aggregate denominators, old-result consistency and paired identities."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from cloblab.scale_common import read_json,file_hash,atomic_json
from cloblab.research_audit import task_plan


def main():
 p=argparse.ArgumentParser();p.add_argument('--out',default='results/wselob_research_audit_v1');p.add_argument('--old-hashes',required=True);a=p.parse_args();o=Path(a.out)
 c=read_json('configs/wselob_research_audit_v1.json');plan=task_plan(c)
 old=read_json(a.old_hashes)
 from cloblab.later_confirmation import LOCKS
 for path,h in LOCKS.items():
  if file_hash(path)!=h:raise ValueError('original preregistration modified')
 for path,h in old.items():
  if file_hash(path)!=h:raise ValueError('old result modified: '+path)
 controls=pd.read_csv(o/'control_blocks.csv');ab=pd.read_csv(o/'ablation_blocks.csv');ex=pd.read_csv(o/'execution_decomposition.csv');fx=pd.read_csv(o/'fixed_exit_latency.csv');pa=pd.read_csv(o/'passive_accounting.csv');clock=pd.read_csv(o/'event_time_summary.csv');algebra=pd.read_csv(o/'feature_algebra.csv')
 assert len(controls)==150 and len(ab)==200
 assert controls.task_id.nunique()==150 and ab.task_id.nunique()==200
 assert len(set(controls.task_id)|set(ab.task_id))==350
 for name,blocks,expected in [('control',controls,2250),('ablation',ab,4050)]:
  daily=pd.read_csv(o/f'{name}_daily.csv')
  assert len(daily)==expected and not daily.duplicated(['task_id','day']).any()
  for tid,g in daily.groupby('task_id'):
   b=blocks[blocks.task_id==tid].iloc[0]
   dates=clock[(clock.symbol==b.symbol)&(clock.day!='all')&(clock.offset_events==20)&(clock.period==b.period)].day
   assert set(g.day)==set(dates) and len(g)==b.days_expected
   assert g.rows.sum()==b.test_rows and g.ic.notna().sum()==b.days_defined
   assert np.isclose(g.ic.mean(skipna=False),b.daily_ic,equal_nan=True)
 states=pd.read_csv(o/'state_diagnostics.csv')
 assert len(states)==1800 and not states.duplicated(['task_id','spread_bin','imbalance_bin']).any()
 for tid,g in states.groupby('task_id'):
  assert len(g)==9 and g.rows.sum()==ab.loc[ab.task_id==tid,'test_rows'].iloc[0]
 keys=['kind','scope','symbol','period','model','feature_group','shuffle','seed','horizon']
 norm=lambda r:tuple(None if pd.isna(r[k]) else r[k] for k in keys)
 actual={norm(r) for r in pd.concat([controls,ab]).to_dict('records')}
 assert actual=={norm(r) for r in plan}
 for _,g in ab.groupby(['symbol','period']):
  assert len(g)==10 and g.test_row_hash.nunique()==1 and g.train_row_hash.nunique()==1
  assert g.test_rows.nunique()==1 and g.train_rows.nunique()==1
 for _,g in controls.groupby(['scope','symbol']):assert g.test_row_hash.nunique()==1 and g.train_row_hash.nunique()==1
 assert len(ex)==516 and len(fx)==186
 assert len(pa)==1032
 assert np.nanmax(ex.max_identity_error_bps)<1e-9 and np.nanmax(fx.max_identity_error_bps)<1e-9
 for tab in [ex,fx]:
  assert np.allclose(tab.gross_midpoint_bps-tab.entry_half_spread_bps-tab.exit_half_spread_bps,tab.crossed_bps,atol=1e-9,equal_nan=True)
  for _,g in tab.groupby(['cohort','symbol','period','horizon']):assert g.common_rows.nunique()==1
  assert (tab.selected_rows<=tab.common_rows).all()
  assert tab.loc[tab.selected_rows==0,'crossed_bps'].isna().all()
 legacy=pd.read_csv('results/wselob_execution_robustness_v1/block_metrics.csv')
 oldlater=pd.read_csv('results/wselob_later_confirmation_v1/aggressive.csv');oldlater=oldlater[oldlater.day=='all']
 original=[]
 for cohort,table in [('monthly',legacy),('later',oldlater)]:
  table=table.copy();table['cohort']=cohort
  if cohort=='later':table['period']='later'
  else:table['period']=table.month
  original.append(table)
 orig=pd.concat(original)
 k=['cohort','symbol','period','horizon','latency','model','control_seed']
 joined=ex.merge(orig,on=k,validate='one_to_one',suffixes=('','_old'))
 assert len(joined)==516
 assert np.allclose(joined.crossed_bps,joined.sign_selected_bps,atol=1e-8,equal_nan=True)
 assert np.array_equal(joined.selected_rows,joined.selected_rows_old)
 assert np.array_equal(joined.common_rows,joined.rows)
 assert len(clock)==2225 and len(clock[clock.day=='all'])==125
 precision=pd.read_csv(o/'event_clock_precision.csv')
 assert len(precision)==420 and precision.monotonic.all() and precision.source_day_matches.all()
 assert not precision.priority_field_used.any()
 assert (clock.valid+clock.invalid==clock.rows).all()
 assert (clock.zero_count<=clock.valid).all()
 assert (clock.loc[clock.valid>0,['p10','p50','p90','p99']].diff(axis=1).iloc[:,1:]>=0).all().all()
 assert len(algebra)==1250 and algebra['rows'].sum()==56887949
 assert algebra.max_abs_error_bps.max()<1e-9
 for offset in ['1','5','10','remaining']:
  assert np.allclose(pa['passive_price_markout_'+offset+'_bps'],pa['spread_'+offset]/2,equal_nan=True)
  assert (pa['markout_'+offset+'_observations']<=pa.fills).all()
 oldmodels=pd.read_csv('results/wselob_xgboost_application_v1/model_metrics_by_symbol_month.csv');base=oldmodels[(oldmodels.horizon==20)&oldmodels.control_seed.isna()&oldmodels.model.isin(['linear','xgboost'])]
 check=ab[ab.feature_group=='F5'].merge(base,left_on=['symbol','period','model'],right_on=['symbol','month','model'],suffixes=('','_old'),validate='one_to_one')
 check['ic_drift']=check.ic-check.ic_old
 check[['symbol','period','model','origin','ic','ic_old','ic_drift','test_row_hash']].to_csv(o/'baseline_reuse_check.csv',index=False)
 assert len(check)==40 and np.allclose(check.ic,check.ic_old,atol=1e-12)
 transfer=pd.read_csv('results/wselob_execution_robustness_v1/transfer_block_metrics.csv')
 old_seed=transfer[(transfer.month=='2017-06')&transfer.control_seed.eq(7)]
 new_seed=controls[(controls.scope=='transfer_june')&(controls.shuffle=='S0')&controls.seed.eq(7)]
 drift=new_seed.merge(old_seed,on='symbol',validate='one_to_one',suffixes=('','_old'))
 assert len(drift)==5 and np.array_equal(drift.test_rows,drift.n_test)
 drift['ic_drift']=drift.ic-drift.ic_old
 drift[['symbol','origin','ic','ic_old','ic_drift','test_rows','test_row_hash']].to_csv(o/'transfer_seed7_drift.csv',index=False)
 origin=pd.concat([controls,ab]).origin.value_counts().to_dict()
 assert origin=={'new_fit':298,'verified_original_prediction':52}
 assert len(pd.read_csv(o/'ablation_paired.csv'))==300
 atomic_json(o/'verification.json',dict(complete=True,old_artifacts_unchanged=len(old),controls=150,ablations=200,control_daily_rows=2250,ablation_daily_rows=4050,state_rows=1800,paired_contrasts=300,matched_ablation_blocks=20,cost_cells=516,fixed_exit_cells=186,passive_cells=1032,event_time_rows=2225,source_clock_days=420,origin_counts=origin,feature_partitions=1250,feature_rows=int(algebra['rows'].sum()),max_algebra_error_bps=float(algebra.max_abs_error_bps.max()),max_cost_identity_error_bps=float(ex.max_identity_error_bps.max()),original_cost_match=True,full_feature_ic_max_abs_drift=float(check.ic_drift.abs().max()),fresh_transfer_seed7_ic_max_abs_drift=float(drift.ic_drift.abs().max()),no_new_independent_test_set=True))
 if (o/'render_manifest.json').exists() and (o/'software_validation.json').exists():
  sources=['configs/wselob_research_audit_v1.json','src/cloblab/research_audit.py','src/cloblab/research_diagnostics.py','src/cloblab/evaluation.py','src/cloblab/scale_runner.py','src/cloblab/later_confirmation.py','scripts/audit_event_clock.py','scripts/render_research_audit.py','scripts/verify_research_audit.py','tests/test_research_audit.py','docs/RESEARCH_AUDIT_PROTOCOL.md','docs/SIGNAL_EXECUTION_DIAGNOSTICS_REPORT.md']
  atomic_json(o/'manifest.json',dict(experiment=c['experiment'],status='complete_post_inspection_explanatory_audit',base_commit='925c63d79944913dd318899d75de34f3ac300b51',source_sha256={s:file_hash(s) for s in sources},artifact_sha256={p.name:file_hash(p) for p in sorted(o.iterdir()) if p.is_file() and p.name!='manifest.json'},new_fits=298,verified_original_predictions=52,original_result_artifacts_unchanged=len(old),scientific_model_manifest='model_manifest.json',diagnostic_manifest='diagnostics_manifest.json',software_validation='software_validation.json',data_source='WSELOB-2017, DOI 10.17632/3g4mhdp899.1, CC BY 4.0',no_row_level_data=True))
 print('verified complete audit and immutable original results')

if __name__=='__main__':main()
