"""Extract one causal decision per pinned Sep 8 BTC-5m event and verify CTF payouts."""
from __future__ import annotations
import argparse,bisect,collections,gzip,hashlib,json,math,subprocess,time
from pathlib import Path
DAY_START=1788825600;DAY_END=DAY_START+86400
CTF='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
RPC='https://polygon-bor-rpc.publicnode.com'

def rows(root,kind):
 p=next((root/kind/'BTC-5m').glob('*.jsonl.gz'))
 with gzip.open(p,'rt') as f:
  for line in f:yield json.loads(line)
def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def finite(x):
 try:
  v=float(x);return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None

def choose(arr,t,max_age,kind):
 if not arr:return None,'no_record'
 times=[x['recv_ms'] for x in arr];j=bisect.bisect_right(times,t)-1
 if j<0:return None,'no_record'
 x=arr[j];stamp=x['recv_ms'];lo=bisect.bisect_left(times,stamp);same=arr[lo:j+1]
 if kind=='bbo':
  vals={(z['payload'].get('best_bid'),z['payload'].get('best_ask')) for z in same}
 else:vals={json.dumps(z['payload'],sort_keys=True) for z in same}
 if len(vals)!=1:return None,'conflicting_same_receive_time'
 age=t-stamp
 if age<0 or age>max_age:return None,'stale'
 if kind=='bbo':
  bid=finite(x['payload'].get('best_bid'));ask=finite(x['payload'].get('best_ask'))
  if bid is None or ask is None or not 0<bid<ask<1:return None,'invalid_bbo'
  return {'bid':bid,'ask':ask,'mid':(bid+ask)/2,'spread':ask-bid,'age_ms':age},None
 levels=x['payload'];bids=levels.get('bids') or [];asks=levels.get('asks') or []
 if not bids or not asks:return None,'empty_book_side'
 def parse(z):return finite(z.get('price')),finite(z.get('size'))
 bb=[parse(z) for z in bids];aa=[parse(z) for z in asks]
 if any(p is None or s is None or p<=0 or p>=1 or s<=0 for p,s in bb+aa):return None,'invalid_book'
 bp=max(p for p,s in bb);ap=min(p for p,s in aa)
 if bp>=ap:return None,'crossed_book'
 bs=sum(s for p,s in bb if p==bp);az=sum(s for p,s in aa if p==ap)
 return {'bid_size':bs,'ask_size':az,'imbalance':(bs-az)/(bs+az),'age_ms':age},None

