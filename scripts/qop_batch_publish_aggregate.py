"""Reduce private QOP event-level diagnostics to public aggregate evidence."""
from __future__ import annotations
import argparse, collections, hashlib, json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--detailed-private',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():raise ValueError('preserve output')
raw=a.detailed_private.read_bytes();data=json.loads(raw)
per_event=data.pop('by_event')
summary={}
for age in ('primary','sensitivity'):
    valid=[e for e in per_event if e[age]['legs'] and e[age]['N']]
    signs=collections.Counter('positive' if e[age]['N']['share_weighted_mean_cents']>0 else 'negative' if e[age]['N']['share_weighted_mean_cents']<0 else 'zero' for e in valid)
    summary[age]={'eligible_events':len(valid),'event_weighted_N5_sign_counts':dict(signs),
      'events_with_no_eligible_legs':len(per_event)-len(valid),
      'eligible_legs_per_event_min_max':[min(e[age]['legs'] for e in valid),max(e[age]['legs'] for e in valid)] if valid else None}
data['by_event_aggregate']=summary
data['private_detailed_aggregate_sha256']=hashlib.sha256(raw).hexdigest()
a.out.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
