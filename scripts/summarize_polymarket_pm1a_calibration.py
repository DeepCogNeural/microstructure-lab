"""Prespecified secondary calibration diagnostics from frozen PM1A final models."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
import torch

from cloblab.polymarket_models import HistoryGRU, market_equal_weights, market_scores
from run_polymarket_pm1a_dev import arrays, gru_predict


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def predictions(final: dict, dev: dict, models: Path, cfg: dict) -> dict:
    out={'P0_raw_midpoint':final['probability'].astype(float)}
    for arm in ('P1_calibration','P2_current_state','P3_history'):
        path=models/f'{arm}.joblib'
        if sha(path)!=dev['costs'][arm]['model_sha256']:raise ValueError(f'changed model {arm}')
        model=joblib.load(path)
        if arm=='P1_calibration':x=final['history'][:,-1][:,[0,9]]
        elif arm=='P2_current_state':x=final['history'][:,-1,:10]
        else:x=final['history'].reshape(len(final['label']),-1)
        out[arm]=model.predict_proba(x)[:,1]
    for seed in cfg['P4']['seeds']:
        arm=f'P4_gru_seed{seed}';path=models/f'{arm}.pt'
        if sha(path)!=dev['costs'][arm]['model_sha256']:raise ValueError(f'changed model {arm}')
        state=torch.load(path,map_location='cpu',weights_only=False)
        model=HistoryGRU(11,state['hidden_size']);model.load_state_dict(state['state'])
        out[arm]=gru_predict(model,final['history'],state['mu'],state['sd'],cfg['P4']['batch_size'])
    out['P4_seed_mean']=np.mean([out[f'P4_gru_seed{seed}'] for seed in cfg['P4']['seeds']],axis=0)
    return out


def calibration(y: np.ndarray,p: np.ndarray,market: np.ndarray,clip: float) -> dict:
    p=np.clip(p.astype(float),clip,1-clip)
    weights=market_equal_weights(market)
    logit=np.log(p/(1-p)).reshape(-1,1)
    logistic=LogisticRegression(penalty=None,solver='lbfgs',max_iter=1000)
    logistic.fit(logit,y,sample_weight=weights)
    bins=[]
    ece=0.0
    for i in range(10):
        lo,hi=i/10,(i+1)/10
        mask=(p>=lo)&(p<hi if i<9 else p<=hi)
        if not mask.any():
            bins.append({'lo':lo,'hi':hi,'opportunities':0,'market_weight_fraction':0.0,
                         'mean_predicted':None,'mean_outcome':None})
            continue
        w=weights[mask];mass=float(w.sum()/weights.sum())
        mp=float(np.average(p[mask],weights=w));my=float(np.average(y[mask],weights=w))
        ece += mass*abs(mp-my)
        bins.append({'lo':lo,'hi':hi,'opportunities':int(mask.sum()),
                     'market_weight_fraction':mass,'mean_predicted':mp,'mean_outcome':my})
    return {'calibration_intercept_descriptive':float(logistic.intercept_[0]),
            'calibration_slope_descriptive':float(logistic.coef_[0,0]),
            'market_weighted_ece_10bins':ece,'reliability_10bins':bins}


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--final',type=Path,required=True)
    ap.add_argument('--dev-report',type=Path,required=True)
    ap.add_argument('--final-result',type=Path,required=True)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--private-market-scores',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists() or args.private_market_scores.exists():raise ValueError('preserve existing diagnostics')
    cfg_path=Path('configs/polymarket_pm1a_model_v1.json')
    cfg=json.loads(cfg_path.read_text());dev=json.loads(args.dev_report.read_text())
    primary=json.loads(args.final_result.read_text())
    if primary['status']!='FINAL_SCORED_ONCE' or primary['final_private_npz_sha256']!=sha(args.final):
        raise ValueError('primary final identity mismatch')
    if primary['model_config_sha256']!=sha(cfg_path) or dev['model_config_sha256']!=sha(cfg_path):
        raise ValueError('protocol changed')
    final=arrays(args.final)
    preds=predictions(final,dev,args.models,cfg)
    scores={arm:market_scores(final['label'],pred,final['market'],cfg['probability_clip'])
            for arm,pred in preds.items()}
    for arm,score in scores.items():
        if abs(score['market_mean_log_loss']-primary['scores'][arm]['market_mean_log_loss'])>1e-10:
            raise ValueError(f'primary result changed: {arm}')
    secondary={arm:calibration(final['label'],pred,final['market'],cfg['probability_clip'])
               for arm,pred in preds.items()}
    private={arm:{'market_log_loss':scores[arm]['_market_log_loss'],
                  'market_brier':scores[arm]['_market_brier']} for arm in scores}
    args.private_market_scores.parent.mkdir(parents=True,exist_ok=True)
    args.private_market_scores.write_text(json.dumps(private,indent=2,sort_keys=True)+'\n')
    report={'stage':'PM1A','kind':'post_primary_prespecified_secondary_calibration',
            'primary_final_sha256':sha(args.final_result),
            'model_config_sha256':sha(cfg_path),'dev_report_sha256':sha(args.dev_report),
            'final_private_npz_sha256':sha(args.final),
            'final_markets':primary['final_markets'],'final_opportunities':primary['final_opportunities'],
            'calibration':secondary,'private_market_scores_sha256':sha(args.private_market_scores),
            'limits':'Descriptive slope/intercept fitted on final labels only for diagnosis, never used to alter/rescore the frozen models. One partial UTC date; reliability bins are highly dependent snapshots and are market weighted.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'complete','arms':len(secondary),'markets':primary['final_markets']}))


if __name__=='__main__':main()
