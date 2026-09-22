import copy
import numpy as np
import pandas as pd
import pytest
from cloblab.research_audit import shuffle_labels,strict_stats,task_plan,task_id,fold_parts,state_scores
from cloblab.evaluation import _spearman_corr,_fit_predict_linear
from cloblab.scale_common import read_json


def test_fixed_plan_and_scientific_identity():
 c=read_json('configs/wselob_research_audit_v1.json');p=task_plan(c)
 assert len(p)==350 and sum(t['kind']=='control' for t in p)==150
 baseline=task_id(c,p[0],{},'code');r=copy.deepcopy(c);r['runtime']={'threads':12,'device':'cuda'}
 assert baseline==task_id(r,p[0],{},'code')
 for key,value in [('seeds',[7]),('horizon',50),('full_features',['spread_bps'])]:
  r=copy.deepcopy(c);r[key]=value
  assert baseline!=task_id(r,p[0],{},'code')
 assert baseline!=task_id(c,p[0],{},'changed')

@pytest.mark.parametrize('method,keys',[('S0',['symbol','day']),('S1',['symbol'])])
def test_shuffle_only_training_label_position_and_multiset(method,keys):
 f=pd.DataFrame({'symbol':np.repeat(['A','B'],40),'day':np.tile(np.repeat(['01','02'],20),2),'markout_20':np.arange(80.),'feature':np.arange(80.)},index=np.arange(80)+500)
 original=f.copy(deep=True);a=shuffle_labels(f,'markout_20',method,7);b=shuffle_labels(f,'markout_20',method,17)
 pd.testing.assert_frame_equal(f,original)
 pd.testing.assert_frame_equal(a,shuffle_labels(f,'markout_20',method,7))
 assert not a.markout_20.equals(b.markout_20)
 pd.testing.assert_frame_equal(a.drop(columns='markout_20'),original.drop(columns='markout_20'))
 for k,g in f.groupby(keys):
  ix=g.index;assert sorted(a.loc[ix,'markout_20'])==sorted(g.markout_20)


def test_transfer_exclusion_and_chronology():
 c=read_json('configs/wselob_research_audit_v1.json');parts=[]
 for s in c['symbols']:
  parts.extend(dict(symbol=s,day=d.strftime('%Y-%m-%d')) for d in pd.date_range('2017-01-01',periods=50))
  parts.append(dict(symbol=s,day='2017-06-01'))
 t=next(t for t in task_plan(c) if t['scope']=='transfer_june')
 train,test=fold_parts(c,[dict(partitions=parts),{}],t)
 assert {p['symbol'] for _,p in train}==set(c['symbols'])-{t['symbol']}
 assert max(p['day'] for _,p in train)<min(p['day'] for _,p in test)


def test_strict_nan_and_constant_prediction():
 assert np.isnan(_spearman_corr(np.ones(30),np.arange(30)))
 r=strict_stats([1,np.nan],2);assert np.isnan(r['mean']) and r['defined']==1 and r['available_case_mean']==1
 assert np.isnan(strict_stats([1],2)['mean'])


def test_scaling_train_only():
 train=pd.DataFrame({'x':[0.,1.,2.,3.],'y':[1.,3.,5.,7.]})
 single=pd.DataFrame({'x':[4.]});mixed=pd.DataFrame({'x':[4.,1e12]})
 assert _fit_predict_linear(train,single,['x'],'y')[0]==_fit_predict_linear(train,mixed,['x'],'y')[0]


def test_state_cutpoints_training_only_and_empty_ties():
 tr=pd.DataFrame({'spread_bps':[1.]*8,'top_imbalance':[0.]*8})
 te=pd.DataFrame({'spread_bps':[1.,100.],'top_imbalance':[0.,100.],'markout_20':[1.,2.]})
 r=state_scores(tr,te,np.array([1.,2.]));assert len(r)==9 and sum(v['rows'] for v in r)==2
 assert r[0]['rows']==1 and all(v['spread_cut1']==1 for v in r)

from cloblab.research_diagnostics import cost_components,selected_cost,exact_clock
from cloblab.advanced_features import add_microstructure_features


