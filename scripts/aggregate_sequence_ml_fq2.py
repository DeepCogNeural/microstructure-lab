"""Strict full-denominator aggregation of the FQ2 formal scaling ladder."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


ARMS = ('B1_history_xgboost', 'S0_history_gru_seed7', 'S0_history_gru_seed17', 'S0_history_gru_seed29')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap(dates: list[str], date_delta: np.ndarray, block: int, draws: int = 5000) -> list[float]:
    rng = np.random.default_rng(20260923 + block)
    months = defaultdict(list)
    for i, date in enumerate(dates):
        months[date[:7]].append(i)
    samples = np.empty(draws)
    for j in range(draws):
        chosen = []
        for idx in months.values():
            if len(idx) < block:
                raise ValueError('short bootstrap month')
            local = []
            while len(local) < len(idx):
                start = int(rng.integers(0, len(idx) - block + 1))
                local.extend(idx[start:start + block])
            chosen.extend(local[:len(idx)])
        samples[j] = date_delta[chosen].mean()
    return [float(x) for x in np.quantile(samples, [.025, .975])]


def read_reports(folder: Path, cfg: dict, cfg_sha: str, mapping: dict) -> tuple[dict, dict]:
    reports, hashes = {}, {}
    for size in cfg['training_sizes_per_stock']:
        reports[size], hashes[str(size)] = {}, {}
        for symbol in cfg['symbols']:
            key = f'{size}/{symbol}'
            name = mapping.get(key, f'fq2_{size}_{symbol}_a1.json')
            path = folder / name
            if not path.is_file():
                raise ValueError(f'missing declared run receipt {key}: {path}')
            report = json.loads(path.read_text())
            if (report['stage'], report['symbol'], report['training_size_per_stock'],
                report['config_sha256'], report['cache_manifest_sha256']) != (
                'FQ2', symbol, size, cfg_sha, cfg['source_cache_manifest_sha256']):
                raise ValueError(f'run identity mismatch: {key}')
            if report['selection_counts']['train'] != size or set(report['costs']) != set(ARMS):
                raise ValueError(f'incomplete model or train size: {key}')
            if not all(report['costs'][a]['train_endpoints'] == size for a in ARMS):
                raise ValueError(f'models trained on different endpoint counts: {key}')
            if len(report['training_endpoint_identity_sha256']) != 64:
                raise ValueError(f'missing endpoint identity: {key}')
            reports[size][symbol] = report
            hashes[str(size)][symbol] = sha(path)
    commits = {r['source_commit'] for by_stock in reports.values() for r in by_stock.values()}
    if len(commits) != 1:
        raise ValueError('different source commits across formal runs')
    return reports, {'run_sha256': hashes, 'source_commit': commits.pop()}


def matrix(reports: dict, split: str, symbols: list[str]) -> tuple[list[str], dict, np.ndarray, list[dict]]:
    cells = defaultdict(dict)
    undefined = []
    for symbol in symbols:
        report = reports[symbol]
        for row in report['scores']:
            if row['split'] != split:
                continue
            key = (row['day'], row['arm'])
            if symbol in cells[key]:
                raise ValueError(f'duplicate score cell: {split}/{key}/{symbol}')
            cells[key][symbol] = row
            if row['ic'] is None:
                undefined.append({'symbol': symbol, 'day': row['day'], 'arm': row['arm'],
                                  'reason': row['undefined_reason']})
    dates = sorted({day for day, arm in cells})
    values = {}
    count = None
    for arm in ARMS:
        if any(set(cells[(day, arm)]) != set(symbols) for day in dates):
            raise ValueError(f'missing stock/day IC cell: {split}/{arm}')
        data = np.asarray([[np.nan if cells[(day, arm)][s]['ic'] is None else cells[(day, arm)][s]['ic']
                            for s in symbols] for day in dates], dtype=float)
        n = np.asarray([[cells[(day, arm)][s]['n'] for s in symbols] for day in dates], dtype=np.int64)
        if count is None:
            count = n
        elif not np.array_equal(count, n):
            raise ValueError(f'scoring row identity/count differs across arms: {split}/{arm}')
        values[arm] = data
    return dates, values, count, undefined


def summarize_level(size: int, by_stock: dict, symbols: list[str]) -> dict:
    dev_dates, dev, dev_n, dev_undefined = matrix(by_stock, 'dev', symbols)
    eval_dates, evaluation, eval_n, eval_undefined = matrix(by_stock, 'eval', symbols)
    out = {
        'training_size_per_stock': size,
        'training_endpoint_identity_sha256': {s: by_stock[s]['training_endpoint_identity_sha256'] for s in symbols},
        'dev_dates': dev_dates, 'evaluation_dates': eval_dates,
        'dev_cells_per_arm': len(dev_dates) * len(symbols),
        'evaluation_cells_per_arm': len(eval_dates) * len(symbols),
        'dev_rows_per_arm': int(dev_n.sum()), 'evaluation_rows_per_arm': int(eval_n.sum()),
        'undefined_cells': {'dev': dev_undefined, 'evaluation': eval_undefined},
        'training_limited': {s: {a: by_stock[s]['costs'][a]['training_limited'] for a in ARMS[1:]}
                             for s in symbols},
        'fit_seconds_by_arm': {a: float(sum(by_stock[s]['costs'][a]['fit_seconds'] for s in symbols)) for a in ARMS},
        'inference_seconds_by_arm': {a: float(sum(by_stock[s]['costs'][a]['inference_seconds'] for s in symbols)) for a in ARMS},
        'gpu_device_occupancy_seconds': float(sum(by_stock[s]['gpu_device_occupancy_seconds'] for s in symbols)),
        'total_task_wall_seconds': float(sum(by_stock[s]['wall_seconds'] for s in symbols)),
        'peak_gpu_allocated_bytes': max(by_stock[s]['costs'][a]['gpu_peak_allocated_bytes']
                                        for s in symbols for a in ARMS[1:]),
        'peak_process_rss_bytes': max(by_stock[s]['process_peak_rss_bytes'] for s in symbols),
        'per_stock': {s: {'dev_rows': by_stock[s]['selection_counts']['dev'],
                          'eval_rows': by_stock[s]['selection_counts']['eval']}
                      for s in symbols},
    }
    if dev_undefined or eval_undefined:
        out['full_denominator_result'] = None
        out['reason'] = 'Undefined cells retained; no row/cell silently excluded from primary statistic.'
        return out
    mean_dev = {a: float(dev[a].mean()) for a in ARMS}
    mean_eval = {a: float(evaluation[a].mean()) for a in ARMS}
    baseline = evaluation[ARMS[0]]
    paired = {}
    for arm in ARMS[1:]:
        delta = evaluation[arm] - baseline
        by_date = delta.mean(axis=1)
        paired[arm] = {
            'mean_delta_ic': float(delta.mean()),
            'ci95_block5': bootstrap(eval_dates, by_date, 5),
            'month_delta': {m: float(delta[[d.startswith(m) for d in eval_dates]].mean())
                            for m in sorted({d[:7] for d in eval_dates})},
            'stock_delta': {s: float(delta[:, i].mean()) for i, s in enumerate(symbols)},
        }
    seed_mean = np.mean([evaluation[a] for a in ARMS[1:]], axis=0)
    delta = seed_mean - baseline
    by_date = delta.mean(axis=1)
    paired['S0_seed_mean'] = {
        'mean_delta_ic': float(delta.mean()),
        'ci95_block5': bootstrap(eval_dates, by_date, 5),
        'month_delta': {m: float(delta[[d.startswith(m) for d in eval_dates]].mean())
                        for m in sorted({d[:7] for d in eval_dates})},
        'stock_delta': {s: float(delta[:, i].mean()) for i, s in enumerate(symbols)},
        'leave_one_stock_out_delta': {s: float(np.delete(delta, i, axis=1).mean())
                                      for i, s in enumerate(symbols)},
    }
    out['full_denominator_result'] = {'dev_mean_ic': mean_dev, 'evaluation_mean_ic': mean_eval,
                                      'paired_vs_B1': paired}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=Path, default=Path('configs/sequence_ml_fq2_v1.json'))
    ap.add_argument('--reports', type=Path, required=True)
    ap.add_argument('--receipt-map', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError('preserve existing formal summary; choose a new path')
    cfg = json.loads(args.config.read_text())
    mapping = json.loads(args.receipt_map.read_text()) if args.receipt_map else {}
    reports, identity = read_reports(args.reports, cfg, sha(args.config), mapping)
    levels = {str(size): summarize_level(size, reports[size], cfg['symbols'])
              for size in cfg['training_sizes_per_stock']}
    first = levels[str(cfg['training_sizes_per_stock'][0])]
    for size in cfg['training_sizes_per_stock'][1:]:
        level = levels[str(size)]
        if (level['dev_dates'], level['evaluation_dates'], level['dev_rows_per_arm'],
            level['evaluation_rows_per_arm']) != (first['dev_dates'], first['evaluation_dates'],
                                                 first['dev_rows_per_arm'], first['evaluation_rows_per_arm']):
            raise ValueError('formal size levels have different scoring denominators')
    result = {
        'stage': 'FQ2', 'study': cfg['study'], 'retrospective_only': True,
        'config_sha256': sha(args.config), 'source_cache_manifest_sha256': cfg['source_cache_manifest_sha256'],
        'source_commit': identity['source_commit'], 'input_run_sha256': identity['run_sha256'],
        'symbols': cfg['symbols'], 'levels': levels,
        'finalists_for_FQ3': cfg['finalist_rule'],
        'limits': 'All 2017 evaluation dates previously exposed; 20k/15-epoch Q2 remains pilot. Date-block intervals condition on fitted models. Device occupancy excludes data-load/B1 allocation time; Slurm accounting is separate.',
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'complete', 'config_sha256': result['config_sha256'],
                      'levels': {size: lev['full_denominator_result']['paired_vs_B1']['S0_seed_mean']['mean_delta_ic']
                                 if lev['full_denominator_result'] else None for size, lev in levels.items()}}))


if __name__ == '__main__':
    main()
