"""Frozen R0/R1/R2/R3 offset-logistic seven-day development comparison."""
from __future__ import annotations
import argparse,hashlib,json,math,os
from collections import Counter
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit,logit

EPS=1e-6
CS=(0.1,1.0,10.0)
TRAIN=('2026-07-27','2026-07-28','2026-07-29')
CAL='2026-07-30'
FORWARD=('2026-07-31','2026-08-01','2026-08-02')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clip(p):return np.clip(p,EPS,1-EPS)
def loss(y,q):
    q=clip(q)
    return -(y*np.log(q)+(1-y)*np.log1p(-q))
def score(y,q):
    if not len(y):return None
    return {'n':len(y),'log_loss':float(loss(y,q).mean()),'brier':float(np.mean((q-y)**2))}
def spline(x,k):
    def d(z,j):return (np.maximum(z-k[j],0)**3-np.maximum(z-k[3],0)**3)/(k[3]-k[j])
    return np.column_stack((x,d(x,0)-d(x,2),d(x,1)-d(x,2)))
def arrays(rows):
    return np.array([z['y'] for z in rows],float),np.array([z['p'] for z in rows],float)
def day_weights(rows):
    counts=Counter(z['date'] for z in rows)
    return np.array([1/(len(counts)*counts[z['date']]) for z in rows],float)

class Design:
    def __init__(self,train):
        x=logit(clip(np.array([z['p'] for z in train],float)))
        self.knots=np.quantile(x,(.05,.35,.65,.95))
        for i in range(1,4):
            if self.knots[i]<=self.knots[i-1]:self.knots[i]=self.knots[i-1]+1e-6
        self.fields=('snapshot_age_ms','mid_change_30s','depth','imbalance')
        self.medians={}
        for field in self.fields:
            v=np.array([z.get(field) if z.get(field) is not None else np.nan for z in train],float)
            v=v[np.isfinite(v)]
            self.medians[field]=float(np.median(v)) if len(v) else 0.0
        w=day_weights(train);raw=self.raw(train)
        self.means={};self.scales={}
        for name,v in raw.items():
            mean=np.sum(v*w[:,None],axis=0)
            scale=np.sqrt(np.sum((v-mean)**2*w[:,None],axis=0));scale[scale<1e-9]=1
            self.means[name]=mean;self.scales[name]=scale
    def raw(self,rows):
        p=np.array([z['p'] for z in rows],float)
        x=logit(clip(p));cal=spline(x,self.knots)
        def filled(field):
            v=np.array([z.get(field) if z.get(field) is not None else np.nan for z in rows],float)
            return np.where(np.isfinite(v),v,self.medians[field])
        snap=np.array([z.get('depth') is not None for z in rows],float)
        history=np.array([z.get('mid_change_30s') is not None for z in rows],float)
        age=np.array([z['bbo_age_ms'] for z in rows],float)
        z=np.column_stack((age,filled('snapshot_age_ms'),snap,history))
        r1=np.column_stack((cal,z))
        r2=np.column_stack((r1,np.array([z['spread'] for z in rows],float),filled('mid_change_30s')))
        depth=np.log1p(np.maximum(filled('depth'),0))
        r3=np.column_stack((r2,depth,filled('imbalance')))
        return {'R1':r1,'R2':r2,'R3':r3}
    def transform(self,rows):
        return {k:(v-self.means[k])/self.scales[k] for k,v in self.raw(rows).items()}

def fit(X,y,p,weights,C):
    n=len(y);XX=np.column_stack((np.ones(n),X));offset=logit(clip(p));lam=1/(C*n)
    def objective(beta):
        eta=offset+XX@beta;prob=expit(eta)
        val=np.sum(weights*(np.logaddexp(0,eta)-y*eta))+.5*lam*np.sum(beta[1:]**2)
        grad=XX.T@(weights*(prob-y));grad[1:]+=lam*beta[1:]
        return val,grad
    result=minimize(objective,np.zeros(XX.shape[1]),method='L-BFGS-B',jac=True,
                    options={'maxiter':300,'ftol':1e-10})
    if not result.success and np.linalg.norm(result.jac)>1e-4:raise RuntimeError('offset logistic did not converge: '+str(result.message))
    return result.x

def predict(X,p,beta):
    XX=np.column_stack((np.ones(len(p)),X))
    return clip(expit(logit(clip(p))+XX@beta))

