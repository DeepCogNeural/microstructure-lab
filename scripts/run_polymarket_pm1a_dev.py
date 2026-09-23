"""Frozen PM1A train/dev study; save models/predictions privately, aggregate scores publicly."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
import torch
from xgboost import XGBClassifier

from cloblab.polymarket_models import HistoryGRU, market_equal_weights, market_scores, market_paired_bootstrap


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def arrays(path: Path) -> dict:
    with np.load(path,allow_pickle=False) as data:
        out = {key:data[key].copy() for key in data.files}
    n = len(out['label'])
    if any(len(out[key]) != n for key in ('history','probability','market','decision_utc')):
        raise ValueError('PM1A array identity lengths differ')
    if out['history'].shape[1:] != (8,11):
        raise ValueError('PM1A history shape differs from frozen protocol')
    return out


def xgb(settings: dict) -> XGBClassifier:
    return XGBClassifier(objective='binary:logistic', eval_metric='logloss',
                         n_estimators=settings['n_estimators'],max_depth=settings['max_depth'],
                         learning_rate=settings['learning_rate'],
                         min_child_weight=settings['min_child_weight'],
                         subsample=settings['subsample'],colsample_bytree=settings['colsample_bytree'],
                         reg_lambda=settings['reg_lambda'],n_jobs=settings['n_jobs'],
                         random_state=settings['random_state'],tree_method='hist')


def gru_predict(model: HistoryGRU, values: np.ndarray, mu: np.ndarray,
                sd: np.ndarray, batch_size: int) -> np.ndarray:
    model.eval()
    chunks = []
    with torch.inference_mode():
        for start in range(0,len(values),batch_size):
            x = torch.from_numpy(((values[start:start+batch_size]-mu)/sd).astype(np.float32))
            chunks.append(torch.sigmoid(model(x)).numpy())
    return np.concatenate(chunks)


def fit_gru(seed: int, train: dict, dev: dict, cfg: dict, private: Path,
            clip: float) -> tuple[np.ndarray,dict]:
    torch.set_num_threads(4)
    torch.manual_seed(seed)
    np.random.seed(seed)
    params = cfg['P4']
    xtr = train['history']
    xdv = dev['history']
    mu = xtr.mean(axis=(0,1),keepdims=True)
    sd = xtr.std(axis=(0,1),keepdims=True).clip(min=1e-6)
    xt = torch.from_numpy(((xtr-mu)/sd).astype(np.float32))
    yt = torch.from_numpy(train['label'].astype(np.float32))
    wt = torch.from_numpy(market_equal_weights(train['market']).astype(np.float32))
    model = HistoryGRU(11,params['hidden_size'])
    optimizer = torch.optim.AdamW(model.parameters(),lr=params['learning_rate'],
                                  weight_decay=params['weight_decay'])
    best_loss,best_state,patience = float('inf'),None,0
    curve=[]
    began=time.monotonic()
    for epoch in range(params['max_epochs']):
        model.train()
        order = torch.randperm(len(yt),generator=torch.Generator().manual_seed(seed+epoch))
        weighted_loss,total_weight=0.0,0.0
        for ids in order.split(params['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            logits=model(xt[ids])
            losses=torch.nn.functional.binary_cross_entropy_with_logits(logits,yt[ids],reduction='none')
            loss=(losses*wt[ids]).sum()/wt[ids].sum()
            if not torch.isfinite(loss).item():
                raise ValueError(f'nonfinite PM1A GRU loss at epoch {epoch+1}')
            loss.backward();optimizer.step()
            weighted_loss += float((losses.detach()*wt[ids]).sum().item())
            total_weight += float(wt[ids].sum().item())
        prediction=gru_predict(model,xdv,mu,sd,params['batch_size'])
        score=market_scores(dev['label'],prediction,dev['market'],clip)
        dev_loss=score['market_mean_log_loss']
        curve.append({'epoch':epoch+1,'train_weighted_log_loss':weighted_loss/total_weight,
                      'dev_market_log_loss':dev_loss})
        if dev_loss < best_loss - 1e-5:
            best_loss=dev_loss
            best_state={name:value.detach().clone() for name,value in model.state_dict().items()}
            patience=0
        else:
            patience += 1
        if patience >= params['patience']:
            break
    fit_seconds=time.monotonic()-began
    if best_state is None:
        raise ValueError('no GRU dev checkpoint')
    model.load_state_dict(best_state)
    path=private/f'P4_gru_seed{seed}.pt'
    torch.save({'state':best_state,'mu':mu,'sd':sd,'hidden_size':params['hidden_size']},path)
    began=time.monotonic()
    prediction=gru_predict(model,xdv,mu,sd,params['batch_size'])
    inference_seconds=time.monotonic()-began
    best_epoch=int(np.argmin([r['dev_market_log_loss'] for r in curve])+1)
    return prediction,{'fit_seconds':fit_seconds,'inference_seconds':inference_seconds,
                       'epochs_run':len(curve),'best_epoch':best_epoch,
                       'training_limited':len(curve)==params['max_epochs'] and best_epoch==len(curve),
                       'learning_curve':curve,'model_sha256':sha(path),
                       'trainable_parameters':sum(p.numel() for p in model.parameters())}


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--train',type=Path,required=True)
    ap.add_argument('--dev',type=Path,required=True)
    ap.add_argument('--build-manifest',type=Path,required=True)
    ap.add_argument('--private',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.private.exists() or args.out.exists():
        raise ValueError('preserve existing PM1A dev attempt')
    began=time.monotonic()
    model_path=Path('configs/polymarket_pm1a_model_v1.json')
    cfg=json.loads(model_path.read_text())
    build=json.loads(args.build_manifest.read_text())
    if build['model_config_sha256']!=sha(model_path):
        raise ValueError('PM1A build/model config mismatch')
    for group,path in (('train',args.train),('dev',args.dev)):
        if sha(path)!=build['splits'][group]['private_npz_sha256']:
            raise ValueError(f'private {group} array changed')
    train,dev=arrays(args.train),arrays(args.dev)
    if set(train['market']) & set(dev['market']):
        raise ValueError('market leakage across train/dev')
    args.private.mkdir(parents=True)
    clip=cfg['probability_clip']
    predictions={'P0_raw_midpoint':dev['probability'].astype(float)}
    costs={'P0_raw_midpoint':{'fit_seconds':0.0,'inference_seconds':0.0}}
    weights=market_equal_weights(train['market'])
    # P1 uses only current implied probability and prespecified time-to-close.
    x1tr=train['history'][:,-1][:,[0,9]]
    x1dv=dev['history'][:,-1][:,[0,9]]
    p1=LogisticRegression(C=cfg['P1']['C'],solver=cfg['P1']['solver'],max_iter=cfg['P1']['max_iter'])
    tick=time.monotonic();p1.fit(x1tr,train['label'],sample_weight=weights)
    fit=time.monotonic()-tick;tick=time.monotonic()
    predictions['P1_calibration']=p1.predict_proba(x1dv)[:,1]
    costs['P1_calibration']={'fit_seconds':fit,'inference_seconds':time.monotonic()-tick}
    joblib.dump(p1,args.private/'P1_calibration.joblib')
    costs['P1_calibration']['model_sha256']=sha(args.private/'P1_calibration.joblib')
    for arm,xtr,xdv,settings in (
        ('P2_current_state',train['history'][:,-1,:10],dev['history'][:,-1,:10],cfg['P2']),
        ('P3_history',train['history'].reshape(len(train['label']),-1),
                      dev['history'].reshape(len(dev['label']),-1),cfg['P3'])):
        model=xgb(settings)
        tick=time.monotonic();model.fit(xtr,train['label'],sample_weight=weights)
        fit=time.monotonic()-tick;tick=time.monotonic()
        predictions[arm]=model.predict_proba(xdv)[:,1]
        costs[arm]={'fit_seconds':fit,'inference_seconds':time.monotonic()-tick}
        path=args.private/f'{arm}.joblib';joblib.dump(model,path)
        costs[arm]['model_sha256']=sha(path)
    for seed in cfg['P4']['seeds']:
        arm=f'P4_gru_seed{seed}'
        predictions[arm],costs[arm]=fit_gru(seed,train,dev,cfg,args.private,clip)
        print(json.dumps({'arm':arm,'fit_seconds':costs[arm]['fit_seconds'],
                          'epochs_run':costs[arm]['epochs_run']}),flush=True)
    scores={arm:market_scores(dev['label'],pred,dev['market'],clip)
            for arm,pred in predictions.items()}
    seed_names=[f'P4_gru_seed{seed}' for seed in cfg['P4']['seeds']]
    predictions['P4_seed_mean']=np.mean([predictions[arm] for arm in seed_names],axis=0)
    scores['P4_seed_mean']=market_scores(dev['label'],predictions['P4_seed_mean'],dev['market'],clip)
    paired={arm:market_paired_bootstrap(scores['P0_raw_midpoint']['_market_log_loss'],
                                        scores[arm]['_market_log_loss'],seed=20260923)
            for arm in scores if arm!='P0_raw_midpoint'}
    paired['P4_seed_mean_minus_P3']=market_paired_bootstrap(scores['P3_history']['_market_log_loss'],
                                                            scores['P4_seed_mean']['_market_log_loss'],seed=20260924)
    # Per-market vectors and row predictions are private; public summary keeps only aggregate metrics.
    for arm in scores:
        scores[arm].pop('_market_log_loss');scores[arm].pop('_market_brier')
    pred_path=args.private/'dev_predictions.npz'
    np.savez_compressed(pred_path,market=dev['market'],label=dev['label'],
                        **{arm:pred for arm,pred in predictions.items()})
    report={'stage':'PM1A','status':'DEV_ONLY_FINAL_CLOSED','model_config_sha256':sha(model_path),
            'build_manifest_sha256':sha(args.build_manifest),
            'train_private_sha256':sha(args.train),'dev_private_sha256':sha(args.dev),
            'train_markets':len(set(train['market'])),'train_opportunities':len(train['label']),
            'dev_markets':len(set(dev['market'])),'dev_opportunities':len(dev['label']),
            'scores':scores,'paired_log_loss':paired,'costs':costs,
            'dev_predictions_private_sha256':sha(pred_path),
            'wall_seconds':time.monotonic()-began,
            'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
            'limits':'One dev UTC date; market bootstrap is conditional on this sampled source/date. Final outcomes remain unopened for model scoring; no independent confirmation or PnL claim.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'dev_markets':report['dev_markets'],
                      'dev_scores':{k:v['market_mean_log_loss'] for k,v in scores.items()}}))


if __name__=='__main__':main()
