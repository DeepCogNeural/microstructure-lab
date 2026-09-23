"""Q11 fixed h20 visible crossing for within-stock and source-only finalists."""
from __future__ import annotations
import argparse, json, subprocess, tempfile
from pathlib import Path
import h5py, numpy as np, pandas as pd
from cloblab.research_diagnostics import cost_components
from cloblab.wselob import reconstruct
from run_sequence_ml_v1 import sha

LATENCIES=(0,1,5)
HORIZON=20
THRESHOLD=1.0

def selected_summary(pred,component,common,selected_override=None):
    selected=common & (np.abs(pred)>THRESHOLD)
    if selected_override is not None:selected &= selected_override
    n=int(selected.sum());denom=int(common.sum())
    if not n:
        return {'common_opportunities':denom,'selected':0,'coverage':0.0 if denom else None,
                'gross_midpoint_bps':None,'entry_half_spread_bps':None,'exit_half_spread_bps':None,
                'crossed_bps':None,'undefined_reason':'no_common_opportunities' if not denom else 'no_threshold_selected_rows'}
    sign=np.sign(pred[selected]);gross=sign*component['gross_long_bps'][selected]
    entry=component['entry_half_spread_bps'][selected];exit_=component['exit_half_spread_bps'][selected]
    crossed=np.where(sign>0,component['long_crossed_bps'][selected],component['short_crossed_bps'][selected])
    error=np.max(np.abs(gross-entry-exit_-crossed))
    if not np.isfinite(error) or error>1e-8:raise ValueError('visible crossing identity failed')
    return {'common_opportunities':denom,'selected':n,'coverage':float(n/denom) if denom else None,
            'gross_midpoint_bps':float(gross.mean()),'entry_half_spread_bps':float(entry.mean()),
            'exit_half_spread_bps':float(exit_.mean()),'crossed_bps':float(crossed.mean()),
            'max_identity_error_bps':float(error),'undefined_reason':None}