def distribution(q):
    return {'min':float(np.min(q)),'p01':float(np.quantile(q,.01)),'p99':float(np.quantile(q,.99)),'max':float(np.max(q))}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--private-dir',type=Path,required=True);parser.add_argument('--public-dir',type=Path,required=True)
    a=parser.parse_args();private=a.private_dir;public=a.public_dir;public.mkdir(parents=True,exist_ok=True)
    source=private/'events_before_labels_private.json';label_source=private/'ctf_labels_private.json'
    rows=json.loads(source.read_text());labels=json.loads(label_source.read_text())
    if len(rows)!=2016 or len(labels)!=2016 or [z['slot'] for z in rows]!=[z['slot'] for z in labels]:raise ValueError('event/label join mismatch')
    for row,lab in zip(rows,labels):
        row['y']=lab['y'] if lab['label_status']=='verified_binary' else None
        row['label_status']=lab['label_status']
    counts={};eligible={}
    for day in TRAIN+(CAL,)+FORWARD:
        group=[z for z in rows if z['date']==day]
        fitrows=[z for z in group if z['y'] is not None and z['p'] is not None and z['identity_status']=='gamma_verified']
        eligible[day]=fitrows
        counts[day]={'calendar_slots':len(group),'verified_binary_labels':sum(z['y'] is not None for z in group),
                     'price_and_label_eligible':len(fitrows),'class_0':sum(z['y']==0 for z in fitrows),
                     'class_1':sum(z['y']==1 for z in fitrows),'valid_quantity':sum(z['depth'] is not None for z in fitrows),
                     'history_available':sum(z['mid_change_30s'] is not None for z in fitrows)}
    train=[z for d in TRAIN for z in eligible[d]];cal=eligible[CAL];forward=[z for d in FORWARD for z in eligible[d]]
    gate={'train_at_least_400':len(train)>=400,'cal_at_least_100':len(cal)>=100,
          'each_forward_at_least_100':all(len(eligible[d])>=100 for d in FORWARD),
          'train_both_classes':{z['y'] for z in train}=={0,1},
          'cal_both_classes':{z['y'] for z in cal}=={0,1}}
    qty={'train':sum(z['depth'] is not None for z in train)/len(train) if train else 0.0}
    qty.update({d:sum(z['depth'] is not None for z in eligible[d])/len(eligible[d]) if eligible[d] else 0.0 for d in FORWARD})
    qty_ok=all(v>=.5 for v in qty.values())
    out={'cohort_counts':counts,'cohort_gate':gate,'quantity_coverage':qty,'quantity_gate_50pct':qty_ok,
         'private_event_table_sha256':sha(source),'private_ctf_labels_sha256':sha(label_source),
         'status':'INSUFFICIENT_COHORT' if not all(gate.values()) else 'MODEL_READY',
         'window_utc':'2026-07-27T00:00:00Z/2026-08-03T00:00:00Z','epsilon':EPS,
         'role':'RETROSPECTIVE_OFFLINE; three forward development dates, no independent final'}
    if not all(gate.values()):
        (public/'model_results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'status':out['status'],'cohort_gate':gate},sort_keys=True));return
    design=Design(train);train_m=design.transform(train);cal_m=design.transform(cal);forward_m=design.transform(forward)
    ytr,ptr=arrays(train);ycal,pcal=arrays(cal);yf,pf=arrays(forward);w=day_weights(train)
    arms=('R1','R2','R3') if qty_ok else ('R1','R2')
    pred={'R0':clip(pf)};models={}
    for arm in arms:
        options=[]
        for C in CS:
            beta=fit(train_m[arm],ytr,ptr,w,C)
            qc=predict(cal_m[arm],pcal,beta)
            options.append((float(loss(ycal,qc).mean()),C,beta))
        best=min(options,key=lambda z:(z[0],z[1]));pred[arm]=predict(forward_m[arm],pf,best[2])
        models[arm]={'selected_C':best[1],'calibration_candidates':[{'C':z[1],'log_loss':z[0]} for z in options],
                     'coefficients_private':best[2].tolist()}
    private_predictions=[];by_day={};index_by_day={d:np.array([z['date']==d for z in forward],bool) for d in FORWARD}
    for j,z in enumerate(forward):
        item={'slot':z['slot'],'date':z['date'],'y':z['y'],'p':z['p'],'bid':z['bid'],'ask':z['ask'],'spread':z['spread'],
              'snapshot_available':z['depth'] is not None,'predictions':{arm:float(q[j]) for arm,q in pred.items()}}
        if 'R3' in pred:item['gain_contribution']=float(loss(np.array([z['y']]),np.array([pred['R2'][j]]))[0]-loss(np.array([z['y']]),np.array([pred['R3'][j]]))[0])
        private_predictions.append(item)
    for day in FORWARD:
        mask=index_by_day[day];yd=yf[mask];qd={name:q[mask] for name,q in pred.items()}
        result={'n':len(yd),'arms':{name:score(yd,q) for name,q in qd.items()},
                'prediction_extremes':{name:distribution(q) for name,q in qd.items()}}
        if 'R3' in qd:
            gain=loss(yd,qd['R2'])-loss(yd,qd['R3'])
            result['R2_minus_R3_gain']={'mean_nats':float(gain.mean()),'positive_events':int((gain>0).sum()),
                 'negative_events':int((gain<0).sum()),'contribution_p01_p50_p99':[float(x) for x in np.quantile(gain,(.01,.5,.99))]}
            spread=np.array([z['spread'] for z in forward],float)[mask]
            bid=np.array([z['bid'] for z in forward],float)[mask];ask=np.array([z['ask'] for z in forward],float)[mask]
            delta=qd['R3']-qd['R2']
            result['nontrading_price_scale']={'median_abs_quantity_correction_over_spread':float(np.median(np.abs(delta)/spread)),
                'R2_below_bid_fraction':float(np.mean(qd['R2']<bid)),'R2_above_ask_fraction':float(np.mean(qd['R2']>ask)),
                'R3_below_bid_fraction':float(np.mean(qd['R3']<bid)),'R3_above_ask_fraction':float(np.mean(qd['R3']>ask))}
            complete=np.array([z['depth'] is not None for z in forward],bool)[mask]
            result['quantity_complete_subset']={'n':int(complete.sum()),'R2':score(yd[complete],qd['R2'][complete]),
                                                'R3':score(yd[complete],qd['R3'][complete])}
            result['quantity_missing_subset']={'n':int((~complete).sum()),'R2':score(yd[~complete],qd['R2'][~complete]),
                                               'R3':score(yd[~complete],qd['R3'][~complete])}
        by_day[day]=result
    out['models']={k:{kk:vv for kk,vv in v.items() if kk!='coefficients_private'} for k,v in models.items()}
    out['train_only_spline_knots_logit']=design.knots.tolist();out['train_only_medians']=design.medians
    out['forward_by_day']=by_day
    out['forward_all_event_equal']={name:score(yf,q) for name,q in pred.items()}
    out['forward_day_equal']={name:{metric:float(np.mean([by_day[d]['arms'][name][metric] for d in FORWARD]))
                                    for metric in ('log_loss','brier')} for name in pred}
    if 'R3' in pred:
        gains=[by_day[d]['R2_minus_R3_gain']['mean_nats'] for d in FORWARD]
        avg=float(np.mean(gains));r3=out['forward_day_equal']['R3'];r2=out['forward_day_equal']['R2']
        simple=min(out['forward_day_equal'][k]['log_loss'] for k in ('R0','R1'))
        decision={'gain_at_least_0_005':avg>=.005,'two_positive_days':sum(g>0 for g in gains)>=2,
                  'brier_not_worse':r3['brier']<=r2['brier'], 'R3_not_worse_than_best_simple':r3['log_loss']<=simple}
        out['primary']={'R2_minus_R3_gain_day_equal_nats':avg,'positive_days':sum(g>0 for g in gains),
                        'planning_checks':decision,'continue_to_new_confirmation_plan':all(decision.values())}
        out['status']='COMPLETED_MULTIDAY_DEVELOPMENT'
    else:
        out['status']='QUANTITY_COVERAGE_GATED';out['primary']='R3 not fit because prespecified valid-snapshot coverage gate failed'
    weights_path=private/'models_private.json';weights_path.write_text(json.dumps({k:v for k,v in models.items()},separators=(',',':'))+'\n');os.chmod(weights_path,0o600)
    predictions_path=private/'predictions_private.json';predictions_path.write_text(json.dumps(private_predictions,separators=(',',':'))+'\n');os.chmod(predictions_path,0o600)
    out['private_models_sha256']=sha(weights_path);out['private_predictions_sha256']=sha(predictions_path)
    (public/'model_results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':out['status'],'cohort_gate':gate,'quantity_gate':qty_ok,'primary':out.get('primary')},sort_keys=True))
if __name__=='__main__':main()
