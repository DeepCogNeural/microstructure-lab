"""Fetch only the frozen BTC-5m calendar slugs to a private raw response cache."""
import concurrent.futures, datetime as dt, hashlib, json, os, subprocess, sys, time
from pathlib import Path
START=int(dt.datetime(2026,7,27,tzinfo=dt.timezone.utc).timestamp())
N=7*288
OUT=Path(sys.argv[1]); OUT.parent.mkdir(parents=True,exist_ok=True)
if OUT.exists():raise SystemExit('refusing to overwrite cache')
def one(i):
    slug=f'btc-updown-5m-{START+i*300}'
    url='https://gamma-api.polymarket.com/events/slug/'+slug
    for attempt in range(3):
        p=subprocess.run(['curl','-sS','-L','--max-time','25','-H','User-Agent: Mozilla/5.0','-H','Accept: application/json','-w','\n%{http_code}',url],capture_output=True,text=True,timeout=30)
        try:
            raw,code=p.stdout.rsplit('\n',1)
            if p.returncode==0 and code=='200':
                x=json.loads(raw)
                if x.get('slug')!=slug:raise ValueError('slug mismatch')
                return {'slot':i,'status':'ok','attempts':attempt+1,'sha256':hashlib.sha256(raw.encode()).hexdigest(),'response':x}
            if code=='404':return {'slot':i,'status':'not_found','attempts':attempt+1}
        except (ValueError,json.JSONDecodeError):pass
        time.sleep(.3*(attempt+1))
    return {'slot':i,'status':'failed','attempts':3}
start=time.monotonic();counts={}
with OUT.open('x') as f:
    os.chmod(OUT,0o600)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures=[ex.submit(one,i) for i in range(N)]
        for j,fut in enumerate(concurrent.futures.as_completed(futures),1):
            x=fut.result();counts[x['status']]=counts.get(x['status'],0)+1
            f.write(json.dumps(x,separators=(',',':'))+'\n')
            if j%100==0:
                f.flush();print('completed',j,'ok',counts.get('ok',0),'missing',counts.get('not_found',0),'failed',counts.get('failed',0),'elapsed_s',round(time.monotonic()-start,1),flush=True)
print('FINAL',json.dumps(counts,sort_keys=True),'elapsed_s',round(time.monotonic()-start,1),flush=True)
