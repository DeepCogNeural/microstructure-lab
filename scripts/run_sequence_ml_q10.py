"""Q10 five-fold transfer: fit only four source stocks, score held-out stock later."""
from __future__ import annotations
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import argparse, copy, json, math, resource, subprocess, sys, time
from pathlib import Path
import joblib, numpy as np, pandas as pd, torch
from cloblab.sequence_ml import FEATURES, IDENTITY, index_day, scoring_endpoints
from cloblab.sequence_model import GRURegressor
from run_sequence_ml_fq2 import endpoint_identity, fit_gru_gpu, predict
from run_sequence_ml_v1 import day_scores, fit_tabular, load_stock, sha

SEEDS=(7,17,29)

def choose_context(q8_reports:Path, source:list[str], cfg:dict)->tuple[int,dict,dict]:
    """Only open April Q8 receipts of the four source stocks."""
    evidence={}; receipts={}; dates_ref=None
    for context in cfg['candidate_contexts']:
        vals=[]
        for symbol in source:
            path=q8_reports/f'q8_context{context}_{symbol}.json'
            report=json.loads(path.read_text())
            if (report['stage'],report['context_states'],report['symbol'],report['config_sha256'],report['cache_manifest_sha256']) != (
                'Q8',context,symbol,cfg['parent_Q8_config_sha256'],cfg['source_cache_manifest_sha256']):
                raise ValueError('Q8 source receipt identity mismatch')
            receipts[f'{context}/{symbol}']=sha(path)
            dev_rows=[r for r in report['scores'] if r['split']=='dev']
            cells={(r['day'],r['arm']):r for r in dev_rows}
            if len(cells)!=len(dev_rows): raise ValueError('duplicate source April score cell')
            dates=sorted({day for day,_ in cells})
            if dates_ref is None: dates_ref=dates
            if dates!=dates_ref or not dates: raise ValueError('source April date mismatch')
            expected={(d,f'S0_history_gru_seed{s}') for d in dates for s in SEEDS}
            if not expected.issubset(cells): raise ValueError('missing source April GRU cell')
            for day in dates:
                ic=[cells[(day,f'S0_history_gru_seed{s}')]['ic'] for s in SEEDS]
                if any(v is None or not np.isfinite(v) for v in ic):
                    raise ValueError('undefined source April IC; no fold context selection')
                vals.append(float(np.mean(ic)))
        evidence[str(context)]=float(np.mean(vals))
    best=max(evidence.values())
    selected=min(c for c in cfg['candidate_contexts'] if evidence[str(c)]>=best-1e-6)
    return selected,evidence,receipts

def heldout_eval_only(cache:Path, manifest:dict, symbol:str, context:int, cfg:dict)->tuple[dict,dict]:
    """Read held-out June/Sep/Nov only; never touch its train/dev labels."""
    parts=sorted((p for p in manifest['partitions'] if p['symbol']==symbol
                  and p['day'][:7] in cfg['heldout_evaluation_months']),key=lambda p:p['day'])
    if not parts: raise ValueError('no held-out evaluation partitions')
    out={k:[] for k in ('x','y','day','event_index')}; hashes={}
    for p in parts:
        path=cache/f"symbol={symbol}"/f"day={p['day']}"/'features.parquet'
        if sha(path)!=p['features_sha256']: raise ValueError('held-out feature hash mismatch')
        frame=pd.read_parquet(path,columns=list(IDENTITY)+list(FEATURES)+['markout_20'])
        index=index_day(frame,cfg['common_eligibility_context'])
        endpoints=scoring_endpoints(frame,index,20)
        if not len(endpoints): raise ValueError('no held-out scoring endpoints')
        positions=endpoints[:,None]+np.arange(1-cfg['common_eligibility_context'],1)[None,:]
        x=frame[list(FEATURES)].to_numpy(dtype=np.float32)[positions][:,-context:,:]
        out['x'].append(x)
        out['y'].append(frame.markout_20.to_numpy(dtype=np.float32)[endpoints])
        out['day'].append(np.repeat(p['day'],len(endpoints)))
        out['event_index'].append(frame.event_index.to_numpy(dtype=np.int64)[endpoints])
        hashes[p['day']]=p['features_sha256']
    return {k:np.concatenate(v) for k,v in out.items()},hashes

