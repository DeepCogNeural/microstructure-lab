"""Read-only CTF token-ID validation for the pinned binary market cohort."""
from __future__ import annotations
import argparse,gzip,hashlib,json,subprocess,time
from pathlib import Path
CTF='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045';USDC_E='2791Bca1f2de4661ED88A30C99A7a9449Aa84174';RPC='https://polygon-bor-rpc.publicnode.com'
def call(calls):
 out={};requests=0;bytes_=0
 for start in range(0,len(calls),60):
  chunk=calls[start:start+60];body=json.dumps([x[1] for x in chunk]);resp=None
  for j in range(3):
   p=subprocess.run(['curl','-sS','--max-time','25','-H','content-type: application/json','--data-binary','@-',RPC],input=body,text=True,capture_output=True,timeout=30);requests+=1;bytes_+=len(p.stdout.encode())
   try:
    a=json.loads(p.stdout)
    if p.returncode==0 and isinstance(a,list) and len(a)==len(chunk):resp={x['id']:x for x in a};break
   except ValueError:pass
   time.sleep(.5*(j+1))
  if resp is None:raise RuntimeError('RPC batch failed after retries')
  for key,req in chunk:
   x=resp.get(req['id'],{}).get('result')
   if not isinstance(x,str) or len(x)!=66:raise RuntimeError('RPC call missing result')
   out[key]=x
 return out,requests,bytes_
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--sample-root',type=Path,required=True);a=ap.parse_args()
 path=next((a.sample_root/'markets'/'BTC-5m').glob('*.jsonl.gz'))
 with gzip.open(path,'rt') as f:markets=[json.loads(s) for s in f if s.strip()]
 markets=[m for m in markets if 1788825600<=m['start_sec'] and m['end_sec']<=1788912000 and str(m['asset']).lower()=='btc' and m['interval_sec']==300];markets.sort(key=lambda m:(m['start_sec'],m['condition_id']))
 if len(markets)!=288:raise ValueError('unexpected markets')
 calls=[];idx=0
 for i,m in enumerate(markets):
  for j,slot in enumerate((1,2)):
   idx+=1;data='0x856296f7'+'0'*64+m['condition_id'][2:]+f'{slot:064x}';calls.append(((i,j),{'jsonrpc':'2.0','id':idx,'method':'eth_call','params':[{'to':CTF,'data':data},'latest']}))
 collections,r1,b1=call(calls);calls=[]
 for (i,j),col in collections.items():
  idx+=1;data='0x39dd7530'+USDC_E.lower().rjust(64,'0')+col[2:];calls.append(((i,j),{'jsonrpc':'2.0','id':idx,'method':'eth_call','params':[{'to':CTF,'data':data},'latest']}))
 positions,r2,b2=call(calls);matches=0;mismatch=[]
 for i,m in enumerate(markets):
  ok=all(str(int(positions[(i,j)],16))==str(m['token_ids'][j]) for j in (0,1))
  matches+=ok
  if not ok:mismatch.append(i)
 public={'status':'DONE' if matches==288 else 'BLOCKED_WITH_EVIDENCE','candidate_events':len(markets),'both_token_ids_ctf_verified':matches,'mismatch_count':len(mismatch),'verification':'CTF getCollectionId for index sets 1/2 and getPositionId with USDC.e collateral, matched to frozen sample ordered token IDs','network_http_requests':r1+r2,'network_response_bytes':b1+b2,'source_markets_gzip_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 pp=a.root/'_private/prediction_market_v4_development/b_token_mismatch_private.json';pp.write_text(json.dumps(mismatch)+'\n')
 out=a.root/'results/prediction_market_v4_development/b_token_identity.json';out.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n');print(json.dumps({'match':matches,'total':len(markets),'http_requests':r1+r2}))
if __name__=='__main__':main()
