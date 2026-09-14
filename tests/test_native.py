import importlib.util
import numpy as np
import pandas as pd
import pytest
from cloblab import native
from cloblab.queue_metrics import summarize

HAS_NATIVE=importlib.util.find_spec('cloblab._replay_queue') is not None
requires_native=pytest.mark.skipif(not HAS_NATIVE,reason='optional C++ extension not built')
DAY='2017-04-03'
DTYPE=[(k,'S1' if k=='action_type' else 'i8') for k in ('time','order_date','order_id','side','price','price_level','volume','priority_date','action_type','symbol_idx')]


def records(actions=None):
    start=pd.Timestamp(DAY+' 10:00',tz='Europe/Warsaw').value
    rows=[(start,1,0,1,0,2,0,-1,b'F',11322)]
    for side in (1,2):
        for k in range(11):
            rows.append((start+len(rows),1,side*100+k,side,10000-k if side==1 else 10002+k,2,2,start+len(rows),b'A',11322))
    for action,ident,side,price,size,priority in (actions or []):
        rows.append((start+len(rows),1,ident,side,price,2,size,priority,action.encode(),11322))
    for k in range(80):rows.append((start+len(rows),1,1000+k,1,9000-k,2,2,-1,b'A',11322))
    return np.array(rows,dtype=DTYPE)


def equal(a,b):
    assert a.keys()==b.keys()
    for k in a:
        if k=='final_queues':assert a[k]==b[k]
        else:np.testing.assert_array_equal(a[k],b[k],err_msg=k)


def test_backend_selection_and_absent_fallback(monkeypatch):
    def missing(_):raise ImportError('absent')
    monkeypatch.setattr(native,'import_module',missing)
    equal(native.replay_day(records(),'PEKAO',DAY,backend='auto'),native.replay_day(records(),'PEKAO',DAY))
    with pytest.raises(RuntimeError,match='unavailable'):native.replay_day(records(),'PEKAO',DAY,backend='native')
    with pytest.raises(ValueError):native.backend_module('unknown')


@requires_native
@pytest.mark.parametrize('interpretation',['retain','reset'])
@pytest.mark.parametrize('actions',[
 [('M',100,-1,-1,1,-1),('D',100,1,-1,-1,-1)],
 [('Y',100,1,10000,3,-1),('Y',2000,1,9500,2,-1)],
 [('M',100,-1,-1,-1,-1)],
 [('M',100,1,9950,2,-1)],
 [('M',100,1,10000,3,-1),('M',100,1,10000,1,-1)],
 [('A',2000,5,10200,2,7),('A',2001,5,10200,2,7)],
 [('A',2000,1,0,2,-1),('D',2000,1,0,2,-1)],
 [('F',0,1,0,0,-1)],
 [('A',2000,1,11000,2,-1),('D',2000,1,11000,2,-1)],
])
def test_replay_states(actions,interpretation):
    r=records(actions)
    p=native.replay_day(r,'PEKAO',DAY,interpretation=interpretation)
    c=native.replay_day(r,'PEKAO',DAY,backend='native',interpretation=interpretation)
    equal(p,c);equal(c,native.replay_day(r,'PEKAO',DAY,backend='native',interpretation=interpretation))


@requires_native
@pytest.mark.parametrize('action,ident',[('A',100),('M',90000),('D',90000)])
def test_state_errors_match(action,ident):
    for backend in ('python','native'):
        with pytest.raises(ValueError):native.replay_day(records([(action,ident,1,10000,2,-1)]),'PEKAO',DAY,backend=backend)


@requires_native
@pytest.mark.parametrize('side',[1,2])
@pytest.mark.parametrize('horizon',[10,20,50])
@pytest.mark.parametrize('latency',[0,1,5])
@pytest.mark.parametrize('interpretation',['retain','reset'])
def test_paths_and_aggregate_parity(side,horizon,latency,interpretation):
    r=records([('M',100,1,10000,1,-1),('D',100,1,10000,0,-1),('A',2000,1,10000,3,-1),('M',2000,1,10000,2,-1)])
    p=native.replay_day(r,'PEKAO',DAY,interpretation=interpretation)
    c=native.replay_day(r,'PEKAO',DAY,backend='native',interpretation=interpretation)
    placements=np.array([22+latency,30+latency],np.int64)
    a=native.queue_paths(p,placements,side,horizon,decision_latency=latency)
    b=native.queue_paths(c,placements,side,horizon,backend='native',decision_latency=latency)
    equal(a,b)
    fa=pd.DataFrame(a);fa['direction']=1 if side==1 else -1
    fb=pd.DataFrame(b);fb['direction']=fa.direction
    pd.testing.assert_series_equal(pd.Series(summarize(fa)),pd.Series(summarize(fb)))


@requires_native
@pytest.mark.parametrize('race',['fill_first','adverse_first','simultaneous','expire','boundary'])
def test_queue_race_fixtures(race):
    from test_queue_execution import events,change
    e=events();change(e,1,2,0);change(e,3,5,4,entered=1,execution=1)
    if race=='fill_first':e['bid'][4:]=99.99;e['ask'][4:]=100.01
    if race=='adverse_first':e['bid'][2:]=99.99;e['ask'][2:]=100.01
    if race=='simultaneous':e['bid'][3:]=99.99;e['ask'][3:]=100.01
    if race=='expire':e['execution'][:]=0
    if race=='boundary':e['segment'][2:]=2
    equal(native.queue_paths(e,np.array([0]),1,10),native.queue_paths(e,np.array([0]),1,10,backend='native'))


@pytest.mark.parametrize('fault',['shape','symbol','time','action'])
def test_malformed_inputs(fault):
    r=records()
    if fault=='shape':r=r.reshape(1,-1)
    if fault=='symbol':r['symbol_idx']=999
    if fault=='time':r['time'][2]=r['time'][0]-1
    if fault=='action':r['action_type'][2]=b'Q'
    with pytest.raises(ValueError):native.replay_day(r,'PEKAO',DAY)
