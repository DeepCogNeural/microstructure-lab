"""Exact-index cost and clock diagnostics; no fitting or queue semantic changes."""
from __future__ import annotations
import argparse
import itertools
from pathlib import Path
import numpy as np
import pandas as pd
from cloblab.later_confirmation import IDENTITY,FEATURES,clean,row_hash
from cloblab.native import replay_day,SNAPSHOT_NAMES
from cloblab.research_audit import strict_stats
from cloblab.scale_common import atomic_json,read_json,digest,file_hash


def cost_components(frame,horizon,latency,fixed_exit=False):
    if horizon<=0 or latency<0 or (fixed_exit and latency>=horizon):raise ValueError('invalid offsets')
    keys=['symbol','day','segment'];g=frame.groupby(keys,sort=False)
    if frame.duplicated(IDENTITY).any() or not g.event_index.diff().dropna().eq(1).all():raise ValueError('duplicate or invalid segment gap')
    cols=['bid_px_1','ask_px_1','event_index']
    entry=g[cols].shift(-latency);exit=g[cols].shift(-(horizon if fixed_exit else horizon+latency))
    valid=(entry.event_index==frame.event_index+latency)&(exit.event_index==frame.event_index+(horizon if fixed_exit else horizon+latency))
    mid=(entry.bid_px_1+entry.ask_px_1)/2;future=(exit.bid_px_1+exit.ask_px_1)/2
    out=frame[IDENTITY].copy()
    out['gross_long_bps']=(1e4*(future-mid)/mid).where(valid)
    out['entry_half_spread_bps']=(1e4*(entry.ask_px_1-entry.bid_px_1)/(2*mid)).where(valid)
    out['exit_half_spread_bps']=(1e4*(exit.ask_px_1-exit.bid_px_1)/(2*mid)).where(valid)
    out['long_crossed_bps']=(1e4*(exit.bid_px_1-entry.ask_px_1)/mid).where(valid)
    out['short_crossed_bps']=(1e4*(entry.bid_px_1-exit.ask_px_1)/mid).where(valid)
    return out


def exact_clock(frame,offset):
    if offset<1 or int(offset)!=offset:raise ValueError('invalid event offset')
    keys=['symbol','day','segment'];g=frame.groupby(keys,sort=False)
    if frame.duplicated(IDENTITY).any() or not g.event_index.diff().dropna().eq(1).all():raise ValueError('invalid event mapping')
    target=g[['event_index','timestamp_ns']].shift(-offset,fill_value=0)
    valid=(target.event_index==frame.event_index+offset)
    dt=(target.timestamp_ns-frame.timestamp_ns)/1e9
    if (dt[valid]<0).any():raise ValueError('nonmonotonic event time')
    return dt.where(valid).to_numpy()


def time_summary(values):
    x=np.asarray(values);ok=np.isfinite(x);v=x[ok]
    q=np.quantile(v,[.1,.5,.9,.99]) if len(v) else np.full(4,np.nan)
    return dict(rows=len(x),valid=int(ok.sum()),invalid=int((~ok).sum()),zero_count=int((v==0).sum()),zero_fraction=float((v==0).mean()) if len(v) else np.nan,unit='seconds',**dict(zip(['p10','p50','p90','p99'],q)))


def selected_cost(pred,components,common):
    selected=common&(np.abs(pred)>1);sign=np.sign(pred)
    gross=sign*components.gross_long_bps.to_numpy();entry=components.entry_half_spread_bps.to_numpy();exit=components.exit_half_spread_bps.to_numpy()
    crossed=np.where(sign>0,components.long_crossed_bps,components.short_crossed_bps)
    residual=gross-entry-exit-crossed
    valid=common&(sign!=0)
    error=float(np.max(np.abs(residual[valid]))) if valid.any() else np.nan
    if np.isfinite(error) and error>1e-9:raise ValueError('cost identity failed')
    mean=lambda x:float(np.asarray(x)[selected].mean()) if selected.any() else np.nan
    return dict(prediction_rows=len(pred),common_rows=int(common.sum()),selected_rows=int(selected.sum()),coverage=float(selected.sum()/common.sum()) if common.any() else np.nan,gross_midpoint_bps=mean(gross),entry_half_spread_bps=mean(entry),exit_half_spread_bps=mean(exit),crossed_bps=mean(crossed),breakeven_shortfall_bps=-mean(crossed),max_identity_error_bps=error,undefined_reason='' if selected.any() else 'no_threshold_selected_rows')


