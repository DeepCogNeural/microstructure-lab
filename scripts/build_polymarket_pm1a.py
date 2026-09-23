"""Build private, market-grouped PM1A train/dev arrays without opening final labels."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from cloblab.polymarket_pm1a import FEATURES, market_opportunities

FILES = ('updown_5m.parquet','updown_15m.parquet','updown_4h.parquet')
COLS = ('market_slug','coin','contract_length','outcome','is_winning_outcome',
        'market_end_at','captured_at','bid_prices','bid_sizes','ask_prices','ask_sizes',
        'best_bid','best_ask','crossed')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--splits', nargs='+', choices=('train','dev','final'), required=True)
    ap.add_argument('--private', type=Path, required=True)
    ap.add_argument('--manifest-out', type=Path, required=True)
    ap.add_argument('--allow-final', action='store_true')
    args = ap.parse_args()
    if 'final' in args.splits and not args.allow_final:
        raise ValueError('final requires explicit one-time unseal after model/code freeze')
    if args.private.exists() or args.manifest_out.exists():
        raise ValueError('preserve existing extraction artifacts')
    base_path = Path('configs/polymarket_pm1a_v1.json')
    model_path = Path('configs/polymarket_pm1a_model_v1.json')
    base = json.loads(base_path.read_text())
    model = json.loads(model_path.read_text())
    if sha(base_path) != model['eligibility_config_sha256']:
        raise ValueError('eligibility config changed')
    split_path = Path(base['market_split'])
    audit_path = Path(base['audit_manifest'])
    if sha(split_path) != model['split_manifest_sha256'] or sha(audit_path) != model['source_audit_sha256']:
        raise ValueError('source/split identity changed')
    split = json.loads(split_path.read_text())['market_ids']
    target = {s: set(split[s]) for s in args.splits}
    all_target = set().union(*target.values())
    audit = json.loads(audit_path.read_text())
    by_market = defaultdict(list)
    labels = {}
    metadata = {}
    for name in FILES:
        path = args.source / name
        if sha(path) != audit['dataset']['source_files'][name]['sha256']:
            raise ValueError(f'source file changed: {name}')
        for batch in pq.ParquetFile(path).iter_batches(batch_size=10000, columns=list(COLS)):
            for row in batch.to_pylist():
                slug = row['market_slug']
                if slug not in all_target or row['outcome'] != base['token']:
                    continue
                label = row.pop('is_winning_outcome')
                if label is None:
                    raise ValueError(f'missing resolved outcome: {slug}')
                if slug in labels and labels[slug] != label:
                    raise ValueError(f'inconsistent terminal outcome: {slug}')
                labels[slug] = label
                key = (row['coin'],row['contract_length'],row['market_end_at'])
                if slug in metadata and metadata[slug] != key:
                    raise ValueError(f'inconsistent market metadata: {slug}')
                metadata[slug] = key
                by_market[slug].append(row)
    if set(by_market) != all_target:
        raise ValueError(f'missing target markets: {len(all_target - set(by_market))}')
    arrays, manifest = {}, {'stage':'PM1A','kind':'private_opportunity_build',
                            'source_version_doi':base['source_version_doi'],
                            'eligibility_config_sha256':sha(base_path),
                            'model_config_sha256':sha(model_path),
                            'split_manifest_sha256':sha(split_path),
                            'source_audit_sha256':sha(audit_path),
                            'feature_names':list(FEATURES),'splits':{},
                            'limits':'Only requested split labels were used; final requires explicit unseal. Private row arrays are excluded from Git.'}
    cfg = base['history']
    for group in args.splits:
        ps, xs, ys, markets, decisions = [], [], [], [], []
        per_coin, per_length = Counter(), Counter()
        eligible_market_count = 0
        for slug in sorted(target[group]):
            rows = by_market[slug]
            opportunities = market_opportunities(rows,
                decision_step=base['decision_cadence_seconds'],
                min_seconds_to_close=base['minimum_seconds_to_close'],
                history_length=cfg['length'], max_age=base['maximum_snapshot_age_seconds'],
                max_lookback=cfg['maximum_lookback_seconds'],
                probability_clip=model['probability_clip'])
            if opportunities:
                eligible_market_count += 1
            coin,length,_ = metadata[slug]
            for decision,p,x in opportunities:
                ps.append(p); xs.append(x); ys.append(int(labels[slug]));
                markets.append(slug); decisions.append(decision.isoformat())
                per_coin[coin] += 1; per_length[length] += 1
        if not xs:
            raise ValueError(f'no eligible opportunities: {group}')
        dest = args.private / f'{group}.npz'
        arrays[group] = (dest, {'probability':np.asarray(ps,dtype=np.float32),
                                'history':np.stack(xs), 'label':np.asarray(ys,dtype=np.int8),
                                'market':np.asarray(markets), 'decision_utc':np.asarray(decisions)})
        manifest['splits'][group] = {'declared_markets':len(target[group]),
                                      'eligible_markets':eligible_market_count,
                                      'eligible_opportunities':len(xs),
                                      'positive_markets':sum(bool(labels[s]) for s in target[group]),
                                      'opportunities_by_coin':dict(sorted(per_coin.items())),
                                      'opportunities_by_length':dict(sorted(per_length.items()))}
    args.private.mkdir(parents=True)
    for group,(dest,data) in arrays.items():
        np.savez_compressed(dest,**data)
        manifest['splits'][group]['private_npz_sha256'] = sha(dest)
    args.manifest_out.parent.mkdir(parents=True,exist_ok=True)
    args.manifest_out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({g:{k:v for k,v in m.items() if k in ('eligible_markets','eligible_opportunities')}
                      for g,m in manifest['splits'].items()}))


if __name__ == '__main__':
    main()
