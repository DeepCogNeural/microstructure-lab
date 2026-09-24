"""Bounded resumable read-only Blockscout receipt cache for frozen QOP hashes."""
import argparse, concurrent.futures, hashlib, json, os, pathlib, threading, time, urllib.parse, urllib.request

p=argparse.ArgumentParser()
p.add_argument('--selection-private',type=pathlib.Path,required=True)
p.add_argument('--cache-dir',type=pathlib.Path,required=True)
p.add_argument('--workers',type=int,default=6)
a=p.parse_args()
if not 1<=a.workers<=8:raise ValueError('workers >8')
x=json.loads(a.selection_private.read_text())
hashes=[t['hash'] for e in x['events'] for t in e['transactions']]
if len(hashes)>2000 or len(set(hashes))!=len(hashes):raise ValueError('hash budget/duplicates')
a.cache_dir.mkdir(parents=True,exist_ok=True)
lock=threading.Lock();next_at=[0.0];bytes_total=[0]
def get(url):
    last=None
    for attempt in range(5):
        with lock:
            wait=max(0,next_at[0]-time.monotonic());next_at[0]=max(next_at[0],time.monotonic())+0.65
        if wait:time.sleep(wait)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'QOP-development-audit/1.0'})
            with urllib.request.urlopen(req,timeout=18) as r:
                blob=r.read()
            with lock:bytes_total[0]+=len(blob)
            return json.loads(blob)
        except Exception as exc:
            last=type(exc).__name__+': '+str(exc)
            time.sleep((attempt+1)*3.0)
    raise RuntimeError(last)
def job(h):
    path=a.cache_dir/(h.removeprefix('0x')+'.json')
    if path.exists():
        try:
            d=json.loads(path.read_text())
            if d.get('hash')==h and d.get('complete') is True:return 'cached'
        except Exception:pass
    out={'hash':h,'complete':False,'tx':None,'logs':None,'error':None}
    try:
        base='https://polygon.blockscout.com/api/v2/transactions/'+h
        out['tx']=get(base)
        logs=[];params=None;pages=0
        while True:
            url=base+'/logs'+('?' + urllib.parse.urlencode(params) if params else '')
            page=get(url)
            logs.extend(page['items']);pages+=1
            params=page.get('next_page_params')
            if not params:break
            if pages>=20:raise RuntimeError('log pagination >20')
        out['logs']={'items':logs,'next_page_params':None,'pages':pages}
        out['complete']=True
    except Exception as exc:
        out['error']=type(exc).__name__+': '+str(exc)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(out,separators=(',',':'))+'\n')
    os.replace(tmp,path)
    return 'ok' if out['complete'] else 'failed'
start=time.monotonic();counts={'ok':0,'cached':0,'failed':0}
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
    futures=[pool.submit(job,h) for h in hashes]
    for n,f in enumerate(concurrent.futures.as_completed(futures),1):
        counts[f.result()]+=1
        if n%100==0 or n==len(hashes):
            print(json.dumps({'done':n,'total':len(hashes),**counts,'new_http_bytes':bytes_total[0],'elapsed_s':round(time.monotonic()-start,1)}),flush=True)
