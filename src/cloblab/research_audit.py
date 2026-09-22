"""Post-inspection matched-feature and shuffled-label audit; private checkpoints."""
from __future__ import annotations
import argparse
import fcntl
import itertools
import importlib.metadata
import os
from pathlib import Path
import time
import numpy as np
import pandas as pd
from cloblab.evaluation import _fit_predict_linear, _spearman_corr
from cloblab.later_confirmation import clean, row_hash, IDENTITY
from cloblab.scale_common import atomic_json, digest, file_hash, read_json
from cloblab.scale_runner import model_parameters

CONFIG = 'configs/wselob_research_audit_v1.json'


def numerical_contract(args):
    """A private, explicitly attested producer profile; not a parity certificate."""
    profile_path = getattr(args, 'numerical_profile', None)
    if not profile_path:
        raise ValueError('run/resume requires --numerical-profile; legacy receipts are artifact-only evidence')
    profile = read_json(profile_path)
    required = {'schema', 'device', 'threads', 'packages', 'numerical_environment_sha256'}
    if set(profile) != required or profile['schema'] != 1:
        raise ValueError('invalid numerical profile schema')
    environment = profile['numerical_environment_sha256']
    if not isinstance(environment, str) or len(environment) != 64 or any(c not in '0123456789abcdef' for c in environment):
        raise ValueError('numerical environment must have a SHA256 attestation')
    packages = {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'xgboost']}
    if profile['device'] != args.device or profile['threads'] != args.threads or profile['packages'] != packages:
        raise ValueError('requested runtime/packages do not match the numerical profile')
    return dict(schema=1, profile_sha256=digest(profile), device=args.device,
                threads=args.threads, packages=packages,
                numerical_environment_sha256=environment)


def require_compatible_receipt(receipt, contract):
    if receipt.get('numerical_contract') != contract:
        raise ValueError('missing or incompatible numerical contract; do not resume in this evidence namespace')


def task_plan(c):
    tasks = []
    for scope,symbol,method,seed in itertools.product(c['control_scopes'],c['symbols'],c['shuffle_methods'],c['seeds']):
        tasks.append(dict(kind='control',scope=scope,symbol=symbol,period='later' if scope=='later' else '2017-06',model='xgboost',feature_group='F5',shuffle=method,seed=seed,horizon=20))
    for symbol,period,model,feature in itertools.product(c['symbols'],c['months'],('linear','xgboost'),c['feature_groups']):
        tasks.append(dict(kind='ablation',scope='monthly',symbol=symbol,period=period,model=model,feature_group=feature,shuffle='none',seed=None,horizon=20))
    return tasks


def task_id(config, task, inputs, implementation):
    scientific = {k:v for k,v in config.items() if k!='runtime'}
    return digest(dict(config=scientific,task=task,inputs=inputs,implementation=implementation))


def shuffle_labels(frame, label, method, seed):
    if method not in ('S0','S1'): raise ValueError('unknown shuffle')
    out = frame.copy()
    rng = np.random.default_rng(seed)
    keys = ['symbol','day'] if method=='S0' else ['symbol']
    column = out.columns.get_loc(label)
    for positions in out.groupby(keys,sort=True).indices.values():
        out.iloc[positions,column] = rng.permutation(out.iloc[positions,column].to_numpy())
    return out


def strict_stats(values, expected=None):
    a=np.asarray(values,dtype=float); n=len(a) if expected is None else expected
    ok=np.isfinite(a); full=len(a)==n and ok.all() and n>0
    return dict(expected=n,defined=int(ok.sum()),mean=float(a.mean()) if full else np.nan,
                median=float(np.median(a)) if full else np.nan,positive=int((a[ok]>0).sum()),
                available_case_mean=float(a[ok].mean()) if ok.any() else np.nan)


def fold_parts(c, manifests, task):
    symbol,period=task['symbol'],task['period']; history=manifests[0]['partitions']
    if task['scope']=='later':
        train=[(0,p) for p in history if p['symbol']==symbol and p['day']<=c['later_train_end']]
        test=[(1,p) for p in manifests[1]['partitions'] if p['symbol']==symbol and p['day'] in c['later_dates']]
        if {p['day'] for _,p in test}!=set(c['later_dates']): raise ValueError('missing later dates')
    else:
        transfer=task['scope']=='transfer_june'
        train=[(0,p) for p in history if (p['symbol']!=symbol if transfer else p['symbol']==symbol) and p['day'][:7]<period]
        test=[(0,p) for p in history if p['symbol']==symbol and p['day'][:7]==period]
    if not train or not test or max(p['day'] for _,p in train)>=min(p['day'] for _,p in test): raise ValueError('noncausal fold')
    expected=set(c['symbols'])-{symbol} if task['scope']=='transfer_june' else {symbol}
    if {p['symbol'] for _,p in train}!=expected: raise ValueError('training stock mismatch')
    if any(sum(p['symbol']==s for _,p in train)<40 for s in expected): raise ValueError('insufficient training days')
    return train,test


