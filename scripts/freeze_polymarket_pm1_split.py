"""Freeze a market-grouped, UTC-day-chronological split without reading outcomes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

FILES=('updown_5m.parquet','updown_15m.parquet','updown_4h.parquet')
COLS=('market_slug','coin','contract_length','captured_at','market_end_at')
CUT1=datetime(2026,8,23,tzinfo=timezone.utc)
CUT2=datetime(2026,8,24,tzinfo=timezone.utc)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists(): raise ValueError('split already exists; preserve it')
    audit=json.loads(args.audit.read_text())
    market={}
    for name in FILES:
        path=args.data/name
        if sha(path)!=audit['dataset']['source_files'][name]['sha256']:
            raise ValueError('source changed since PM0 audit')
        file=pq.ParquetFile(path)
        for batch in file.iter_batches(batch_size=10000,columns=list(COLS)):
            cols=batch.to_pydict()
            for values in zip(*(cols[c] for c in COLS)):
                slug,coin,length,captured,end=values
                info=market.setdefault(slug,{'coin':coin,'contract_length':length,
                                             'first_capture':captured,'last_capture':captured,'end':end})
                if (info['coin'],info['contract_length'],info['end'])!=(coin,length,end):
                    raise ValueError(f'inconsistent market metadata: {slug}')
                info['first_capture']=min(info['first_capture'],captured)
                info['last_capture']=max(info['last_capture'],captured)
    if len(market)!=audit['identity']['unique_markets']:
        raise ValueError('market count changed')
    groups={'train':[],'dev':[],'final':[],'purged_boundary':[]}
    for slug,info in market.items():
        first,end=info['first_capture'],info['end']
        if end<=CUT1:
            group='train'
        elif first>=CUT1 and end<=CUT2:
            group='dev'
        elif first>=CUT2:
            group='final'
        else:
            group='purged_boundary'
        groups[group].append(slug)
    for ids in groups.values(): ids.sort()
    if len(set(sum(groups.values(),[])))!=len(market): raise ValueError('market split overlap')
    output={'stage':'PM0','kind':'frozen_PM1A_split','outcome_blind':True,
            'source_audit_sha256':sha(args.audit),
            'source_version_doi':audit['dataset']['version_doi'],
            'cutoffs_utc':{'train_end_exclusive':CUT1.isoformat(),
                           'dev_end_exclusive':CUT2.isoformat()},
            'rule':'Assign whole market by first observed capture and market end; train ends by Aug23 UTC, dev starts Aug23 and ends by Aug24, final starts Aug24. Purge markets spanning either boundary. No outcome values used.',
            'market_ids':groups,
            'counts':{g:{'markets':len(ids),
                         'coins':dict(sorted(Counter(market[s]['coin'] for s in ids).items())),
                         'contract_lengths':dict(sorted(Counter(market[s]['contract_length'] for s in ids).items())),
                         'first_capture_utc':min((market[s]['first_capture'] for s in ids),default=None).isoformat() if ids else None,
                         'last_market_end_utc':max((market[s]['end'] for s in ids),default=None).isoformat() if ids else None}
                      for g,ids in groups.items()},
            'limits':'Only four UTC calendar days of sampled markets; final is a partial later day and cannot establish durable temporal generalization. No final outcomes inspected before this split was frozen.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps({g:v['markets'] for g,v in output['counts'].items()}))


if __name__=='__main__':main()
