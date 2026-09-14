"""Same-input native parity and fixed repeated timings; rows stay private."""
import argparse
from pathlib import Path
import hashlib
import itertools
import json
import time
import gc
import h5py
import numpy as np
import pandas as pd
from cloblab.native import replay_day, queue_paths, SNAPSHOT_NAMES
from cloblab.scale_common import atomic_json, read_json, file_hash, digest

MONTHS=('2017-04','2017-06','2017-09','2017-11')


def output_hash(result):
    h=hashlib.sha256()
    for name,value in sorted(result.items()):
        h.update(name.encode())
        if name=='final_queues':h.update(json.dumps(value,separators=(',',':')).encode());continue
        a=np.ascontiguousarray(value)
        h.update(a.dtype.str.encode());h.update(str(a.shape).encode());h.update(a.tobytes())
    return h.hexdigest()


def equal(left,right):
    if left.keys()!=right.keys():raise ValueError('output schema differs')
    for key in left:
        if key=='final_queues':
            if left[key]!=right[key]:raise ValueError('final queue rank differs')
        elif not np.array_equal(left[key],right[key],equal_nan=True):
            raise ValueError('parity failed: '+key)
    # Byte hashes are required too: no tolerance or hidden float drift.
    a,b=output_hash(left),output_hash(right)
    if a!=b:raise ValueError('byte parity failed despite value parity')
    return a


def timed(call):
    gc.collect();start=time.perf_counter();value=call();elapsed=time.perf_counter()-start
    return value,elapsed


