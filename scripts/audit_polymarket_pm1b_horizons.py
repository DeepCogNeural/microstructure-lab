"""Outcome-blind future-book denominator audit for frozen PM1B horizon choice."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from cloblab.polymarket_l2 import audit_snapshot
from cloblab.polymarket_pm1a import market_opportunities

FILES=('updown_5m.parquet','updown_15m.parquet','updown_4h.parquet')
COLS=('market_slug','coin','contract_length','outcome','market_end_at','captured_at',
      'bid_prices','bid_sizes','ask_prices','ask_sizes','best_bid','best_ask','crossed')
HORIZONS=(5,15,30)
MAX_FUTURE_AGE_SECONDS=5


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def future_book_index(times, rows, decision, horizon_seconds, max_future_age_seconds=5):
    """Find a valid strictly later capture as of the fixed future clock."""
    target=decision+timedelta(seconds=horizon_seconds)
    j=bisect_right(times,target)-1
    if j<0 or times[j]<=decision:
        return None,'no_strictly_future_capture'
    if (target-times[j]).total_seconds()>max_future_age_seconds:
        return None,'future_stale'
    if not audit_snapshot(rows[j]).valid_midpoint:
        return None,'future_invalid_book'
    return j,None

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists():raise ValueError('preserve original horizon audit')
    base_path=Path('configs/polymarket_pm1a_v1.json')
    base=json.loads(base_path.read_text())
    split_path=Path(base['market_split']);audit_path=Path(base['audit_manifest'])
    split=json.loads(split_path.read_text())['market_ids']
    group_for={slug:group for group,slugs in split.items() for slug in slugs}
    audit=json.loads(audit_path.read_text())
    rows=defaultdict(list);metadata={}
    for name in FILES:
        path=args.source/name
        if sha(path)!=audit['dataset']['source_files'][name]['sha256']:
            raise ValueError(f'source changed: {name}')
        for batch in pq.ParquetFile(path).iter_batches(batch_size=10000,columns=list(COLS)):
            for row in batch.to_pylist():
                if row['outcome']!=base['token']:continue
                slug=row['market_slug']
                rows[slug].append(row)
                key=(row['coin'],row['contract_length'],row['market_end_at'])
                if slug in metadata and metadata[slug]!=key:raise ValueError('market metadata conflict')
                metadata[slug]=key
    if set(rows)!=set(group_for):raise ValueError('market identity mismatch')
    counts={(group,h):Counter() for group in ('train','dev','final','purged_boundary') for h in HORIZONS}
    by_coin={(group,h):Counter() for group in ('train','dev','final','purged_boundary') for h in HORIZONS}
    by_length={(group,h):Counter() for group in ('train','dev','final','purged_boundary') for h in HORIZONS}
    params=base['history']
    for slug,book in rows.items():
        book.sort(key=lambda row:row['captured_at'])
        times=[row['captured_at'] for row in book]
        coin,length,_=metadata[slug];group=group_for[slug]
        opportunities=market_opportunities(book,
            decision_step=base['decision_cadence_seconds'],
            min_seconds_to_close=base['minimum_seconds_to_close'],
            history_length=params['length'],max_age=base['maximum_snapshot_age_seconds'],
            max_lookback=params['maximum_lookback_seconds'],probability_clip=1e-4)
        for h in HORIZONS:
            c=counts[group,h];c['declared_markets']+=1
            c['primary_opportunities']+=len(opportunities)
            usable=0
            for decision,_,_ in opportunities:
                j,reason=future_book_index(times,book,decision,h,MAX_FUTURE_AGE_SECONDS)
                if j is None:
                    c[reason]+=1;continue
                c['usable_opportunities']+=1;usable+=1
                by_coin[group,h][coin]+=1;by_length[group,h][length]+=1
            c['markets_with_usable_opportunity']+=usable>0
    report={'stage':'PM1B','kind':'outcome_blind_horizon_coverage',
            'source_version_doi':base['source_version_doi'],
            'source_audit_sha256':sha(audit_path),'pm1a_config_sha256':sha(base_path),
            'market_split_sha256':sha(split_path),'horizons_seconds':HORIZONS,
            'future_lookup_rule':'latest Up book captured strictly after decision and at/before decision+h; target capture age <=5 seconds; valid two-sided unlocked/uncrossed book. Count only; no future-price change or terminal labels inspected.',
            'coverage':{group:{str(h):dict(sorted(counts[group,h].items()))|
                               {'usable_by_coin':dict(sorted(by_coin[group,h].items())),
                                'usable_by_contract_length':dict(sorted(by_length[group,h].items()))}
                                for h in HORIZONS}
                        for group in ('train','dev','final','purged_boundary')},
            'limits':'Denominators alone choose primary horizon. Future quote as-of capture is collector time, not exchange event time. No repricing model or target values were inspected.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({group:{str(h):counts[group,h]['usable_opportunities'] for h in HORIZONS}
                      for group in ('train','dev','final')}))


if __name__=='__main__':main()
