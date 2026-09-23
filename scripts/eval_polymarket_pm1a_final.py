"""One-time frozen PM1A final scoring from private fitted train/dev models."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import torch

from cloblab.polymarket_models import HistoryGRU, market_scores, market_paired_bootstrap
from run_polymarket_pm1a_dev import arrays, gru_predict


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--final',type=Path,required=True)
    ap.add_argument('--final-build-manifest',type=Path,required=True)
    ap.add_argument('--train',type=Path,required=True)
    ap.add_argument('--dev',type=Path,required=True)
    ap.add_argument('--dev-report',type=Path,required=True)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists():raise ValueError('preserve original final result')
    cfg_path=Path('configs/polymarket_pm1a_model_v1.json')
    cfg=json.loads(cfg_path.read_text())
    dev_report=json.loads(args.dev_report.read_text())
    build=json.loads(args.final_build_manifest.read_text())
    if dev_report['status']!='DEV_ONLY_FINAL_CLOSED' or dev_report['model_config_sha256']!=sha(cfg_path):
        raise ValueError('dev fit/protocol mismatch')
    if build['model_config_sha256']!=sha(cfg_path) or build['split_manifest_sha256']!=cfg['split_manifest_sha256']:
        raise ValueError('final build/protocol mismatch')
    if sha(args.final)!=build['splits']['final']['private_npz_sha256']:
        raise ValueError('final array identity mismatch')
    if sha(args.train)!=dev_report['train_private_sha256'] or sha(args.dev)!=dev_report['dev_private_sha256']:
        raise ValueError('train/dev fit input identity mismatch')
    final,train,dev=arrays(args.final),arrays(args.train),arrays(args.dev)
    if set(final['market']) & (set(train['market']) | set(dev['market'])):
        raise ValueError('final market overlaps train/dev')
    started=time.monotonic()
    predictions={'P0_raw_midpoint':final['probability'].astype(float)}
    for arm in ('P1_calibration','P2_current_state','P3_history'):
        path=args.models/f'{arm}.joblib'
        if sha(path)!=dev_report['costs'][arm]['model_sha256']:
            raise ValueError(f'fitted model hash differs: {arm}')
        model=joblib.load(path)
        if arm=='P1_calibration':x=final['history'][:,-1][:,[0,9]]
        elif arm=='P2_current_state':x=final['history'][:,-1,:10]
        else:x=final['history'].reshape(len(final['label']),-1)
        predictions[arm]=model.predict_proba(x)[:,1]
    for seed in cfg['P4']['seeds']:
        arm=f'P4_gru_seed{seed}'
        path=args.models/f'{arm}.pt'
        if sha(path)!=dev_report['costs'][arm]['model_sha256']:
            raise ValueError(f'fitted GRU hash differs: {arm}')
        stored=torch.load(path,map_location='cpu',weights_only=False)
        model=HistoryGRU(11,stored['hidden_size'])
        model.load_state_dict(stored['state'])
        predictions[arm]=gru_predict(model,final['history'],stored['mu'],stored['sd'],cfg['P4']['batch_size'])
    seed_names=[f'P4_gru_seed{seed}' for seed in cfg['P4']['seeds']]
    predictions['P4_seed_mean']=np.mean([predictions[name] for name in seed_names],axis=0)
    clip=cfg['probability_clip']
    scores={arm:market_scores(final['label'],pred,final['market'],clip)
            for arm,pred in predictions.items()}
    paired={arm:market_paired_bootstrap(scores['P0_raw_midpoint']['_market_log_loss'],
                                        scores[arm]['_market_log_loss'],seed=20260925)
            for arm in scores if arm!='P0_raw_midpoint'}
    paired['P4_seed_mean_minus_P3']=market_paired_bootstrap(scores['P3_history']['_market_log_loss'],
                                                            scores['P4_seed_mean']['_market_log_loss'],seed=20260926)
    for arm in scores:
        scores[arm].pop('_market_log_loss');scores[arm].pop('_market_brier')
    report={'stage':'PM1A','status':'FINAL_SCORED_ONCE','retrospective_external_domain_pilot':True,
            'model_config_sha256':sha(cfg_path),'dev_report_sha256':sha(args.dev_report),
            'final_build_manifest_sha256':sha(args.final_build_manifest),
            'final_private_npz_sha256':sha(args.final),
            'final_markets':len(set(final['market'])),'final_opportunities':len(final['label']),
            'scores':scores,'paired_log_loss':paired,'inference_wall_seconds':time.monotonic()-started,
            'limits':'One partial final UTC date of sampled markets. Market bootstrap conditions on this date/source; no durable out-of-time or WSE independent confirmation, and no realized PnL.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'final_markets':report['final_markets'],
                      'final_scores':{k:v['market_mean_log_loss'] for k,v in scores.items()}}))


if __name__=='__main__':main()
