"""Aggregate PM2 as-of provenance gate from the public OutcomeTick sample."""
from __future__ import annotations
import argparse, datetime as dt, gzip, hashlib, io, json, tarfile
from pathlib import Path

MARKETS='polymarket-data-samples/data/polymarket/daily/markets/BTC-5m/BTC-5m-markets-2026-09-08.jsonl.gz'
BOOK='polymarket-data-samples/data/polymarket/daily/book/BTC-5m/BTC-5m-book-2026-09-08.jsonl.gz'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def rows(tar, name):
    f=tar.extractfile(name)
    if f is None: raise ValueError('missing source file: '+name)
    with gzip.GzipFile(fileobj=f) as gz:
        for line in gz:
            yield json.loads(line)
def ms(iso):
    return int(dt.datetime.fromisoformat(iso.replace('Z','+00:00')).timestamp()*1000)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--archive',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    if a.out.exists(): raise ValueError('preserve existing PM2 gate receipt')
    with tarfile.open(a.archive,'r:gz') as tar:
        metadata=list(rows(tar,MARKETS)); first={}
        for row in rows(tar,BOOK):
            slug=row['slug']; recv=int(row['recv_ms'])
            first[slug]=min(recv,first.get(slug,recv))
    if len(metadata)!=len({m['slug'] for m in metadata}): raise ValueError('duplicate metadata slug')
    by_slug={m['slug']:m for m in metadata}; matched=set(by_slug)&set(first)
    result={'stage':'PM2_SOURCE_GATE','status':'ASOF_STRIKE_PROVENANCE_UNVERIFIED','archive_sha256':sha(a.archive),
      'metadata_rows':len(metadata),'book_event_markets':len(first),'matched_markets':len(matched),
      'book_markets_without_metadata':len(set(first)-set(by_slug)),
      'metadata_markets_without_book':len(set(by_slug)-set(first)),
      'matched_missing_strike':sum(by_slug[s].get('strike_value') is None for s in matched),
      'matched_metadata_updated_after_first_book':sum(ms(by_slug[s]['raw']['updatedAt'])>first[s] for s in matched),
      'matched_metadata_updated_after_close':sum(ms(by_slug[s]['raw']['updatedAt'])>=int(by_slug[s]['end_sec'])*1000 for s in matched),
      'matched_distinct_settlement_descriptions':len({by_slug[s]['raw'].get('description') for s in matched}),
      'matched_distinct_resolution_urls':len({by_slug[s]['raw'].get('resolutionSource') for s in matched}),
      'rule':'The available metadata snapshot is post-close. The value/timing of strike and settlement rule as observable at each decision time cannot be inferred from that snapshot alone. No structural model fit or paid expansion.'}
    if (result['metadata_rows'],result['matched_markets'],result['matched_missing_strike'])!=(292,290,18): raise ValueError('sample identity changed')
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('status','matched_markets','matched_metadata_updated_after_close')}))
if __name__=='__main__': main()
