"""Read-only receipt check for 24 fixed structural examples and 3 unmatched prints."""
from __future__ import annotations
import argparse,collections,hashlib,json,time,urllib.request,urllib.parse
from pathlib import Path
from decimal import Decimal

p=argparse.ArgumentParser();p.add_argument('--identity-private',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--public',type=Path,required=True);a=p.parse_args()
if a.private.exists() or a.public.exists():raise ValueError('preserve output')
x=json.loads(a.identity_private.read_text());a.cache.mkdir(parents=True,exist_ok=True)
selected=[h for v in x['selected_24_by_category'].values() for h in v]
missing=sorted({z['tx'] for z in x['unmatched']})
assert len(selected)==24 and len(missing)==3 and not set(selected)&set(missing)
requests=0;download_bytes=0;next_at=0.
def get(url):
 global requests,download_bytes,next_at
 last=None
 for attempt in range(4):
  delay=max(0,next_at-time.monotonic())
  if delay:time.sleep(delay)
  next_at=time.monotonic()+0.8
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Rocklabs-QOP-measurement/1.0'})
   with urllib.request.urlopen(req,timeout=20) as f:blob=f.read()
   requests+=1;download_bytes+=len(blob)
   return json.loads(blob)
  except Exception as e:
   last=type(e).__name__+': '+str(e);time.sleep((attempt+1)*2)
 raise RuntimeError(last)

def receipt(h):
 f=a.cache/(h.removeprefix('0x')+'.json')
 if f.exists():return json.loads(f.read_text()),True
 u='https://polygon.blockscout.com/api/v2/transactions/'+h
 try:
  tx=get(u);ls=[];params=None;pages=0
  while True:
   url=u+'/logs'+('?' + urllib.parse.urlencode(params) if params else '')
   d=get(url);ls.extend(d['items']);pages+=1;params=d.get('next_page_params')
   if not params:break
   if pages>=20:raise RuntimeError('log pagination >20')
  out={'status':'complete','tx':tx,'logs':ls,'pages':pages}
 except Exception as exc:out={'status':'error','error':type(exc).__name__+': '+str(exc)}
 f.write_text(json.dumps(out,separators=(',',':'))+'\n')
 return out,False

def addr(v):return str(v.get('hash') if isinstance(v,dict) else v).lower()
def unique_matching(orders,fills,fees,events):
 if not len(orders)==len(fills)==len(fees)==len(events):return 'count_mismatch',None
 choices=[]
 for order,fill,fee in zip(orders,fills,fees):
  choices.append([j for j,e in enumerate(events) if addr(e.get('maker'))==addr(order[1])
   and str(e.get('tokenId'))==str(order[3]) and str(e.get('side'))==str(order[6])
   and str(e.get('makerAmountFilled'))==str(fill) and str(e.get('fee'))==str(fee)])
 solutions=[]
 def visit(i,used,ids):
  if len(solutions)>1:return
  if i==len(choices):solutions.append(ids);return
  for j in choices[i]:
   if j not in used:visit(i+1,used|{j},ids+[j])
 visit(0,set(),[])
 return ('unique',solutions[0]) if len(solutions)==1 else ('absent' if not solutions else 'ambiguous',None)

checks=[];raw_evidence=[];unmatched=[]
for h in selected+missing:
 r,cached=receipt(h)
 if h in missing:
  unmatched.append({'hash':h,'cache_status':r['status'],'block_status':(r.get('tx') or {}).get('status'),
    'block_timestamp':(r.get('tx') or {}).get('timestamp'),
    'matching_logs':sum((q.get('decoded') or {}).get('method_call','').startswith(('OrdersMatched(','OrderFilled(')) for q in r.get('logs',[])),
    'pages':r.get('pages'),'error':r.get('error')})
  continue
 item={'hash':h,'cache_status':r['status'],'cached':cached,'pages':r.get('pages'),'reason':None}
 if r['status']!='complete':item['reason']='http_or_pagination_failed';checks.append(item);continue
 tx=r['tx'];dec=tx.get('decoded_input') or {}
 if not dec.get('method_call','').startswith('matchOrders('):item['reason']='method_not_matchOrders';checks.append(item);continue
 inp={q['name']:q['value'] for q in dec.get('parameters',[])}
 if not {'conditionId','takerOrder','makerOrders','takerFillAmount','makerFillAmounts','takerFeeAmount','makerFeeAmounts'}<=inp.keys():item['reason']='incomplete_input';checks.append(item);continue
 contract=addr(tx.get('to'));logs=[q for q in r['logs'] if addr(q.get('address'))==contract]
 events=[q for q in logs if (q.get('decoded') or {}).get('method_call','').startswith('OrdersMatched(')]
 fills=[q for q in logs if (q.get('decoded') or {}).get('method_call','').startswith('OrderFilled(')]
 if len(events)!=1:item['reason']='match_event_count';checks.append(item);continue
 m={q['name']:q['value'] for q in events[0]['decoded']['parameters']}
 e=[{q['name']:q['value'] for q in z['decoded']['parameters']} for z in fills]
 taker=[z for z in e if str(z.get('orderHash')).lower()==str(m.get('takerOrderHash')).lower()]
 maker=[z for z in e if str(z.get('orderHash')).lower()!=str(m.get('takerOrderHash')).lower()]
 if len(taker)!=1:item['reason']='taker_not_unique';checks.append(item);continue
 t=taker[0];order=inp['takerOrder']
 if (addr(t.get('maker'))!=addr(order[1]) or str(t.get('tokenId'))!=str(order[3])
  or str(t.get('side'))!=str(order[6]) or str(t.get('makerAmountFilled'))!=str(inp['takerFillAmount'])
  or str(t.get('fee'))!=str(inp['takerFeeAmount'])):
  item['reason']='taker_input_event_mismatch';checks.append(item);continue
 state,assignment=unique_matching(inp['makerOrders'],inp['makerFillAmounts'],inp['makerFeeAmounts'],maker)
 if state!='unique':item['reason']='maker_'+state;checks.append(item);continue
 private_groups=[g for g in x['groups'] if g['tx']==h]
 if len(private_groups)!=1 or len(private_groups[0]['maker_legs'])!=len(maker):item['reason']='hour_log_group_mismatch';checks.append(item);continue
 receipt_maker_log_indices={int(str(z['index']),0) for z in fills
   if str({q['name']:q['value'] for q in z['decoded']['parameters']}.get('orderHash')).lower()!=str(m['takerOrderHash']).lower()}
 hour_maker_log_indices={leg['key'][3] for leg in private_groups[0]['maker_legs']}
 if receipt_maker_log_indices!=hour_maker_log_indices:
  item['reason']='hour_receipt_maker_log_identity_mismatch';checks.append(item);continue
 item.update({'reason':'verified','maker_inputs':len(maker),'contract':contract,
    'maker_token_complement_count':sum(str(z['tokenId'])!=str(t['tokenId']) for z in maker)})
 checks.append(item);raw_evidence.append({'hash':h,'tx':tx,'logs':r['logs']})
private={'selected_checks':checks,'unmatched':unmatched,'receipts':raw_evidence}
a.private.parent.mkdir(parents=True,exist_ok=True);a.private.write_text(json.dumps(private,separators=(',',':'))+'\n')
status=collections.Counter(z['reason'] for z in checks)
pub={'status':'FIXED_RECEIPT_AUDIT','selected':len(selected),'selected_by_category':{k:len(v) for k,v in x['selected_24_by_category'].items()},
 'selected_outcomes':dict(status),'unmatched_selected':len(missing),'unmatched_receipt_status':dict(collections.Counter(z['cache_status'] for z in unmatched)),
 'unmatched_with_any_matching_logs':sum(z['matching_logs']>0 for z in unmatched),
 'maker_input_count_total_verified':sum(z.get('maker_inputs',0) for z in checks if z['reason']=='verified'),
 'complement_maker_inputs_verified':sum(z.get('maker_token_complement_count',0) for z in checks if z['reason']=='verified'),
 'http_requests_this_run':requests,'response_bytes_this_run':download_bytes,
 'private_evidence_sha256':hashlib.sha256(a.private.read_bytes()).hexdigest(),
 'note':'24 fixed structural examples checked against decoded transaction input and complete receipt logs; unmatched three checked by exact hash only. Public output excludes hashes and raw logs.'}
a.public.parent.mkdir(parents=True,exist_ok=True);a.public.write_text(json.dumps(pub,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:pub[k] for k in ['selected_outcomes','unmatched_receipt_status','unmatched_with_any_matching_logs','http_requests_this_run']}))
