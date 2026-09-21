"""Synthetic-only prereveal checks. Dates are identifiers, not real market inputs."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from cloblab import later_confirmation as c
from cloblab.evaluation import _fit_predict_linear
from cloblab.passive_execution import passive_paths
from cloblab.queue_metrics import summarize


def frames():
    def frame(days):
        out=pd.DataFrame([(day,i) for day in days for i in range(30)],columns=['day','event_index'])
        out['symbol']='PEKAO';out['segment']=1;out['timestamp_ns']=np.arange(len(out))
        for j,k in enumerate(c.FEATURES):out[k]=np.sin(np.arange(len(out))*(j+1)/11)
        out['unused_future_feature']=999
        for h in (10,20,50):out[f'markout_{h}']=out[c.FEATURES[0]]*.2
        return out
    return frame(['2017-12-21','2017-12-22']),frame(c.DATES)


def test_frozen_settings_and_task_denominator():
    config=c.frozen_config()
    assert config['features']==c.FEATURES
    assert len(c.tasks())==len(set(c.tasks()))==35
    assert sum(t[3] is None for t in c.tasks())==30
    expected=json.loads(Path('configs/wselob_xgboost_application_v1.json').read_text())['models']['xgboost']
    assert config['models']['xgboost']=={k:v for k,v in expected.items() if k not in ('scope','device')}
    assert config['training']['refit_during_confirmation'] is False


def test_training_isolation_reference_linear_and_frozen_prediction():
    train,test=frames();config=c.frozen_config()
    actual=c.fit_once(train,test,20,'linear',None,config)
    expected=_fit_predict_linear(train,test,c.FEATURES,'markout_20')
    np.testing.assert_array_equal(actual,expected)
    # Changing future labels cannot affect predictions on any confirmation day.
    changed=test.copy();changed['markout_20']=1e9
    np.testing.assert_array_equal(actual,c.fit_once(train,changed,20,'linear',None,config))
    for day in c.DATES:
        bad=train.copy();bad.loc[0,'day']=day
        with pytest.raises(ValueError,match='cutoff'):c.fit_once(bad,test,20,'linear',None,config)
    bad=train.copy();bad.loc[0,'symbol']='PZU'
    with pytest.raises(ValueError,match='pooling'):c.fit_once(bad,test,20,'linear',None,config)


def test_one_fit_all_days_exact_xgb_features_parameters_and_shuffle(monkeypatch):
    import xgboost
    train,test=frames();calls=[];cfg=c.frozen_config()
    class Fake:
        def __init__(self,**params):calls.append(('params',params))
        def fit(self,x,y):calls.append(('fit',list(x.columns),y.to_numpy().copy()))
        def predict(self,x):calls.append(('predict',len(x)));return np.zeros(len(x))
    monkeypatch.setattr(xgboost,'XGBRegressor',Fake)
    c.fit_once(train,test,20,'xgboost',7,cfg,2)
    assert len([x for x in calls if x[0]=='fit'])==1
    assert calls[-1]==('predict',len(test))
    assert calls[1][1]==c.FEATURES
    assert calls[0][1]=={**{k:v for k,v in cfg['models']['xgboost'].items() if k!='hyperparameter_search'},'device':'cpu','n_jobs':2}
    rng=np.random.default_rng(7);expected=np.concatenate([rng.permutation(p.markout_20.to_numpy()) for _,p in train.groupby('day',sort=True)])
    np.testing.assert_array_equal(calls[1][2],expected)


def test_all_partitions_no_substitution_and_training_selection():
    manifest={'partitions':[{'symbol':s,'day':d} for s in c.SYMBOLS for d in c.DATES]}
    for s in c.SYMBOLS:assert len(c.select_partitions(manifest,s,True))==3
    missing=copy.deepcopy(manifest);missing['partitions'].pop()
    with pytest.raises(ValueError,match='15'):c.select_partitions(missing,'PEKAO',True)
    replacement=copy.deepcopy(manifest);replacement['partitions'][0]['day']='2017-12-26'
    with pytest.raises(ValueError):c.select_partitions(replacement,'KGHM',True)
    history={'partitions':[{'symbol':'PEKAO','day':str(d.date())} for d in pd.bdate_range('2017-01-02',periods=45)]+manifest['partitions']}
    assert max(p['day'] for p in c.select_partitions(history,'PEKAO'))<'2017-12-27'


def quotes():
    out=pd.DataFrame([(d,i) for d in c.DATES for i in range(80)],columns=['day','event_index'])
    out['symbol']='PEKAO';out['segment']=1;out['timestamp_ns']=np.arange(len(out))
    out['bid_px_1']=100+out.event_index*.01;out['ask_px_1']=out.bid_px_1+.02
    return out


def test_crossing_exact_indices_common_rows_and_day_boundary():
    snapshots=quotes();test=snapshots[c.IDENTITY].copy()
    joined,eligible=c.crossing_frame(test,snapshots,20)
    assert eligible.sum()==3*55
    assert c.row_hash(joined)==c.row_hash(test)
    expected=10000*((100+.25)-(100+.05+.02))/(100+.05+.01)
    assert joined.loc[0,'long_crossed_bps_5']==pytest.approx(expected)
    assert not eligible[79]  # Never borrow the next day's event.
    split=snapshots.copy();split.loc[split.event_index>=40,'segment']=2
    _,valid=c.crossing_frame(split[c.IDENTITY],split,20)
    assert valid.sum()==3*30


def test_queue_reference_zero_signal_denominator_and_boundaries():
    from test_queue_execution import events,change
    e=events();e['tick']=np.full(len(e['valid']),.01);change(e,1,2,0);change(e,3,5,4,entered=1,execution=1)
    indices=np.array([0,0,0],dtype=np.int64);pred=np.array([2.,0.,-2.])
    frame,excluded=c.passive_frame(e,indices,pred,10,0)
    ref=passive_paths(e,indices,1,10,tick=np.full(3,e.get('tick',np.full(len(e['valid']),.01))[0])) if 'tick' in e else None
    assert excluded==0
    stats=summarize(frame)
    assert stats['eligible_decisions']==3 and stats['placed_orders']==2 and stats['zero_signal_decisions']==1
    assert stats['fill_probability']==stats['fills']/3
    if ref is not None: assert frame.loc[0,'fill_time']==ref['fill_time'][0]


def test_five_stock_aggregation_not_rows_or_days():
    rows=[]
    for i,s in enumerate(c.SYMBOLS):
        for model in ('linear','xgboost'):
            rows.append(dict(symbol=s,day='all',horizon=20,model=model,control_seed=np.nan,ic=i/10+(.01 if model=='xgboost' else 0),n_test=100000 if i==4 else 10))
    frame=pd.DataFrame(rows);table,headline=c.primary_table(frame)
    assert headline['linear']==pytest.approx(.2)
    assert headline['delta']==pytest.approx(.01) and headline['wins']==5
    with pytest.raises(ValueError):c.primary_table(frame.iloc[:-1])
    with pytest.raises(ValueError):c.primary_table(pd.concat([frame,frame]))
    frame.loc[0,'ic']=np.nan
    assert np.isnan(c.primary_table(frame)[1]['linear'])
    assert c.strict_mean([1.,np.nan])!=c.strict_mean([1.,np.nan])


def test_privacy_and_incomplete_publication(tmp_path):
    for record in [{'path':'private-location'},dict(hostname='private-machine'),{'raw_rows':[1,2]},{'symbol':'unexpected'}]:
        with pytest.raises(ValueError):c.safe_public_records([record])
    old=tmp_path/'wselob_xgboost_application_v1';old.mkdir();(old/'sentinel').write_text('unchanged')
    with pytest.raises(ValueError,match='incomplete'):c.aggregate([],old,'binding','a'*40)
    assert (old/'sentinel').read_text()=='unchanged'
    assert c.safe_public_records([{'symbol':'PEKAO','rows':3,'ic':float('nan')}])[0]['ic'] is None


def test_decile_ties_and_daily_assignments():
    q=quotes();pred=np.repeat(np.arange(12),20).astype(float)
    blocks,curves=c.aggressive_records(q[c.IDENTITY],pred,q,20)
    assert len(blocks)==12
    df=pd.DataFrame(curves)
    for latency in (0,1,5):
        period=df[(df.latency==latency)&(df.day=='all')].set_index('bin')
        daily=df[(df.latency==latency)&(df.day!='all')].groupby('bin').rows.sum()
        pd.testing.assert_series_equal(period.rows,daily,check_names=False)


def complete_receipts():
    receipts=[]
    for task in c.tasks():
        symbol,horizon,model,seed=task
        pred=[dict(day=d,ic=.2+(.01 if model=='xgboost' else 0),n_test=3) for d in ['all',*c.DATES]]
        aggressive=[dict(day=d,latency=l,rows=3,selected_rows=1,sign_selected_bps=-2.) for d in ['all',*c.DATES] for l in (0,1,5)]
        passive=[dict(day=d,latency=l,interpretation=i,eligible_decisions=3,zero_signal_decisions=1,placed_orders=2,fills=1,fill_probability=1/3,markout_5=-.2,spread_5=1.) for d in ['all',*c.DATES] for l in (0,1,5) for i in ('retain','reset')]
        curves=[dict(**p,bin=b) for p in passive for b in range(1,11)]
        receipts.append(dict(task=list(task),binding='b',fit_count=1,training_last_day='2017-12-22',training_rows=120,training_row_hash='same',test_row_hash='same',prediction_hash='a'*64,training_counts=[],test_counts=[],inventory=[dict(symbol=symbol,day=d,raw_messages=10,snapshot_rows=8,replay_exclusions={'outside_window':2}) for d in c.DATES],prediction=pred,aggressive=aggressive,passive=passive,aggressive_deciles=[],passive_deciles=curves,queue_deciles=[]))
    return receipts


def test_complete_aggregate_publication_guard_and_identity(tmp_path):
    results=complete_receipts()
    bad=copy.deepcopy(results);bad[0]['test_row_hash']='different'
    with pytest.raises(ValueError,match='unpaired'):c.aggregate(bad,tmp_path/c.OUTPUT_NAME,'b','a'*40)
    protected=tmp_path/'old-results';protected.mkdir()
    with pytest.raises(ValueError,match='overwrite'):c.aggregate(results,protected,'b','a'*40)
    out=tmp_path/c.OUTPUT_NAME
    headline=c.aggregate(results,out,'b','a'*40)
    assert headline['delta']==pytest.approx(.01)
    assert json.loads((out/'manifest.json').read_text())['completed_fits']==35
    assert len(pd.read_csv(out/'prediction.csv'))==140
    assert len(pd.read_csv(out/'passive.csv'))==840
    with pytest.raises(ValueError,match='overwrite'):c.aggregate(results,out,'b','a'*40)


def test_partial_task_never_refits(tmp_path):
    task=c.tasks()[0];folder=tmp_path/c.task_name(task);folder.mkdir();(folder/'started.json').write_text('{}')
    with pytest.raises(ValueError,match='incomplete task'):
        c.run_task(task,SimpleNamespace(work=tmp_path),{},'b',{}, {})


def test_tail_contrasts_missing_bins_never_forced():
    curve=pd.DataFrame([dict(symbol='PEKAO',day='all',horizon=20,model='linear',control_seed=np.nan,latency=0,interpretation='retain',bin=i,fill_probability=i/10,markout_5=-i/10) for i in range(1,11)])
    out=c.tail_contrasts(curve)
    assert out.iloc[0].fill_probability_tail_minus_center==pytest.approx(-.45)
    assert c.tail_contrasts(curve.iloc[:-1]).fill_probability_tail_minus_center.isna().all()


def test_synthetic_end_to_end_task_cache_replay_fit_resume(tmp_path,monkeypatch):
    import h5py
    from test_native import records,DAY
    from cloblab.wselob import reconstruct
    cfg=c.frozen_config();rawroot=tmp_path/'raw';rawroot.mkdir()
    raw=rawroot/cfg['dataset']['sources']['PEKAO']['filename']
    tailroot=tmp_path/'tail';historyroot=tmp_path/'history'
    tail={'partitions':[{'symbol':s,'day':d} for s in c.SYMBOLS if s!='PEKAO' for d in c.DATES]}
    shift0=pd.Timestamp(DAY+' 10:00',tz='Europe/Warsaw').value
    with h5py.File(raw,'w') as handle:
        for day in c.DATES:
            r=records();r['time']+=pd.Timestamp(day+' 10:00',tz='Europe/Warsaw').value-shift0
            handle.create_dataset('d'+day.replace('-','')+'/table',data=r)
            snapshots,_=reconstruct(r,day,'PEKAO');features=c.prepare(snapshots,[10,20,50])
            folder=tailroot/'symbol=PEKAO'/('day='+day);folder.mkdir(parents=True)
            snapshots.to_parquet(folder/'snapshots.parquet',index=False)
            features[c.IDENTITY+c.FEATURES+[f'markout_{h}' for h in (10,20,50)]].to_parquet(folder/'features.parquet',index=False)
            tail['partitions'].append(dict(symbol='PEKAO',day=day,features_sha256=c.file_hash(folder/'features.parquet'),snapshots_sha256=c.file_hash(folder/'snapshots.parquet')))
    cfg['dataset']['sources']['PEKAO']['sha256']=c.file_hash(raw)
    train,_=frames();history={'partitions':[]}
    for date in pd.bdate_range('2017-01-02',periods=40):
        day=str(date.date());f=train[train.day=='2017-12-21'].copy();f['day']=day
        folder=historyroot/'symbol=PEKAO'/('day='+day);folder.mkdir(parents=True)
        f.to_parquet(folder/'features.parquet',index=False)
        history['partitions'].append(dict(symbol='PEKAO',day=day,features_sha256=c.file_hash(folder/'features.parquet')))
    args=SimpleNamespace(work=tmp_path/'work',history=historyroot,tail=tailroot,raw=rawroot,threads=1)
    original=c._fit_predict_linear;fits=[]
    def counted(*a):fits.append(len(a[0]));return original(*a)
    monkeypatch.setattr(c,'_fit_predict_linear',counted)
    result=c.run_task(('PEKAO',20,'linear',None),args,cfg,'b',history,tail)
    assert len(fits)==1 and len(result['prediction'])==4 and len(result['passive'])==24
    assert c.run_task(('PEKAO',20,'linear',None),args,cfg,'b',history,tail)==result
    assert len(fits)==1