def rpc_payouts(markets):
 out={};calls=[];nextid=1
 for m in markets:
  c=m['condition_id'][2:]
  for typ,selector,idx in [('up','0x0504c814',0),('down','0x0504c814',1),('den','0xdd34de67',None)]:
   data=selector+c+(f'{idx:064x}' if idx is not None else '')
   calls.append((nextid,m['condition_id'],typ,{'jsonrpc':'2.0','id':nextid,'method':'eth_call','params':[{'to':CTF,'data':data},'latest']}));nextid+=1
 request_count=0;bytes_received=0;fail=[]
 for offset in range(0,len(calls),75):
  batch=calls[offset:offset+75];body=json.dumps([z[3] for z in batch]);resp=None
  for attempt in range(3):
   proc=subprocess.run(['curl','-sS','--max-time','25','-H','content-type: application/json','--data-binary','@-',RPC],input=body,text=True,capture_output=True,timeout=30)
   request_count+=1;bytes_received+=len(proc.stdout.encode())
   try:
    payload=json.loads(proc.stdout)
    if proc.returncode==0 and isinstance(payload,list) and len(payload)==len(batch):resp={x['id']:x for x in payload};break
   except (ValueError,KeyError):pass
   time.sleep(0.5*(attempt+1))
  if resp is None:
   fail.extend((z[1],z[2]) for z in batch);continue
  for id,condition,typ,_ in batch:
   item=resp.get(id,{})
   try:value=int(item['result'],16)
   except (KeyError,ValueError,TypeError):value=None
   out.setdefault(condition,{})[typ]=value
 return out,{'http_requests':request_count,'response_bytes':bytes_received,'failed_calls':len(fail)}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--sample-root',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True);a=ap.parse_args()
 if digest(a.archive)!='9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506':raise ValueError('archive mismatch')
 markets=[x for x in rows(a.sample_root,'markets') if DAY_START<=x['start_sec'] and x['end_sec']<=DAY_END and str(x['asset']).lower()=='btc' and x['interval_sec']==300]
 markets.sort(key=lambda x:(x['start_sec'],x['condition_id']))
 if len(markets)>288 or len(markets)==0:raise ValueError('unexpected candidate universe')
 target={str(m['token_ids'][0]):m for m in markets};data={k:collections.defaultdict(list) for k in ('best_bid_ask','book')}
 for kind in data:
  for x in rows(a.sample_root,kind):
   asset=str(x.get('asset_id'));m=target.get(asset)
   if m and x['recv_ms']<=m['end_sec']*1000-120000:data[kind][asset].append(x)
  for arr in data[kind].values():arr.sort(key=lambda x:(x['recv_ms'],x['event_ts_ms']))
 payouts,network=rpc_payouts(markets)
 coverage=collections.Counter();fitrows=[];allrows=[]
 for idx,m in enumerate(markets):
  raw=m['raw'];t=m['end_sec']*1000-120000;asset=str(m['token_ids'][0]);rr={'candidate_index':idx,'start_sec':m['start_sec'],'condition_id':m['condition_id'],'token_id':asset,'decision_ms':t,'window':int(idx*4//len(markets))}
  try:
   outcomes=json.loads(raw['outcomes']);tokens=json.loads(raw['clobTokenIds']);meta_prices=[float(v) for v in json.loads(raw['outcomePrices'])]
   identity=(outcomes==['Up','Down'] and list(map(str,tokens))==list(map(str,m['token_ids'])) and raw['conditionId'].lower()==m['condition_id'].lower() and len(set(tokens))==2)
  except (KeyError,ValueError,TypeError):identity=False;meta_prices=[]
  rr['identity_ok']=identity;pay=payouts.get(m['condition_id'],{});vector=(pay.get('up'),pay.get('down'),pay.get('den'));rr['payout_vector']=vector
  payoutok=identity and vector in ((1,0,1),(0,1,1))
  metaconsistent= len(meta_prices)==2 and meta_prices==[float(vector[0]),float(vector[1])] if payoutok else False
  rr['label_status']='verified_binary' if payoutok and metaconsistent else ('metadata_conflict' if payoutok else 'unknown_or_nonbinary')
  rr['y']=int(vector[0]) if rr['label_status']=='verified_binary' else None
  bbo,berr=choose(data['best_bid_ask'][asset],t,1000,'bbo');past,perr=choose(data['best_bid_ask'][asset],t-30000,1000,'bbo')
  book,serr=choose(data['book'][asset],t,5000,'book');bookpast,sperr=choose(data['book'][asset],t-30000,5000,'book')
  rr['bbo_status']=berr or 'ok';rr['history_bbo_status']=perr or 'ok';rr['snapshot_status']=serr or 'ok';rr['history_snapshot_status']=sperr or 'ok'
  if bbo:
   rr.update({'p':bbo['mid'],'spread':bbo['spread'],'bbo_age_ms':bbo['age_ms'],'bid':bbo['bid'],'ask':bbo['ask']})
  if book:rr.update({'depth':book['bid_size']+book['ask_size'],'imbalance':book['imbalance'],'snapshot_age_ms':book['age_ms']})
  if past:rr['mid_change_30s']=bbo['mid']-past['mid'] if bbo else None
  if book and bookpast:rr['imbalance_change_30s']=book['imbalance']-bookpast['imbalance']
  for k in ('p','spread','depth','imbalance','snapshot_age_ms','mid_change_30s','imbalance_change_30s'):rr.setdefault(k,None)
  coverage['candidate']+=1;coverage['label_'+rr['label_status']]+=1;coverage['bbo_'+rr['bbo_status']]+=1
  coverage['snapshot_'+rr['snapshot_status']]+=1;coverage['hist_bbo_'+rr['history_bbo_status']]+=1;coverage['hist_snapshot_'+rr['history_snapshot_status']]+=1
  if bbo and rr['y'] is not None:coverage['paired_score_eligible']+=1;fitrows.append(rr)
  allrows.append(rr)
 private=a.root/'_private/prediction_market_v4_development';private.mkdir(parents=True,exist_ok=True)
 pp=private/'b_event_table_private.json';pp.write_text(json.dumps(allrows,separators=(',',':'))+'\n')
 public={'status':'DEVELOPMENT_PRICING_REPLICATION / WITHIN_DAY_RETROSPECTIVE','source_archive_sha256':digest(a.archive),'candidate_events':len(markets),'coverage':dict(coverage),'eligible_train_cal_late':{k:sum(z['p'] is not None and z['y'] is not None for z in allrows[lo:hi]) for k,lo,hi in [('train',0,int(.5*len(allrows))),('calibration',int(.5*len(allrows)),int(.75*len(allrows))),('late',int(.75*len(allrows)),len(allrows))]},'label_verification':'CTF onchain payout vector and sample metadata identity/outcome price agreement; no quote-derived labels','terminal_label_publication_time':'unknown; offline retrospective only','network':network,'private_event_table_sha256':digest(pp),'features':'one per event, receive-time causal, no terminal/raw metadata feature','limitations':'snapshot is age-limited complete snapshot, not continuous replay; one day only'}
 out=a.root/'results/prediction_market_v4_development/b_coverage.json';out.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n');print(json.dumps({'candidate':len(markets),'eligible':coverage['paired_score_eligible'],'labels':coverage['label_verified_binary'],'network':network}))
if __name__=='__main__':main()
