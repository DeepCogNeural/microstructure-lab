"""Frozen later-period confirmation; no outcomes are read on import or planning."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd

from cloblab.evaluation import _fit_predict_linear, _score_predictions
from cloblab.execution_labels import crossed_labels
from cloblab.licensed_experiment import prepare
from cloblab.native import replay_day, queue_paths, SNAPSHOT_NAMES
from cloblab.queue_metrics import summarize as queue_summary
from cloblab.robustness import summarize_predictions
from cloblab.scale_common import atomic_json, digest, file_hash, read_json

PREREG = '7d5671612ecf286da2690d5747658d09b0474529'
CONFIG = 'configs/wselob_later_confirmation_v1.json'
PROTOCOL = 'docs/LATER_PARTITIONS_CONFIRMATION_PROTOCOL.md'
LOCKS = {CONFIG: '5c6067943ad128dc7ab33b555f0e793cf497396e3723dca03fb6d0aa1df6a1ab',
         PROTOCOL: '40074b0a266e82e4a3609b11e3349f71cf46de10b2528d1944cc88025f709197'}
SYMBOLS = ['KGHM', 'PEKAO', 'PKNORLEN', 'PKOBP', 'PZU']
DATES = ['2017-12-27', '2017-12-28', '2017-12-29']
FEATURES = ['spread_bps', 'top_imbalance', 'depth_imbalance', 'ofi_l1_norm', 'microprice_minus_mid_bps']
IDENTITY = ['symbol', 'day', 'segment', 'event_index', 'timestamp_ns']
OUTPUT_NAME = 'wselob_later_confirmation_v1'


def frozen_config():
    for path, expected in LOCKS.items():
        if file_hash(path) != expected:
            raise ValueError('preregistration changed')
    return read_json(CONFIG)


def tasks():
    return [(s, h, m, None) for s, h, m in itertools.product(SYMBOLS, (10, 20, 50), ('linear', 'xgboost'))] + [(s, 20, 'xgboost', 7) for s in SYMBOLS]


def task_name(task):
    s, h, m, seed = task
    return f'{s}-{h}-{m}-{seed if seed is not None else "primary"}'


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, np.generic): return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value): return None
    return value


def row_hash(frame):
    return hashlib.sha256(frame[IDENTITY].to_csv(index=False).encode()).hexdigest()


def select_partitions(manifest, symbol, confirmation=False):
    parts = manifest['partitions']
    keys = [(p['symbol'], p['day']) for p in parts]
    if len(keys) != len(set(keys)): raise ValueError('duplicate partitions')
    if confirmation:
        if set(keys) != set(itertools.product(SYMBOLS, DATES)):
            raise ValueError('all 15 confirmation partitions required; no substitution')
        selected = [p for p in parts if p['symbol'] == symbol]
    else:
        selected = [p for p in parts if p['symbol'] == symbol and '2017-01-01' <= p['day'] <= '2017-12-22']
        if len(selected) < 40: raise ValueError('insufficient historical days')
    return sorted(selected, key=lambda p: p['day'])


def read_features(root, parts, horizon):
    pieces, counts = [], []
    for part in parts:
        path = Path(root)/f"symbol={part['symbol']}"/f"day={part['day']}"/'features.parquet'
        if file_hash(path) != part['features_sha256']: raise ValueError('feature hash mismatch')
        frame = pd.read_parquet(path, columns=IDENTITY+FEATURES+[f'markout_{horizon}'])
        if set(frame.symbol) != {part['symbol']} or set(frame.day) != {part['day']}:
            raise ValueError('partition identity mismatch')
        finite_features = np.isfinite(frame[FEATURES]).all(axis=1)
        finite_label = np.isfinite(frame[f'markout_{horizon}'])
        counts.append(dict(symbol=part['symbol'], day=part['day'], horizon=horizon,
                           feature_rows=len(frame), excluded_nonfinite_features=int((~finite_features).sum()),
                           excluded_label_after_features=int((finite_features & ~finite_label).sum()),
                           eligible_rows=int((finite_features & finite_label).sum())))
        pieces.append(frame.loc[finite_features & finite_label])
    out = pd.concat(pieces, ignore_index=True).sort_values(['day', 'event_index']).reset_index(drop=True)
    if out.duplicated(IDENTITY).any() or out.empty: raise ValueError('empty or duplicate eligible rows')
    return out, counts


def fit_once(train, test, horizon, model, seed, config, threads=1):
    if set(train.symbol) != set(test.symbol) or len(set(train.symbol)) != 1:
        raise ValueError('cross-symbol pooling forbidden')
    if train.day.max() > '2017-12-22' or set(test.day) != set(DATES):
        raise ValueError('training cutoff or confirmation days violated')
    label = f'markout_{horizon}'
    if seed is not None:
        if (model, horizon, seed) != ('xgboost', 20, 7): raise ValueError('unknown control')
        train = train.copy()
        rng = np.random.default_rng(7)
        for _, idx in train.groupby('day', sort=True).indices.items():
            train.loc[idx, label] = rng.permutation(train.loc[idx, label].to_numpy())
    if model == 'linear':
        prediction = _fit_predict_linear(train, test, FEATURES, label)
    elif model == 'xgboost':
        from xgboost import XGBRegressor
        params = {k: v for k, v in config['models']['xgboost'].items() if k != 'hyperparameter_search'}
        estimator = XGBRegressor(**params, device='cpu', n_jobs=threads)
        estimator.fit(train[FEATURES], train[label])
        prediction = estimator.predict(test[FEATURES]).astype(float)
    else: raise ValueError('unknown model')
    if not np.isfinite(prediction).all(): raise ValueError('nonfinite predictions')
    return prediction


def prediction_records(frame, prediction, horizon):
    records = []
    for day in ['all', *DATES]:
        mask = np.ones(len(frame), bool) if day == 'all' else (frame.day == day).to_numpy()
        records.append(dict(day=day, **_score_predictions(prediction[mask], frame.loc[mask, f'markout_{horizon}'].to_numpy(), 1.0)))
    return records


def crossing_frame(test, snapshots, horizon):
    result = test[IDENTITY].copy()
    for latency in (0, 1, 5):
        labels = crossed_labels(snapshots, horizon, latency)
        labels = labels.rename(columns={k: f'{k}_{latency}' for k in ('long_crossed_bps', 'short_crossed_bps')})
        result = result.merge(labels, on=IDENTITY, how='left', validate='one_to_one', sort=False)
    if row_hash(result) != row_hash(test): raise ValueError('crossing row identity changed')
    columns = [f'{side}_crossed_bps_{d}' for d in (0, 1, 5) for side in ('long', 'short')]
    return result, np.isfinite(result[columns]).all(axis=1).to_numpy()


def bins(prediction, fallback=False):
    value = np.asarray(pd.qcut(prediction, 10, labels=False, duplicates='drop'), dtype=float)
    if fallback and np.isnan(value).all(): value = np.zeros(len(prediction))
    return value+1


def aggressive_records(test, prediction, snapshots, horizon):
    frame, valid = crossing_frame(test, snapshots, horizon)
    frame = frame.loc[valid].reset_index(drop=True)
    pred = prediction[valid]
    assignments = bins(pred, True) if len(pred) else np.array([])
    summaries, curves = [], []
    for latency in (0, 1, 5):
        long = frame[f'long_crossed_bps_{latency}'].to_numpy()
        short = frame[f'short_crossed_bps_{latency}'].to_numpy()
        for day in ['all', *DATES]:
            mask = np.ones(len(frame), bool) if day == 'all' else (frame.day == day).to_numpy()
            p, l, s = pred[mask], long[mask], short[mask]
            if len(p):
                summary, _ = summarize_predictions(p, l, s)
                # Day summaries retain period bins, rather than re-binning.
                dec = pd.DataFrame({'bin': assignments[mask], 'prediction': p, 'long': l, 'short': s})
                curve = dec.groupby('bin').agg(rows=('prediction','size'), prediction_bps=('prediction','mean'), long_crossed_bps=('long','mean'), short_crossed_bps=('short','mean')).reset_index()
                summary.update(top_decile_long_bps=curve.long_crossed_bps.iloc[-1], bottom_decile_short_bps=curve.short_crossed_bps.iloc[0], decile_bins=len(curve), ordered_deciles=float(len(curve)==10 and curve.long_crossed_bps.diff().dropna().ge(0).all() and curve.short_crossed_bps.diff().dropna().le(0).all()))
                curves.extend(dict(day=day, latency=latency, **r) for r in curve.to_dict('records'))
            else:
                summary = dict(rows=0, threshold_bps=1., selected_rows=0, coverage=np.nan, sign_selected_bps=np.nan, top_decile_long_bps=np.nan, bottom_decile_short_bps=np.nan, decile_bins=0, ordered_deciles=np.nan)
            original = len(test) if day == 'all' else int((test.day==day).sum())
            summaries.append(dict(day=day, latency=latency, prediction_rows=original, excluded_crossing_common=original-int(mask.sum()), **summary))
    return summaries, curves


def passive_frame(events, indices, prediction, horizon, latency):
    placements = indices+latency
    safe = np.minimum(placements, len(events['valid'])-1)
    eligible = (placements<len(events['valid'])) & events['valid'][safe] & (events['segment'][safe]==events['segment'][indices])
    p = placements[eligible]
    direction = np.sign(prediction[eligible])
    frame = pd.DataFrame({'prediction': prediction[eligible], 'direction': direction})
    if len(p):
        paths = {side: queue_paths(events, p, side, horizon, backend='python', tick=events['tick'][p], decision_latency=latency) for side in (1,2)}
        for name in paths[1]: frame[name] = np.where(direction>0, paths[1][name], paths[2][name])
        for name in ('fill_time','adverse_time'): frame.loc[direction==0,name] = -1
    return frame, int((~eligible).sum())


def passive_records(pieces, exclusions):
    summary, prediction_curves, queue_curves = [], [], []
    for (interpretation, latency), group in pieces.items():
        frame = pd.concat(group, ignore_index=True)
        frame['prediction_bin'] = bins(frame.prediction) if len(frame) else np.array([])
        frame['queue_bin'] = np.nan
        placed = frame.direction != 0
        if placed.any(): frame.loc[placed,'queue_bin'] = bins(frame.loc[placed,'queue_ahead'])
        for day in ['all',*DATES]:
            part = frame if day=='all' else frame[frame.day==day]
            result = queue_summary(part) if len(part) else dict(eligible_decisions=0, placed_orders=0, zero_signal_decisions=0, fills=0, fill_probability=np.nan, fill_before_adverse=np.nan, mean_fill_time=np.nan, markout_5=np.nan, spread_5=np.nan)
            excluded = sum(v for (i,d,date),v in exclusions.items() if i==interpretation and d==latency and (day=='all' or date==day))
            summary.append(dict(day=day, interpretation=interpretation, latency=latency, excluded_invalid_placement=excluded, **result))
            for column, destination in [('prediction_bin',prediction_curves),('queue_bin',queue_curves)]:
                for decile, block in part.groupby(column):
                    destination.append(dict(day=day, interpretation=interpretation, latency=latency, bin=int(decile), **queue_summary(block)))
    return summary, prediction_curves, queue_curves


def snapshot_days(raw, tail_root, parts):
    import h5py
    from cloblab.wselob import reconstruct
    for part in parts:
        symbol, day = part['symbol'], part['day']
        folder = Path(tail_root)/f'symbol={symbol}'/f'day={day}'
        path = folder/'snapshots.parquet'
        with h5py.File(raw,'r') as handle: records = handle['d'+day.replace('-','')+'/table'][:]
        if file_hash(path) != part['snapshots_sha256']: raise ValueError('snapshot hash mismatch')
        snapshots = pd.read_parquet(path)
        # Original replay and preparation are the frozen feature/label oracle.
        reference, audit = reconstruct(records, day, symbol)
        if not snapshots.equals(reference): raise ValueError('original replay mismatch')
        regenerated = prepare(snapshots, [10,20,50])
        stored = pd.read_parquet(folder/'features.parquet')
        cols = IDENTITY+FEATURES+[f'markout_{h}' for h in (10,20,50)]
        if not regenerated[cols].reset_index(drop=True).equals(stored[cols].reset_index(drop=True)):
            raise ValueError('feature/label oracle mismatch')
        yield day, records, snapshots, audit


def run_task(task, args, config, binding, historical, tail):
    symbol,horizon,model,seed = task
    folder = Path(args.work)/task_name(task)
    folder.mkdir(parents=True, exist_ok=True)
    # Never refit an existing partial run silently. Complete receipts can resume.
    target = folder/'aggregate.json'
    if target.exists():
        result = read_json(target)
        if result['binding'] != binding or result['task'] != list(task): raise ValueError('stale task')
        return result
    marker = folder/'started.json'
    if marker.exists(): raise ValueError('incomplete task: preserve run and investigate before retry')
    atomic_json(marker, dict(binding=binding, task=task))
    train_parts = select_partitions(historical,symbol)
    test_parts = select_partitions(tail,symbol,True)
    train, train_counts = read_features(args.history,train_parts,horizon)
    test, test_counts = read_features(args.tail,test_parts,horizon)
    prediction = fit_once(train,test,horizon,model,seed,config,args.threads)
    train_hash = row_hash(train)
    train_rows = len(train)
    del train
    np.savez_compressed(folder/'predictions.npz',prediction=prediction, **{k:test[k].to_numpy() for k in IDENTITY})
    prediction_hash = file_hash(folder/'predictions.npz')
    pred_records = prediction_records(test,prediction,horizon)
    raw = Path(args.raw)/config['dataset']['sources'][symbol]['filename']
    if file_hash(raw) != config['dataset']['sources'][symbol]['sha256']: raise ValueError('raw hash mismatch')
    snapshots_all, inventories = [], []
    pieces = {(i,d):[] for i,d in itertools.product(('retain','reset'),(0,1,5))}
    exclusions = {}
    for day,records,snapshots,audit in snapshot_days(raw,args.tail,test_parts):
        snapshots_all.append(snapshots)
        inventories.append(dict(symbol=symbol,day=day,raw_messages=len(records),snapshot_rows=len(snapshots),replay_exclusions=audit))
        mask = (test.day==day).to_numpy()
        indices = test.loc[mask,'event_index'].to_numpy(dtype=np.int64)
        for interpretation in ('retain','reset'):
            events = replay_day(records,symbol,day,backend='python',interpretation=interpretation)
            valid = np.flatnonzero(events['valid'])
            if not np.array_equal(valid,snapshots.event_index.to_numpy()) or not np.array_equal(events['snapshots'][valid],snapshots[SNAPSHOT_NAMES].to_numpy()):
                raise ValueError('queue replay differs from original snapshots')
            for latency in (0,1,5):
                frame,excluded = passive_frame(events,indices,prediction[mask],horizon,latency)
                frame['day'] = day
                pieces[interpretation,latency].append(frame)
                exclusions[interpretation,latency,day] = excluded
    aggressive, aggressive_curves = aggressive_records(test,prediction,pd.concat(snapshots_all,ignore_index=True),horizon)
    passive, passive_curves, queue_curves = passive_records(pieces,exclusions)
    result = dict(binding=binding,task=task,fit_count=1,training_last_day=max(p['day'] for p in train_parts),training_rows=train_rows,training_row_hash=train_hash,test_row_hash=row_hash(test),prediction_hash=prediction_hash,training_counts=train_counts,test_counts=test_counts,inventory=inventories,prediction=pred_records,aggressive=aggressive,aggressive_deciles=aggressive_curves,passive=passive,passive_deciles=passive_curves,queue_deciles=queue_curves)
    result = clean(result)
    atomic_json(target,result)
    print(json.dumps(dict(task=task_name(task),state='complete')),flush=True)
    return result


def strict_mean(values):
    a = pd.to_numeric(pd.Series(list(values)), errors='coerce').to_numpy(dtype=float)
    return float(np.mean(a)) if len(a) and np.isfinite(a).all() else np.nan


def primary_table(prediction):
    primary = prediction[(prediction.day=='all') & (prediction.horizon==20) & prediction.control_seed.isna()]
    expected = set(itertools.product(SYMBOLS,('linear','xgboost')))
    if len(primary)!=10 or set(primary[['symbol','model']].itertuples(index=False,name=None))!=expected:
        raise ValueError('primary requires exactly five paired stock-period blocks')
    table = primary.pivot(index='symbol',columns='model',values='ic').reindex(SYMBOLS).reset_index()
    table['delta'] = table.xgboost-table.linear
    headline = dict(linear=strict_mean(table.linear),xgboost=strict_mean(table.xgboost),delta=strict_mean(table.delta),median_delta=float(table.delta.median()) if table.delta.notna().all() else np.nan,wins=int((table.delta>0).sum()) if table.delta.notna().all() else None,blocks=5,defined_blocks=int(table.delta.notna().sum()))
    return table,headline


def tail_contrasts(curves):
    keys=['symbol','day','horizon','model','control_seed','latency','interpretation']
    rows=[]
    for ident,group in curves.groupby(keys,dropna=False,sort=True):
        by=group.set_index('bin')
        for side,number in [('lower',1),('upper',10)]:
            row=dict(zip(keys,ident)); row['tail_bin']=number
            row['bins_available']=len(by)
            for metric in ('fill_probability','markout_5'):
                row[metric+'_tail_minus_center'] = (by.loc[number,metric]-strict_mean(by.loc[[5,6],metric])) if set(by.index)==set(range(1,11)) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def safe_public_records(records):
    """Allow only numeric metrics and controlled categorical values, never free text."""
    categories = {'symbol':set(SYMBOLS), 'day':{'all',*DATES}, 'model':{'linear','xgboost'}, 'interpretation':{'retain','reset'}}
    for record in records:
        for key,value in record.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',key): raise ValueError('invalid metric name')
            if isinstance(value,str) and value not in categories.get(key,set()): raise ValueError('non-public string')
            if value is not None and not isinstance(value,(str,int,float,bool,np.generic)): raise ValueError('non-scalar public value')
    return clean(records)


def aggregate(results, out, binding, implementation):
    if len(results)!=35 or {tuple(r['task']) for r in results} != set(tasks()): raise ValueError('incomplete 35-fit experiment')
    if any(r['binding']!=binding or r['fit_count']!=1 or r['training_last_day']>'2017-12-22' for r in results): raise ValueError('invalid fit receipt')
    for symbol,horizon in itertools.product(SYMBOLS,(10,20,50)):
        matched = [r for r in results if r['task'][:2]==[symbol,horizon]]
        if len({r['test_row_hash'] for r in matched})!=1 or len({r['training_row_hash'] for r in matched})!=1: raise ValueError('unpaired model rows')
    out = Path(out)
    if out.name!=OUTPUT_NAME or out.exists(): raise ValueError('new experiment output directory required; never overwrite results')
    tables = {}
    for name in ('prediction','aggressive','aggressive_deciles','passive','passive_deciles','queue_deciles'):
        records=[]
        for result in results:
            symbol,horizon,model,seed=result['task']
            records.extend(dict(symbol=symbol,horizon=horizon,model=model,control_seed=seed,**row) for row in result[name])
        safe_public_records(records)
        tables[name]=pd.DataFrame(records)
    for name,counts in [('prediction',(35,105)),('aggressive',(105,315)),('passive',(210,630))]:
        frame=tables[name]
        if (int((frame.day=='all').sum()),int((frame.day!='all').sum()))!=counts: raise ValueError('incomplete analysis cells')
    primary,headline=primary_table(tables['prediction'])
    tables['primary_prediction']=primary
    tables['tail_contrasts']=tail_contrasts(tables['passive_deciles'])
    # All headline averages are strict five-stock means; counts also get totals.
    count_columns={'rows','selected_rows','prediction_rows','excluded_crossing_common','eligible_decisions','placed_orders','zero_signal_decisions','fills','excluded_invalid_placement','n_test'}
    for name in ('prediction','aggressive','passive'):
        frame=tables[name]
        keys=['day','horizon','model','control_seed']+[k for k in ('latency','interpretation') if k in frame]
        summary=[]
        for ident,group in frame.groupby(keys,dropna=False,sort=True):
            if len(group)!=5 or set(group.symbol)!=set(SYMBOLS): raise ValueError('incomplete headline stocks')
            row=dict(zip(keys,ident));row['blocks']=5
            for col in group.select_dtypes(include='number').columns:
                if col in keys:continue
                row[col]=strict_mean(group[col]);row[col+'_defined_blocks']=int(group[col].notna().sum())
                if col in count_columns or col.endswith('_observations'):row[col+'_total']=int(group[col].sum())
            summary.append(row)
        tables[name+'_summary']=pd.DataFrame(summary)
    for symbol,horizon in itertools.product(SYMBOLS,(10,20,50)):
        group=tables['aggressive']; group=group[(group.symbol==symbol)&(group.horizon==horizon)]
        for day,part in group.groupby('day'):
            if part.rows.nunique()!=1: raise ValueError('unpaired aggressive rows')
        group=tables['passive'];group=group[(group.symbol==symbol)&(group.horizon==horizon)]
        if (group.groupby(['day','latency','interpretation']).eligible_decisions.nunique()>1).any(): raise ValueError('unpaired queue rows')
    inventory=[];eligibility=[];seen=set()
    for result in results:
        for row in result['inventory']:
            key=(row['symbol'],row['day'])
            if key not in seen:
                inventory.append({**{k:row[k] for k in ('symbol','day','raw_messages','snapshot_rows')}, **{'replay_'+k:v for k,v in row['replay_exclusions'].items() if k!='day'}});seen.add(key)
        if result['task'][2]=='linear': eligibility.extend(result['test_counts'])
    if seen!=set(itertools.product(SYMBOLS,DATES)):raise ValueError('incomplete source inventory')
    tables['partition_inventory']=pd.DataFrame(safe_public_records(inventory))
    tables['eligibility']=pd.DataFrame(safe_public_records(eligibility))
    out.mkdir(parents=True)
    for name,frame in tables.items():frame.to_csv(out/(name+'.csv'),index=False)
    # Explicit provenance whitelist: no private directory or environment dump.
    receipts=[dict(task=r['task'],fit_count=r['fit_count'],training_rows=r['training_rows'],training_last_day=r['training_last_day'],training_row_hash=r['training_row_hash'],test_row_hash=r['test_row_hash'],prediction_hash=r['prediction_hash'],training_counts=r['training_counts']) for r in results]
    atomic_json(out/'manifest.json',clean(dict(complete=True,audit_commit=read_json(CONFIG)['audit_commit'],preregistration_commit=PREREG,implementation_commit=implementation,binding=binding,settings_hashes=LOCKS,expected_fits=35,completed_fits=35,source_partitions=15,shared_dates=3,primary=headline,receipts=receipts,software={n:importlib.metadata.version(n) for n in ('numpy','pandas','xgboost','h5py','pyarrow')},output_hashes={p.name:file_hash(p) for p in sorted(out.glob('*.csv'))})))
    return headline


def committed_implementation(commit):
    paths = [Path(CONFIG), Path(PROTOCOL), *sorted(Path('src/cloblab').glob('*.py'))]
    archive = Path('CONFIRMATION_CODE_RECEIPT.json')
    if archive.exists():
        receipt = read_json(archive)
        if receipt['commit'] != commit: raise ValueError('archive commit mismatch')
        expected = receipt['files']
    else:
        expected = {str(p): hashlib.sha256(subprocess.check_output(['git','show',commit+':'+str(p)])).hexdigest() for p in paths}
        subprocess.run(['git','merge-base','--is-ancestor',PREREG,commit],check=True)
    if any(expected.get(str(p)) != file_hash(p) for p in paths):
        raise ValueError('uncommitted or changed implementation')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('history','tail','raw','work'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--out',default='results/'+OUTPUT_NAME)
    parser.add_argument('--implementation-commit',required=True)
    parser.add_argument('--reveal-authorized',action='store_true')
    parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1)
    parser.add_argument('--threads',type=int,default=1);parser.add_argument('--aggregate-only',action='store_true')
    args=parser.parse_args()
    if not args.reveal_authorized:raise ValueError('explicit post-commit reveal authorization required')
    if not re.fullmatch('[0-9a-f]{40}',args.implementation_commit) or args.implementation_commit in (PREREG,read_json(CONFIG)['audit_commit']):raise ValueError('pre-reveal implementation commit required')
    config=frozen_config()
    committed_implementation(args.implementation_commit)
    if not 1<=args.threads<=24 or not 0<=args.shard<args.shards:raise ValueError('invalid resource bounds')
    historical=read_json(Path(args.history)/'manifest.json');tail=read_json(Path(args.tail)/'manifest.json')
    for s in SYMBOLS:select_partitions(historical,s);select_partitions(tail,s,True)
    binding=digest(dict(settings=LOCKS,history=historical,tail=tail,implementation=args.implementation_commit,code={p.name:file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}))
    if args.aggregate_only:
        results=[read_json(Path(args.work)/task_name(task)/'aggregate.json') for task in tasks()]
        aggregate(results,args.out,binding,args.implementation_commit)
        print('Complete frozen experiment aggregated: 35 fits; no missing tasks.',flush=True)
    else:
        for index,task in enumerate(tasks()):
            if index%args.shards==args.shard:run_task(task,args,config,binding,historical,tail)

if __name__=='__main__':main()
