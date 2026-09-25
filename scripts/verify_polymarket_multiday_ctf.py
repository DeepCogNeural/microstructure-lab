"""Resume the frozen BTC-5m cohort with keyed, durable, bounded CTF queries.

Raw responses, semantic keys, token identities and labels remain private. The
legacy importer reconstructs the exact 2458c591 request order before assigning
responses to keys; new batching never determines cache identity.
"""
from __future__ import annotations
import argparse, datetime as dt, email.utils, fcntl, hashlib, json, os, re
import resource, shutil, subprocess, tempfile, time
from collections import Counter
from pathlib import Path

CTF='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
USDC_E='2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
RPC='https://polygon-bor-rpc.publicnode.com'
DAYS=('2026-07-27','2026-07-28','2026-07-29','2026-07-30','2026-07-31','2026-08-01','2026-08-02')
SOURCE_VERSION='polygon-publicnode-ctf/2458c591-legacy-v1'
BATCH=25

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def atomic(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    with open(tmp,'w') as f:
        os.chmod(tmp,0o600);json.dump(obj,f,sort_keys=True,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
    fd=os.open(p.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def index_mapping(root):
    mapping={};hashes={}
    for day in DAYS:
        p=root/day/'onchain_index.json';hashes[day]=sha(p)
        for token,condition in json.loads(p.read_text())['token_to_condition'].items():
            token=str(token);condition=str(condition).lower()
            if token in mapping and mapping[token]!=condition: raise ValueError('index identity contradiction')
            mapping[token]=condition
    return mapping,hashes

def call_spec(data,condition=None,index=None,block='latest',method='eth_call',params=None):
    return {'chain':137,'contract':CTF.lower(),'method':method,
            'params':params if params is not None else [{'to':CTF,'data':data},block],
            'condition':condition.lower() if condition else None,'outcome_index':index,
            'block_tag':block,'source_version':SOURCE_VERSION}
def collection_spec(e,j):
    c=e['condition_id'];return call_spec('0x856296f7'+'0'*64+c[2:]+f'{j:064x}',c,j-1)
def position_spec(e,j,col):
    return call_spec('0x39dd7530'+USDC_E.lower().rjust(64,'0')+col[2:],e['condition_id'],j-1)
def payout_spec(e,kind):
    c=e['condition_id'];i={'n0':0,'n1':1,'den':None}[kind]
    data=('0xdd34de67' if i is None else '0x0504c814')+c[2:]+('' if i is None else f'{i:064x}')
    return call_spec(data,c,i)

def valid_result(value,spec):
    if not isinstance(value,str):return False
    if spec['method']=='eth_call':return re.fullmatch(r'0x[0-9a-fA-F]{64}',value) is not None
    if spec['method'] in ('eth_chainId','eth_blockNumber'):
        return re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)',value) is not None
    return False

def validate(payload,requests):
    """Structural ID failure rejects batch; otherwise preserve each valid item."""
    expected={q['id'] for q in requests}
    if len(expected)!=len(requests):raise ValueError('duplicate request ids')
    if not isinstance(payload,list) or any(not isinstance(x,dict) for x in payload):raise ValueError('invalid RPC batch')
    ids=[x.get('id') for x in payload]
    if any(type(i) is not int for i in ids) or len(set(ids))!=len(ids) or set(ids)!=expected:raise ValueError('RPC id set/uniqueness mismatch')
    by_id={q['id']:q for q in requests};good={};bad={}
    for item in payload:
        i=item['id']
        if item.get('jsonrpc')!='2.0' or 'error' in item or not valid_result(item.get('result'),by_id[i]['spec']):
            bad[i]='rpc_error_or_invalid_result'
        else:good[i]=item['result'].lower()
    return good,bad

class Rpc:
    def __init__(self,root,deadline,transport=None,sleeper=time.sleep,now=time.time):
        self.root=root;root.mkdir(parents=True,exist_ok=True)
        self.success=root/'success.json';self.ledger_path=root/'ledger.json'
        self.cache=json.loads(self.success.read_text()) if self.success.exists() else {}
        self.ledger=json.loads(self.ledger_path.read_text()) if self.ledger_path.exists() else {
            'logical_calls':0,'http_requests':0,'retry_logical_calls':0,'retry_http_requests':0,
            'response_bytes':0,'attempts':{},'attempt_log':[],'last_success_time':now(),
            'last_send_time':0,'blocked_reason':None}
        self.deadline=deadline;self.transport=transport or self.curl;self.sleep=sleeper;self.now=now
        # Recover a saved reply if interrupted before cache/ledger finalization.
        for record in self.ledger['attempt_log']:
            if record['state']!='reserved_before_send':continue
            reply=root/f"reply_{record['http_sequence']:05d}.json"
            if reply.exists() and 'specs' in record:
                raw=json.loads(reply.read_text());body=raw['body'].encode()
                self.ledger['response_bytes']+=len(body)
                requests=[{'id':i+1,'spec':s} for i,s in enumerate(record['specs'])]
                good={}
                try:
                    if raw['http_status']!=200 or raw['error']:raise ValueError('saved transport error')
                    good,_=validate(json.loads(raw['body']),requests)
                except (ValueError,TypeError):pass
                for q in requests:
                    if q['id'] in good:self.save(q['spec'],good[q['id']],{'reply_sha256':sha(reply),'http_sequence':record['http_sequence'],'block_number':'unknown_latest'})
                record.update(state='recovered_saved_response',bytes=len(body),successes=len(good))
                if good:self.ledger['last_success_time']=now()
        # Unknown post-send/pre-save responses reserve the transport maximum.
        self.ledger['unknown_response_bytes_reserved']=sum(1048576 for r in self.ledger['attempt_log'] if r['state']=='reserved_before_send')
        atomic(self.success,self.cache)
        self.persist()
    def persist(self):atomic(self.ledger_path,self.ledger)
    def get(self,spec):
        hit=self.cache.get(digest(spec))
        if hit is None:return None
        if hit['spec']!=spec or not valid_result(hit['result'],spec):raise ValueError('corrupt semantic cache')
        return hit['result']
    def save(self,spec,result,provenance):
        key=digest(spec);old=self.get(spec)
        if old is not None and old!=result:raise ValueError('conflicting successful response')
        self.cache[key]={'spec':spec,'result':result,'provenance':provenance}
    def curl(self,body):
        with tempfile.TemporaryDirectory(dir=self.root) as td:
            p=Path(td);h=p/'headers';b=p/'body'
            command=['curl','-sS','--max-time','30','--max-filesize','1048576','-D',str(h),'-o',str(b),
                     '-w','%{http_code}','-H','content-type: application/json','--data-binary','@-',RPC]
            try:
                r=subprocess.run(command,input=json.dumps(body),text=True,capture_output=True,timeout=35)
                status=int(r.stdout) if r.stdout.isdigit() else 0;error=None if r.returncode==0 else 'curl_exit_'+str(r.returncode)
            except subprocess.TimeoutExpired:status=0;error='transport_timeout'
            raw=b.read_bytes() if b.exists() else b'';retry_after=0.0
            if h.exists():
                for line in h.read_text(errors='replace').splitlines():
                    if line.lower().startswith('retry-after:'):
                        v=line.split(':',1)[1].strip()
                        try:retry_after=max(retry_after,float(v))
                        except ValueError:
                            try:retry_after=max(retry_after,email.utils.parsedate_to_datetime(v).timestamp()-self.now())
                            except (TypeError,ValueError):pass
            return status,raw,max(0,retry_after),error
    def call(self,specs):
        unique={digest(s):s for s in specs};pending=[s for s in unique.values() if self.get(s) is None]
        while pending:
            if self.ledger['blocked_reason']:break
            # Exhausted keys are not resent, but other independent keys proceed.
            available=[s for s in pending if self.ledger['attempts'].get(digest(s),0)<3]
            if not available:break
            batch=available[:BATCH];keys=[digest(s) for s in batch]
            now=self.now();reason=None
            if now>=self.deadline:reason='wall_deadline'
            elif now-self.ledger['last_success_time']>=600:reason='ten_minutes_without_success'
            elif self.ledger['logical_calls']+len(batch)>30000:reason='logical_budget'
            elif self.ledger['http_requests']+1>2000:reason='http_budget'
            elif self.ledger['response_bytes']+self.ledger.get('unknown_response_bytes_reserved',0)+1048576>536870912:reason='response_budget_reserve'
            elif shutil.disk_usage(self.root).free<10*1024**3:reason='disk_free_below_10GiB'
            if reason:self.ledger['blocked_reason']=reason;self.persist();break
            retry_n=sum(self.ledger['attempts'].get(k,0)>0 for k in keys)
            delay=max(0,1-(now-self.ledger['last_send_time']))
            if retry_n:delay=max(delay,2**max(self.ledger['attempts'].get(k,0) for k in keys))
            self.sleep(delay)
            if self.now()>=self.deadline:self.ledger['blocked_reason']='wall_deadline';self.persist();break
            seq=self.ledger['http_requests']+1
            requests=[{'id':i+1,'spec':s} for i,s in enumerate(batch)]
            body=[{'jsonrpc':'2.0','id':q['id'],'method':q['spec']['method'],'params':q['spec']['params']} for q in requests]
            self.ledger['logical_calls']+=len(batch);self.ledger['http_requests']+=1
            self.ledger['retry_logical_calls']+=retry_n;self.ledger['retry_http_requests']+=int(retry_n>0)
            for k in keys:self.ledger['attempts'][k]=self.ledger['attempts'].get(k,0)+1
            self.ledger['last_send_time']=self.now()
            record={'http_sequence':seq,'keys':keys,'specs':batch,'reserved_at':self.now(),'state':'reserved_before_send'}
            self.ledger['attempt_log'].append(record);self.persist()
            status,raw,retry_after,error=self.transport(body)
            self.ledger['response_bytes']+=len(raw)
            rawpath=self.root/f'reply_{seq:05d}.json'
            # Preserve original body even for errors, privately and atomically.
            atomic(rawpath,{'http_status':status,'body':raw.decode(errors='replace'),'error':error})
            good={};bad={}
            try:
                if status!=200 or error:raise ValueError(error or f'HTTP_{status}')
                good,bad=validate(json.loads(raw),requests)
            except (ValueError,TypeError) as exc:bad={q['id']:str(exc) for q in requests}
            for q in requests:
                if q['id'] in good:self.save(q['spec'],good[q['id']],{'reply_sha256':sha(rawpath),'http_sequence':seq,'block_number':'unknown_latest'})
            atomic(self.success,self.cache)
            record.update({'state':'response_saved','http_status':status,'bytes':len(raw),'successes':len(good),'errors':bad})
            if good:self.ledger['last_success_time']=self.now()
            self.persist()
            pending=[s for s in pending if self.get(s) is None]
            if seq%10==0:print(json.dumps({'http':seq,'logical':self.ledger['logical_calls'],'pending_this_phase':len(pending)}),flush=True)
            if retry_after:
                if self.now()+retry_after>=min(self.deadline,self.ledger['last_success_time']+600):
                    self.ledger['blocked_reason']='retry_after_exceeds_progress_or_wall_limit';self.persist();break
                self.sleep(retry_after)
        return {digest(s):self.get(s) for s in specs}

def import_legacy(rpc,old,roster,missing):
    phases={};idx=1;collections=[]
    for slot in missing:
        for j in (1,2):collections.append({'id':idx,'spec':collection_spec(roster[str(slot)],j)});idx+=1
    phases['collection']=collections
    receipts={};counts={};invalid={}
    def phase(name,requests):
        good_count=bad_count=0
        for p in sorted(old.glob(name+'_*.json')):
            offset=int(p.stem.split('_')[1]);batch=requests[offset:offset+25]
            if not batch:raise ValueError('legacy offset beyond frozen requests')
            good,bad=validate(json.loads(p.read_text()),batch);receipts[p.name]=sha(p)
            for q in batch:
                if q['id'] in good:
                    rpc.save(q['spec'],good[q['id']],{'legacy_file':p.name,'reply_sha256':sha(p),'original_id':q['id'],'block_number':'unknown_latest'})
            good_count+=len(good);bad_count+=len(bad)
        counts[name]=good_count;invalid[name]=bad_count
    phase('collection',collections)
    positions=[]
    for slot in missing:
        for j in (1,2):
            e=roster[str(slot)];col=rpc.get(collection_spec(e,j))
            if col is None:raise ValueError('legacy collection missing: cannot reconstruct position order')
            positions.append({'id':idx,'spec':position_spec(e,j,col)});idx+=1
    phase('position',positions)
    payouts=[]
    for slot,e in sorted(roster.items(),key=lambda z:int(z[0])):
        for kind in ('n0','n1','den'):payouts.append({'id':idx,'spec':payout_spec(e,kind)});idx+=1
    phase('payout',payouts);atomic(rpc.success,rpc.cache)
    return {'successful':counts,'invalid_items':invalid,'legacy_response_sha256':receipts,'block_numbers':'not_recorded; latest calls were not a single block'}

def direction(e,positions):
    if any(x is None for x in positions):return None,'identity_query_failed'
    p=[str(int(x,16)) for x in positions]
    if p==[e['up_token'],e['down_token']]:return 0,'verified'
    if p==[e['down_token'],e['up_token']]:return 1,'verified'
    return None,'identity_contradiction'

def label(up_index,vec,identity_status,prices=None):
    if identity_status!='verified' or up_index not in (0,1):return identity_status if identity_status!='verified' else 'direction_unknown',None,None
    if any(v is None for v in vec):return 'payout_query_failed',None,None
    n0,n1,den=vec
    if any(type(v) is not int or v<0 for v in vec):return 'invalid_payout',None,None
    if den==0:return ('unresolved' if n0==n1==0 else 'invalid_payout'),None,None
    if n0+n1!=den:return 'invalid_payout',None,None
    if n0 not in (0,den) or n1 not in (0,den):return 'nonbinary_payout',None,None
    y=vec[up_index]//den
    try:
        prices=json.loads(prices) if isinstance(prices,str) else prices
        diagnostic=[float(x) for x in prices]==[float(y),float(1-y)]
    except (TypeError,ValueError):diagnostic=None
    return 'verified_binary',y,diagnostic

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--private-dir',type=Path,required=True);ap.add_argument('--index-root',type=Path,required=True)
    ap.add_argument('--public-dir',type=Path,required=True);ap.add_argument('--import-only',action='store_true');a=ap.parse_args()
    root=a.private_dir;pub=a.public_dir;manifest=json.loads((pub/'resume_manifest.json').read_text())
    for name in ('events_before_labels_private.json','roster_private.json','freeze_private.json'):
        if sha(root/name)!=manifest['hashes'][name]:raise ValueError('frozen input hash mismatch: '+name)
    if sha(Path('configs/polymarket_multiday_price_v1.json'))!=manifest['hashes']['polymarket_multiday_price_v1.json']:raise ValueError('config mismatch')
    rows=json.loads((root/'events_before_labels_private.json').read_text());roster=json.loads((root/'roster_private.json').read_text())
    if len(rows)!=2016 or len(roster)!=2016 or {str(x['slot']) for x in rows}!=set(roster):raise ValueError('cohort mismatch')
    mapping,hashes=index_mapping(a.index_root);stop=json.loads((pub/'ctf_request_budget_stop.json').read_text())
    if hashes!=stop['index_sha256']:raise ValueError('index changed since frozen requests')
    missing=[]
    for k,e in sorted(roster.items(),key=lambda z:int(z[0])):
        c=e['condition_id'].lower();pair=[mapping.get(e[x]) for x in ('up_token','down_token')]
        if any(x is not None and x!=c for x in pair):raise ValueError('index identity contradiction')
        if pair!=[c,c]:missing.append(int(k))
    if len(missing)!=395:raise ValueError('legacy identity request order mismatch')
    cache=root/'ctf_resume_private';cache.mkdir(exist_ok=True)
    with open(cache/'writer.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        deadline=dt.datetime.fromisoformat(manifest['deadline_utc'].replace('Z','+00:00')).timestamp()
        rpc=Rpc(cache,deadline);migration=import_legacy(rpc,root/'ctf_batches_private',roster,missing)
        atomic(cache/'migration.json',migration)
        public_migration={k:v for k,v in migration.items() if k!='legacy_response_sha256'}
        public_migration['legacy_hash_manifest_sha256']=sha(cache/'migration.json')
        atomic(pub/'cache_migration.json',public_migration)
        if a.import_only:print(json.dumps(public_migration));return
        if (root/'ctf_labels_private.json').exists():raise ValueError('existing label output: inspect/archive before replacement')
        start_cpu=resource.getrusage(resource.RUSAGE_SELF)
        chain=call_spec(None,method='eth_chainId',params=[])
        chain_result=rpc.call([chain])[digest(chain)]
        if chain_result is not None and int(chain_result,16)!=137:raise ValueError('wrong RPC chain')
        ordered=[e for _,e in sorted(roster.items(),key=lambda z:int(z[0]))]
        if chain_result is not None:
            rpc.call([collection_spec(e,j) for e in ordered for j in (1,2)])
            specs=[position_spec(e,j,rpc.get(collection_spec(e,j))) for e in ordered for j in (1,2) if rpc.get(collection_spec(e,j)) is not None]
            rpc.call(specs)
            rpc.call([payout_spec(e,k) for e in ordered for k in ('n0','n1','den')])
        labels=[];counts=Counter();daily={d:Counter() for d in DAYS};remaining=Counter()
        for row in rows:
            e=roster[str(row['slot'])];pos=[]
            for j in (1,2):
                col=rpc.get(collection_spec(e,j))
                if col is None:remaining['collection']+=1
                result=rpc.get(position_spec(e,j,col)) if col is not None else None
                if result is None:remaining['position']+=1
                pos.append(result)
            up_index,identity=direction(e,pos)
            vec=[]
            for kind in ('n0','n1','den'):
                v=rpc.get(payout_spec(e,kind))
                if v is None:remaining['payout']+=1
                vec.append(int(v,16) if v is not None else None)
            status,y,gamma=label(up_index,vec,identity,e.get('gamma_outcome_prices'))
            counts[status]+=1;daily[row['date']][status]+=1
            counts['identity_'+identity]+=1
            if up_index==1:counts['up_at_index_1']+=1
            if gamma is False:counts['gamma_price_difference']+=1
            labels.append({'slot':row['slot'],'identity_status':identity,'identity_source':'CTF_collection_position_both_tokens',
                           'up_outcome_index':up_index,'payout_vector':vec,'label_status':status,'y':y,'gamma_price_consistent_diagnostic':gamma})
        labels_path=root/'ctf_labels_private.json';atomic(labels_path,labels)
        ledger=rpc.ledger;newkeys=set(ledger['attempts']);completed=sum(k in rpc.cache for k in newkeys)
        exhausted=sum(k not in rpc.cache and n>=3 for k,n in ledger['attempts'].items())
        summary={'status':'COMPLETE' if not remaining and chain_result else 'ACCESS_OR_BUDGET_BLOCKED',
                 'events':len(labels),'counts':dict(counts),'by_day':daily,'remaining_keys':dict(remaining),
                 'old_logical_request_interval':[9976,10000],
                 'new_requests':{k:ledger[k] for k in ('logical_calls','http_requests','retry_logical_calls','retry_http_requests','response_bytes','blocked_reason')},
                 'new_unique_keys_attempted':len(newkeys),'new_successful_keys':completed,'exhausted_keys':exhausted,
                 'private_labels_sha256':sha(labels_path),'private_ledger_sha256':sha(rpc.ledger_path),
                 'private_cache_sha256':sha(rpc.success),'cache_migration_sha256':sha(cache/'migration.json'),
                 'index_sha256':hashes,'source_bytes_read_or_downloaded':0,'block_tag':'latest',
                 'block_numbers':'unknown for legacy and resumed calls; not a common-block snapshot',
                 'label_time':'unknown; RETROSPECTIVE_OFFLINE','gamma_is_diagnostic_only':True}
        if counts['identity_contradiction'] or counts['invalid_payout']:summary['status']='STOP_CORRECTNESS'
        used=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
        summary['resource_usage']={'self_cpu_seconds':used.ru_utime+used.ru_stime,'child_cpu_seconds':child.ru_utime+child.ru_stime,'max_rss_bytes_macos':used.ru_maxrss,'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        atomic(pub/'settlement_closeout.json',summary)
        print(json.dumps(summary,sort_keys=True),flush=True)
if __name__=='__main__':main()
