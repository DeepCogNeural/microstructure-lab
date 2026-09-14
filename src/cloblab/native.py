"""Optional batch C++20 backend; Python remains the semantic reference.

replay_day returns event arrays and dense ten-level snapshots (NaN when invalid).
queue_paths returns the existing passive_paths field schema. No backend setting
changes the scientific experiment. Input arrays must not mutate during calls.
"""
from importlib import import_module
import numpy as np
import pandas as pd
from cloblab.queue_book import QueueBook
from cloblab.passive_execution import passive_paths
from cloblab.wselob import SYMBOL_IDS

EVENT_NAMES = ['bid','ask','bid_size','ask_size','bid_orders','ask_orders','tick',
    'old_side','old_price','old_quantity','old_entered','new_side','new_price','new_quantity','new_entered','execution']
SNAPSHOT_NAMES = [f'{side}_{kind}_{level}' for side in ('bid','ask') for level in range(1,11) for kind in ('px','sz')]


def backend_module(backend):
    if backend not in ('python','native','auto'):
        raise ValueError('backend must be python, native or auto')
    if backend=='python':return None
    try:return import_module('cloblab._replay_queue')
    except ImportError as exc:
        if backend=='auto':return None
        raise RuntimeError('C++ backend unavailable; build cpp/ or select backend=python') from exc


def normalize_records(records,symbol,day):
    names=('time','order_date','order_id','side','price','price_level','volume','priority_date','action_type','symbol_idx')
    if records.ndim!=1 or not records.dtype.names or any(k not in records.dtype.names for k in names):
        raise ValueError('expected structured WSELOB order records')
    if symbol not in SYMBOL_IDS or not np.all(records['symbol_idx']==SYMBOL_IDS[symbol]):raise ValueError('unexpected instrument')
    if any(records.dtype[k].kind not in 'iu' for k in names if k!='action_type'):raise ValueError('integer source fields required')
    if len(records) and np.any(records['time'][1:]<records['time'][:-1]):raise ValueError('non-monotonic source message time')
    times=pd.to_datetime(records['time'],unit='ns',utc=True).tz_convert('Europe/Warsaw')
    if len(records) and set(times.strftime('%Y-%m-%d'))!={day}:raise ValueError('source day mismatch')
    actions=np.asarray([x.decode() if isinstance(x,bytes) else str(x) for x in records['action_type']])
    if not np.isin(actions,['A','Y','M','D','F']).all():raise ValueError('unknown action')
    if np.any(np.abs(records['price_level'])>12):raise ValueError('unsupported price scale')
    matrix=np.empty((len(records),10),np.int64)
    for i,k in enumerate(names):matrix[:,i]=np.array([ord(x) for x in actions]) if k=='action_type' else records[k]
    start=pd.Timestamp(day+' 10:00',tz='Europe/Warsaw').value
    end=pd.Timestamp(day+' 16:00',tz='Europe/Warsaw').value
    return matrix,start,end


def python_replay(records,start,end,interpretation):
    n=len(records);book=QueueBook(interpretation)
    out={k:np.zeros(n) for k in EVENT_NAMES}
    out.update(valid=np.zeros(n,bool),segment=np.full(n,-1,np.int64),live_orders=np.zeros(n,np.int64),
               old_priority=np.zeros(n,np.int64),new_priority=np.zeros(n,np.int64),snapshots=np.full((n,40),np.nan))
    previous=None;segment=0;barriers=0;tick=np.inf;initialized=False
    for i,row in enumerate(pd.DataFrame.from_records(records).itertuples(index=False)):
        action=row.action_type.decode() if isinstance(row.action_type,bytes) else row.action_type
        barriers+=action in ('F','Y')
        if action=='F':initialized=True;previous=None
        if not initialized:raise ValueError('missing source reset')
        old,new=book.apply(row)
        out['segment'][i]=-(n+1)+barriers
        out['live_orders'][i]=len(book.orders)
        for prefix,order in [('old',old),('new',new)]:
            if order:
                for field in ('side','price','quantity','entered','priority'):out[prefix+'_'+field][i]=getattr(order,field)
        if old and action=='D':out['execution'][i]=old.quantity
        if old and new and action=='M' and (old.side,old.price)==(new.side,new.price):out['execution'][i]=max(0,old.quantity-new.quantity)
        if row.time<start or row.time>=end:continue
        snap=book.snapshot()
        if snap is None:previous=None;continue
        if previous is None or i!=previous+1:segment+=1
        previous=i;out['valid'][i]=True;out['segment'][i]=segment*(n+1)+barriers
        out['snapshots'][i]=[snap[k] for k in SNAPSHOT_NAMES]
        for side,name in [(1,'bid'),(2,'ask')]:
            out[name][i]=snap[name+'_px_1'];out[name+'_size'][i]=snap[name+'_sz_1']
            out[name+'_orders'][i]=len(book.queue(side,snap[name+'_px_1']))
            tick=min(tick,float(np.abs(np.diff([snap[f'{name}_px_{level}'] for level in range(1,11)])).min()))
        out['tick'][i]=tick
    out['final_queues']=[(side,price,*rank[:2],*rank[2],quantity) for (side,price),queue in sorted(book.queues.items()) for rank,quantity in queue.items()]
    return out


def replay_day(records,symbol,day,*,backend='python',interpretation='retain'):
    if interpretation not in ('retain','reset'):raise ValueError('unknown priority interpretation')
    matrix,start,end=normalize_records(records,symbol,day)
    module=backend_module(backend)
    if module is None:return python_replay(records,start,end,interpretation)
    return module.replay(matrix,start,end,interpretation=='reset')


def queue_paths(events,placements,side,horizon,*,backend='python',unit=1,tick=.01,decision_latency=0):
    placement=np.asarray(placements)
    if placement.ndim!=1 or placement.dtype.kind not in 'iu':raise ValueError('integer one-dimensional placements required')
    if decision_latency not in (0,1,5) or unit!=1:raise ValueError('unsupported frozen policy')
    ticks=np.broadcast_to(np.asarray(tick,dtype=float),placement.shape).copy()
    if not np.isfinite(ticks).all() or (ticks<=0).any():raise ValueError('invalid tick')
    module=backend_module(backend)
    if module is None:return passive_paths(events,placement,side,horizon,unit,ticks,decision_latency)
    # Native expects a tick field for the shared event schema; fixtures may use
    # a supplied scalar tick instead. It is unused by the state machine itself.
    if 'tick' not in events:events={**events,'tick':np.zeros(len(events['valid']))}
    return module.paths(events,np.asarray(placement,dtype=np.int64),side,horizon,ticks,decision_latency)
