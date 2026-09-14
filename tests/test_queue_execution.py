from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from cloblab.queue_book import QueueBook
from cloblab.wselob import OrderBook
from cloblab.passive_execution import passive_paths
from cloblab.queue_metrics import summarize, paired_summary


def order(action, ident=1, volume=2, price=10000, priority=-1):
    return SimpleNamespace(action_type=action,order_date=1,order_id=ident,side=1,
                           price=price,price_level=2,volume=volume,priority_date=priority,time=10)


def test_queue_priority_and_parity():
    q,r=QueueBook(),OrderBook()
    for row in [order('F'),order('A',1,priority=20),order('A',2,priority=10),order('M',1,volume=1),order('D',2)]:
        q.apply(row);r.apply(row);q.assert_parity(r)
    assert len(q.queue(1,100))==1
    assert q.visible[(1,1)].quantity==1


@pytest.mark.parametrize('volume,price',[(1,10000),(3,10000),(2,10000),(2,10100)])
@pytest.mark.parametrize('interpretation',['retain','reset'])
def test_modifications(volume,price,interpretation):
    q=QueueBook(interpretation);q.apply(order('A'))
    old=q.visible[(1,1)]
    q.apply(order('M',volume=volume,price=price))
    new=q.visible[(1,1)]
    assert (new.entered==old.entered)==(interpretation=='retain' and price==10000)


def test_explicit_priority_and_retransmission():
    q=QueueBook();q.apply(order('Y',priority=10));q.apply(order('M',priority=20))
    assert q.visible[(1,1)].priority==20
    q.apply(order('Y',volume=3,priority=20))
    assert len(q.visible)==1
    with pytest.raises(ValueError):q.apply(order('A'))
    with pytest.raises(ValueError):q.apply(order('D',ident=99))


def events():
    n=70
    x={k:np.zeros(n) for k in ['old_side','old_price','old_quantity','old_entered','new_side','new_price','new_quantity','new_entered','execution']}
    x.update(valid=np.ones(n,bool),segment=np.ones(n,int),bid=np.full(n,100.),ask=np.full(n,100.02),
             bid_size=np.full(n,2.),ask_size=np.full(n,2.),bid_orders=np.ones(n),ask_orders=np.ones(n))
    return x


def change(x,i,oldqty,newqty,entered=0,newentered=None,execution=0,price=100):
    for key,val in dict(old_side=1,old_price=price,old_quantity=oldqty,old_entered=entered,
                        new_side=1 if newqty else 0,new_price=price if newqty else 0,
                        new_quantity=newqty,new_entered=entered if newentered is None else newentered,execution=execution).items():x[key][i]=val


def test_partial_ahead_and_behind_execution():
    x=events();change(x,1,2,1,execution=1);change(x,2,1,0,execution=1)
    # Removing the last ahead share is insufficient to consume our extra unit.
    assert passive_paths(x,[0],1,10)['fill_time'][0]==-1
    change(x,3,2,1,entered=1,execution=1)
    result=passive_paths(x,[0],1,10)
    assert result['fill_time'][0]==3
    assert result['queue_ahead'][0]==2


def test_new_and_cancelled_behind_never_increase_or_decrease_ahead():
    x=events();change(x,1,0,100,entered=1);change(x,2,100,0,entered=1,execution=100)
    assert passive_paths(x,[0],1,10)['fill_time'][0]==-1


def test_cancellation_ahead_clears_but_does_not_fill():
    x=events();change(x,1,2,0);change(x,2,5,4,entered=1,execution=1)
    assert passive_paths(x,[0],1,10)['fill_time'][0]==2


def test_unrelated_price_cannot_fill():
    x=events();change(x,1,2,0);change(x,2,5,4,entered=1,execution=1,price=99)
    assert passive_paths(x,[0],1,10)['fill_time'][0]==-1


def test_expiry_and_boundary():
    x=events();change(x,1,2,0);change(x,11,5,4,entered=1,execution=1)
    assert passive_paths(x,[0],1,10)['fill_time'][0]==-1
    assert passive_paths(x,[0],1,20)['fill_time'][0]==11
    x['segment'][5:]=2
    assert passive_paths(x,[0],1,20)['fill_time'][0]==-1


def test_latency_uses_placement_quote_and_no_future_placement_information():
    x=events();x['bid'][5:]=99.;x['ask'][5:]=99.02
    result=passive_paths(x,[5],1,10)
    assert result['placement_price'][0]==99
    x['bid'][6:]=98
    assert passive_paths(x,[5],1,10)['placement_price'][0]==99


