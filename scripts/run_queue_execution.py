"""Frozen all-block passive queue diagnostics; private row checkpoints only."""
import argparse
from pathlib import Path
import itertools
import json
import h5py
import numpy as np
import pandas as pd
from cloblab.queue_book import QueueBook
from cloblab.wselob import OrderBook
from cloblab.passive_execution import passive_paths
from cloblab.queue_metrics import summarize, deciles, paired_summary
from cloblab.scale_common import read_json, atomic_json, file_hash, digest
from cloblab.scientific_identity import scientific_config
from run_execution_robustness import collect_receipts, load_month, expected_keys


def replay_day(records, cached, interpretation, backend="python"):
    if backend != "python":
        from cloblab.native import replay_day as native_replay, SNAPSHOT_NAMES
        result = native_replay(records, str(cached.symbol.iloc[0]), str(cached.day.iloc[0]), backend=backend, interpretation=interpretation)
        indices = np.flatnonzero(result["valid"])
        if not np.array_equal(indices, cached.event_index.to_numpy()):
            raise ValueError("native replay differs from frozen valid indices")
        if not np.array_equal(result["snapshots"][indices], cached[SNAPSHOT_NAMES].to_numpy()):
            raise ValueError("native replay differs from frozen ten-level snapshots")
        return result
    n=len(records)
    names=['bid','ask','bid_size','ask_size','bid_orders','ask_orders','tick',
           'old_side','old_price','old_quantity','old_entered','new_side','new_price','new_quantity','new_entered','execution']
    data={k:np.zeros(n) for k in names}
    data['valid']=np.zeros(n,bool)
    data['segment']=np.full(n,-1,dtype=np.int64)
    book, reference = QueueBook(interpretation), OrderBook()
    expected=cached.set_index('event_index')
    lookup={int(r.event_index):r for r in cached.itertuples(index=False)}
    initialized=False
    seen_tick=np.inf
    for i,row in enumerate(pd.DataFrame.from_records(records).itertuples(index=False)):
        action=row.action_type.decode()
        initialized |= action=='F'
        if not initialized:raise ValueError('missing source reset')
        old,new=book.apply(row)
        reference.apply(row)
        # Full order and queue parity once per 1000 messages, plus all retained
        # cached ten-level snapshots below. This is a bounded independent check.
        if i%1000==0:book.assert_parity(reference)
        for prefix,order in [('old',old),('new',new)]:
            if order:
                for field in ('side','price','quantity','entered'):data[prefix+'_'+field][i]=getattr(order,field)
        if old and action=='D':data['execution'][i]=old.quantity
        if old and new and action=='M' and (old.side,old.price)==(new.side,new.price):
            data['execution'][i]=max(0,old.quantity-new.quantity)
        if i not in lookup:continue
        target=lookup[i]
        snap=book.snapshot()
        if snap is None or any(snap[k]!=getattr(target,k) for k in snap):
            raise ValueError('queue replay differs from frozen ten-level snapshot')
        if int(row.time)!=target.timestamp_ns:raise ValueError('source/cache timestamp mismatch')
        data['valid'][i]=True
        data['segment'][i]=target.segment
        for side,name in [(1,'bid'),(2,'ask')]:
            price=snap[name+'_px_1']
            data[name][i]=price
            data[name+'_size'][i]=snap[name+'_sz_1']
            data[name+'_orders'][i]=len(book.queue(side,price))
            prices=np.array([snap[f'{name}_px_{level}'] for level in range(1,11)])
            seen_tick=min(seen_tick,float(np.abs(np.diff(prices)).min()))
        data['tick'][i]=seen_tick
    # Retransmission is not matching evidence. Break diagnostics at any Y/F
    # even when the original cache has no invalid visible-book gap.
    barriers=np.cumsum(np.isin(records['action_type'],[b'F',b'Y']))
    data['segment']=data['segment']*(n+1)+barriers
    return data


