"""Aggregate five strict source-only stock-transfer folds on common held-out rows."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from aggregate_sequence_ml_fq2 import bootstrap
ARMS=('B1_history_xgboost','S0_history_gru_seed7','S0_history_gru_seed17','S0_history_gru_seed29','S0_seed_mean_prediction')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def contrast(test,baseline,dates,symbols):
    delta=test-baseline
    return {'mean_delta_ic':float(delta.mean()),'ci95_date_block5':bootstrap(dates,delta.mean(axis=1),5),
            'month_delta_ic':{m:float(delta[[d.startswith(m) for d in dates]].mean()) for m in sorted({d[:7] for d in dates})},
            'stock_delta_ic':{s:float(delta[:,i].mean()) for i,s in enumerate(symbols)}}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,default=Path('configs/sequence_ml_q10_v1.json'));ap.add_argument('--reports',type=Path,default=Path('results/sequence_ml_q10_v1'));ap.add_argument('--q8-reports',type=Path,default=Path('results/sequence_ml_q8_v1'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise ValueError('preserve Q10 aggregate')
    cfg=json.loads(a.config.read_text());symbols=cfg['symbols'];reports={};hashes={};dates=set()
    for heldout in symbols:
        path=a.reports/f'q10_transfer_{heldout}.json';r=json.loads(path.read_text())
        if (r['stage'],r['heldout_symbol'],r['config_sha256'],r['cache_manifest_sha256'],r['source_symbols'])!=(
            'Q10',heldout,sha(a.config),cfg['source_cache_manifest_sha256'],[s for s in symbols if s!=heldout]):raise ValueError('fold identity mismatch')
        selected=r['selected_context_from_source_April']
        if selected not in cfg['candidate_contexts']:raise ValueError('selected context outside grid')
        source_ic=r['source_April_context_ic'];best=max(source_ic.values())
        expected_choice=min(c for c in cfg['candidate_contexts'] if source_ic[str(c)]>=best-1e-6)
        if selected!=expected_choice:raise ValueError('source-only April choice mismatch')
        expected_source_keys={f'{c}/{s}' for c in cfg['candidate_contexts'] for s in symbols if s!=heldout}
        if set(r['source_Q8_receipt_sha256'])!=expected_source_keys:raise ValueError('source receipt scope includes heldout or omits source')
        for key,digest in r['source_Q8_receipt_sha256'].items():
            context,symbol=key.split('/')
            if sha(a.q8_reports/f'q8_context{context}_{symbol}.json')!=digest:raise ValueError('source Q8 receipt changed')
        source_dates=None
        for context in cfg['candidate_contexts']:
            vals=[]
            for symbol in r['source_symbols']:
                q8_source=json.loads((a.q8_reports/f'q8_context{context}_{symbol}.json').read_text())
                dev=[row for row in q8_source['scores'] if row['split']=='dev']
                by_cell={(row['day'],row['arm']):row for row in dev}
                if len(by_cell)!=len(dev):raise ValueError('duplicate source Q8 April cell')
                days=sorted({day for day,_ in by_cell})
                if source_dates is None:source_dates=days
                if days!=source_dates or not days:raise ValueError('source April dates differ')
                for day in days:
                    seed_ic=[by_cell[(day,f'S0_history_gru_seed{s}')]['ic'] for s in (7,17,29)]
                    if any(v is None or not np.isfinite(v) for v in seed_ic):raise ValueError('undefined source April cell')
                    vals.append(float(np.mean(seed_ic)))
            if abs(float(np.mean(vals))-float(source_ic[str(context)]))>1e-12:
                raise ValueError('reported source-only April context score mismatch')
        q8_path=a.q8_reports/f'q8_context{selected}_{heldout}.json';q8=json.loads(q8_path.read_text())
        if (q8['endpoint_identity_sha256']['eval']!=r['heldout_eval_endpoint_identity_sha256'] or
            q8['selection_counts']['eval']!=r['heldout_eval_rows']):raise ValueError('heldout Q8 scoring identity mismatch')
        if set(r['costs'])!=set(ARMS[:4]) or any(r['costs'][f'S0_history_gru_seed{s}']['train_endpoints']!=800000 for s in (7,17,29)):
            raise ValueError('incomplete source-only models')
        if len(r['source_symbols'])!=4 or len(r['source_endpoint_identity_sha256'])!=4 or r['source_train_rows']!=800000:
            raise ValueError('source denominator mismatch')
        reports[heldout]=r;hashes[heldout]=sha(path)
        dates.update(row['day'] for row in r['scores'])
    if len({r['source_commit'] for r in reports.values()})!=1:raise ValueError('mixed Q10 runner commits')
    dates=sorted(dates);cells={}
    for heldout,r in reports.items():
        for row in r['scores']:
            if row['split']!='eval' or row['symbol']!=heldout or row['arm'] not in ARMS:raise ValueError('bad score cell')
            key=(row['day'],heldout,row['arm'])
            if key in cells:raise ValueError('duplicate cell')
            cells[key]=row
    expected={(d,s,arm) for d in dates for s in symbols for arm in ARMS}
    if set(cells)!=expected:raise ValueError('incomplete fold/date/arm denominator')
    n=np.zeros((len(dates),len(symbols)),dtype=np.int64)
    values={arm:np.full(n.shape,np.nan) for arm in ARMS};undefined=[]
    for di,d in enumerate(dates):
        for si,s in enumerate(symbols):
            count=cells[(d,s,ARMS[0])]['n'];n[di,si]=count
            for arm in ARMS:
                row=cells[(d,s,arm)]
                if row['n']!=count:raise ValueError('unequal scored opportunities')
                if row['ic'] is None:undefined.append({'day':d,'symbol':s,'arm':arm,'reason':row.get('undefined_reason')})
                else:values[arm][di,si]=row['ic']
    primary=None
    if not undefined:
        b1=values[ARMS[0]];s0=np.mean([values[a] for a in ARMS[1:4]],axis=0)
        primary={'mean_ic':{a:float(v.mean()) for a,v in values.items()},'S0_seed_mean_ic':float(s0.mean()),
                 'S0_seed_mean_vs_B1':contrast(s0,b1,dates,symbols),
                 'S0_prediction_mean_vs_B1':contrast(values['S0_seed_mean_prediction'],b1,dates,symbols),
                 'each_seed_vs_B1':{str(s):contrast(values[f'S0_history_gru_seed{s}'],b1,dates,symbols) for s in (7,17,29)}}
    out={'stage':'Q10','retrospective_only':True,'config_sha256':sha(a.config),'source_commit':next(iter(reports.values()))['source_commit'],
         'cache_manifest_sha256':cfg['source_cache_manifest_sha256'],'symbols':symbols,'dates':dates,
         'cells_per_arm':int(n.size),'rows_per_arm':int(n.sum()),'undefined_cells':undefined,
         'full_denominator_result':primary,'selected_context_per_fold':{s:reports[s]['selected_context_from_source_April'] for s in symbols},
         'source_April_context_ic':{s:reports[s]['source_April_context_ic'] for s in symbols},
         'training_limited':{s:{arm:reports[s]['costs'][arm]['training_limited'] for arm in ARMS[1:4]} for s in symbols},
         'fold_train_rows':{s:reports[s]['source_train_rows'] for s in symbols},
         'task_wall_seconds':sum(r['wall_seconds'] for r in reports.values()),
         'gpu_device_occupancy_seconds':sum(r['gpu_device_occupancy_seconds'] for r in reports.values()),
         'input_receipt_sha256':hashes,
         'limits':'All five stocks and historical dates previously viewed. Strict source-only fit and April selection, held-out labels only for retrospective scoring. No independent/fill/profit claim.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'cells':out['cells_per_arm'],'rows':out['rows_per_arm'],'undefined':len(undefined),'delta':None if primary is None else primary['S0_seed_mean_vs_B1']['mean_delta_ic']}))
if __name__=='__main__':main()
