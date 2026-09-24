"""Snapshot-to-snapshot replay diagnostics for one fixed Rocklabs BTC-5m hour.

The replay is offline measurement only. It never uses a future snapshot to repair a
prior book or promotes exchange-time sorting to a receive-causal feature stream.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,hashlib,json,statistics
from decimal import Decimal,InvalidOperation
from pathlib import Path
import zstandard as zstd

def ms(x):
 if isinstance(x,(int,float)) or (isinstance(x,str) and x.isdigit()):return int(x)
 return int(dt.datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()*1000)
def parse_book(z):
 out={}
 for side,key in [('BUY','bids'),('SELL','asks')]:
  levels={}
  for q in z.get(key,[]):
   try:p=Decimal(str(q['price']));v=Decimal(str(q['size']))
   except (KeyError,InvalidOperation):continue
   if v>0:levels[p]=v
  out[side]=levels
 return out
def top(state,side,k=1):
 xs=sorted(state[side].items(),reverse=(side=='BUY'))
 return tuple(xs[:k])
def bbo(state):return (top(state,'BUY',1),top(state,'SELL',1))
def compare(state,ref):
 bid,ask=bbo(state);rbid,rask=bbo(ref)
 px=(bid[0][0] if bid else None,ask[0][0] if ask else None)
 rpx=(rbid[0][0] if rbid else None,rask[0][0] if rask else None)
 return {'full':state==ref,'bbo_prices':px==rpx,'touch_size':bbo(state)==bbo(ref),
   'top2':top(state,'BUY',2)==top(ref,'BUY',2) and top(state,'SELL',2)==top(ref,'SELL',2),
   'bid_price':px[0]==rpx[0],'ask_price':px[1]==rpx[1],
   'bid_touch_size':bid==rbid,'ask_touch_size':ask==rask}
def diff_minimal(state,ref):
 out={}
 for side in ('BUY','SELL'):
  keys=set(state[side])|set(ref[side]);d=[]
  for p in sorted(keys,reverse=(side=='BUY')):
   a=state[side].get(p);b=ref[side].get(p)
   if a!=b:d.append({'price':str(p),'replayed_size':str(a) if a is not None else None,'snapshot_size':str(b) if b is not None else None})
  out[side]={'different_levels':len(d),'first_five':d[:5]}
 return out

def replay(seq,mode,private_examples,max_examples=8):
 seq=sorted(seq,key=(lambda z:(z['exchange_ms'],z['order'])) if mode=='exchange_stable' else (lambda z:z['order']))
 state=None;previous=None;metrics=collections.Counter();n=0;between=[];pair_issues=collections.Counter()
 last_exchange=None;last_receive=None
 for z in seq:
  if last_exchange is not None and z['exchange_ms']<last_exchange:metrics['exchange_backsteps']+=1
  if last_receive is not None and z['recv_ms']<last_receive:metrics['receive_backsteps']+=1
  last_exchange=z['exchange_ms'];last_receive=z['recv_ms']
  if z['type']=='book':
   ref=z['book']
   if state is not None:
    n+=1;c=compare(state,ref)
    for k,v in c.items():metrics[k+'_match']+=int(v)
    metrics['compared']+=1
    if not c['full']:
     if c['bbo_prices'] and c['touch_size'] and c['top2']:category='deep_only'
     elif c['bbo_prices'] and c['touch_size']:category='shallow_depth'
     elif c['bbo_prices']:category='touch_size'
     else:category='bbo_price'
     pair_issues[category]+=1
     if sum(q['mode']==mode and q['mismatch_category']==category for q in private_examples)<1:
      private_examples.append({'mode':mode,'mismatch_category':category,'token':z['token'],'previous_snapshot':previous,
       'next_snapshot':{'line':z['order'][0],'exchange_ms':z['exchange_ms'],'recv_ms':z['recv_ms'],'hash':z.get('hash')},
       'field_match':c,'level_diff':diff_minimal(state,ref),
       'intervening_update_count':len(between),'last_ten_updates':between[-10:]})
    sig=[(q['side'],q['price'],q['size'],q['exchange_ms']) for q in between]
    pair_issues['identical_update_repeats']+=len(sig)-len(set(sig))
    by_key=collections.defaultdict(set)
    for q in between:by_key[(q['side'],q['price'],q['exchange_ms'])].add(q['size'])
    pair_issues['same_ms_same_level_conflicting_sizes']+=sum(len(v)>1 for v in by_key.values())
    if any(q['exchange_ms']==z['exchange_ms'] for q in between):pair_issues['snapshot_same_exchange_ms_as_update']+=1
    if not c['full'] and any(q['recv_ms']>z['recv_ms'] for q in between):pair_issues['full_mismatch_with_later_received_update']+=1
    if not c['bbo_prices'] and any(q['recv_ms']>z['recv_ms'] for q in between):pair_issues['bbo_mismatch_with_later_received_update']+=1
    if between:
     pair_issues['pairs_with_any_update']+=1
     if any(q['recv_ms']>z['recv_ms'] for q in between):pair_issues['update_received_after_snapshot']+=1
   state={'BUY':dict(ref['BUY']),'SELL':dict(ref['SELL'])};previous={'line':z['order'][0],'exchange_ms':z['exchange_ms'],'recv_ms':z['recv_ms'],'hash':z.get('hash')};between=[]
  elif state is not None:
   side=z['side'];p=z['price'];size=z['size']
   if side not in ('BUY','SELL') or not Decimal(0)<p<Decimal(1) or size<0:
    metrics['invalid_update']+=1;continue
   if size==0:state[side].pop(p,None)
   else:state[side][p]=size
   direct=z.get('direct_bbo')
   if direct is not None:
    metrics['direct_bbo_numeric']+=1
    bid,ask=direct
    if Decimal(0)<bid<ask<Decimal(1):metrics['direct_bbo_strict_valid']+=1
    got=bbo(state)
    replayed=(got[0][0][0] if got[0] else None,got[1][0][0] if got[1] else None)
    if replayed==direct:metrics['direct_bbo_matches_replay']+=1
   between.append({'line':z['order'][0],'exchange_ms':z['exchange_ms'],'recv_ms':z['recv_ms'],
    'side':side,'price':str(p),'size':str(size)})
 return {'metrics':dict(metrics),'mismatch_categories':dict(pair_issues)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--sample',type=Path,required=True);p.add_argument('--identity-private',type=Path,required=True)
 p.add_argument('--scope',choices=['first','all'],required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--public',type=Path,required=True);a=p.parse_args()
 if a.private.exists() or a.public.exists():raise ValueError('preserve output')
 ident=json.loads(a.identity_private.read_text());slugs=sorted(ident['active_slugs'],key=lambda s:int(s.rsplit('-',1)[-1]));chosen=slugs[:1] if a.scope=='first' else slugs
 token_slug=ident['token_slug'];tokens={t for t,s in token_slug.items() if s in chosen}
 seqs=collections.defaultdict(list);meta=collections.Counter();side_values=collections.Counter();received_later_than_exchange=[]
 with zstd.open(a.sample/'clob.jsonl.zst','rt') as f:
  for line_idx,line in enumerate(f):
   x=json.loads(line);c=x['content'];c=json.loads(c) if isinstance(c,str) else c
   ys=c if isinstance(c,list) else [c];recv=ms(x['timestamp'])
   if isinstance(c,list):meta['array_lines']+=1;meta['array_items']+=len(c)
   for sub_idx,y in enumerate(ys):
    if not isinstance(y,dict):continue
    typ=y.get('event_type')
    if typ=='book':
     tok=str(y.get('asset_id'))
     if tok in tokens:
      t=ms(y['timestamp']);seqs[tok].append({'type':'book','token':tok,'order':(line_idx,sub_idx,0),'exchange_ms':t,'recv_ms':recv,
       'hash':y.get('hash'),'book':parse_book(y)})
      meta['book']+=1;received_later_than_exchange.append(recv-t)
    elif typ=='price_change':
     t=ms(y['timestamp'])
     for j,q in enumerate(y.get('price_changes',[])):
      tok=str(q.get('asset_id'))
      if tok not in tokens:continue
      try:price=Decimal(str(q['price']));size=Decimal(str(q['size']))
      except (KeyError,InvalidOperation):meta['bad_numeric_update']+=1;continue
      side=str(q.get('side'));side_values[side]+=1
      try:direct=(Decimal(str(q['best_bid'])),Decimal(str(q['best_ask'])))
      except (KeyError,InvalidOperation):direct=None
      if direct is not None:meta['direct_bbo_numeric']+=1
      if 'sequence_id' in q or 'seq_id' in q or 'sequence_id' in y or 'seq_id' in y:meta['sequence_field_present']+=1
      seqs[tok].append({'type':'change','token':tok,'order':(line_idx,sub_idx,j),'exchange_ms':t,'recv_ms':recv,
       'side':side,'price':price,'size':size,'hash':q.get('hash'),'direct_bbo':direct})
      meta['updates']+=1;received_later_than_exchange.append(recv-t)
 output={};examples=[]
 for slug in chosen:
  ent=[]
  for tok in sorted(t for t in tokens if token_slug[t]==slug):
   local={m:replay(seqs[tok],m,examples) for m in ('file_order','exchange_stable')}
   ent.append({'token':tok,'book':sum(z['type']=='book' for z in seqs[tok]),'updates':sum(z['type']=='change' for z in seqs[tok]),'modes':local})
  output[slug]=ent
 private={'scope':a.scope,'event_results':output,'minimal_mismatch_examples':examples,'side_values':dict(side_values)}
 a.private.parent.mkdir(parents=True,exist_ok=True);a.private.write_text(json.dumps(private,default=str,separators=(',',':'))+'\n')
 pub_events=[]
 for slug,ent in output.items():
  e={'event_index':chosen.index(slug),'tokens':len(ent),'book':sum(z['book'] for z in ent),'updates':sum(z['updates'] for z in ent),'modes':{}}
  for mode in ('file_order','exchange_stable'):
   metrics=collections.Counter();issues=collections.Counter()
   for z in ent:metrics.update(z['modes'][mode]['metrics']);issues.update(z['modes'][mode]['mismatch_categories'])
   e['modes'][mode]={'metrics':dict(metrics),'mismatch_categories':dict(issues)}
  pub_events.append(e)
 pub={'status':'OFFLINE_SNAPSHOT_REPLAY_DIAGNOSTIC_ONLY','scope':a.scope,'events':pub_events,
   'target_tokens':len(tokens),'source_event_count':len(chosen),'target_event_counts':dict(meta),
   'update_side_values':dict(side_values),'receive_minus_exchange_ms_min_median_max':
    [min(received_later_than_exchange),statistics.median(received_later_than_exchange),max(received_later_than_exchange)] if received_later_than_exchange else None,
   'private_minimal_examples_count':len(examples),'private_evidence_sha256':hashlib.sha256(a.private.read_bytes()).hexdigest(),
   'warning':'Both orderings are offline diagnostics. Exchange sorting can place later-received records earlier and is not a certified causal stream.'}
 a.public.parent.mkdir(parents=True,exist_ok=True);a.public.write_text(json.dumps(pub,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'scope':a.scope,'events':len(chosen),'first_file_full':pub_events[0]['modes']['file_order']['metrics'].get('full_match'),
  'first_exchange_full':pub_events[0]['modes']['exchange_stable']['metrics'].get('full_match'),
  'first_compared':pub_events[0]['modes']['file_order']['metrics'].get('compared')}))
if __name__=='__main__':main()
