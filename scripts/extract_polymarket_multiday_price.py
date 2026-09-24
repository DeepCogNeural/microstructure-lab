"""One-pass, fixed-window Rocklabs BTC-5m quote extraction. Raw output is private.

Only manifest-listed 2026-07-27..08-02 CLOB objects are scanned. The signed URL
column never enters public output. The original 96 GiB preflight remains intact.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, io, json, math, os, re, resource, shutil, subprocess, threading, time, zipfile
from collections import Counter, defaultdict
from pathlib import Path

START=1785110400
DAYS=('2026-07-27','2026-07-28','2026-07-29','2026-07-30','2026-07-31','2026-08-01','2026-08-02')
CAP=112*2**30
DEADLINE_UTC=dt.datetime(2026,9,24,21,3,tzinfo=dt.timezone.utc).timestamp()
MIN_FREE_BYTES=10*2**30
ZIP_MEMBER='poly-data-share/manifest.tsv'

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def iso_us(value):
    try:
        t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(dt.timezone.utc)
        delta=t-dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
        return (delta.days*86400+delta.seconds)*1000000+delta.microseconds
    except (ValueError,TypeError,AttributeError):return None

def number(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def parse_list(x):
    try:return json.loads(x) if isinstance(x,str) else x
    except (TypeError,ValueError):return None

def metadata_condition(payload):
    market=payload.get('market')
    return market.get('conditionId') if isinstance(market,dict) else market

def roster(gamma_path):
    items={}
    attempts=0
    for line in gamma_path.open():
        x=json.loads(line); slot=x['slot']; attempts+=x['attempts']
        if slot in items:raise ValueError('duplicate Gamma slot')
        items[slot]=x
    if set(items)!=set(range(7*288)):raise ValueError('incomplete fixed Gamma slot audit')
    events={};bad=Counter()
    for slot in sorted(items):
        x=items[slot]
        if x['status']!='ok':bad[x['status']]+=1;continue
        raw=x['response'];start=START+300*slot;slug=f'btc-updown-5m-{start}'
        ms=[m for m in raw.get('markets',[]) if m.get('slug')==slug]
        if raw.get('slug')!=slug or len(ms)!=1:bad['slug_or_market']+=1;continue
        m=ms[0]; outcomes=parse_list(m.get('outcomes'));tokens=parse_list(m.get('clobTokenIds'))
        if outcomes!=['Up','Down'] or not isinstance(tokens,list) or len(tokens)!=2 or len(set(map(str,tokens)))!=2:bad['token_orientation']+=1;continue
        end=iso_us(m.get('endDate'))
        if end!=(start+300)*1000000 or iso_us(raw.get('endDate'))!=end:bad['end_time']+=1;continue
        condition=m.get('conditionId')
        if not isinstance(condition,str) or not re.fullmatch('0x[0-9a-fA-F]{64}',condition):bad['condition']+=1;continue
        events[slot]={'slot':slot,'slug':slug,'start_sec':start,'end_sec':start+300,'date':DAYS[slot//288],
                      'condition_id':condition,'up_token':str(tokens[0]),'down_token':str(tokens[1]),
                      'gamma_sha256':x['sha256'],'gamma_outcome_prices':m.get('outcomePrices')}
    if len({v['condition_id'] for v in events.values()})!=len(events):raise ValueError('repeated condition')
    if len({v['up_token'] for v in events.values()})!=len(events):raise ValueError('repeated Up token')
    return events,bad,attempts

def source_registry(zip_path):
    zb=zip_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(zb)) as z:mb=z.read(ZIP_MEMBER)
    objects={};all_fixed=[]
    for line in csv.reader(io.StringIO(mb.decode()),delimiter='\t'):
        if len(line)!=3:raise ValueError('bad manifest row')
        size_text,path,url=line
        if path in objects:raise ValueError('duplicate source path')
        size=int(size_text)
        if size<0:raise ValueError('negative source size')
        objects[path]=(size,url)
        if any('/'+d+'/' in path for d in DAYS):all_fixed.append({'path':path,'size_bytes':size})
    if sum(x['size_bytes'] for x in all_fixed)>CAP:raise ValueError('112 GiB input cap exceeded by manifest')
    groups=defaultdict(list)
    for path,(size,url) in objects.items():
        m=re.fullmatch(r'raw/(2026-07-(?:27|28|29|30|31)|2026-08-0[12])/(\d{4})(?:_[^/]*)?\.jsonl\.zst',path)
        if m:groups[(m[1],m[2][:2])].append((path,size,url))
    if set(groups)!={(d,f'{h:02d}') for d in DAYS for h in range(24)}:raise ValueError('CLOB hourly paths incomplete')
    return groups,sorted(all_fixed,key=lambda x:x['path']),sha_bytes(zb),sha_bytes(mb)

def local_source(base,path):
    if path=='raw/2026-07-28/0800.jsonl.zst':return base/'sample-2026-07-28-0800/clob.jsonl.zst'
    if path in ('raw/2026-07-29/0800.jsonl.zst','raw/2026-07-30/0800.jsonl.zst'):
        return base/'validation-windows'/path
    return None

def quote_summary(y):
    bid=number(y.get('best_bid'));ask=number(y.get('best_ask'))
    valid=bid is not None and ask is not None and 0<bid<ask<1
    return {'bid':bid,'ask':ask,'valid':valid}

def book_summary(y):
    out={'valid_top':False,'valid_size':False,'bid':None,'ask':None,'bid_size':None,'ask_size':None,'reason':None}
    sides=[]
    for key in ('bids','asks'):
        levels=y.get(key)
        if not isinstance(levels,list) or not levels:out['reason']='empty_or_nonlist';return out
        pairs=[];seen=set()
        for z in levels:
            if not isinstance(z,dict):out['reason']='invalid_level';return out
            price=number(z.get('price'));size=number(z.get('size'))
            if price is None or size is None or not 0<price<1 or size<=0:
                out['reason']='nonfinite_or_nonpositive';return out
            if price in seen:out['reason']='duplicate_level';return out
            seen.add(price);pairs.append((price,size))
        sides.append(pairs)
    bp,bs=max(sides[0],key=lambda z:z[0]);ap,az=min(sides[1],key=lambda z:z[0])
    if bp>=ap:out['reason']='crossed_or_locked';return out
    out.update(valid_top=True,valid_size=True,bid=bp,ask=ap,bid_size=bs,ask_size=az)
    return out

def update(old,new,kind):
    if old is None or new['recv_us']>old['recv_us']:
        return {**new,'price_conflict':False,'size_conflict':False}
    if new['recv_us']<old['recv_us']:return old
    if (old['bid'],old['ask'])!=(new['bid'],new['ask']) or old['valid']!=new['valid']:
        old['price_conflict']=True
    if kind=='book' and (old.get('bid_size'),old.get('ask_size'),old.get('reason'))!=(new.get('bid_size'),new.get('ask_size'),new.get('reason')):
        old['size_conflict']=True
    return old

def choose(rec,cutoff_us,max_age_us,kind):
    if rec is None:return None,'no_record'
    if rec['price_conflict']:return None,'conflicting_same_receive_top'
    if cutoff_us-rec['recv_us']>max_age_us:return None,'stale'
    if kind=='book':
        if not rec['valid_top']:return None,'invalid_book_top_'+str(rec['reason'])
        if rec['size_conflict']:return None,'conflicting_same_receive_size'
        if not rec['valid_size']:return None,'invalid_book_size_'+str(rec['reason'])
    elif not rec['valid']:return None,'invalid_bbo'
    return rec,None

def stream_object(path,size,url,local,pattern_file,process):
    source=None;srcproc=None
    if local is not None and local.is_file():source=local.open('rb');origin='local'
    else:
        srcproc=subprocess.Popen(['curl','-fSLsS','--max-time','900',url],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        source=srcproc.stdout;origin='source_url'
    dec=subprocess.Popen(['zstd','-dc'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    filt=subprocess.Popen(['rg','-F','-f',str(pattern_file)],stdin=dec.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    dec.stdout.close()
    digest=hashlib.sha256();seen=[0];error=[]
    def feed():
        try:
            for chunk in iter(lambda:source.read(1<<20),b''):
                digest.update(chunk);seen[0]+=len(chunk);dec.stdin.write(chunk)
        except Exception as exc:error.append(type(exc).__name__)
        finally:
            try:dec.stdin.close()
            except OSError:pass
            source.close()
    worker=threading.Thread(target=feed,daemon=True);worker.start()
    parse_error=None
    try:
        for line in filt.stdout:process(line)
    except Exception as exc:parse_error=exc
    finally:
        filt.stdout.close();worker.join(timeout=30)
        frc=filt.wait(timeout=30);drc=dec.wait(timeout=30)
        serr=dec.stderr.read(200);dec.stderr.close();filt.stderr.close()
        src_rc=srcproc.wait(timeout=30) if srcproc else 0
        if srcproc:srcproc.stderr.close()
    if parse_error:raise parse_error
    if error or seen[0]!=size or src_rc!=0 or drc!=0 or frc not in (0,1):
        raise RuntimeError(f'source_scan_failure origin={origin} bytes={seen[0]} expected={size} curl={src_rc} zstd={drc} rg={frc} pump={error} zstd_error={bool(serr)}')
    return {'path':path,'size_bytes':size,'read_bytes':seen[0],'read_sha256':digest.hexdigest(),'origin':origin}

def extract_hour(day,hour,objects,events,patterns,base,output):
    slots={i:e for i,e in events.items() if e['date']==day and e['start_sec']//3600%24==int(hour)}
    tokens={e['up_token']:i for i,e in slots.items()}
    states={i:{'bbo_end':None,'bbo_past':None,'book_end':None,'metadata_seen':False,'metadata_conflict':False} for i in slots}
    counts=Counter();unknown_metadata=set()
    def process(line):
        nonlocal counts
        x=json.loads(line);c=x.get('content');c=json.loads(c) if isinstance(c,str) else c
        recv=iso_us(x.get('timestamp'))
        if recv is None:counts['invalid_receive_timestamp']+=1;return
        ys=c if isinstance(c,list) else [c]
        for y in ys:
            if not isinstance(y,dict):continue
            if x.get('message_type')=='market_metadata':
                slug=str(y.get('event_slug',''))
                if slug.startswith('btc-updown-5m-'):
                    counts['btc_metadata_rows']+=1
                    try:slot=(int(slug.rsplit('-',1)[-1])-START)//300
                    except ValueError:continue
                    if slot in states:
                        if str(y.get('token_id'))==events[slot]['up_token']:
                            states[slot]['metadata_seen']=True
                            condition=metadata_condition(y)
                            if str(condition).lower()!=events[slot]['condition_id'].lower():states[slot]['metadata_conflict']=True
                    else:unknown_metadata.add(slug)
                continue
            typ=y.get('event_type')
            if typ=='price_change':
                for change in y.get('price_changes') or []:
                    if not isinstance(change,dict):continue
                    slot=tokens.get(str(change.get('asset_id')))
                    if slot is None:continue
                    counts['target_bbo_items']+=1
                    e=events[slot];end=(e['end_sec']-120)*1000000;past=end-30000000
                    if recv>end:continue
                    q={'recv_us':recv,**quote_summary(change)}
                    s=states[slot];s['bbo_end']=update(s['bbo_end'],q,'bbo')
                    if recv<=past:s['bbo_past']=update(s['bbo_past'],q,'bbo')
            elif typ=='book':
                slot=tokens.get(str(y.get('asset_id')))
                if slot is None:continue
                counts['target_book_rows']+=1
                e=events[slot];end=(e['end_sec']-120)*1000000
                if recv>end:continue
                b=book_summary(y);b['recv_us']=recv;b['valid']=b['valid_top']
                s=states[slot];s['book_end']=update(s['book_end'],b,'book')
    receipts=[]
    for path,size,url in objects:
        receipt=stream_object(path,size,url,local_source(base,path),patterns,process)
        receipts.append(receipt)
    out=[]
    for slot,e in slots.items():
        s=states[slot];end=(e['end_sec']-120)*1000000
        q,qe=choose(s['bbo_end'],end,1000000,'bbo')
        past,pe=choose(s['bbo_past'],end-30000000,1000000,'bbo')
        book,be=choose(s['book_end'],end,5000000,'book')
        row={'slot':slot,'date':day,'identity_status':'metadata_conflict' if s['metadata_conflict'] else 'gamma_verified',
             'metadata_seen':s['metadata_seen'],'bbo_status':qe or 'ok','history_status':pe or 'ok','snapshot_status':be or 'ok',
             'decision_us':end,'p':None,'spread':None,'bid':None,'ask':None,'bbo_age_ms':None,
             'mid_change_30s':None,'depth':None,'imbalance':None,'snapshot_age_ms':None}
        if q:
            row.update(p=(q['bid']+q['ask'])/2,spread=q['ask']-q['bid'],bid=q['bid'],ask=q['ask'],bbo_age_ms=(end-q['recv_us'])/1000)
            if past:row['mid_change_30s']=row['p']-(past['bid']+past['ask'])/2
        if book:
            bs,az=book['bid_size'],book['ask_size']
            row.update(depth=bs+az,imbalance=(bs-az)/(bs+az),snapshot_age_ms=(end-book['recv_us'])/1000)
        out.append(row)
    result={'date':day,'hour':hour,'events':out,'source_receipts':receipts,'counts':dict(counts),
            'unknown_btc_metadata_count':len(unknown_metadata)}
    output.write_text(json.dumps(result,separators=(',',':'))+'\n');os.chmod(output,0o600)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-zip',type=Path,required=True);ap.add_argument('--gamma-cache',type=Path,required=True)
    ap.add_argument('--private-dir',type=Path,required=True);ap.add_argument('--source-base',type=Path,required=True)
    ap.add_argument('--prior-read-bytes',type=int,default=0)
    a=ap.parse_args();private=a.private_dir;private.mkdir(parents=True,exist_ok=True);os.chmod(private,0o700)
    groups,registry,zip_hash,manifest_hash=source_registry(a.source_zip)
    events,bad,requests=roster(a.gamma_cache)
    if requests>10000:raise ValueError('Gamma request cap')
    frozen={'protocol':'POLYMARKET_MULTIDAY_PRICE_INFORMATION_ONLY','window':list(DAYS),'source_zip_sha256':zip_hash,
            'source_manifest_sha256':manifest_hash,'fixed_manifest_objects':registry,'gamma_cache_sha256':sha_bytes(a.gamma_cache.read_bytes()),
            'gamma_requests':requests,'gamma_valid_events':len(events),'gamma_invalid_reasons':dict(bad),
            'rules':{'decision':'end_minus_120s','history':'30s','bbo_age_ms_max':1000,'snapshot_age_ms_max':5000,
                     'latest_raw_before_validity':True,'one_up_token_per_event':True,'source_read_cap_bytes':CAP}}
    freeze_path=private/'freeze_private.json'
    if freeze_path.exists():
        old=json.loads(freeze_path.read_text())
        if old!=frozen:raise ValueError('freeze mismatch; refusing to resume')
    else:freeze_path.write_text(json.dumps(frozen,indent=2,sort_keys=True)+'\n');os.chmod(freeze_path,0o600)
    (private/'roster_private.json').write_text(json.dumps(events,separators=(',',':'))+'\n')
    patterns=private/'patterns_private.txt';patterns.write_text('btc-updown-5m-\n'+'\n'.join(e['up_token'] for e in events.values())+'\n');os.chmod(patterns,0o600)
    hour_dir=private/'hours';hour_dir.mkdir(exist_ok=True)
    if a.prior_read_bytes<0:raise ValueError('negative prior read bytes')
    scanned=a.prior_read_bytes;done=0;start=time.monotonic()
    for day in DAYS:
        for h in range(24):
            if time.time()>=DEADLINE_UTC:raise RuntimeError('four-hour wall deadline reached')
            cpu=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
            cpu+=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime+resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime
            if cpu>32*3600:raise RuntimeError('32 CPU-core-hour cap reached')
            if shutil.disk_usage(private).free<MIN_FREE_BYTES:raise RuntimeError('local free space below 10 GiB')
            hour=f'{h:02d}';out=hour_dir/f'{day}-{hour}.json'
            if out.exists():
                x=json.loads(out.read_text());scanned+=sum(r['read_bytes'] for r in x['source_receipts']);done+=1;continue
            planned=sum(z[1] for z in groups[(day,hour)])
            if scanned+planned>CAP:raise RuntimeError('actual compressed input cap would be exceeded')
            x=extract_hour(day,hour,groups[(day,hour)],events,patterns,a.source_base,out)
            scanned+=sum(r['read_bytes'] for r in x['source_receipts']);done+=1
            if done%4==0:print('hours',done,'of',168,'compressed_bytes',scanned,'wall_s',round(time.monotonic()-start,1),flush=True)
    print('FINAL hours',done,'compressed_bytes',scanned,'wall_s',round(time.monotonic()-start,1),flush=True)
if __name__=='__main__':main()