def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--config',type=Path,default=Path('configs/sequence_ml_q10_v1.json'))
    ap.add_argument('--q8-reports',type=Path,default=Path('results/sequence_ml_q8_v1'))
    ap.add_argument('--cache',type=Path,required=True)
    ap.add_argument('--heldout',required=True)
    ap.add_argument('--private',type=Path,required=True)
    ap.add_argument('--aggregate',type=Path,required=True)
    a=ap.parse_args();cfg=json.loads(a.config.read_text())
    if a.heldout not in cfg['symbols'] or a.private.exists() or a.aggregate.exists():
        raise ValueError('fold outside protocol or output exists')
    if sha(Path('configs/sequence_ml_q8_v1.json'))!=cfg['parent_Q8_config_sha256']:
        raise ValueError('Q8 parent changed')
    if sha(a.cache/'manifest.json')!=cfg['source_cache_manifest_sha256'] or not torch.cuda.is_available():
        raise ValueError('source cache/GPU mismatch')
    source=[s for s in cfg['symbols'] if s!=a.heldout]
    selected,evidence,receipts=choose_context(a.q8_reports,source,cfg)
    began=time.monotonic();base=json.loads(Path('configs/sequence_ml_fq2_v1.json').read_text())
    model_cfg=copy.deepcopy(base);model_cfg['training_endpoints_per_stock_max']=cfg['source_train_endpoints_per_stock'];model_cfg['context_states']=cfg['common_eligibility_context'];model_cfg['evaluation_months']=[]
    manifest=json.loads((a.cache/'manifest.json').read_text())
    source_stocks={}; ids={}; feature_hashes={}
    for symbol in source:
        stock,_,hashes=load_stock(a.cache,manifest,symbol,model_cfg)
        if len(stock['train']['y'])!=cfg['source_train_endpoints_per_stock']:
            raise ValueError('source 200k context128 endpoint shortage')
        q8=json.loads((a.q8_reports/f'q8_context{selected}_{symbol}.json').read_text())
        ids[symbol]={split:endpoint_identity(data['day'],data['event_index']) for split,data in stock.items()}
        if any(ids[symbol][split]!=q8['endpoint_identity_sha256'][split] for split in ('train','dev')):
            raise ValueError('source/Q8 train/dev endpoint identities differ')
        source_stocks[symbol]=stock;feature_hashes[symbol]=hashes
    pooled={split:{key:np.concatenate([source_stocks[s][split][key] for s in source])
                   for key in ('x','y','day','event_index')} for split in ('train','dev')}
    del source_stocks
    for split in pooled: pooled[split]['x']=pooled[split]['x'][:,-selected:,:]
    # The reused FQ2 fitters require an eval array but do not consume eval labels
    # for fitting. Give them source April features and dummy labels only.
    dummy_eval={'x':pooled['dev']['x'],'y':np.zeros(len(pooled['dev']['y']),dtype=np.float32)}
    source_dev_rows=len(pooled['dev']['y'])
    fit_input={'train':pooled['train'],'dev':pooled['dev'],'eval':dummy_eval}
    a.private.mkdir(parents=True)
    costs={}
    _,_,costs['B1_history_xgboost']=fit_tabular('B1_history_xgboost',fit_input,model_cfg,a.private)
    print(json.dumps({'heldout':a.heldout,'arm':'B1_history_xgboost','fit_seconds':costs['B1_history_xgboost']['fit_seconds']}),flush=True)
    for seed in SEEDS:
        arm=f'S0_history_gru_seed{seed}'
        _,_,costs[arm]=fit_gru_gpu(seed,fit_input,model_cfg,a.private)
        print(json.dumps({'heldout':a.heldout,'arm':arm,'fit_seconds':costs[arm]['fit_seconds'],'epochs':costs[arm]['epochs_run']}),flush=True)
    del pooled,fit_input,dummy_eval
    heldout,heldout_hashes=heldout_eval_only(a.cache,manifest,a.heldout,selected,cfg)
    predictions={};inference={}
    tic=time.monotonic();b1=joblib.load(a.private/'B1_history_xgboost.joblib')
    predictions['B1_history_xgboost']=b1.predict(heldout['x'].reshape(len(heldout['y']),-1));inference['B1_history_xgboost']=time.monotonic()-tic
    del b1
    for seed in SEEDS:
        arm=f'S0_history_gru_seed{seed}';tic=time.monotonic()
        stored=torch.load(a.private/f'{arm}.pt',map_location='cpu',weights_only=False)
        model=GRURegressor(hidden_size=model_cfg['gru']['hidden_size']).cuda();model.load_state_dict(stored['state'])
        predictions[arm]=predict(model,heldout['x'],stored['mu'],stored['sigma'],model_cfg['gru']['batch_size'],torch.device('cuda'))*stored['target_sigma']+stored['target_mu']
        torch.cuda.synchronize();inference[arm]=time.monotonic()-tic
        del model,stored
    predictions['S0_seed_mean_prediction']=np.mean([predictions[f'S0_history_gru_seed{s}'] for s in SEEDS],axis=0)
    scores=[]
    for arm,pred in predictions.items():
        for row in day_scores(heldout['y'],pred,heldout['day']):
            scores.append({'symbol':a.heldout,'arm':arm,'split':'eval',**row})
    private_predictions=a.private/'predictions.npz'
    np.savez_compressed(private_predictions,y=heldout['y'],day=heldout['day'],event_index=heldout['event_index'],**predictions)
    report={'stage':'Q10','retrospective_only':True,'heldout_symbol':a.heldout,'source_symbols':source,
            'selected_context_from_source_April':selected,'source_April_context_ic':evidence,
            'source_Q8_receipt_sha256':receipts,'config_sha256':sha(a.config),
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'cache_manifest_sha256':sha(a.cache/'manifest.json'),
            'source_endpoint_identity_sha256':ids,'source_feature_hashes_by_day':feature_hashes,
            'heldout_eval_endpoint_identity_sha256':endpoint_identity(heldout['day'],heldout['event_index']),
            'heldout_eval_feature_hashes_by_day':heldout_hashes,
            'source_train_rows':sum(costs[arm]['train_endpoints'] for arm in ['B1_history_xgboost']),
            'source_dev_rows':source_dev_rows,
            'heldout_eval_rows':len(heldout['y']),'scores':scores,'costs':costs,
            'heldout_inference_seconds':inference,'private_predictions_sha256':sha(private_predictions),
            'wall_seconds':time.monotonic()-began,
            'gpu_device_occupancy_seconds':sum(c.get('device_occupancy_seconds',0) for c in costs.values()),
            'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
            'limits':'All heldout stocks/dates previously exposed. Source-only pooled fit; held-out Jan-Apr labels absent from fit/selection. No independent/fill/profit claim.'}
    a.aggregate.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.aggregate.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2,sort_keys=True,default=int)+'\n');os.replace(tmp,a.aggregate)
    print(json.dumps({'heldout':a.heldout,'selected_context':selected,'rows':len(heldout['y']),'status':'complete'}),flush=True)
if __name__=='__main__':main()