def test_simultaneous_race_and_postfill_offsets():
    x=events();change(x,1,2,0);change(x,2,5,4,entered=1,execution=1)
    x['bid'][2:]=99.99;x['ask'][2:]=100.01
    r=passive_paths(x,[0],1,10)
    assert r['simultaneous'][0] and not r['fill_before_adverse'][0]
    assert r['markout_1'][0]==0
    assert r['spread_1'][0]==0


def test_missing_and_unpaired_denominators():
    b=pd.DataFrame([dict(symbol='S',month='M',model=m,control_seed=np.nan,interpretation='retain',
        horizon=10,latency=0,eligible_decisions=n,fill_probability=.1,fill_before_adverse=.1,markout_5=0,spread_5=0)
        for m,n in [('linear',10),('xgboost',11)]])
    with pytest.raises(ValueError,match='unpaired'):paired_summary(b,['S'],['M'])
    with pytest.raises(ValueError,match='incomplete'):paired_summary(b.iloc[:1],['S'],['M'])


def test_reset_interpretation_reorders_the_visible_queue():
    q=QueueBook('reset')
    a=order('A',1,priority=10);a.time=10;q.apply(a)
    b=order('A',2,priority=20);b.time=20;q.apply(b)
    amendment=order('M',1,volume=3);amendment.time=30;q.apply(amendment)
    assert [key[2][1] for key,_ in q.queue(1,100)]==[2,1]


def test_remaining_original_horizon_is_not_shifted_by_latency():
    x=events();change(x,6,2,0,entered=0);change(x,11,5,4,entered=6,execution=1)
    # Placement at 5, fill at 11, original decision horizon at 10: undefined.
    r=passive_paths(x,[5],1,10,decision_latency=5)
    assert r['fill_time'][0]==6
    assert np.isnan(r['markout_remaining'][0])


def test_zero_direction_remains_in_denominator():
    r=passive_paths(events(),[0],1,10)
    frame=pd.DataFrame(r);frame['direction']=0
    summary=summarize(frame)
    assert summary['eligible_decisions']==1
    assert summary['placed_orders']==0
    assert summary['fill_probability']==0
    assert np.isnan(summary['markout_5'])


def test_queue_science_identity_excludes_runtime_but_binds_assumptions():
    from cloblab.scientific_identity import scientific_config
    config={'execution_labels':{'virtual_size':1,'priority_interpretations':['retain'],'workers':1}}
    base=scientific_config(config)
    config['execution_labels']['workers']=7
    assert scientific_config(config)==base
    config['execution_labels']['priority_interpretations']=['reset']
    assert scientific_config(config)!=base


def test_published_queue_denominators_and_original_predictions():
    import json
    from pathlib import Path
    root=Path('results/wselob_queue_execution_v1')
    if not root.exists():pytest.skip('full-data aggregates are not published yet')
    manifest=json.loads((root/'run_manifest.json').read_text())
    assert manifest['state']=='complete'
    assert manifest['planned_cells']==manifest['completed_cells']==822
    assert manifest['completed_stock_months']==20
    original=pd.read_csv('results/wselob_xgboost_application_v1/model_metrics_by_symbol_month.csv')
    expected=set(original[original.model.isin(['linear','xgboost'])].task_id)
    assert {r['task_id'] for r in manifest['prediction_evidence']}==expected
    b=pd.read_csv(root/'block_metrics.csv')
    assert len(b)==822
    assert not b.duplicated(['symbol','month','horizon','model','control_seed','latency','interpretation']).any()
    assert (b.eligible_decisions==b.placed_orders+b.zero_signal_decisions).all()
    assert np.allclose(b.fill_probability,b.fills/b.eligible_decisions)
    assert np.allclose(b.fill_before_adverse+b.adverse_before_fill+b.simultaneous+b.no_event_fraction,1)
    assert (b.fills<=b.placed_orders).all()
    primary=b[b.control_seed.isna()]
    pair=primary[primary.model=='linear'].merge(primary[primary.model=='xgboost'],on=['symbol','month','horizon','latency','interpretation'],suffixes=('_l','_x'))
    assert len(pair)==360
    assert (pair.eligible_decisions_l==pair.eligible_decisions_x).all()
    groups=['model','horizon','control_seed','latency','interpretation']
    expected_mean=b.groupby(groups,dropna=False).fill_probability.mean().sort_index()
    published=pd.read_csv(root/'fill_summary.csv').set_index(groups).fill_probability.sort_index()
    assert np.allclose(expected_mean,published)
    for prefix in ('markout','spread'):
        for offset in ('1','5','10','remaining'):
            assert (b[f'{prefix}_{offset}_observations']<=b.fills).all()
