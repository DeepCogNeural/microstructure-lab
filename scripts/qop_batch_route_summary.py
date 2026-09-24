"""Publish only aggregates of fixed QOP target-token maker legs by print route."""
from __future__ import annotations
import argparse, json
from collections import Counter
from decimal import Decimal
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--build-private', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if a.out.exists():
    raise ValueError('preserve output')
rows = json.loads(a.build_private.read_text())['leg_rows']
routes = {}
for route in ('target', 'complement'):
    subset = [x for x in rows if x['print_token'] == route]
    eligible = [x for x in subset if not x['failure']['1000_5000']]
    routes[route] = {
        'legs': len(subset),
        'events': len({x['event_idx'] for x in subset}),
        'distinct_hashes': len({x['hash'] for x in subset}),
        'shares': str(sum((Decimal(x['shares']) for x in subset), Decimal(0))),
        'passive_sides': dict(Counter('BUY' if x['sign'] == 1 else 'SELL' for x in subset)),
        'eligible_5s_1000ms_legs': len(eligible),
        'eligible_5s_1000ms_shares': str(sum((Decimal(x['shares']) for x in eligible), Decimal(0))),
    }
assert sum(x['legs'] for x in routes.values()) == len(rows)
a.out.write_text(json.dumps({
    'status': 'DEVELOPMENT_AGGREGATE_ONLY',
    'routes': routes,
    'interpretation': 'Public print token route is a representation of the active match; target maker leg price and direction come from receipt asset exchange, never from public print price.',
}, indent=2, sort_keys=True) + '\n')
