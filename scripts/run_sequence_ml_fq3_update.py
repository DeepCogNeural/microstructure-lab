"""Formal rolling 200k GPU refits paired to fixed FQ2 event rows."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import os
import resource
import subprocess
import sys
import time

import numpy as np
import torch

from run_sequence_ml_fq2 import endpoint_identity, fit_gru_gpu
from run_sequence_ml_v1 import day_scores, fit_tabular, load_stock, sha


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--symbol', required=True)
    ap.add_argument('--month', required=True)
    ap.add_argument('--private', type=Path, required=True)
    ap.add_argument('--fixed-private', type=Path, required=True)
    ap.add_argument('--fixed-report', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists() or args.private.exists():
        raise ValueError('preserve existing attempt; use new output paths')
    base_path = Path('configs/sequence_ml_fq2_v1.json')
    fq3_path = Path('configs/sequence_ml_fq3_v1.json')
    base, fq3 = json.loads(base_path.read_text()), json.loads(fq3_path.read_text())
    if sha(base_path) != fq3['base_config_sha256']:
        raise ValueError('FQ2 base config changed')
    if args.symbol not in base['symbols'] or args.month not in fq3['updated_models']['evaluation_months']:
        raise ValueError('unplanned stock/month')
    if not torch.cuda.is_available():
        raise RuntimeError('FQ3 formal rolling GRU requires CUDA')
    manifest_path = args.cache / 'manifest.json'
    if sha(manifest_path) != base['source_cache_manifest_sha256']:
        raise ValueError('cache identity mismatch')
    fixed_report = json.loads(args.fixed_report.read_text())
    if (fixed_report['stage'], fixed_report['symbol'], fixed_report['training_size_per_stock'],
        fixed_report['config_sha256']) != ('FQ2', args.symbol, fq3['formal_size_per_stock'], sha(base_path)):
        raise ValueError('fixed FQ2 report identity mismatch')
    fixed_path = args.fixed_private / 'predictions.npz'
    if sha(fixed_path) != fixed_report['private_predictions_sha256']:
        raise ValueError('fixed predictions hash mismatch')
    settings = fq3['updated_models'][args.month]
    config = copy.deepcopy(base)
    config['train_months'] = settings['train_months']
    config['dev_month'] = settings['dev_month']
    config['evaluation_months'] = [args.month]
    config['training_endpoints_per_stock_max'] = fq3['formal_size_per_stock']
    started = time.monotonic()
    stock, exclusions, feature_hashes = load_stock(args.cache, json.loads(manifest_path.read_text()),
                                                   args.symbol, config)
    if len(stock['train']['y']) != fq3['formal_size_per_stock']:
        raise ValueError(f'insufficient training endpoints: {len(stock["train"]["y"])}')
    with np.load(fixed_path) as fixed:
        mask = np.char.startswith(fixed['eval_day'].astype(str), args.month)
        if (not np.array_equal(fixed['eval_day'][mask], stock['eval']['day'])
            or not np.array_equal(fixed['eval_event_index'][mask], stock['eval']['event_index'])
            or not np.array_equal(fixed['eval_y'][mask], stock['eval']['y'])):
            raise ValueError('fixed/updated scoring rows or targets differ')
        names = [fq3['baseline']] + [f"{fq3['sequence']}_seed{s}" for s in fq3['sequence_seeds']]
        fixed_predictions = {arm: fixed[f'eval_{arm}'][mask].copy() for arm in names}
    args.private.mkdir(parents=True)
    scores, costs, updated = {}, {}, {}
    for arm in names:
        if arm == fq3['baseline']:
            _, pred, cost = fit_tabular(arm, stock, config, args.private)
        else:
            seed = int(arm.rsplit('seed', 1)[1])
            _, pred, cost = fit_gru_gpu(seed, stock, config, args.private)
        updated[arm] = pred
        costs[arm] = cost
        scores[arm] = {
            'fixed': day_scores(stock['eval']['y'], fixed_predictions[arm], stock['eval']['day']),
            'updated': day_scores(stock['eval']['y'], pred, stock['eval']['day'])}
        print(json.dumps({'symbol': args.symbol, 'month': args.month, 'arm': arm,
                          'fit_seconds': cost['fit_seconds'], 'epochs': cost.get('epochs_run')}), flush=True)
    prediction_path = args.private / 'updated_predictions.npz'
    np.savez_compressed(prediction_path, day=stock['eval']['day'], event_index=stock['eval']['event_index'],
                        actual=stock['eval']['y'], **updated)
    report = {'stage': 'FQ3', 'symbol': args.symbol, 'evaluation_month': args.month,
              'retrospective_only': True, 'base_config_sha256': sha(base_path),
              'fq3_config_sha256': sha(fq3_path),
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'cache_manifest_sha256': sha(manifest_path),
              'fixed_fq2_report_sha256': sha(args.fixed_report),
              'fixed_prediction_sha256': sha(fixed_path),
              'training_endpoint_identity_sha256': endpoint_identity(stock['train']['day'], stock['train']['event_index']),
              'feature_hashes_by_day': feature_hashes,
              'train_endpoints': len(stock['train']['y']), 'dev_endpoints': len(stock['dev']['y']),
              'evaluation_endpoints': len(stock['eval']['y']), 'eligibility': exclusions,
              'scores': scores, 'costs': costs,
              'private_updated_predictions_sha256': sha(prediction_path),
              'wall_seconds': time.monotonic() - started,
              'gpu_device_occupancy_seconds': sum(c.get('device_occupancy_seconds', 0) for c in costs.values()),
              'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                        (1 if sys.platform == 'darwin' else 1024),
              'software': {'python': sys.version.split()[0], 'torch': torch.__version__},
              'limitations': 'Retrospective rolling refit, not independent final or causal decay estimate.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=int) + '\n')
    os.replace(tmp, args.out)
    print(json.dumps({'symbol': args.symbol, 'month': args.month, 'status': 'complete',
                      'wall_seconds': report['wall_seconds']}), flush=True)


if __name__ == '__main__':
    main()
