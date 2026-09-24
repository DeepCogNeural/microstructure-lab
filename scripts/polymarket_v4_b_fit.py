"""Frozen event-level B0/B1/B2/B3 offset-logistic development comparison."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit,logit
EPS=1e-6; CS=(0.1,1.0,10.0)
FIELDS=('depth','imbalance','snapshot_age_ms','mid_change_30s','imbalance_change_30s')

def clip(p):return np.clip(p,EPS,1-EPS)
def losses(y,p):
 p=clip(p);return -(y*np.log(p)+(1-y)*np.log1p(-p))
def summary(y,p):
 l=losses(y,p);return {'n':len(y),'log_loss':float(l.mean()),'brier':float(np.mean((p-y)**2))}
def spline(x,knots):
 k=knots
 def d(z,j):return (np.maximum(z-k[j],0)**3-np.maximum(z-k[3],0)**3)/(k[3]-k[j])
 return np.column_stack([x,d(x,0)-d(x,2),d(x,1)-d(x,2)])
class Design:
 def __init__(self,train):
  x=logit(clip(np.array([z['p'] for z in train])))
  self.knots=np.quantile(x,[.05,.35,.65,.95]);
  for i in range(1,4):
   if self.knots[i]<=self.knots[i-1]:self.knots[i]=self.knots[i-1]+1e-6
  self.medians={};
  for f in FIELDS:
   v=np.array([z.get(f) if z.get(f) is not None else np.nan for z in train],float);finite=v[np.isfinite(v)];self.medians[f]=float(np.median(finite)) if len(finite) else 0.0
  self.medians['bbo_age_ms']=float(np.median([z['bbo_age_ms'] for z in train]))
  raw=self.raw(train);self.means={};self.scales={}
  for k,v in raw.items():
   self.means[k]=np.mean(v,axis=0);self.scales[k]=np.std(v,axis=0);self.scales[k][self.scales[k]<1e-9]=1
 def raw(self,rows):
  x=logit(clip(np.array([z['p'] for z in rows])))
  sp=spline(x,self.knots);age=np.array([z['bbo_age_ms'] for z in rows],float)
  vals={f:np.array([z.get(f) if z.get(f) is not None else np.nan for z in rows],float) for f in FIELDS}
  miss={f:(~np.isfinite(v)).astype(float) for f,v in vals.items()}
  fill={f:np.where(np.isfinite(v),v,self.medians[f]) for f,v in vals.items()}
  z=np.column_stack([age,fill['snapshot_age_ms'],*[miss[f] for f in FIELDS]])
  b1=np.column_stack([sp,z]);b2=np.column_stack([b1,[z['spread'] for z in rows],np.log1p(np.maximum(fill['depth'],0)),fill['imbalance']]);b3=np.column_stack([b2,fill['mid_change_30s'],fill['imbalance_change_30s']])
  return {'B1':b1,'B2':b2,'B3':b3}
 def matrices(self,rows):
  raw=self.raw(rows);return {k:(v-self.means[k])/self.scales[k] for k,v in raw.items()}

def fit(X,y,p,C):
 n=len(y);offset=logit(clip(p));XX=np.column_stack([np.ones(n),X]);lam=1/(C*n)
 def f(w):
  eta=offset+XX@w;pr=expit(eta);loss=np.mean(np.logaddexp(0,eta)-y*eta)+.5*lam*np.sum(w[1:]**2)
  grad=XX.T@(pr-y)/n;grad[1:]+=lam*w[1:];return loss,grad
 opt=minimize(f,np.zeros(XX.shape[1]),method='L-BFGS-B',jac=True,options={'maxiter':300,'ftol':1e-10})
 if not opt.success and np.linalg.norm(opt.jac)>1e-4:raise RuntimeError('logistic did not converge: '+opt.message)
 return opt.x

def predict(X,p,w):return clip(expit(logit(clip(p))+np.column_stack([np.ones(len(p)),X])@w))
def selected(rows,a,b):return [x for x in rows[a:b] if x['p'] is not None and x['y'] is not None]
def eval_split(rows,name,fracs):
 N=len(rows);lo,trainend,calend,scoreend=[int(z*N) for z in fracs]
 train=selected(rows,lo,trainend);cal=selected(rows,trainend,calend);test=selected(rows,calend,scoreend)
 counts={'candidate_train':trainend-lo,'candidate_calibration':calend-trainend,'candidate_scored':scoreend-calend,'eligible_train':len(train),'eligible_calibration':len(cal),'eligible_scored':len(test),'train_class_0':sum(x['y']==0 for x in train),'train_class_1':sum(x['y']==1 for x in train)}
 if min(counts['train_class_0'],counts['train_class_1'])<10 or len(test)<20 or not cal:return {'status':'INSUFFICIENT_FOR_LEARNED_ARMS','counts':counts},None
 design=Design(train);mat={s:design.matrices(v) for s,v in [('train',train),('cal',cal),('test',test)]}
 yy={s:np.array([z['y'] for z in v],float) for s,v in [('train',train),('cal',cal),('test',test)]};pp={s:np.array([z['p'] for z in v],float) for s,v in [('train',train),('cal',cal),('test',test)]}
 predictions={'B0':pp['test']};arms={'B0':{'selected_C':None,'calibration_candidates':None,'late':summary(yy['test'],pp['test'])}}
 for arm in ('B1','B2','B3'):
  cand=[]
  for C in CS:
   w=fit(mat['train'][arm],yy['train'],pp['train'],C);pc=predict(mat['cal'][arm],pp['cal'],w)
   cand.append((float(losses(yy['cal'],pc).mean()),C,w))
  best=min(cand,key=lambda t:(t[0],t[1]));q=predict(mat['test'][arm],pp['test'],best[2]);predictions[arm]=q
  arms[arm]={'selected_C':best[1],'calibration_candidates':[{ 'C':z[1],'log_loss':z[0]} for z in cand],'late':summary(yy['test'],q)}
 comparisons={}
 for a,b in [('B1','B0'),('B2','B1'),('B3','B2')]:
  dif=losses(yy['test'],predictions[a])-losses(yy['test'],predictions[b]);block=np.array_split(dif,4)
  comparisons[a+'_minus_'+b]={'mean_log_loss_difference':float(dif.mean()),'mean_brier_difference':float(np.mean((predictions[a]-yy['test'])**2-(predictions[b]-yy['test'])**2)),'paired_quartile_means':[float(x.mean()) for x in block if len(x)],'positive_event_count':int((dif>0).sum()),'negative_event_count':int((dif<0).sum())}
 complete=np.array([all(z.get(f) is not None for f in FIELDS) for z in test]);intersection={}
 for arm in ('B0','B1','B2','B3'):intersection[arm]=summary(yy['test'][complete],predictions[arm][complete]) if complete.any() else None
 bid=np.array([z['bid'] for z in test]);ask=np.array([z['ask'] for z in test]);q=predictions['B2'];gap={'q_below_bid_fraction':float(np.mean(q<bid)),'q_above_ask_fraction':float(np.mean(q>ask)),'median_q_minus_mid':float(np.median(q-pp['test']))}
 public={'status':'DONE','counts':counts,'arms':arms,'comparisons':comparisons,'complete_feature_intersection_n':int(complete.sum()),'complete_feature_intersection':intersection,'B2_quote_gap':gap,'train_only_spline_knots_logit':design.knots.tolist(),'epsilon':EPS}
 priv={'split':name,'indices':[z['candidate_index'] for z in test],'y':yy['test'].astype(int).tolist(),'predictions':{k:v.tolist() for k,v in predictions.items()}}
 return public,priv

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();r=a.root
 rows=json.loads((r/'_private/prediction_market_v4_development/b_event_table_private.json').read_text());N=len(rows)
 assert N==288 and [x['candidate_index'] for x in rows]==list(range(N))
 out={'status':'DEVELOPMENT_PRICING_REPLICATION / WITHIN_DAY_RETROSPECTIVE','primary_comparison':'B2 minus B1 late event-equal log loss','source_event_table_sha256':hashlib.sha256((r/'_private/prediction_market_v4_development/b_event_table_private.json').read_bytes()).hexdigest(),'splits':{},'interpretation_boundary':'one exposed day; onchain payout verified, label publication time unknown; no trading or fresh final'};priv=[]
 for name,fracs in [('primary',(0,.5,.75,1)),('forward_1',(0,.4,.5,.6)),('forward_2',(0,.5,.6,.75)),('forward_3',(0,.6,.75,1))]:
  result,receipt=eval_split(rows,name,fracs);out['splits'][name]=result
  if receipt:priv.append(receipt)
 private=r/'_private/prediction_market_v4_development/b_predictions_private.json';private.write_text(json.dumps(priv,separators=(',',':'))+'\n');out['private_predictions_sha256']=hashlib.sha256(private.read_bytes()).hexdigest()
 public=r/'results/prediction_market_v4_development/b_scoring.json';public.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'primary':out['splits']['primary']['comparisons'] if out['splits']['primary']['status']=='DONE' else out['splits']['primary'],'forward':[out['splits'][k]['status'] for k in ('forward_1','forward_2','forward_3')]},sort_keys=True))
if __name__=='__main__':main()
