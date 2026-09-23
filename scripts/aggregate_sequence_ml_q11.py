"""Strict full-denominator aggregation of fixed finalist visible-crossing diagnostics."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
MODES=('Q8_within_stock','Q10_source_only_transfer')
ARMS=('B1_history_xgboost','S0_seed_mean')
DELAYS=(0,1,5)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def matrix(reports,symbols,dates,key):
    cells={}
    for symbol,r in reports.items():
        for row in r[key]:
            k=(row['day'],symbol,row['mode'],row['arm'],row['delay_events'])
            if k in cells:raise ValueError('duplicate crossing cell')
            cells[k]=row
    expected={(d,s,m,a,l) for d in dates for s in symbols for m in MODES for a in ARMS for l in DELAYS}
    if set(cells)!=expected:raise ValueError('incomplete execution denominator')
    result={}
    for mode in MODES:
        result[mode]={}
        for arm in ARMS:
            result[mode][arm]={}
            for delay in DELAYS:
                vals=[];n=[];common=[];undefined=[]
                for d in dates:
                    for s in symbols:
                        row=cells[(d,s,mode,arm,delay)]
                        common.append(row['common_opportunities']);n.append(row['selected'])
                        if row['crossed_bps'] is None and row['selected']:
                            raise ValueError('selected execution cell missing crossed value')
                        if row['crossed_bps'] is None:
                            undefined.append({'day':d,'symbol':s,'reason':row['undefined_reason']})
                        else:vals.append(row['crossed_bps'])
                result[mode][arm][str(delay)]={'cells':len(dates)*len(symbols),
                    'common_opportunities_sum_across_cells':int(sum(common)),
                    'selected_sum_across_cells':int(sum(n)),
                    'undefined_cells':undefined,
                    'equal_stock_day_crossed_bps':float(np.mean(vals)) if not undefined else None,
                    'defined_cell_mean_descriptive':float(np.mean(vals)) if vals else None,
                    'pooled_selected_crossed_bps_descriptive':float(sum(cells[(d,s,mode,arm,delay)]['crossed_bps']*cells[(d,s,mode,arm,delay)]['selected'] for d in dates for s in symbols if cells[(d,s,mode,arm,delay)]['crossed_bps'] is not None)/sum(n)) if sum(n) else None}
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,default=Path('configs/sequence_ml_q11_v1.json'));ap.add_argument('--reports',type=Path,default=Path('results/sequence_ml_q11_v1'));ap.add_argument('--q8-summary',type=Path,default=Path('results/sequence_ml_q8_v1/q8_summary.json'));ap.add_argument('--q10-summary',type=Path,default=Path('results/sequence_ml_q10_v1/q10_summary.json'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise ValueError('preserve Q11 aggregate')
    cfg=json.loads(a.config.read_text());symbols=cfg['symbols'];reports={};hashes={};dates=set()
    if (cfg['decision_threshold_bps'],cfg['entry_delay_original_events'],cfg['exit_horizon_original_events'])!=(1.0,list(DELAYS),20):
        raise ValueError('execution configuration differs from frozen aggregator')
    if sha(a.q8_summary)!=cfg['parent_Q8_summary_sha256'] or sha(a.q10_summary)!=cfg['parent_Q10_summary_sha256']:
        raise ValueError('parent result summary changed')
    q8=json.loads(a.q8_summary.read_text());q10=json.loads(a.q10_summary.read_text())
    source_registry=json.loads(Path('configs/wselob_sources_v1.json').read_text())
    if sha(Path('configs/wselob_sources_v1.json'))!=cfg['source_registry_sha256']:
        raise ValueError('original source registry changed')
    for symbol in symbols:
        path=a.reports/f'q11_execution_{symbol}.json';r=json.loads(path.read_text())
        if (r['stage'],r['symbol'],r['config_sha256'],r['cache_manifest_sha256'])!=('Q11',symbol,sha(a.config),cfg['source_cache_manifest_sha256']):raise ValueError('Q11 receipt identity mismatch')
        if (r['q8_summary_sha256'],r['q10_summary_sha256'],r['q8_selected_context'],r['q10_source_only_context'],r['original_source_sha256']) != (
            sha(a.q8_summary),sha(a.q10_summary),q8['selected_context_from_April_only'],q10['selected_context_per_fold'][symbol],source_registry['files'][symbol]['sha256']):
            raise ValueError('parent context/source lineage mismatch')
        reports[symbol]=r;hashes[symbol]=sha(path);dates.update(x['day'] for x in r['day_receipts'])
    if len({r['source_commit'] for r in reports.values()})!=1:raise ValueError('mixed Q11 code commits')
    dates=sorted(dates);expected={(d,s) for d in dates for s in symbols}
    if {(x['day'],s) for s,r in reports.items() for x in r['day_receipts']}!=expected:raise ValueError('incomplete stock/day receipts')
    common={(x['day'],s):x['common_all_delay_rows'] for s,r in reports.items() for x in r['day_receipts']}
    for s,r in reports.items():
        for key in ('execution','both_selected'):
            for x in r[key]:
                if x['common_opportunities']!=common[(x['day'],s)]:raise ValueError('not common across delays/modes')
        main={(x['day'],x['mode'],x['arm'],x['delay_events']):x for x in r['execution']}
        for x in r['both_selected']:
            if x['selected']>main[(x['day'],x['mode'],x['arm'],x['delay_events'])]['selected']:
                raise ValueError('both-selected exceeds main selected count')
    out={'stage':'Q11','retrospective_only':True,'config_sha256':sha(a.config),'source_commit':next(iter(reports.values()))['source_commit'],
         'cache_manifest_sha256':cfg['source_cache_manifest_sha256'],'symbols':symbols,'dates':dates,
         'stock_day_cells':len(expected),'common_opportunities':sum(common.values()),
         'execution':matrix(reports,symbols,dates,'execution'),
         'both_selected':matrix(reports,symbols,dates,'both_selected'),
         'input_receipt_sha256':hashes,
         'limits':'Visible crossing at original t+20 exit and 0/1/5 delayed entries on same rows. Selected opportunity sets differ by model. No actual fills, fees, queue, impact, inventory or realized PnL.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'cells':out['stock_day_cells'],'common_opportunities':out['common_opportunities']}))
if __name__=='__main__':main()
