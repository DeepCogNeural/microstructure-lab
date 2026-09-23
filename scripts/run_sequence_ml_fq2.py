"""FQ2 paired training-scale study; private models and row predictions stay outside Git."""
from __future__ import annotations

import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')

import argparse
import copy
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
import torch

from cloblab.sequence_model import GRURegressor
from run_sequence_ml_v1 import day_scores, fit_tabular, load_stock, sha


def endpoint_identity(day: np.ndarray, event: np.ndarray) -> str:
    if len(day) != len(event) or len(set(zip(day.tolist(), event.tolist()))) != len(day):
        raise ValueError('duplicate/mismatched training identity')
    digest = hashlib.sha256()
    for d, e in zip(day, event):
        digest.update(f'{d}/{int(e)}\n'.encode())
    return digest.hexdigest()


def predict(model: GRURegressor, values: np.ndarray, mu: np.ndarray,
            sigma: np.ndarray, batch_size: int, device: torch.device) -> np.ndarray:
    model.eval()
    out = []
    with torch.inference_mode():
        for start in range(0, len(values), batch_size):
            batch = torch.from_numpy((values[start:start + batch_size] - mu) / sigma).to(device)
            out.append(model(batch).cpu().numpy())
    return np.concatenate(out)


def fit_gru_gpu(seed: int, stock: dict, config: dict, private: Path) -> tuple:
    setup = config['gru']
    if setup['device'] != 'cuda:0' or not torch.cuda.is_available():
        raise RuntimeError('formal FQ2 requires the declared CUDA device')
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    device = torch.device(setup['device'])
    train, dev, evaluation = (stock[k] for k in ('train', 'dev', 'eval'))
    mu = train['x'].mean(axis=(0, 1), keepdims=True)
    sigma = train['x'].std(axis=(0, 1), keepdims=True).clip(min=1e-6)
    target_mu = float(train['y'].mean())
    target_sigma = max(float(train['y'].std()), 1e-6)
    x_train = torch.from_numpy((train['x'] - mu) / sigma)
    y_train = torch.from_numpy((train['y'] - target_mu) / target_sigma)
    x_dev = torch.from_numpy((dev['x'] - mu) / sigma)
    y_dev = torch.from_numpy((dev['y'] - target_mu) / target_sigma)
    model = GRURegressor(hidden_size=setup['hidden_size']).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=setup['learning_rate'],
                                   weight_decay=setup['weight_decay'])
    best_loss, best_state, patience = float('inf'), None, 0
    curve = []
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    began = time.monotonic()
    for epoch in range(setup['epochs_max']):
        model.train()
        order = torch.randperm(len(y_train), generator=torch.Generator().manual_seed(seed + epoch))
        total_loss = torch.zeros((), device=device)
        batches = 0
        for ids in order.split(setup['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            loss = ((model(x_train[ids].to(device)) - y_train[ids].to(device)) ** 2).mean()
            if not torch.isfinite(loss).item():
                raise ValueError(f'nonfinite GRU loss seed={seed} epoch={epoch+1}')
            loss.backward()
            optimizer.step()
            total_loss += loss.detach()
            batches += 1
        model.eval()
        dev_loss = torch.zeros((), device=device)
        with torch.inference_mode():
            for start in range(0, len(y_dev), setup['batch_size']):
                x = x_dev[start:start + setup['batch_size']].to(device)
                y = y_dev[start:start + setup['batch_size']].to(device)
                dev_loss += ((model(x) - y) ** 2).sum()
        torch.cuda.synchronize(device)
        dev_mse = float(dev_loss.item() / len(y_dev))
        curve.append({'epoch': epoch + 1, 'train_batch_mse_mean': float((total_loss / batches).item()),
                      'dev_mse': dev_mse})
        if dev_mse < best_loss - 1e-5:
            best_loss = dev_mse
            best_state = {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= setup['patience']:
            break
    torch.cuda.synchronize(device)
    fit_seconds = time.monotonic() - began
    if best_state is None:
        raise ValueError('no finite dev checkpoint')
    model.load_state_dict(best_state)
    path = private / f'S0_history_gru_seed{seed}.pt'
    torch.save({'state': best_state, 'mu': mu, 'sigma': sigma,
                'target_mu': target_mu, 'target_sigma': target_sigma}, path)
    torch.cuda.synchronize(device)
    began = time.monotonic()
    pdev = predict(model, dev['x'], mu, sigma, setup['batch_size'], device) * target_sigma + target_mu
    peval = predict(model, evaluation['x'], mu, sigma, setup['batch_size'], device) * target_sigma + target_mu
    torch.cuda.synchronize(device)
    inference_seconds = time.monotonic() - began
    best_epoch = int(np.argmin([point['dev_mse'] for point in curve]) + 1)
    metrics = {'fit_seconds': fit_seconds, 'inference_seconds': inference_seconds,
               'device_occupancy_seconds': fit_seconds + inference_seconds,
               'gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(device),
               'gpu_peak_reserved_bytes': torch.cuda.max_memory_reserved(device),
               'model_sha256': sha(path), 'model_bytes': path.stat().st_size,
               'train_endpoints': len(train['y']), 'epochs_run': len(curve),
               'best_epoch': best_epoch, 'learning_curve': curve,
               'trainable_parameters': sum(p.numel() for p in model.parameters()),
               'training_limited': len(curve) == setup['epochs_max'] and best_epoch == len(curve)}
    del model, optimizer, x_train, y_train, x_dev, y_dev
    torch.cuda.empty_cache()
    return pdev, peval, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path('configs/sequence_ml_fq2_v1.json'))
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--size', type=int, required=True)
    parser.add_argument('--private', type=Path, required=True)
    parser.add_argument('--aggregate', type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(args.config.read_text())
    if args.symbol not in frozen['symbols'] or args.size not in frozen['training_sizes_per_stock']:
        raise ValueError('symbol or size outside frozen protocol')
    if args.aggregate.exists() or args.private.exists():
        raise ValueError('output already exists; preserve original run or use a new attempt path')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; formal FQ2 has no CPU substitution')
    if sha(args.cache / 'manifest.json') != frozen['source_cache_manifest_sha256']:
        raise ValueError('source cache manifest mismatch')
    args.private.mkdir(parents=True)
    config = copy.deepcopy(frozen)
    config['training_endpoints_per_stock_max'] = args.size
    manifest = json.loads((args.cache / 'manifest.json').read_text())
    started = time.monotonic()
    stock, exclusions, hashes = load_stock(args.cache, manifest, args.symbol, config)
    if len(stock['train']['y']) != args.size:
        raise ValueError(f'insufficient causal training endpoints: {len(stock["train"]["y"])}')
    train_identity = endpoint_identity(stock['train']['day'], stock['train']['event_index'])
    predictions, scores, costs = {}, [], {}
    for arm, train in [('B1_history_xgboost', lambda: fit_tabular('B1_history_xgboost', stock, config, args.private))] + [
        (f'S0_history_gru_seed{seed}', lambda seed=seed: fit_gru_gpu(seed, stock, config, args.private))
        for seed in frozen['gru']['seeds']
    ]:
        pdev, peval, cost = train()
        predictions[arm] = {'dev': pdev, 'eval': peval}
        costs[arm] = cost
        for split, values in (('dev', pdev), ('eval', peval)):
            for row in day_scores(stock[split]['y'], values, stock[split]['day']):
                scores.append({'symbol': args.symbol, 'arm': arm, 'split': split, **row})
        print(json.dumps({'symbol': args.symbol, 'size': args.size, 'arm': arm,
                          'fit_seconds': cost['fit_seconds'], 'epochs': cost.get('epochs_run')}), flush=True)
    private_predictions = args.private / 'predictions.npz'
    np.savez_compressed(private_predictions,
                        **{f'{split}_{field}': stock[split][field] for split in ('dev', 'eval')
                           for field in ('y', 'day', 'event_index')},
                        **{f'{split}_{arm}': values[split] for arm, values in predictions.items()
                           for split in ('dev', 'eval')})
    report = {
        'stage': 'FQ2', 'study': frozen['study'], 'retrospective_only': True,
        'symbol': args.symbol, 'training_size_per_stock': args.size,
        'config_sha256': sha(args.config),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'cache_manifest_sha256': sha(args.cache / 'manifest.json'),
        'training_endpoint_identity_sha256': train_identity,
        'feature_hashes_by_day': hashes,
        'selection_counts': {split: len(data['y']) for split, data in stock.items()},
        'eligibility': exclusions, 'scores': scores, 'costs': costs,
        'private_predictions_sha256': sha(private_predictions),
        'wall_seconds': time.monotonic() - started,
        'gpu_device_occupancy_seconds': sum(c.get('device_occupancy_seconds', 0) for c in costs.values()),
        'gpu_device_name': torch.cuda.get_device_name(0),
        'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                  (1 if sys.platform == 'darwin' else 1024),
        'software': {'python': sys.version.split()[0], 'torch': torch.__version__},
        'limitations': 'All evaluated 2017 dates previously exposed; GPU occupancy is timed assigned-device use, not SM utilization or independent confirmation.'
    }
    args.aggregate.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.aggregate.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=int) + '\n')
    os.replace(tmp, args.aggregate)
    print(json.dumps({'status': 'complete', 'symbol': args.symbol, 'size': args.size,
                      'wall_seconds': report['wall_seconds']}), flush=True)


if __name__ == '__main__':
    main()
