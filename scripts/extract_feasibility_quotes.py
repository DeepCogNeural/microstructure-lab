"""Extract only preregistered feasibility tokens from three fixed source hours."""
import csv,datetime as dt,hashlib,io,json,math,re,shutil,time,urllib.request,zipfile
from pathlib import Path
import zstandard
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--work-dir',type=Path,required=True)
args=parser.parse_args()
ROOT=args.repo;OUT=args.work_dir;RAW=OUT/'quote_raw';RAW.mkdir(exist_ok=True)
def us(x):
 d=dt.datetime.fromisoformat(x.replace('Z','+00:00'));e=d-dt.datetime(1970,1,1,tzinfo=dt.timezone.utc);return (e.days*86400+e.seconds)*1000000+e.microseconds
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
targets=json.load(open(OUT/'clob_targets_private.json'));bytoken={t['token']:{**t,'decision_us':us(t['decision'])} for t in targets};states={};logs=[]
manifest=json.load(open(OUT/'feasibility_clob_manifest.json'))
with zipfile.ZipFile(ROOT/'_private/rocklabs/2026-09-23/poly-data-share.zip') as z:rows=list(csv.reader(io.StringIO(z.read('poly-data-share/manifest.tsv').decode()),delimiter='\t'))
source={r[1]:(int(r[0]),r[2]) for r in rows};pattern=re.compile('|'.join(re.escape(t) for t in bytoken));start=time.monotonic()
def add(tok,kind,recv,bid,ask,inner,path):
 t=bytoken.get(str(tok))
 if t is None or recv>t['decision_us']:return
 key=(str(tok),kind);v={'receive_us':recv,'bid':bid,'ask':ask,'source_event_time':inner,'source':path};old=states.get(key)
 if old is None or recv>old['receive_us']:states[key]={**v,'pairs':[[bid,ask]]}
 elif recv==old['receive_us'] and [bid,ask] not in old['pairs']:old['pairs'].append([bid,ask])
def num(x):
 try:return float(x)
 except (ValueError,TypeError):return None
def quote_status(v,kind):
 if v is None:return 'no_record_before_decision_in_selected_hours'
 if kind=='snapshot_top':return 'diagnostic_unvalidated'
 if len(v['pairs'])>1:return 'conflicting_latest'
 bid,ask=v['bid'],v['ask']
 if bid is None or ask is None or not math.isfinite(bid) or not math.isfinite(ask):return 'invalid_latest'
 if 0<bid<ask<1:return 'valid'
 if 0<=bid<=ask<=1:return 'boundary_or_locked_latest'
 return 'invalid_latest'
for obj in manifest['objects']:
 path=obj['path'];size,url=source[path];local=RAW/(path.replace('/','__'));ledger={'path':path,'expected_bytes':size,'attempts':0,'downloaded_bytes':0};s=time.monotonic();cpu=time.process_time()
 if not local.exists():
  if shutil.disk_usage(RAW).free-size<10*1024**3:raise RuntimeError('disk reserve')
  for attempt in range(3):
   ledger['attempts']+=1
   try:
    with urllib.request.urlopen(url,timeout=60) as response,local.with_suffix('.part').open('wb') as f:
     while True:
      b=response.read(1024*1024)
      if not b:break
      f.write(b);ledger['downloaded_bytes']+=len(b)
    if local.with_suffix('.part').stat().st_size!=size:raise ValueError('source byte mismatch')
    local.with_suffix('.part').rename(local);break
   except Exception as e:
    ledger.setdefault('errors',[]).append(type(e).__name__)
    if attempt==2:raise RuntimeError('download failed '+path) from None
    time.sleep(2*(attempt+1))
 if local.stat().st_size!=size:raise ValueError('existing source byte mismatch')
 ledger['sha256']=sha(local);ledger['lines']=0;ledger['selected_lines']=0
 with zstandard.open(local,'rt') as f:
  for line in f:
   ledger['lines']+=1
   if not pattern.search(line):continue
   ledger['selected_lines']+=1;x=json.loads(line);recv=us(x['timestamp']);c=x['content'];c=json.loads(c) if isinstance(c,str) else c
   for y in c if isinstance(c,list) else [c]:
    if not isinstance(y,dict):continue
    kind=y.get('event_type')
    if kind=='price_change':
     for p in y.get('price_changes',[]):add(p.get('asset_id'),'direct_bbo',recv,num(p.get('best_bid')),num(p.get('best_ask')),y.get('timestamp'),path)
    elif kind=='book' and str(y.get('asset_id')) in bytoken:
     bids=[num(p.get('price')) for p in y.get('bids',[]) if num(p.get('size')) is not None and num(p.get('size'))>0];asks=[num(p.get('price')) for p in y.get('asks',[]) if num(p.get('size')) is not None and num(p.get('size'))>0]
     bid=max(bids) if bids and all(v is not None for v in bids) else None;ask=min(asks) if asks and all(v is not None for v in asks) else None
     add(y.get('asset_id'),'snapshot_top',recv,bid,ask,y.get('timestamp'),path)
 ledger['wall_seconds']=time.monotonic()-s;ledger['cpu_seconds']=time.process_time()-cpu;logs.append(ledger);save(OUT/'quote_source_receipts.json',logs);print(json.dumps(ledger),flush=True)
result=[]
for tok,t in bytoken.items():
 for kind in ['direct_bbo','snapshot_top']:
  v=states.get((tok,kind));r={**t,'kind':kind}
  if v is None:r['status']='no_record_before_decision_in_selected_hours'
  else:
   r.update(v);r['age_ms']=(t['decision_us']-v['receive_us'])/1000;bid,ask=v['bid'],v['ask']
   r['status']='valid' if bid is not None and ask is not None and math.isfinite(bid) and math.isfinite(ask) and 0<=bid<=ask<=1 else 'invalid_latest'
   if len(v['pairs'])>1:r['status']='conflicting_latest'
  r['inclusive_arithmetic_status']=r['status'];r['status']=quote_status(v,kind)
  result.append(r)
save(OUT/'feasibility_quotes_private.json',result)
summary=[]
for category,example in sorted({(t['category'],t['example']) for t in targets}):
 for kind in ['direct_bbo','snapshot_top']:
  selected=[r for r in result if (r['category'],r['example'],r['kind'])==(category,example,kind)];counts={s:sum(r['status']==s for r in selected) for s in sorted({r['status'] for r in selected})};ages=[r['age_ms'] for r in selected if 'age_ms' in r]
  summary.append({'category':category,'example':example,'kind':kind,'tokens':len(selected),'status_counts':counts,'age_ms_min':min(ages) if ages else None,'age_ms_max':max(ages) if ages else None})
save(OUT/'feasibility_quotes_aggregate.json',{'selection_manifest_sha256':sha(OUT/'feasibility_clob_manifest.json'),'private_quote_sha256':sha(OUT/'feasibility_quotes_private.json'),'summary':summary,'sources':logs,'wall_seconds':time.monotonic()-start,'note':'No freshness gate imposed. Source outer ISO timestamp mapped to receive time; latest invalid not replaced with older valid. Strict direct BBO requires 0<bid<ask<1; inclusive arithmetic status retained. Snapshot tops are unvalidated diagnostics and never certify connection.'})