def read_parts(roots,parts,features,horizon=20):
    frames=[]; label=f'markout_{horizon}'
    for root,p in parts:
        path=Path(roots[root])/f"symbol={p['symbol']}"/f"day={p['day']}"/'features.parquet'
        if file_hash(path)!=p['features_sha256']: raise ValueError('cache hash mismatch')
        f=pd.read_parquet(path,columns=IDENTITY+features+[label])
        if set(f.symbol)!={p['symbol']} or set(f.day)!={p['day']}:raise ValueError('partition identity')
        frames.append(f[np.isfinite(f[features+[label]]).all(axis=1)])
    f=pd.concat(frames,ignore_index=True)
    if f.empty or f.duplicated(IDENTITY).any():raise ValueError('empty or duplicate fold')
    return f


def daily_scores(frame,pred):
    rows=[]; y=frame.markout_20.to_numpy()
    for day,ix in frame.groupby('day',sort=True).indices.items():
        p,a=pred[ix],y[ix]
        ic=_spearman_corr(p,a)
        rows.append(dict(day=day,rows=len(ix),ic=ic,prediction_mean_bps=p.mean(),label_mean_bps=a.mean(),prediction_std_bps=p.std(),label_std_bps=a.std(),undefined_reason='' if np.isfinite(ic) else 'constant_or_insufficient_rank_variation'))
    return rows


def state_scores(train,test,pred):
    cuts={k:np.quantile(train[k],[1/3,2/3]) for k in ['spread_bps','top_imbalance']}
    a=np.searchsorted(cuts['spread_bps'],test.spread_bps,side='left')
    b=np.searchsorted(cuts['top_imbalance'],test.top_imbalance,side='left')
    rows=[]
    for i,j in itertools.product(range(3),repeat=2):
        mask=(a==i)&(b==j);y=test.loc[mask,'markout_20'].to_numpy()
        rows.append(dict(spread_bin=i+1,imbalance_bin=j+1,rows=int(mask.sum()),ic=_spearman_corr(pred[mask],y),spread_cut1=cuts['spread_bps'][0],spread_cut2=cuts['spread_bps'][1],imbalance_cut1=cuts['top_imbalance'][0],imbalance_cut2=cuts['top_imbalance'][1]))
    return rows


def reusable_prediction(task,test,roots,c):
    # Legacy feature order and model parameters are frozen by the archived public
    # configuration; published execution receipt binds the exact prediction hash.
    if task['scope']=='later':
        if task['shuffle']!='S0' or task['seed']!=7:return None
        for root in roots:
            p=Path(root)/f"{task['symbol']}-20-{task['model']}-{'primary' if task['seed'] is None else task['seed']}"/'predictions.npz'
            if not p.exists():continue
            receipt=read_json(p.parent/'aggregate.json')
            if receipt['test_row_hash']!=row_hash(test) or file_hash(p)!=receipt['prediction_hash']:raise ValueError('later prediction binding')
            with np.load(p,allow_pickle=False) as data:
                if not np.array_equal(data['event_index'],test.event_index) or not np.array_equal(data['timestamp_ns'],test.timestamp_ns):raise ValueError('later row identity')
                return data['prediction'].copy(),receipt['prediction_hash']
        return None
    if task['scope']=='transfer_june' or task['feature_group']!='F5' or task['shuffle']=='S1':return None
    evidence=read_json('results/wselob_execution_robustness_v1/run_manifest.json')['task_evidence']
    matches=[r for r in evidence if r['symbol']==task['symbol'] and r['month']==task['period'] and r['horizon']==20 and r['model']==task['model'] and r['control_seed']==task['seed']]
    if len(matches)!=1:return None
    receipt=matches[0]
    for root in roots:
        path=Path(root)/'tasks'/receipt['legacy_task_id']/'predictions.npz'
        if not path.exists():continue
        if file_hash(path)!=receipt['prediction_sha256']:raise ValueError('legacy prediction hash')
        with np.load(path,allow_pickle=False) as data:
            for k in ['timestamp_ns','event_index']:
                if not np.array_equal(data[k],test[k]):raise ValueError('legacy row identity')
            if not np.array_equal(data['actual'],test.markout_20):raise ValueError('legacy labels')
            return data['prediction'].copy(),receipt['prediction_sha256']
    return None


