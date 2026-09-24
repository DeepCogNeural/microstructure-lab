"""Frozen finite QOP development models and event-equal economic descriptions."""
from __future__ import annotations
import argparse,collections,hashlib,json,math
from pathlib import Path
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor

p=argparse.ArgumentParser()
p.add_argument('--features-private',type=Path,required=True)
p.add_argument('--build-private',type=Path,required=True)
p.add_argument('--config',type=Path,required=True)
p.add_argument('--out-private',type=Path,required=True)
p.add_argument('--out-public',type=Path,required=True)
a=p.parse_args()
if a.out_private.exists() or a.out_public.exists():raise ValueError('preserve output')
config=json.loads(a.config.read_text());data=json.loads(a.features_private.read_text())['rows']
built=json.loads(a.build_private.read_text())['leg_rows']
if config['prediction']['feature_cutoffs_ms_before_print_receive'] != [1000,5000]:raise ValueError('config cutoffs')

def ready(x):
    return bool(x['shift']['0']['labels'].get('5000')) and all(x['features'].get(f'0_{cut}') for cut in (1000,5000))
common=[x for x in data if ready(x)]
for x in common:
    for cut in (1000,5000):
        for layer in ('M0','M1','M2'):
            if not all(math.isfinite(v) for v in x['features'][f'0_{cut}'][layer]):raise ValueError('nonfinite feature')
splits={'train':[x for x in common if x['event_idx']<48],
        'calibration':[x for x in common if 48<=x['event_idx']<72],
        'late':[x for x in common if x['event_idx']>=72]}
counts={k:{'legs':len(v),'events':len({x['event_idx'] for x in v}),'shares':str(sum(float(x['shares']) for x in v))} for k,v in splits.items()}
minimum=all(x['legs']>=30 and x['events']>=8 for x in counts.values())
purge_gaps={}
for left,right,label in (('train','calibration','train_to_calibration'),('calibration','late','calibration_to_late')):
    if splits[left] and splits[right]:
        gap=min(x['print_recv_ms'] for x in splits[right])-max(x['print_recv_ms'] for x in splits[left])
        purge_gaps[label]=gap
        if gap<=35000:raise ValueError('35-second boundary purge violated')


# Raw denominator contains every receipt-joined selected-token leg in an event,
# even if quote/feature missing. Failed receipt transactions lack known maker shares.
raw_volume=collections.defaultdict(float)
for x in built:raw_volume[x['event_idx']]+=float(x['shares'])

def weights(seq):
    volumes=collections.defaultdict(float)
    for x in seq:volumes[x['event_idx']]+=float(x['shares'])
    return np.array([float(x['shares'])/volumes[x['event_idx']] for x in seq])

def metrics(y,pred,w):
    diff=np.asarray(pred)-np.asarray(y)
    return {'mse':float(np.average(diff*diff,weights=w)), 'mae':float(np.average(np.abs(diff),weights=w)),
            'bias':float(np.average(diff,weights=w))}

def weighted_quantile(values,w,q):
    order=np.argsort(values,kind='stable');v=np.asarray(values)[order];ww=np.asarray(w)[order]
    idx=np.searchsorted(np.cumsum(ww),q*ww.sum(),side='left')
    return float(v[min(idx,len(v)-1)])

def economic(late,late_scores,cal_scores,cal_w):
    result={}; y=np.array([float(x['shift']['0']['labels']['5000']['N']) for x in late]);shares=np.array([float(x['shares']) for x in late])
    events=sorted({x['event_idx'] for x in late});indices={e:np.array([i for i,x in enumerate(late) if x['event_idx']==e]) for e in events}
    for retention in (0.5,0.75,0.9,1.0):
        threshold=None if retention==1 else weighted_quantile(cal_scores,cal_w,1-retention)
        kept=np.ones(len(late),dtype=bool) if threshold is None else np.asarray(late_scores)>=threshold
        J=[];Jall=[];retained=[];lost_pos=[]
        for e in events:
            ix=indices[e];v=raw_volume[e]
            if v<=0:continue
            J.append(float(np.sum(shares[ix]*kept[ix]*y[ix])/v))
            Jall.append(float(np.sum(shares[ix]*y[ix])/v))
            retained.append(float(np.sum(shares[ix]*kept[ix])/v))
            lost_pos.append(float(np.sum(shares[ix]*(~kept[ix])*np.maximum(y[ix],0))/v))
        result[str(retention)]={'threshold_from_calibration':threshold,
            'event_count':len(J),'J_cents_per_raw_share':float(np.mean(J)) if J else None,
            'J_all_observed_cents_per_raw_share':float(np.mean(Jall)) if Jall else None,
            'J_minus_J_all_cents_per_raw_share':float(np.mean(np.array(J)-np.array(Jall))) if J else None,
            'mean_retained_raw_share_fraction':float(np.mean(retained)) if retained else None,
            'mean_abandoned_positive_cents_per_raw_share':float(np.mean(lost_pos)) if lost_pos else None,
            'late_legs_retained':int(kept.sum())}
    return result

