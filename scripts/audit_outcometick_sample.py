"""Outcome-blind checksum/schema/timing audit of the free OutcomeTick sample day."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--release',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--data',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists(): raise ValueError('preserve existing audit')
    release=json.loads(args.release.read_text())
    if release['tag_name']!='samples-2026-09-08': raise ValueError('unexpected release')
    assets={a['name']:a for a in release['assets']}
    if sha(args.archive)!=assets[args.archive.name]['digest'].split(':')[1]:
        raise ValueError('sample archive checksum mismatch')
    results={}
    for path in sorted(args.data.rglob('*.gz')):
        if path.name not in assets or sha(path)!=assets[path.name]['digest'].split(':')[1]:
            raise ValueError(f'component checksum mismatch: {path}')
        data={'bytes':path.stat().st_size,'sha256':sha(path),'rows':0,'field_types':{},
              'event_ts_ms_min':None,'event_ts_ms_max':None,'recv_ms_min':None,'recv_ms_max':None,
              'market_count':0,'issues':{}}
        issues=Counter()
        markets=set()
        with gzip.open(path,'rt') as f:
            if path.name.endswith('.csv.gz'):
                reader=csv.DictReader(f)
                data['field_types']={field:'csv_string' for field in reader.fieldnames}
                for row in reader:
                    data['rows']+=1
                    for field in ('feed_ts_ms','server_ts_ms','recv_ms'):
                        try: value=int(row[field])
                        except (KeyError,TypeError,ValueError):
                            issues[f'invalid_{field}']+=1
                            continue
                        if field in ('feed_ts_ms','recv_ms'):
                            key=field.replace('feed_ts_ms','event_ts_ms')
                            data[f'{key}_min']=value if data[f'{key}_min'] is None else min(data[f'{key}_min'],value)
                            data[f'{key}_max']=value if data[f'{key}_max'] is None else max(data[f'{key}_max'],value)
                    if not row.get('full_accuracy_value'):
                        issues['missing_full_accuracy_value']+=1
            else:
                for line in f:
                    data['rows']+=1
                    row=json.loads(line)
                    if data['rows']==1:
                        data['field_types']={k:type(v).__name__ for k,v in row.items()}
                        if isinstance(row.get('payload'),dict):
                            data['payload_keys_first_row']=sorted(row['payload'])
                        if isinstance(row.get('raw'),dict):
                            data['raw_keys_first_row']=sorted(row['raw'])
                    if not isinstance(row.get('slug'),str) or not row['slug']:
                        issues['missing_market_slug']+=1
                    else:
                        markets.add(row['slug'])
                    for field in ('event_ts_ms','recv_ms'):
                        value=row.get(field)
                        if not isinstance(value,int):
                            if path.name.find('markets')<0: issues[f'invalid_{field}']+=1
                            continue
                        data[f'{field}_min']=value if data[f'{field}_min'] is None else min(data[f'{field}_min'],value)
                        data[f'{field}_max']=value if data[f'{field}_max'] is None else max(data[f'{field}_max'],value)
                    if 'markets' in path.name:
                        if not row.get('strike_value'): issues['missing_strike']+=1
                        if not isinstance(row.get('token_ids'),list) or len(row['token_ids'])!=2:
                            issues['not_two_tokens']+=1
                        if not row.get('resolved'): issues['unresolved']+=1
                        config=(row.get('raw') or {}).get('cryptoMarketConfig') or {}
                        if config.get('twapLookbackSeconds') != 60:
                            issues['twap_lookback_not_60s']+=1
        data['market_count']=len(markets)
        data['issues']=dict(sorted(issues.items()))
        results[path.name]=data
    output={'stage':'PM0','source':'OutcomeTick free public sample','release_tag':release['tag_name'],
            'release_id':release['id'],'release_published_at':release['published_at'],
            'archive_sha256':sha(args.archive),'archive_bytes':args.archive.stat().st_size,
            'files':results,'outcome_blind':True,
            'limits':'One 2026-09-08 BTC 5m day. Full-depth snapshots/deltas/trades are archived as received, not exact queue/fill evidence. No paid archive or account data used.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'complete','files':len(results),'rows':{k:v['rows'] for k,v in results.items()}}))


if __name__=='__main__': main()