def run_task(task,c,manifests,args,implementation):
    contract = numerical_contract(args)
    parts=fold_parts(c,manifests,task)
    inputs=[[{k:p[k] for k in ['symbol','day','features_sha256']} for _,p in x] for x in parts]
    tid=task_id(c,task,inputs,implementation);folder=Path(args.work)/tid;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt=folder/'receipt.json'
        if receipt.exists():
            r=read_json(receipt)
            if r['task_id']!=tid:raise ValueError('stale receipt')
            require_compatible_receipt(r, contract)
            for name,h in r['artifacts'].items():
                if file_hash(folder/name)!=h:raise ValueError('corrupt completed artifact')
            return 'reused_checkpoint'
        started=time.monotonic();atomic_json(folder/'started.json',dict(task=task,task_id=tid))
        train,test=[read_parts([args.history,args.tail],p,c['full_features']) for p in parts]
        original_train_hash=row_hash(train);test_hash=row_hash(test)
        existing=reusable_prediction(task,test,args.prediction_roots,c)
        if existing:
            pred,oldhash=existing;origin='verified_original_prediction';fit_seconds=0.
        else:
            training=shuffle_labels(train,'markout_20',task['shuffle'],task['seed']) if task['shuffle']!='none' else train
            features=c['feature_groups'][task['feature_group']];fit_start=time.monotonic()
            if task['model']=='linear':pred=_fit_predict_linear(training,test,features,'markout_20')
            else:
                from xgboost import XGBRegressor
                params=model_parameters(c,args.device,args.threads)
                model=XGBRegressor(**params);model.fit(training[features],training.markout_20)
                import json
                if args.device.startswith('cuda') and not json.loads(model.get_booster().save_config())['learner']['generic_param']['device'].startswith('cuda'):raise ValueError('accelerator fallback')
                pred=model.predict(test[features])
            fit_seconds=time.monotonic()-fit_start;origin='new_fit';oldhash=None
        pred=np.asarray(pred,dtype=float)
        if not np.isfinite(pred).all():raise ValueError('nonfinite predictions')
        daily=daily_scores(test,pred);ds=strict_stats([r['ic'] for r in daily])
        y=test.markout_20.to_numpy();ic=_spearman_corr(pred,y)
        r=dict(**task,task_id=tid,origin=origin,original_prediction_sha256=oldhash,train_rows=len(train),test_rows=len(test),train_row_hash=original_train_hash,test_row_hash=test_hash,last_train_day=train.day.max(),first_test_day=test.day.min(),ic=ic,prediction_std_bps=pred.std(),daily_ic=ds['mean'],daily_ic_available_case=ds['available_case_mean'],days_expected=ds['expected'],days_defined=ds['defined'],mean_day_prediction_label_ic=_spearman_corr([d['prediction_mean_bps'] for d in daily],[d['label_mean_bps'] for d in daily]),undefined_reason='' if np.isfinite(ic) else 'constant_or_insufficient_rank_variation')
        atomic_json(folder/'metrics.json',clean(dict(block=r,daily=daily,states=state_scores(train,test,pred) if task['kind']=='ablation' else [])))
        # Private row predictions permit later paired diagnostics; never published.
        temp=folder/'predictions.tmp.npz';np.savez_compressed(temp,prediction=pred,actual=y,event_index=test.event_index.to_numpy(),timestamp_ns=test.timestamp_ns.to_numpy());os.replace(temp,folder/'predictions.npz')
        atomic_json(folder/'receipt.json',dict(task_id=tid,task=task,numerical_contract=contract,
            prediction_evidence=dict(origin=origin,profile_role='fit_producer' if origin=='new_fit' else 'archive_import_runtime_not_original_producer',sha256=file_hash(folder/'predictions.npz'),archived_source_sha256=oldhash),
            artifacts={n:file_hash(folder/n) for n in ['metrics.json','predictions.npz']},runtime=dict(device=args.device,threads=args.threads,fit_seconds=fit_seconds,wall_seconds=time.monotonic()-started)))
        print(f"{task['kind']} {task['scope']} {task['symbol']} {task['period']} {task['model']} {task['feature_group']} {task['shuffle']} {task['seed']} {origin} seconds={time.monotonic()-started:.1f}",flush=True)
        return origin


def implementation_hash():
    return digest({p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('evaluation.py'),Path(__file__).with_name('scale_runner.py'),Path(__file__).with_name('later_confirmation.py')]})