def load_predictions(q8_report,q8_private,q10_report,q10_private):
    if sha(q8_private)!=q8_report['private_predictions_sha256'] or sha(q10_private)!=q10_report['private_predictions_sha256']:
        raise ValueError('private prediction hash mismatch')
    with np.load(q8_private,allow_pickle=False) as q8, np.load(q10_private,allow_pickle=False) as q10:
        day=q8['eval_day'].astype(str).copy();event=q8['eval_event_index'].copy();y=q8['eval_y'].copy()
        if not (np.array_equal(day,q10['day'].astype(str)) and np.array_equal(event,q10['event_index'])
                and np.array_equal(y,q10['y'])):raise ValueError('Q8/Q10 scoring rows differ')
        pred={
            'Q8_within_stock':{'B1_history_xgboost':q8['eval_B1_history_xgboost'].copy(),
                               'S0_seed_mean':np.mean([q8[f'eval_S0_history_gru_seed{s}'] for s in (7,17,29)],axis=0)},
            'Q10_source_only_transfer':{'B1_history_xgboost':q10['B1_history_xgboost'].copy(),
                                        'S0_seed_mean':q10['S0_seed_mean_prediction'].copy()}}
    if any(len(p)!=len(y) or not np.isfinite(p).all() for mode in pred.values() for p in mode.values()):
        raise ValueError('invalid prediction array')
    return day,event,y,pred

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,default=Path('configs/sequence_ml_q11_v1.json'))
    ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--raw',type=Path,required=True);ap.add_argument('--symbol',required=True)
    ap.add_argument('--q8-summary',type=Path,required=True);ap.add_argument('--q8-reports',type=Path,required=True);ap.add_argument('--q8-private',type=Path,required=True)
    ap.add_argument('--q10-summary',type=Path,required=True)
    ap.add_argument('--q10-report',type=Path,required=True);ap.add_argument('--q10-private',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();cfg=json.loads(a.config.read_text())
    if a.symbol not in cfg['symbols'] or a.out.exists():raise ValueError('symbol/output outside protocol')
    if (cfg['decision_threshold_bps'],cfg['entry_delay_original_events'],cfg['exit_horizon_original_events'])!=(THRESHOLD,list(LATENCIES),HORIZON):
        raise ValueError('execution configuration differs from frozen runner')
    if sha(a.q8_summary)!=cfg['parent_Q8_summary_sha256'] or sha(a.q10_summary)!=cfg['parent_Q10_summary_sha256']:
        raise ValueError('parent summary changed')
    if sha(Path('configs/wselob_sources_v1.json'))!=cfg['source_registry_sha256']:
        raise ValueError('WSE source registry changed')
    q8_summary=json.loads(a.q8_summary.read_text());q8_context=q8_summary['selected_context_from_April_only']
    if q8_context not in cfg['contexts']:raise ValueError('Q8 no valid April-selected context')
    q8_path=a.q8_reports/f'q8_context{q8_context}_{a.symbol}.json';q8_report=json.loads(q8_path.read_text())
    q10_report=json.loads(a.q10_report.read_text())
    q10_summary=json.loads(a.q10_summary.read_text())
    if (q8_report['stage'],q10_report['stage'],q10_report['heldout_symbol'])!=('Q8','Q10',a.symbol):raise ValueError('report identity')
    if (q8_summary['stage'],q10_summary['stage'])!=('Q8','Q10') or sha(q8_path)!=q8_summary['input_receipt_sha256'][f'{q8_context}/{a.symbol}']:
        raise ValueError('Q8 summary/report lineage mismatch')
    if (sha(a.q10_report)!=q10_summary['input_receipt_sha256'][a.symbol]
        or q10_report['selected_context_from_source_April']!=q10_summary['selected_context_per_fold'][a.symbol]):
        raise ValueError('Q10 summary/report lineage mismatch')
    if sha(a.cache/'manifest.json')!=cfg['source_cache_manifest_sha256'] or q8_report['cache_manifest_sha256']!=cfg['source_cache_manifest_sha256'] or q10_report['cache_manifest_sha256']!=cfg['source_cache_manifest_sha256']:
        raise ValueError('cache lineage mismatch')
    day,event,y,predictions=load_predictions(q8_report,a.q8_private,q10_report,a.q10_private)
    if len(y)!=q8_report['selection_counts']['eval'] or len(y)!=q10_report['heldout_eval_rows']:raise ValueError('row denominator mismatch')
    manifest=json.loads((a.cache/'manifest.json').read_text());part={(p['symbol'],p['day']):p for p in manifest['partitions']}
    source=json.loads(Path('configs/wselob_sources_v1.json').read_text())['files'][a.symbol]
    raw=a.raw/source['filename']
    if raw.stat().st_size!=source['bytes'] or sha(raw)!=source['sha256']:
        raise ValueError('original WSE source file mismatch')
    summaries=[];both_selected=[];day_receipts=[];source_hashes={}
    source_file=h5py.File(raw,'r')
    for date in np.unique(day):
        ids=np.flatnonzero(day==date);p=part[(a.symbol,date)]
        folder=a.cache/f'symbol={a.symbol}'/f'day={date}'
        file=folder/'features.parquet'
        if sha(file)!=p['features_sha256']:raise ValueError('feature cache partition hash mismatch')
        source_hashes[date]={'features':p['features_sha256'],'snapshots':p['snapshots_sha256']}
        features=pd.read_parquet(folder/'features.parquet',columns=['event_index','segment','timestamp_ns','markout_20'])
        key='d'+date.replace('-','')
        if key not in source_file:raise ValueError('original WSE day missing')
        quotes,_=reconstruct(source_file[key+'/table'][:],date,a.symbol)
        with tempfile.TemporaryDirectory() as temp:
            snapshot=Path(temp)/'snapshots.parquet'
            quotes.to_parquet(snapshot,index=False,compression='zstd')
            if sha(snapshot)!=p['snapshots_sha256']:raise ValueError('replayed snapshot hash mismatch')
        if not (np.array_equal(features.event_index.to_numpy(),quotes.event_index.to_numpy())
                and np.array_equal(features.segment.to_numpy(),quotes.segment.to_numpy())
                and np.array_equal(features.timestamp_ns.to_numpy(),quotes.timestamp_ns.to_numpy())):
            raise ValueError('quote/label identity differs')
        quote_events=quotes.event_index.to_numpy(dtype=np.int64)
        positions=np.searchsorted(quote_events,event[ids])
        if (np.any(positions>=len(quote_events)) or not np.array_equal(quote_events[positions],event[ids])
            or not np.array_equal(features.markout_20.to_numpy(dtype=np.float32)[positions],y[ids])):
            raise ValueError('prediction/label original-event mismatch')
        comp={d:cost_components(quotes,HORIZON,d,fixed_exit=True).iloc[positions].reset_index(drop=True) for d in LATENCIES}
        arrays={d:{k:comp[d][k].to_numpy(dtype=float) for k in ('gross_long_bps','entry_half_spread_bps','exit_half_spread_bps','long_crossed_bps','short_crossed_bps')} for d in LATENCIES}
        common=np.logical_and.reduce([np.isfinite(x['long_crossed_bps']) & np.isfinite(x['short_crossed_bps']) for x in arrays.values()])
        quote=quotes[['bid_px_1','ask_px_1']].to_numpy(dtype=float)
        quote_valid=np.isfinite(quote).all(axis=1)&(quote[:,0]>0)&(quote[:,1]>quote[:,0])
        for offset in (*LATENCIES,HORIZON):
            ix=positions+offset
            common &= (ix<len(quote))&quote_valid[np.minimum(ix,len(quote)-1)]
        day_receipts.append({'day':date,'prediction_rows':len(ids),'common_all_delay_rows':int(common.sum()),'excluded_all_delay_rows':int(len(ids)-common.sum())})
        for mode,models in predictions.items():
            one={arm:arr[ids] for arm,arr in models.items()}
            both=common & (np.abs(one['B1_history_xgboost'])>THRESHOLD) & (np.abs(one['S0_seed_mean'])>THRESHOLD)
            for d in LATENCIES:
                for arm,pred in one.items():
                    summaries.append({'symbol':a.symbol,'day':date,'mode':mode,'arm':arm,'delay_events':d,
                                      **selected_summary(pred,arrays[d],common)})
                    both_selected.append({'symbol':a.symbol,'day':date,'mode':mode,'arm':arm,'delay_events':d,
                                          **selected_summary(pred,arrays[d],common,both)})
    source_file.close()
    report={'stage':'Q11','retrospective_only':True,'symbol':a.symbol,'config_sha256':sha(a.config),
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'cache_manifest_sha256':cfg['source_cache_manifest_sha256'],
            'original_source_sha256':source['sha256'],
            'q8_summary_sha256':sha(a.q8_summary),'q8_report_sha256':sha(q8_path),'q8_private_predictions_sha256':sha(a.q8_private),
            'q10_summary_sha256':sha(a.q10_summary),'q10_report_sha256':sha(a.q10_report),'q10_private_predictions_sha256':sha(a.q10_private),
            'q8_selected_context':q8_context,'q10_source_only_context':q10_report['selected_context_from_source_April'],
            'source_partition_hashes':source_hashes,'day_receipts':day_receipts,
            'execution':summaries,'both_selected':both_selected,
            'limits':'Fixed visible original-event h20 crossing, exact 0/1/5 entry delays, no actual fills/fees/queue/impact/inventory or profit claim.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'symbol':a.symbol,'days':len(day_receipts),'common_all_delay':sum(r['common_all_delay_rows'] for r in day_receipts)}))
if __name__=='__main__':main()
