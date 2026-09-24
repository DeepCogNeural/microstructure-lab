"""Frozen QOP A economic closeout on existing common late rows and predictions."""
from __future__ import annotations
import argparse, collections, hashlib, json, math
from pathlib import Path
import numpy as np

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def q(values,w,fraction):
    order=np.argsort(values,kind='stable'); v=np.asarray(values)[order]; ww=np.asarray(w)[order]
    return float(v[min(np.searchsorted(np.cumsum(ww),fraction*ww.sum(),side='left'),len(v)-1)])
def mean(xs): return float(np.mean(xs)) if xs else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();r=a.root
    private=r/'_private/qop_batch_v1'; out=r/'results/prediction_market_v4_development'
    src={name:private/name for name in ['features_private.json','build_private.json','model_predictions_private.json']}
    feats=json.loads(src['features_private.json'].read_text())['rows']; built=json.loads(src['build_private.json'].read_text())['leg_rows']; preds=json.loads(src['model_predictions_private.json'].read_text())['predictions']
    pubold=json.loads((r/'results/polymarket_qop_batch_v1/model_evaluation.json').read_text())
    volume=collections.defaultdict(float)
    for x in built:volume[int(x['event_idx'])]+=float(x['shares'])
    ready=lambda x: bool(x['shift']['0']['labels'].get('5000')) and all(x['features'].get(f'0_{c}') for c in (1000,5000))
    cal=[x for x in feats if ready(x) and 48<=x['event_idx']<72]; late=[x for x in feats if ready(x) and x['event_idx']>=72]
    calvol=collections.defaultdict(float)
    for x in cal:calvol[x['event_idx']]+=float(x['shares'])
    calw=np.array([float(x['shares'])/calvol[x['event_idx']] for x in cal]);
    ids=[(x['event_idx'],x['hash'],x['leg_idx']) for x in late]
    events=list(range(72,96)); byevent={e:[i for i,x in enumerate(late) if x['event_idx']==e] for e in events}
    y=np.array([float(x['shift']['0']['labels']['5000']['N']) for x in late]);v=np.array([float(x['shares']) for x in late]);
    res={'status':'DEVELOPMENT_RECEIVE_CLOCK_ONLY','units':'cents per raw joined selected target share, event-equal','source_sha256':{k:sha(p) for k,p in src.items()},'old_public_model_evaluation_sha256':sha(r/'results/polymarket_qop_batch_v1/model_evaluation.json'),'late_events_total':len(events),'late_raw_joined_shares':sum(volume[e] for e in events),'late_common_rows':len(late),'late_common_shares':float(v.sum()),'unjoined_transactions':35,'models':{},'primary_retention':0.75,'comparison':'within-event expected random retention at same expected observable share count; no execution/P&L claim'}
    private_rows=[]
    for p in preds:
        key=p['key']
        if not key.startswith('N_'):continue
        if [tuple(x) for x in p['late_ids']]!=ids:raise ValueError('private prediction/row identity mismatch')
        scores=np.array(p['late_scores']); cs=np.array(p['calibration_scores']);
        if len(cs)!=len(cal) or len(scores)!=len(late):raise ValueError('score length mismatch')
        table={}
        for retention in (0.5,0.75,0.9,1.0):
            thresh=None if retention==1 else q(cs,calw,1-retention)
            keep=np.ones(len(late),dtype=bool) if thresh is None else scores>=thresh
            rows=[]
            for e in events:
                ix=byevent[e]; V=volume[e];U=float(v[ix].sum()) if ix else 0.0
                if V<=0:raise ValueError('missing raw denominator')
                if not ix or U<=0:
                    rows.append({'event_idx':e,'V':V,'U':U,'J':None,'Jall':None,'pi':None,'EJrandom':None,'S':None});continue
                k=keep[ix];J=float(np.sum(v[ix]*k*y[ix])/V); Jall=float(np.sum(v[ix]*y[ix])/V); pi=float(np.sum(v[ix]*k)/U); random=pi*Jall
                row={'event_idx':e,'V':V,'U':U,'J':J,'Jall':Jall,'pi':pi,'EJrandom':random,'S':J-random,'retained_raw_fraction':float(np.sum(v[ix]*k)/V),'lost_positive':float(np.sum(v[ix]*(~k)*np.maximum(y[ix],0))/V),'kept_legs':int(k.sum()),'common_legs':len(ix)};rows.append(row)
            ok=[x for x in rows if x['S'] is not None]
            mean_j=mean([x['J'] for x in ok]);mean_all=mean([x['Jall'] for x in ok]);mean_s=mean([x['S'] for x in ok]);
            old=pubold['models'][key]['economic'][str(retention)]
            if not math.isclose(mean_j,old['J_cents_per_raw_share'],rel_tol=1e-9,abs_tol=1e-9):raise ValueError('old J mismatch')
            if not math.isclose(mean_all,old['J_all_observed_cents_per_raw_share'],rel_tol=1e-9,abs_tol=1e-9):raise ValueError('old Jall mismatch')
            max_e=max(ok,key=lambda x:x['V'])
            block=[[x for x in ok if (x['event_idx']-72)//6==b] for b in range(4)]
            table[str(retention)]={'threshold_from_calibration':thresh,'evaluated_events':len(ok),'empty_common_events':len(rows)-len(ok),'J':mean_j,'J_all_observed':mean_all,'E_J_random':mean([x['EJrandom'] for x in ok]),'S_within_event':mean_s,'J_minus_Jall':mean_j-mean_all,'mean_U_over_V':mean([x['U']/x['V'] for x in ok]),'mean_retained_U_fraction':mean([x['pi'] for x in ok]),'mean_retained_V_fraction':mean([x['retained_raw_fraction'] for x in ok]),'mean_lost_positive':mean([x['lost_positive'] for x in ok]),'kept_legs':sum(x['kept_legs'] for x in ok),'events_with_any_retention':sum(x['kept_legs']>0 for x in ok),'largest_raw_event_removed_S':mean([x['S'] for x in ok if x['event_idx']!=max_e['event_idx']]),'largest_raw_event_removed_J':mean([x['J'] for x in ok if x['event_idx']!=max_e['event_idx']]),'six_hour_S':[mean([x['S'] for x in b]) for b in block],'six_hour_J':[mean([x['J'] for x in b]) for b in block]}
            private_rows.append({'key':key,'retention':retention,'events':rows})
        res['models'][key]=table
    (r/'_private/prediction_market_v4_development').mkdir(parents=True,exist_ok=True)
    (r/'_private/prediction_market_v4_development/a_event_private.json').write_text(json.dumps(private_rows,separators=(',',':'))+'\n')
    # Private event rows are kept under ignored _private only; public file has aggregates.
    (out/'a_economics.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'models':len(res['models']),'primary':{k:x['0.75']['S_within_event'] for k,x in res['models'].items()}},sort_keys=True))
if __name__=='__main__':main()