def load_legacy(symbol,period,h,model,seed,rows,roots,evidence):
    matches=[r for r in evidence if (r['symbol'],r['month'],r['horizon'],r['model'],r['control_seed'])==(symbol,period,h,model,seed)]
    if len(matches)!=1:raise ValueError('missing published prediction evidence')
    r=matches[0]
    for root in roots:
        path=Path(root)/'tasks'/r['legacy_task_id']/'predictions.npz'
        if not path.exists():continue
        if file_hash(path)!=r['prediction_sha256']:raise ValueError('prediction hash')
        with np.load(path,allow_pickle=False) as saved:
            if not all(np.array_equal(saved[k],rows[k]) for k in ['event_index','timestamp_ns']):raise ValueError('prediction identity')
            if not np.array_equal(saved['actual'],rows[f'markout_{h}']):raise ValueError('prediction labels')
            return saved['prediction'].copy(),r['prediction_sha256']
    raise FileNotFoundError(f'missing original prediction {symbol} {period} {h} {model} {seed}')


def clock_and_quotes(args,c):
    import h5py
    sources=read_json('configs/wselob_sources_v1.json')['files']
    frames={};times=[];algebra=[];bindings=[]
    for root,cohort in [(args.history,'monthly'),(args.tail,'later')]:
        manifest=read_json(Path(root)/'manifest.json')
        for symbol in c['symbols']:
            raw=Path(args.raw)/sources[symbol]['filename']
            if file_hash(raw)!=sources[symbol]['sha256']:raise ValueError('raw hash')
            with h5py.File(raw,'r') as handle:
                for p in manifest['partitions']:
                    if p['symbol']!=symbol:continue
                    day=p['day'];folder=Path(root)/f'symbol={symbol}'/f'day={day}';path=folder/'features.parquet'
                    if file_hash(path)!=p['features_sha256']:raise ValueError('feature hash')
                    f=pd.read_parquet(path);v=np.isfinite(f[FEATURES]).all(axis=1)
                    error=f.loc[v,'microprice_minus_mid_bps']-.5*f.loc[v,'spread_bps']*f.loc[v,'top_imbalance']
                    algebra.append(dict(symbol=symbol,day=day,rows=len(f),valid_rows=int(v.sum()),max_abs_error_bps=float(error.abs().max()),mean_abs_error_bps=float(error.abs().mean())))
                    if cohort=='monthly' and day[:7] not in c['months']:continue
                    records=handle['d'+day.replace('-','')+'/table'][:]
                    ix=f.event_index.to_numpy(dtype=np.int64)
                    if not np.array_equal(records['time'][ix],f.timestamp_ns):raise ValueError('event timestamp mismatch')
                    if np.any(np.diff(records['time'])<0):raise ValueError('nonmonotonic raw time')
                    events=replay_day(records,symbol,day,backend='native')
                    if not np.array_equal(np.flatnonzero(events['valid']),ix):raise ValueError('native/cache valid indices differ')
                    q=f.copy();q['bid_px_1']=events['snapshots'][ix,SNAPSHOT_NAMES.index('bid_px_1')];q['ask_px_1']=events['snapshots'][ix,SNAPSHOT_NAMES.index('ask_px_1')]
                    # Independently re-evaluate the cached labels on exact source rows.
                    mid=(q.bid_px_1+q.ask_px_1)/2
                    for h in [10,20,50]:
                        endpoint=q.assign(mid=mid).groupby(['symbol','day','segment']).mid.shift(-h)
                        rebuilt=1e4*(endpoint/mid-1)
                        if not np.array_equal(rebuilt.to_numpy(),q[f'markout_{h}'].to_numpy(),equal_nan=True):raise ValueError('label reconstruction mismatch')
                    period=day[:7] if cohort=='monthly' else 'later';key=(cohort,symbol,period)
                    frames.setdefault(key,[]).append(q)
                    for offset in c['clock']['offsets']:
                        dt=exact_clock(q,offset)
                        times.append(dict(cohort=cohort,symbol=symbol,period=period,day=day,offset_events=offset,**time_summary(dt)))
                    bindings.append(dict(cohort=cohort,symbol=symbol,day=day,features_sha256=p['features_sha256'],raw_sha256=sources[symbol]['sha256']))
            print(f'quotes ready {cohort} {symbol}',flush=True)
    return frames,times,algebra,bindings


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['history','tail','raw','work','later']:p.add_argument('--'+name,required=True)
    p.add_argument('--prediction-roots',nargs='+',required=True);p.add_argument('--out',default='results/wselob_research_audit_v1');p.add_argument('--aggregate-only',action='store_true');a=p.parse_args()
    c=read_json('configs/wselob_research_audit_v1.json');work=Path(a.work);work.mkdir(parents=True,exist_ok=True);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    binding=digest(dict(config=c,code=file_hash(__file__),history=file_hash(Path(a.history)/'manifest.json'),tail=file_hash(Path(a.tail)/'manifest.json')))
    checkpoint=work/'diagnostics.json'
    if checkpoint.exists():
        saved=read_json(checkpoint)
        if saved['binding']!=binding:raise ValueError('stale diagnostics')
    else:
        if a.aggregate_only:raise ValueError('missing diagnostics checkpoint')
        frames,times,algebra,bindings=clock_and_quotes(a,c)
        execution=[];fixed=[];reuse=[]
        evidence=read_json('results/wselob_execution_robustness_v1/run_manifest.json')['task_evidence']
        for (cohort,symbol,period),pieces in frames.items():
            quotes=pd.concat(pieces,ignore_index=True)
            for offset in c['clock']['offsets']:
                times.append(dict(cohort=cohort,symbol=symbol,period=period,day='all',offset_events=offset,**time_summary(exact_clock(quotes,offset))))
            for h in [10,20,50]:
                mask=np.isfinite(quotes[FEATURES+[f'markout_{h}']]).all(axis=1);rows=quotes.loc[mask].reset_index(drop=True)
                variants=[(r['model'],r['control_seed']) for r in evidence if (r['symbol'],r['month'],r['horizon'])==(symbol,period,h)] if cohort=='monthly' else [('linear',None),('xgboost',None)]+([('xgboost',7)] if h==20 else [])
                for model,seed in variants:
                    if cohort=='monthly':pred,sha=load_legacy(symbol,period,h,model,seed,rows,a.prediction_roots,evidence)
                    else:
                        folder=Path(a.later)/f'{symbol}-{h}-{model}-{seed if seed is not None else "primary"}';r=read_json(folder/'aggregate.json');path=folder/'predictions.npz'
                        if r['test_row_hash']!=row_hash(rows) or file_hash(path)!=r['prediction_hash']:raise ValueError('later identity/hash')
                        with np.load(path,allow_pickle=False) as data:pred=data['prediction'].copy()
                        sha=r['prediction_hash']
                    reuse.append(dict(cohort=cohort,symbol=symbol,period=period,horizon=h,model=model,seed=seed,prediction_sha256=sha))
                    for fixed_exit in [False,True] if h==20 else [False]:
                        comp={d:cost_components(quotes,h,d,fixed_exit).loc[mask].reset_index(drop=True) for d in [0,1,5]}
                        common=np.logical_and.reduce([np.isfinite(f[['long_crossed_bps','short_crossed_bps']]).all(axis=1).to_numpy() for f in comp.values()])
                        for d,f in comp.items():
                            result=dict(cohort=cohort,symbol=symbol,period=period,horizon=h,latency=d,model=model,control_seed=seed,unit='bp',**selected_cost(pred,f,common))
                            (fixed if fixed_exit else execution).append(result)
            print(f'cost complete {cohort} {symbol} {period}',flush=True)
        saved=clean(dict(binding=binding,times=times,algebra=algebra,execution=execution,fixed=fixed,input_bindings=bindings,prediction_reuse=reuse));atomic_json(checkpoint,saved)
    for name,key in [('event_time_summary','times'),('feature_algebra','algebra'),('execution_decomposition','execution'),('fixed_exit_latency','fixed')]:pd.DataFrame(saved[key]).to_csv(out/(name+'.csv'),index=False)
    passive=[]
    for cohort,path in [('monthly','results/wselob_queue_execution_v1/block_metrics.csv'),('later','results/wselob_later_confirmation_v1/passive.csv')]:
        f=pd.read_csv(path)
        if cohort=='later':f=f[f.day=='all']
        f=f.copy();f['cohort']=cohort
        for h in ['1','5','10','remaining']:f['passive_price_markout_'+h+'_bps']=f['spread_'+h]/2
        passive.append(f)
    pd.concat(passive,ignore_index=True).to_csv(out/'passive_accounting.csv',index=False)
    atomic_json(out/'diagnostics_manifest.json',dict(binding=binding,complete=True,original_prediction_tasks=len(saved['prediction_reuse']),cost_cells=len(saved['execution']),fixed_exit_cells=len(saved['fixed']),input_bindings=saved['input_bindings'],prediction_reuse=saved['prediction_reuse'],csv_hashes={p.name:file_hash(p) for p in out.glob('*.csv')}))

if __name__=='__main__':main()
