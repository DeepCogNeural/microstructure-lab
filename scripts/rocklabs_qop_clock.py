"""Aggregate-only timing evidence for the fixed Rocklabs one-hour maker groups."""
from __future__ import annotations
import argparse,collections,hashlib,json,statistics
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--identity-private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise ValueError('preserve output')
x=json.loads(a.identity_private.read_text());groups={(g['tx'],g['contract'],g['match_log_index']):g for g in x['groups']}
rows=[];reason=collections.Counter();maker_legs=0
for line,sub,tx,contract,idx in x['joined_print_indices']:
 g=groups[(tx,contract,idx)]
 pr=next((z for z in x['prints'] if z['line']==line and z['sub']==sub),None)
 if pr is None or g['taker'] is None:reason['missing_print_or_taker']+=1;continue
 t=g['taker'];inner=int(pr['inner_ms']);recv=int(pr['recv_ms'])
 try:block=int(t['ts_block'])*1000;chain=int(t['ts_recv_ms'])
 except (ValueError,TypeError):reason['chain_time_invalid']+=1;continue
 rows.append((recv-inner,block-inner,chain-inner,len(g['maker_legs'])))
 maker_legs+=len(g['maker_legs'])

def dist(xs):
 z=sorted(xs)
 if not z:return None
 return {'min_ms':z[0],'median_ms':statistics.median(z),'p95_ms':z[min(len(z)-1,int(.95*(len(z)-1)))],'max_ms':z[-1]}
result={'status':'UNKNOWN_PER_LEG_MATCH_TIME','groups':len(rows),'maker_legs':maker_legs,
 'groups_with_multiple_maker_legs':sum(q[3]>1 for q in rows),
 'public_exchange_to_capture_receive':dist([q[0] for q in rows]),
 'chain_block_time_minus_public_exchange':dist([q[1] for q in rows]),
 'chain_indexer_receive_minus_public_exchange':dist([q[2] for q in rows]),
 'invalid_reason_counts':dict(reason),
 'timestamp_sources':{'public_inner':'CLOB last_trade_price.timestamp, exchange ms, generation semantics unknown',
  'public_outer':'Rocklabs websocket receive timestamp, collector-side',
  'chain_block':'Polygon block time, whole-second only',
  'chain_indexer_receive':'Rocklabs chain indexer receive time, post-block'},
 'per_maker_leg_independent_match_timestamp_count':0,
 'statement':'Observed low public message latency and later chain/block times do not independently bound match time for any of the multiple maker legs. No C/A/M or cancellation lead is computed.',
 'private_identity_sha256':hashlib.sha256(a.identity_private.read_bytes()).hexdigest()}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:result[k] for k in ['groups','maker_legs','groups_with_multiple_maker_legs','per_maker_leg_independent_match_timestamp_count']}))