public={'status':'DONE' if minimum else 'BLOCKED_DATA_INSUFFICIENT',
        'common_model_ready_legs':len(common),'split_counts':counts,'boundary_gaps_ms':purge_gaps,
        'raw_selected_target_legs':len(built),
        'late_raw_shares':str(sum(raw_volume[e] for e in range(72,96))),
        'late_model_ready_shares':counts['late']['shares'],
        'feature_source_sha256':hashlib.sha256(a.features_private.read_bytes()).hexdigest(),
        'config_sha256':hashlib.sha256(a.config.read_bytes()).hexdigest(),
        'models':{},'reference':{},'limits':'All dates are one researcher-exposed development day; late block is exploratory and no complete policy P&L is identified.'}
private_predictions=[]
if minimum:
    train,cal,late=(splits[k] for k in ('train','calibration','late'))
    wt,wc,wl=(weights(x) for x in (train,cal,late))
    for target in ('N','D'):
        yt,yc,yl=(np.array([float(x['shift']['0']['labels']['5000'][target]) for x in seq]) for seq in (train,cal,late))
        public['reference'][target]={
            'train_mean_predictor_late':metrics(yl,np.full(len(yl),float(np.average(yt,weights=wt))),wl),
            'zero_change_late':metrics(yl,np.zeros(len(yl)),wl) if target=='D' else None}
        for cutoff in (1000,5000):
            for layer in ('M0','M1','M2'):
                xt,xc,xl=(np.array([x['features'][f'0_{cutoff}'][layer] for x in seq],dtype=float) for seq in (train,cal,late))
                scaler=StandardScaler().fit(xt,sample_weight=wt)
                zt,zc,zl=(scaler.transform(x) for x in (xt,xc,xl))
                candidates=[]
                for alpha in (1.,10.,100.):
                    mdl=Ridge(alpha=alpha).fit(zt,yt,sample_weight=wt)
                    pc=mdl.predict(zc)
                    candidates.append((metrics(yc,pc,wc)['mse'],alpha,mdl))
                _,alpha,model=min(candidates,key=lambda x:(x[0],x[1]))
                pc,pl=model.predict(zc),model.predict(zl)
                key=f'{target}_{cutoff}_{layer}_ridge'
                public['models'][key]={'alpha':alpha,'train_design_rank':int(np.linalg.matrix_rank(zt)),
                    'feature_count':zt.shape[1], 'calibration':metrics(yc,pc,wc),'late':metrics(yl,pl,wl),
                    'calibration_mse_by_alpha':{str(v):mse for mse,v,_ in candidates}}
                if target=='N':public['models'][key]['economic']=economic(late,pl,pc,wc)
                private_predictions.append({'key':key,'calibration_scores':pc.tolist(),'late_scores':pl.tolist(),
                    'late_ids':[(x['event_idx'],x['hash'],x['leg_idx']) for x in late]})
            # Single shallow boosting implementation on exactly M2 features.
            layer='M2';xt,xc,xl=(np.array([x['features'][f'0_{cutoff}'][layer] for x in seq],dtype=float) for seq in (train,cal,late))
            trees=[]
            for depth in (2,3):
                mdl=HistGradientBoostingRegressor(max_depth=depth,max_iter=100,learning_rate=.05,
                    l2_regularization=1.,random_state=7).fit(xt,yt,sample_weight=wt)
                pc=mdl.predict(xc)
                trees.append((metrics(yc,pc,wc)['mse'],depth,mdl))
            _,depth,model=min(trees,key=lambda x:(x[0],x[1]))
            pc,pl=model.predict(xc),model.predict(xl)
            key=f'{target}_{cutoff}_M2_shallow_boosting'
            public['models'][key]={'max_depth':depth,'n_iter':int(model.n_iter_),
                'calibration':metrics(yc,pc,wc),'late':metrics(yl,pl,wl),
                'calibration_mse_by_depth':{str(v):mse for mse,v,_ in trees}}
            if target=='N':public['models'][key]['economic']=economic(late,pl,pc,wc)
            private_predictions.append({'key':key,'calibration_scores':pc.tolist(),'late_scores':pl.tolist(),
                'late_ids':[(x['event_idx'],x['hash'],x['leg_idx']) for x in late]})
else:
    public['blocked_reason']='Each train/calibration/late split requires at least 8 events and 30 complete legs on one common opportunity set.'
a.out_private.write_text(json.dumps({'split_counts':counts,'predictions':private_predictions},separators=(',',':'))+'\n')
public['private_predictions_sha256']=hashlib.sha256(a.out_private.read_bytes()).hexdigest()
a.out_public.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':public['status'],'common':len(common),'split_counts':counts,'model_count':len(public['models'])}))