def aggregate(c,manifests,args,implementation):
    blocks=[];days=[];states=[];evidence=[]
    for task in task_plan(c):
        parts=fold_parts(c,manifests,task)
        inputs=[[{k:p[k] for k in ['symbol','day','features_sha256']} for _,p in x] for x in parts]
        tid=task_id(c,task,inputs,implementation);folder=Path(args.work)/tid
        receipt=read_json(folder/'receipt.json')
        if receipt['task_id']!=tid:raise ValueError('identity mismatch')
        if 'numerical_contract' not in receipt or 'prediction_evidence' not in receipt:
            raise ValueError('legacy receipt: aggregate the completed v1 with its archived implementation')
        for n,h in receipt['artifacts'].items():
            if file_hash(folder/n)!=h:raise ValueError('artifact mismatch')
        data=read_json(folder/'metrics.json');blocks.append(data['block'])
        if receipt['prediction_evidence']['sha256'] != receipt['artifacts']['predictions.npz'] or receipt['prediction_evidence']['origin'] != data['block']['origin']:
            raise ValueError('prediction evidence binding mismatch')
        evidence.append(dict(task_id=tid,profile_sha256=receipt['numerical_contract']['profile_sha256'],
                             **receipt['prediction_evidence']))
        days.extend({**task,'task_id':tid,**r} for r in data['daily']);states.extend({**task,'task_id':tid,**r} for r in data['states'])
    frame=pd.DataFrame(blocks);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for kind in ['control','ablation']:
        subset=frame[frame.kind==kind];subset.to_csv(out/f'{kind}_blocks.csv',index=False)
        pd.DataFrame([r for r in days if r['kind']==kind]).to_csv(out/f'{kind}_daily.csv',index=False)
    pd.DataFrame(states).to_csv(out/'state_diagnostics.csv',index=False)
    control=frame[frame.kind=='control'];summary=[]
    for keys,g in control.groupby(['scope','symbol','shuffle']):
        for metric in ['ic','daily_ic','mean_day_prediction_label_ic']:
            summary.append(dict(zip(['scope','symbol','shuffle'],keys),metric=metric,**strict_stats(g[metric],5)))
    pd.DataFrame(summary).to_csv(out/'control_summary.csv',index=False)
    ab=frame[frame.kind=='ablation'];contrasts=[]
    for model,g in ab.groupby('model'):
        p=g.pivot(index=['symbol','period'],columns='feature_group',values='ic')
        for hi,lo in [('F2','F1'),('F3','F2'),('F4','F2'),('F5','F3'),('F5','F4')]:
            for (symbol,period),v in (p[hi]-p[lo]).items():contrasts.append(dict(model=model,contrast=hi+'-'+lo,symbol=symbol,period=period,delta_ic=v))
    for feature,g in ab.groupby('feature_group'):
        p=g.pivot(index=['symbol','period'],columns='model',values='ic')
        for (symbol,period),v in (p.xgboost-p.linear).items():contrasts.append(dict(model='xgboost-linear',contrast=feature,symbol=symbol,period=period,delta_ic=v))
    cf=pd.DataFrame(contrasts);cf.to_csv(out/'ablation_paired.csv',index=False)
    sums=[dict(model=m,contrast=f,**strict_stats(g.delta_ic,20)) for (m,f),g in cf.groupby(['model','contrast'])]
    pd.DataFrame(sums).to_csv(out/'ablation_summary.csv',index=False)
    atomic_json(out/'model_manifest.json',dict(complete=True,numerical_compatibility='explicit producer profile; artifact hash identifies evidence, not backend parity',prediction_evidence=evidence,config_hash=digest(c),implementation_hash=implementation,control_cells=len(control),ablation_cells=len(ab),new_fits=int((frame.origin=='new_fit').sum()),verified_original_predictions=int((frame.origin=='verified_original_prediction').sum()),task_ids=sorted(frame.task_id),csv_hashes={p.name:file_hash(p) for p in out.glob('*.csv')}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['plan','run','resume','aggregate']);p.add_argument('--config',default=CONFIG);p.add_argument('--history',required=True);p.add_argument('--tail',required=True);p.add_argument('--work',required=True);p.add_argument('--out',default='results/wselob_research_audit_v1');p.add_argument('--prediction-roots',nargs='*',default=[]);p.add_argument('--numerical-profile');p.add_argument('--device',default='cpu');p.add_argument('--threads',type=int,default=4);p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1);p.add_argument('--limit',type=int);p.add_argument('--scopes',nargs='+');a=p.parse_args()
    if not 1<=a.threads<=24 or not 0<=a.shard<a.shards:raise ValueError('invalid bounded runtime')
    c=read_json(a.config);manifests=[read_json(Path(root)/'manifest.json') for root in [a.history,a.tail]];code=implementation_hash();tasks=task_plan(c)
    if a.command=='plan':
        atomic_json(Path(a.work)/'plan.json',dict(config=c,implementation=code,tasks=tasks));print(len(tasks));return
    if a.command=='aggregate':aggregate(c,manifests,a,code);return
    selected=[t for t in tasks if not a.scopes or t['scope'] in a.scopes][a.shard::a.shards]
    for t in selected[:a.limit] if a.limit else selected:run_task(t,c,manifests,a,code)

if __name__=='__main__':main()
