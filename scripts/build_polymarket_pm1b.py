"""Build private, market-grouped repricing targets from frozen PM1A decisions."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from audit_polymarket_pm1b_horizons import COLS, FILES, future_book_index


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--group',choices=('train','dev','final'),required=True)
    ap.add_argument('--pm1a-private',type=Path,required=True)
    ap.add_argument('--pm1a-build-manifest',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out-private',type=Path,required=True)
    ap.add_argument('--out-manifest',type=Path,required=True)
    ap.add_argument('--allow-final',action='store_true')
    args=ap.parse_args()
    if args.group=='final' and not args.allow_final:
        raise ValueError('final repricing target is sealed until model/code freeze')
    if args.out_private.exists() or args.out_manifest.exists():
        raise ValueError('preserve original PM1B extraction')
    cfg_path=Path('configs/polymarket_pm1b_v1.json')
    cfg=json.loads(cfg_path.read_text())
    horizon_path=Path('results/polymarket_pm1b_v1/horizon_audit.json')
    if sha(horizon_path)!=cfg['horizon_audit_sha256']:
        raise ValueError('horizon audit changed')
    horizon=json.loads(horizon_path.read_text())
    pm1a_build=json.loads(args.pm1a_build_manifest.read_text())
    if sha(args.pm1a_private)!=pm1a_build['splits'][args.group]['private_npz_sha256']:
        raise ValueError('PM1A opportunity identity changed')
    with np.load(args.pm1a_private,allow_pickle=False) as old:
        opportunity={key:old[key].copy() for key in ('probability','history','market','decision_utc')}
    if opportunity['history'].shape[1:]!=(8,11):
        raise ValueError('history shape changed')
    if len(set(opportunity['market']))!=pm1a_build['splits'][args.group]['eligible_markets']:
        raise ValueError('PM1A market denominator changed')
    audit_path=Path('results/polymarket_pm0_v1/polyorderbooks_audit.json')
    audit=json.loads(audit_path.read_text())
    target_markets=set(opportunity['market'])
    books=defaultdict(list)
    metadata={}
    for name in FILES:
        path=args.source/name
        if sha(path)!=audit['dataset']['source_files'][name]['sha256']:
            raise ValueError(f'source file changed: {name}')
        for batch in pq.ParquetFile(path).iter_batches(batch_size=10000,columns=list(COLS)):
            for row in batch.to_pylist():
                slug=row['market_slug']
                if row['outcome']!='Up' or slug not in target_markets:continue
                books[slug].append(row)
                key=(row['coin'],row['contract_length'],row['market_end_at'])
                if slug in metadata and metadata[slug]!=key:
                    raise ValueError(f'inconsistent market metadata: {slug}')
                metadata[slug]=key
    if set(books)!=target_markets:
        raise ValueError('missing source markets')
    times={}
    for slug,rows in books.items():
        rows.sort(key=lambda row:row['captured_at'])
        times[slug]=[row['captured_at'] for row in rows]
        if len(set(times[slug]))!=len(times[slug]):
            raise ValueError('duplicate token capture')
    keep=[];targets=[];future_capture=[]
    counts=Counter();by_length=Counter();by_coin=Counter()
    for i,slug in enumerate(opportunity['market']):
        decision=datetime.fromisoformat(str(opportunity['decision_utc'][i]))
        j,reason=future_book_index(times[str(slug)],books[str(slug)],decision,
                                   cfg['primary_horizon_seconds'],5)
        if j is None:
            counts[reason]+=1;continue
        row=books[str(slug)][j]
        future=(row['best_bid']+row['best_ask'])/2
        change=future-float(opportunity['probability'][i])
        if not np.isfinite(change) or abs(change)>1:
            raise ValueError('invalid future probability change')
        keep.append(i);targets.append(change);future_capture.append(row['captured_at'].isoformat())
        coin,length,_=metadata[str(slug)]
        by_coin[coin]+=1;by_length[length]+=1
    expected=horizon['coverage'][args.group][str(cfg['primary_horizon_seconds'])]
    if len(keep)!=expected['usable_opportunities'] or len(set(opportunity['market'][keep]))!=expected['markets_with_usable_opportunity']:
        raise ValueError('PM1B denominator differs from outcome-blind audit')
    for key in ('no_strictly_future_capture','future_stale','future_invalid_book'):
        if counts[key]!=expected.get(key,0):
            raise ValueError(f'PM1B exclusion count differs: {key}')
    args.out_private.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.out_private,
                        probability=opportunity['probability'][keep],
                        history=opportunity['history'][keep],
                        market=opportunity['market'][keep],
                        decision_utc=opportunity['decision_utc'][keep],
                        future_capture_utc=np.asarray(future_capture),
                        repricing=np.asarray(targets,dtype=np.float32))
    manifest={'stage':'PM1B','group':args.group,'status':'PRIVATE_TARGET_BUILT',
              'protocol_sha256':sha(cfg_path),'horizon_audit_sha256':sha(horizon_path),
              'pm1a_opportunity_sha256':sha(args.pm1a_private),
              'source_audit_sha256':sha(audit_path),
              'eligible_markets':len(set(opportunity['market'][keep])),
              'eligible_opportunities':len(keep),
              'exclusions':dict(sorted(counts.items())),
              'by_coin':dict(sorted(by_coin.items())),
              'by_contract_length':dict(sorted(by_length.items())),
              'private_target_sha256':sha(args.out_private),
              'limits':'No repricing target values or row arrays are public; final requires explicit unseal after fitted model/code freeze.'}
    args.out_manifest.parent.mkdir(parents=True,exist_ok=True)
    args.out_manifest.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'group':args.group,'markets':manifest['eligible_markets'],
                      'opportunities':manifest['eligible_opportunities']}))


if __name__=='__main__':main()