def run_month(args, config, manifest, found, symbol, month, binding):
    work=Path(args.work)
    checkpoint=work/f'{symbol}-{month}.json'
    if checkpoint.exists():
        x=read_json(checkpoint)
        if x['binding']!=binding:raise ValueError('stale queue checkpoint')
        return x
    rows_by_h={}
    for h in config['dataset']['horizons_events']:
        rows,_=load_month(args.cache,manifest,symbol,month,config['features']['primary_set'],h)
        rows_by_h[h]=rows
    predictions={}
    for key,(folder,receipt) in found.items():
        if key[:2]!=(symbol,month):continue
        rows=rows_by_h[key[2]]
        with np.load(folder/'predictions.npz',allow_pickle=False) as p:
            for name in ('event_index','timestamp_ns'):
                if not np.array_equal(p[name],rows[name]):raise ValueError('prediction row mismatch')
            if not np.array_equal(p['actual'],rows[f'markout_{key[2]}']):raise ValueError('prediction outcome mismatch')
            predictions[key]=p['prediction'].copy()
    outputs={}
    source=read_json('configs/wselob_sources_v1.json')['files'][symbol]
    raw=Path(args.raw)/source['filename']
    if file_hash(raw)!=source['sha256']:raise ValueError('raw source hash mismatch')
    replay_rows=0
    with h5py.File(raw,'r') as handle:
        for day in sorted(set(rows_by_h[10].day)):
            cached=pd.read_parquet(Path(args.cache)/f'symbol={symbol}'/f'day={day}'/'snapshots.parquet')
            records=handle['d'+day.replace('-','')+'/table'][:]
            for interpretation in config['execution_labels']['priority_interpretations']:
                events=replay_day(records,cached,interpretation,args.backend)
                replay_rows+=len(records)
                for h,rows in rows_by_h.items():
                    mask=(rows.day==day).to_numpy()
                    indices=rows.loc[mask,'event_index'].to_numpy(dtype=int)
                    for latency in (0,1,5):
                        placements=indices+latency
                        safe=np.minimum(placements,len(records)-1)
                        eligible=(placements<len(records)) & events['valid'][safe] & (events['segment'][safe]==events['segment'][indices])
                        selected=placements[eligible]
                        from cloblab.native import queue_paths
                        paths={side:queue_paths(events,selected,side,h,backend=args.backend,tick=events['tick'][selected],decision_latency=latency) for side in (1,2)}
                        for key,pred in predictions.items():
                            if key[2]!=h:continue
                            prediction=pred[mask][eligible]
                            sign=np.sign(prediction)
                            frame=pd.DataFrame({'prediction':prediction,'direction':sign})
                            for name in paths[1]:
                                frame[name]=np.where(sign>0,paths[1][name],paths[2][name])
                            for name in ('fill_time','adverse_time'):frame.loc[sign==0,name]=-1
                            ident=(*key,latency,interpretation)
                            outputs.setdefault(ident,[]).append(frame)
            print(json.dumps({'symbol':symbol,'day':day,'state':'replayed'}),flush=True)
    blocks,pdec,qdec=[],[],[]
    for ident,pieces in outputs.items():
        frame=pd.concat(pieces,ignore_index=True)
        labels=dict(zip(['symbol','month','horizon','model','control_seed','latency','interpretation'],ident))
        blocks.append({**labels,**summarize(frame)})
        pdec.extend({**labels,**x} for x in deciles(frame,'prediction'))
        qdec.extend({**labels,**x} for x in deciles(frame[frame.direction!=0].reset_index(drop=True),'queue_ahead'))
    x={'binding':binding,'blocks':blocks,'prediction_deciles':pdec,'queue_deciles':qdec,'replayed_source_rows':replay_rows}
    # pandas provides standards-compliant nulls for undefined conditional means.
    x=json.loads(pd.Series(x).to_json())
    atomic_json(checkpoint,x)
    return x


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','cache','raw','work','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--prediction-roots',nargs='+',required=True)
    p.add_argument('--symbol')
    p.add_argument('--month')
    p.add_argument('--aggregate-only',action='store_true')
    p.add_argument('--backend',choices=['python','native','auto'],default='python')
    args=p.parse_args()
    config,manifest=read_json(args.config),read_json(Path(args.cache)/'manifest.json')
    found=collect_receipts(args.prediction_roots,config)
    if {r['task']['cache_hash'] for _,r in found.values()}!={digest(manifest)}:raise ValueError('wrong prediction cache binding')
    sources=[Path(__file__),Path('scripts/run_execution_robustness.py')]+[Path('src/cloblab')/f for f in ('queue_book.py','passive_execution.py','queue_metrics.py','wselob.py','scientific_identity.py')]
    binding=digest({'science':scientific_config(config),'cache':digest(manifest),'source':{p.name:file_hash(p) for p in sources},'predictions':sorted(r['artifacts']['predictions.npz'] for _,r in found.values())})
    Path(args.work).mkdir(parents=True,exist_ok=True)
    all_results=[]
    for symbol,month in itertools.product(config['dataset']['symbols'],config['evaluation']['fixed_test_months']):
        if args.symbol and symbol!=args.symbol:continue
        if args.month and month!=args.month:continue
        if args.aggregate_only:
            result=read_json(Path(args.work)/f'{symbol}-{month}.json')
            if result['binding']!=binding:raise ValueError('wrong checkpoint binding')
        else:result=run_month(args,config,manifest,found,symbol,month,binding)
        all_results.append(result)
    if args.symbol or args.month:return
    blocks=pd.DataFrame([r for x in all_results for r in x['blocks']])
    keys=['symbol','month','horizon','model','control_seed','latency','interpretation']
    actual={tuple(None if pd.isna(r[k]) else r[k] for k in keys) for r in blocks.to_dict('records')}
    expected={(*key,latency,interpretation) for key in expected_keys(config) for latency in (0,1,5) for interpretation in ('retain','reset')}
    if len(blocks)!=len(expected) or actual!=expected:raise ValueError('incomplete queue denominator')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    blocks.to_csv(out/'block_metrics.csv',index=False)
    groups=['model','horizon','control_seed','latency','interpretation']
    numeric=[c for c in blocks.columns if c not in keys]
    summary=blocks.groupby(groups,dropna=False)[numeric].mean().reset_index()
    count=blocks.groupby(groups,dropna=False).size().reset_index(name='blocks')
    summary=summary.merge(count,on=groups)
    # Every mean exposes its defined block count; undefined block values never
    # become zero, and strict headline means require all intended blocks.
    for col in numeric:
        counts=blocks.groupby(groups,dropna=False)[col].count().to_numpy()
        summary[col+'_defined_blocks']=counts
        summary.loc[counts!=summary.blocks,col]=np.nan
    for name in ('fill_summary','adverse_selection_summary','realized_spread_summary','fill_adverse_race_summary'):
        summary.to_csv(out/(name+'.csv'),index=False)
    summary[summary.control_seed.notna()].to_csv(out/'control_summary.csv',index=False)
    for name,field in [('fill_by_prediction_decile','prediction_deciles'),('fill_by_queue_decile','queue_deciles')]:
        d=pd.DataFrame([r for x in all_results for r in x[field]])
        d.to_csv(out/('block_'+name+'.csv'),index=False)
        g=d.groupby(groups+['decile'],dropna=False)
        z=g[numeric].mean();z['blocks']=g.size()
        for col in numeric:z[col+'_defined_blocks']=g[col].count()
        z.reset_index().to_csv(out/(name+'.csv'),index=False)
    paired_summary(blocks,config['dataset']['symbols'],config['evaluation']['fixed_test_months']).to_csv(out/'paired_model_differences.csv',index=False)
    atomic_json(out/'run_manifest.json',{'state':'complete','binding':binding,'scientific_config':scientific_config(config),
       'planned_cells':len(expected),'completed_cells':len(blocks),'completed_stock_months':len(all_results),
       'source_replay_rows_including_two_interpretations':sum(x['replayed_source_rows'] for x in all_results),
       'interpretation':'conditional depletion diagnostics; no identified exact fills',
       'identified_lower_fill_probability':0,'lower_bound_conditional_markouts':None,
       'prediction_evidence':[{'task_id':r['task']['task_id'],'prediction_sha256':r['artifacts']['predictions.npz']} for _,r in found.values()]})

if __name__=='__main__':main()