def quotes():
 n=12
 return pd.DataFrame(dict(symbol=['A']*n,day=['2017-01-01']*n,segment=[1]*6+[2]*6,event_index=np.arange(n),timestamp_ns=1483228800000000000+np.arange(n,dtype=np.int64)*101,bid_px_1=100+np.arange(n)/10,ask_px_1=100.2+np.arange(n)/10))

@pytest.mark.parametrize('fixed',[False,True])
@pytest.mark.parametrize('d',[0,1,2])
def test_exact_cost_long_short_delay_identity(fixed,d):
 f=quotes();out=cost_components(f,3,d,fixed);valid=np.isfinite(out.long_crossed_bps).to_numpy()
 for sign in [-1,1]:
  r=selected_cost(np.full(len(f),2.*sign),out,valid)
  assert abs(r['gross_midpoint_bps']-r['entry_half_spread_bps']-r['exit_half_spread_bps']-r['crossed_bps'])<1e-10
  assert r['max_identity_error_bps']<1e-10
 assert np.isnan(out.long_crossed_bps.iloc[5])
 r=selected_cost(np.ones(len(f)),out,valid);assert r['selected_rows']==0 and np.isnan(r['crossed_bps'])


def test_event_clock_nanosecond_precision_segment_and_gap():
 f=quotes();d=exact_clock(f,2);assert np.all(d[np.isfinite(d)]==202e-9)
 assert np.isnan(d[4]) and np.isnan(d[5]) and np.isnan(d[-1])
 f.loc[1,'timestamp_ns']=f.loc[0,'timestamp_ns'];assert exact_clock(f,1)[0]==0
 with pytest.raises(ValueError):exact_clock(f.drop(index=2),1)

@pytest.mark.parametrize('bidq,askq',[(1,1),(0,3),(5,0),(0,0),(1e9,1)])
def test_microprice_algebra_and_zero_depth(bidq,askq):
 f=pd.DataFrame(dict(bid_px_1=[100.],ask_px_1=[100.2],bid_sz_1=[bidq],ask_sz_1=[askq]))
 r=add_microstructure_features(f).iloc[0]
 expected=.5*(1e4*.2/100.1)*(bidq-askq)/(bidq+askq) if bidq+askq else 0
 assert abs(r.microprice_minus_mid_bps-expected)<1e-10

from cloblab.research_audit import read_parts
from cloblab.scale_common import file_hash


def test_all_ablation_groups_use_full_feature_intersection(tmp_path):
 c=read_json('configs/wselob_research_audit_v1.json');f=quotes()
 for feature in c['full_features']:f[feature]=1.
 f['markout_20']=np.arange(len(f),dtype=float);f.loc[0,'ofi_l1_norm']=np.nan;f.loc[1,'depth_imbalance']=np.inf
 folder=tmp_path/'symbol=A'/'day=2017-01-01';folder.mkdir(parents=True);path=folder/'features.parquet';f.to_parquet(path,index=False)
 part=dict(symbol='A',day='2017-01-01',features_sha256=file_hash(path))
 selected=read_parts([tmp_path],[(0,part)],c['full_features'])
 assert selected.event_index.tolist()==list(range(2,len(f)))
 for features in c['feature_groups'].values():assert len(selected[features])==10

from types import SimpleNamespace
from cloblab.research_audit import aggregate


def test_aggregate_rejects_missing_receipt_instead_of_dropping(tmp_path):
 c=read_json('configs/wselob_research_audit_v1.json')
 parts=[dict(symbol=s,day=d.strftime('%Y-%m-%d'),features_sha256='frozen') for s in c['symbols'] for d in pd.date_range('2017-01-01',periods=50)]
 parts += [dict(symbol=s,day='2017-06-01',features_sha256='test') for s in c['symbols']]
 args=SimpleNamespace(work=tmp_path,out=tmp_path/'out')
 with pytest.raises(FileNotFoundError):aggregate(c,[dict(partitions=parts),dict(partitions=[])],args,'code')
 assert not (tmp_path/'out').exists()