def one_day(raw,cache,config,symbol,key,binding,work):
    target=work/(symbol+'-'+key+'.json')
    if target.exists():
        x=read_json(target)
        if x['binding']!=binding:raise ValueError('stale native benchmark receipt')
        return x
    day=pd.Timestamp(key[1:]).strftime('%Y-%m-%d')
    with h5py.File(raw,'r') as handle:records=handle[key+'/table'][:]
    queue_domain=day[:7] in MONTHS
    part=cache/f'symbol={symbol}'/f'day={day}'
    cached=None
    if queue_domain:
        if (part/'snapshots.parquet').exists():cached=pd.read_parquet(part/'snapshots.parquet')
        else:
            from cloblab.wselob import reconstruct
            cached=reconstruct(records,day,symbol)[0]
        expected=config['cache_partitions'][symbol+'/'+day]
        if file_hash(part/'features.parquet')!=expected:raise ValueError('frozen feature partition hash differs')
    features=pd.read_parquet(part/'features.parquet') if queue_domain else None
    receipts=[];queue_hash=hashlib.sha256();queue_decisions=0;queue_times={'python':[0.,0.,0.],'native':[0.,0.,0.]}
    replay_times={'python':[],'native':[]}
    measured_queue=symbol=='PEKAO' and day[:7]=='2017-06'
    for interpretation in ('retain','reset'):
        outputs={}
        for backend in ('python','native'):
            outputs[backend],duration=timed(lambda:replay_day(records,symbol,day,backend=backend,interpretation=interpretation))
            if interpretation=='retain':replay_times[backend].append(duration)
        receipt=equal(outputs['python'],outputs['native']);receipts.append(receipt)
        if interpretation=='retain':
            # Fixed three passes, both include normalization, allocation and
            # boundary conversion; HDF5 read is excluded from both.
            for repeat in (1,2):
                for backend in (('native','python') if repeat==1 else ('python','native')):
                    repeated,duration=timed(lambda:replay_day(records,symbol,day,backend=backend,interpretation=interpretation))
                    if output_hash(repeated)!=receipt:raise ValueError('repeat replay differs')
                    replay_times[backend].append(duration);del repeated
        if queue_domain:
            valid=np.flatnonzero(outputs['python']['valid'])
            if not np.array_equal(valid,cached.event_index.to_numpy()):raise ValueError('frozen cache indices differ')
            if not np.array_equal(outputs['python']['snapshots'][valid],cached[SNAPSHOT_NAMES].to_numpy()):raise ValueError('frozen snapshots differ')
            for h,d,side in itertools.product((10,20,50),(0,1,5),(1,2)):
                f=features.replace([np.inf,-np.inf],np.nan).dropna(subset=config['features']['primary_set']+[f'markout_{h}'])
                indices=f.event_index.to_numpy(dtype=np.int64);placement=indices+d
                e=outputs['python'];safe=np.minimum(placement,len(records)-1)
                eligible=(placement<len(records)) & e['valid'][safe] & (e['segment'][safe]==e['segment'][indices])
                placement=placement[eligible];ticks=e['tick'][placement]
                count_repeats=3 if measured_queue and h==20 else 1
                reference=None
                for repeat in range(count_repeats):
                    pairs={}
                    for backend in (('native','python') if repeat==1 else ('python','native')):
                        pairs[backend],duration=timed(lambda:queue_paths(outputs[backend],placement,side,h,backend=backend,tick=ticks,decision_latency=d))
                        if measured_queue and h==20:queue_times[backend][repeat]+=duration
                    qhash=equal(pairs['python'],pairs['native'])
                    if reference is not None and reference!=qhash:raise ValueError('repeat queue differs')
                    reference=qhash
                queue_hash.update(reference.encode());queue_decisions+=len(placement)
        del outputs
    result={'binding':binding,'symbol':symbol,'day':day,'messages':len(records),'replay_hashes':receipts,
            'replay_seconds':replay_times,'queue_domain':queue_domain,'queue_decisions':queue_decisions,
            'queue_hash':queue_hash.hexdigest(),'measured_queue':measured_queue,'queue_seconds':queue_times,
            'queue_benchmark_decisions':queue_decisions//3 if measured_queue else 0}
    # Horizons have different eligibility: calculate measured h20 count exactly.
    if measured_queue:
        f=features.replace([np.inf,-np.inf],np.nan).dropna(subset=config['features']['primary_set']+['markout_20'])
        count=0
        e=replay_day(records,symbol,day,backend='native')
        idx=f.event_index.to_numpy(dtype=np.int64)
        for d in (0,1,5):
            p=idx+d;s=np.minimum(p,len(records)-1)
            count+=int(((p<len(records)) & e['valid'][s] & (e['segment'][s]==e['segment'][idx])).sum())*2*2
        result['queue_benchmark_decisions']=count
    atomic_json(target,result)
    print(json.dumps({'symbol':symbol,'day':day,'state':'complete'}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('raw','cache','work','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--aggregate-only',action='store_true');p.add_argument('--max-days',type=int)
    args=p.parse_args();work=Path(args.work);work.mkdir(parents=True,exist_ok=True)
    sources=read_json('configs/wselob_sources_v1.json');config=read_json('configs/wselob_queue_execution_v1.json')
    manifest=read_json(Path(args.cache)/'manifest.json')
    config['cache_partitions']={p['symbol']+'/'+p['day']:p['features_sha256'] for p in manifest['partitions']}
    paths=[Path(__file__),Path('src/cloblab/native.py'),Path('src/cloblab/queue_book.py'),Path('src/cloblab/passive_execution.py'),Path('src/cloblab/wselob.py'),*sorted(Path('cpp').glob('*.*'))]
    binding=digest({'source':{str(p):file_hash(p) for p in paths},'sources':sources,'config':config,'replay_repeats':3,'queue_benchmark':'PEKAO June all days h20 d0/1/5 both sides both interpretations 3 repeats'})
    tasks=[]
    for symbol,entry in sources['files'].items():
        raw=Path(args.raw)/entry['filename']
        if not args.aggregate_only and file_hash(raw)!=entry['sha256']:raise ValueError('source content mismatch')
        with h5py.File(raw,'r') as handle:tasks.extend((raw,symbol,key) for key in sorted(handle))
    if args.max_days:tasks=tasks[:args.max_days]
    results=[]
    for index,(raw,symbol,key) in enumerate(tasks):
        if not args.aggregate_only and index%args.shards!=args.shard:continue
        if args.aggregate_only:
            r=read_json(work/(symbol+'-'+key+'.json'))
            if r['binding']!=binding:raise ValueError('wrong receipt binding')
        else:r=one_day(raw,Path(args.cache),config,symbol,key,binding,work)
        results.append(r)
    if not args.aggregate_only:return
    if len(results)!=1250:raise ValueError('full source denominator incomplete')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for scope in ('replay','queue'):
        chosen=results if scope=='replay' else [r for r in results if r['measured_queue']]
        timings={backend:np.sum([r[scope+'_seconds'][backend] for r in chosen],axis=0) for backend in ('python','native')}
        n=sum(r['messages'] if scope=='replay' else r['queue_benchmark_decisions'] for r in chosen)
        speedup=float(np.median(timings['python'])/np.median(timings['native']))
        for backend in ('python','native'):
            wall=float(np.median(timings[backend]));rows.append({'scope':scope,'backend':backend,'units':n,'unit':'messages' if scope=='replay' else 'virtual_orders',
                'source_messages':sum(r['messages'] for r in chosen),'partitions':len(chosen),'median_seconds':wall,'units_per_second':n/wall,'native_speedup':speedup,'repetitions':3,
                'timing_definition':'median_of_three_summed_per_day_kernel_wall_times_excluding_file_IO'})
    pd.DataFrame(rows).to_csv(out/'benchmark_summary.csv',index=False)
    atomic_json(out/'parity_summary.json',{'complete':True,'binding':binding,'source_days':len(results),'source_messages':sum(r['messages'] for r in results),
      'queue_days':sum(r['queue_domain'] for r in results),'queue_virtual_orders':sum(r['queue_decisions'] for r in results),
      'replay_interpretations':['retain','reset'],'replay_output_hash':digest([r['replay_hashes'] for r in results]),
      'queue_output_hash':digest([r['queue_hash'] for r in results]),'exact_bytes':True,'floating_tolerance':0,
      'fields':['all event arrays','live order counts','old/new priority timestamps','dense ten-level snapshots','validity and segment IDs','final ordered queues','all 16 passive-path fields'],
      'scientific_results_changed':False,'peak_memory':'not isolated; no comparative memory claim'})

if __name__=='__main__':main()
