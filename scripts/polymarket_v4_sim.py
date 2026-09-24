"""Known-truth synthetic B0/B1/B2 protocol power check; no market outcome reuse."""
from __future__ import annotations
import argparse,concurrent.futures,copy,hashlib,json,os,resource,time
from pathlib import Path
import numpy as np
from scipy.special import expit,logit
from polymarket_v4_b_fit import Design,fit,predict,losses,clip,CS
MECHS=((0.,1.,0.),(.2,.8,0.),(.2,.8,.25),(.2,.8,.25))
MULTS=(1,4,16);SEEDS=range(100);THRESHOLDS=(0.,.005,.01)

def one_seed(source,mult,mech,seed):
 rng=np.random.default_rng(seed+100000*mult+1000000*mech);n=len(source)*mult
 ix=rng.integers(0,len(source),size=n);rows=[dict(source[i]) for i in ix];trainend=n//2;calend=3*n//4
 raw=np.array([z['imbalance'] if z.get('imbalance') is not None else np.nan for z in rows]);training=raw[:trainend];finite=training[np.isfinite(training)]
 med=float(np.median(finite)) if len(finite) else 0.;z=np.where(np.isfinite(raw),raw,med);scale=float(np.std(z[:trainend]));scale=scale if scale>1e-9 else 1.;z=(z-float(np.mean(z[:trainend])))/scale
 a,b,beta=MECHS[mech];p=np.array([x['p'] for x in rows]);betas=np.full(n,beta)
 if mech==3:betas[calend:]=-beta
 q=expit(a+b*logit(clip(p))+betas*z);y=rng.binomial(1,q)
 for j,row in enumerate(rows):row['y']=int(y[j]);row['candidate_index']=j
 train=rows[:trainend];cal=rows[trainend:calend];test=rows[calend:]
 if min(int(y[:trainend].sum()),int(trainend-y[:trainend].sum()))<10:return {'status':'class_insufficient'}
 d=Design(train);xx={name:d.matrices(rr) for name,rr in [('train',train),('cal',cal),('test',test)]};yy={name:np.array([r['y'] for r in rr]) for name,rr in [('train',train),('cal',cal),('test',test)]};pp={name:np.array([r['p'] for r in rr]) for name,rr in [('train',train),('cal',cal),('test',test)]}
 pred={'B0':pp['test']};chosen={}
 for arm in ('B1','B2'):
  candidates=[]
  for C in CS:
   w=fit(xx['train'][arm],yy['train'],pp['train'],C)
   candidates.append((float(losses(yy['cal'],predict(xx['cal'][arm],pp['cal'],w)).mean()),C,w))
  best=min(candidates,key=lambda x:(x[0],x[1]));chosen[arm]=best[1];pred[arm]=predict(xx['test'][arm],pp['test'],best[2])
 score={k:float(losses(yy['test'],v).mean()) for k,v in pred.items()};oracle=float(losses(yy['test'],q[calend:]).mean())
 return {'status':'DONE','B0':score['B0'],'B1':score['B1'],'B2':score['B2'],'oracle':oracle,'B1_minus_B0':score['B1']-score['B0'],'B2_minus_B1':score['B2']-score['B1'],'selected_C':chosen}

def run_cell(source,mult,mech):
 started=time.monotonic();results=[one_seed(source,mult,mech,seed) for seed in SEEDS];usage=resource.getrusage(resource.RUSAGE_SELF)
 return {'multiplier':mult,'mechanism':mech,'results':results,'wall_seconds':time.monotonic()-started,'worker_user_cpu_seconds':usage.ru_utime,'worker_system_cpu_seconds':usage.ru_stime,'worker_peak_rss_raw':usage.ru_maxrss}

def public_cell(cell,n):
 done=[x for x in cell['results'] if x['status']=='DONE'];diff=np.array([x['B2_minus_B1'] for x in done]);cal=np.array([x['B1_minus_B0'] for x in done]);
 return {'mechanism':cell['mechanism'],'n':n*cell['multiplier'],'seeds_attempted':len(cell['results']),'seeds_done':len(done),'class_insufficient':len(cell['results'])-len(done),'B2_minus_B1_mean':float(diff.mean()) if len(diff) else None,'B2_minus_B1_median':float(np.median(diff)) if len(diff) else None,'B2_minus_B1_q10_q90':np.quantile(diff,[.1,.9]).tolist() if len(diff) else None,'B1_minus_B0_mean':float(cal.mean()) if len(cal) else None,'rich_model_selected_fraction_by_threshold':{str(t):float(np.mean(diff< -t)) if len(diff) else None for t in THRESHOLDS},'rich_model_harmed_fraction':float(np.mean(diff>0)) if len(diff) else None,'wall_seconds':cell['wall_seconds'],'worker_cpu_seconds':cell['worker_user_cpu_seconds']+cell['worker_system_cpu_seconds'],'worker_peak_rss_raw':cell['worker_peak_rss_raw']}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args();r=a.root
 if not 1<=a.workers<=8:raise ValueError('worker limit')
 inputp=r/'_private/prediction_market_v4_development/b_event_table_private.json';source=[x for x in json.loads(inputp.read_text()) if x['p'] is not None and x['y'] is not None]
 if len(source)!=254:raise ValueError('unexpected n')
 started=time.monotonic();cells=[];private=r/'_private/prediction_market_v4_development/sim_cells_private';private.mkdir(parents=True,exist_ok=True)
 with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
  futures={(mult,mech):pool.submit(run_cell,source,mult,mech) for mult in MULTS for mech in range(4)}
  for mult,mech in ((mult,mech) for mult in MULTS for mech in range(4)):
   cell=futures[(mult,mech)].result();cells.append(public_cell(cell,len(source)))
   (private/f'n{mult}_m{mech}.json').write_text(json.dumps(cell,separators=(',',':'))+'\n')
   print(json.dumps({'n':mult*len(source),'mechanism':mech,'done':cells[-1]['seeds_done'],'wall':round(cell['wall_seconds'],2)}),flush=True)
 public={'status':'SYNTHETIC_KNOWN_TRUTH_COMPLETE','base_n':len(source),'mechanisms':{'0':'logit(q)=logit(p)','1':'0.2+0.8 logit(p)','2':'0.2+0.8 logit(p)+0.25 z','3':'same as 2 until late score, then -0.25 z'},'z':'train-standardized current snapshot imbalance; missing values train-median-imputed','resampling':'iid with replacement from one exposed Sep 8 day; repeated rows are not independent new dates','seed_rule':'seed+100000*multiplier+1000000*mechanism, seeds 0..99','thresholds_nats':THRESHOLDS,'cells':cells,'total_simulated_datasets':sum(x['seeds_attempted'] for x in cells),'wall_seconds':time.monotonic()-started,'allocated_cpu_core_hours_upper_bound':a.workers*(time.monotonic()-started)/3600,'workers':a.workers,'input_event_table_sha256':hashlib.sha256(inputp.read_bytes()).hexdigest(),'limitations':'conditional on the chosen generator and same-day feature distribution; does not infer real market alpha or across-day power'}
 out=r/'results/prediction_market_v4_development/simulation.json';out.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n');print(json.dumps({'complete':len(cells),'wall_seconds':public['wall_seconds'],'core_hours_upper':public['allocated_cpu_core_hours_upper_bound']}))
if __name__=='__main__':main()
