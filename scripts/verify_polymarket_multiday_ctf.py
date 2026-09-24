"""Verify fixed BTC-5m Up-token identity and post-hoc binary CTF payout.

Run only after the label-blind seven-day event/quote extraction is frozen. All
row-level conditions, token IDs and RPC replies remain under _private/.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,subprocess,time
from pathlib import Path

CTF='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
USDC_E='2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
RPC='https://polygon-bor-rpc.publicnode.com'
DAYS=('2026-07-27','2026-07-28','2026-07-29','2026-07-30','2026-07-31','2026-08-01','2026-08-02')
MAX_LOGICAL_CALLS=10000
BATCH=25

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def index_mapping(root):
    mapping={};conflicts=[];hashes={}
    for day in DAYS:
        p=root/day/'onchain_index.json';data=json.loads(p.read_text());hashes[day]=sha(p)
        for token,condition in data['token_to_condition'].items():
            token=str(token);condition=str(condition).lower()
            if token in mapping and mapping[token]!=condition:conflicts.append(token)
            mapping[token]=condition
    if conflicts:raise ValueError('onchain token/condition conflict')
    return mapping,hashes

def make_call(reqid,data):
    return {'jsonrpc':'2.0','id':reqid,'method':'eth_call','params':[{'to':CTF,'data':data},'latest']}

class Rpc:
    def __init__(self,cache,initial_calls):
        self.cache=cache;cache.mkdir(parents=True,exist_ok=True);self.logical=initial_calls;self.http=0;self.bytes=0
    def call(self,phase,requests):
        result={}
        for offset in range(0,len(requests),BATCH):
            batch=requests[offset:offset+BATCH];path=self.cache/f'{phase}_{offset:05d}.json'
            if path.exists():
                payload=json.loads(path.read_text());raw=path.read_bytes()
            else:
                body=json.dumps(batch,separators=(',',':'))
                payload=None;raw=None
                for attempt in range(2):
                    if self.logical+len(batch)>MAX_LOGICAL_CALLS:raise RuntimeError('official logical request cap reached')
                    p=subprocess.run(['curl','-sS','-L','--max-time','30','-H','content-type: application/json','--data-binary','@-','-w','\n%{http_code}',RPC],
                                     input=body,text=True,capture_output=True,timeout=35)
                    self.logical+=len(batch);self.http+=1
                    try:
                        response,status=p.stdout.rsplit('\n',1)
                        self.bytes+=len(response.encode())
                        maybe=json.loads(response)
                        if p.returncode==0 and status=='200' and isinstance(maybe,list) and len(maybe)==len(batch):
                            payload=maybe;raw=response.encode();break
                    except (ValueError,json.JSONDecodeError):pass
                    time.sleep(.5*(attempt+1))
                if payload is None:raise RuntimeError(f'RPC {phase} batch {offset} failed')
                path.write_bytes(raw);os.chmod(path,0o600)
            expected={z['id'] for z in batch};actual={z.get('id') for z in payload if isinstance(z,dict)}
            if expected!=actual:raise RuntimeError('RPC batch id mismatch')
            for item in payload:
                v=item.get('result')
                if not isinstance(v,str) or not v.startswith('0x'):raise RuntimeError('RPC result missing or error')
                result[item['id']]=v
        return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--private-dir',type=Path,required=True);a.add_argument('--index-root',type=Path,required=True)
    p=a.parse_args();root=p.private_dir
    if not (root/'events_before_labels_private.json').exists():raise ValueError('label-blind event table not frozen')
    if (root/'ctf_labels_private.json').exists():raise ValueError('refusing to overwrite CTF label table')
    roster=json.loads((root/'roster_private.json').read_text());rows=json.loads((root/'events_before_labels_private.json').read_text())
    if len(rows)!=2016 or {str(x['slot']) for x in rows}!=set(roster):raise ValueError('cohort mismatch')
    mapping,index_hashes=index_mapping(p.index_root)
    missing=[];verified_index=[]
    for key,e in sorted(roster.items(),key=lambda z:int(z[0])):
        up=mapping.get(e['up_token']);down=mapping.get(e['down_token']);condition=e['condition_id'].lower()
        if (up is not None and up!=condition) or (down is not None and down!=condition):raise ValueError('index identity contradiction')
        if up==condition and down==condition:verified_index.append(int(key))
        else:missing.append(int(key))
    rpc=Rpc(root/'ctf_batches_private',2016)
    req=[];meta={};idx=1
    for slot in missing:
        e=roster[str(slot)];condition=e['condition_id'][2:]
        for j in (1,2):
            data='0x856296f7'+'0'*64+condition+f'{j:064x}'
            req.append(make_call(idx,data));meta[idx]=(slot,j);idx+=1
    collection=rpc.call('collection',req)
    req=[];positions={};meta2={}
    for qid,(slot,j) in meta.items():
        col=collection[qid]
        if len(col)!=66:raise ValueError('invalid collection id')
        data='0x39dd7530'+USDC_E.lower().rjust(64,'0')+col[2:]
        req.append(make_call(idx,data));meta2[idx]=(slot,j);idx+=1
    position=rpc.call('position',req)
    for qid,(slot,j) in meta2.items():
        e=roster[str(slot)];expected=e['up_token'] if j==1 else e['down_token']
        positions[(slot,j)]=str(int(position[qid],16))==expected
    req=[];meta3={}
    for key,e in sorted(roster.items(),key=lambda z:int(z[0])):
        slot=int(key);condition=e['condition_id'][2:]
        for kind,selector,j in (('up','0x0504c814',0),('down','0x0504c814',1),('den','0xdd34de67',None)):
            data=selector+condition+(f'{j:064x}' if j is not None else '')
            req.append(make_call(idx,data));meta3[idx]=(slot,kind);idx+=1
    payouts=rpc.call('payout',req)
    by_slot={int(k):{} for k in roster}
    for qid,(slot,kind) in meta3.items():by_slot[slot][kind]=int(payouts[qid],16)
    out=[];counts={'index_verified':len(verified_index),'ctf_position_verification_attempted':len(missing),'ctf_position_match':0,
                   'binary_payout':0,'gamma_payout_consistent':0,'unknown_or_nonbinary':0,'gamma_conflict':0}
    for key,e in sorted(roster.items(),key=lambda z:int(z[0])):
        slot=int(key);token_ok=slot in verified_index or (positions.get((slot,1)) and positions.get((slot,2)))
        if slot in missing and token_ok:counts['ctf_position_match']+=1
        vec=by_slot[slot];binary=(vec['up'],vec['down'],vec['den']) in ((1,0,1),(0,1,1))
        if binary:counts['binary_payout']+=1
        else:counts['unknown_or_nonbinary']+=1
        prices=e.get('gamma_outcome_prices')
        try:prices=[float(v) for v in (json.loads(prices) if isinstance(prices,str) else prices)]
        except (TypeError,ValueError):prices=[]
        consistent=binary and prices==[float(vec['up']),float(vec['down'])]
        if consistent:counts['gamma_payout_consistent']+=1
        elif binary:counts['gamma_conflict']+=1
        out.append({'slot':slot,'identity_status':'verified' if token_ok else 'unverified',
                    'identity_source':'onchain_index' if slot in verified_index else 'CTF_position',
                    'payout_vector':[vec['up'],vec['down'],vec['den']],
                    'label_status':'verified_binary' if token_ok and consistent else 'unknown_or_conflict',
                    'y':vec['up'] if token_ok and consistent else None})
    target=root/'ctf_labels_private.json';target.write_text(json.dumps(out,separators=(',',':'))+'\n');os.chmod(target,0o600)
    public={'status':'RETROSPECTIVE_OFFLINE','source':'CTF eth_call at latest block; Gamma current metadata, seven cached onchain index maps',
            'label_publication_time':'unknown','events':len(out),'counts':counts,'gamma_http_attempts':2016,
            'ctf_http_requests':rpc.http,'ctf_logical_calls_including_gamma':rpc.logical,'ctf_response_bytes':rpc.bytes,
            'index_sha256':index_hashes,'private_ctf_labels_sha256':sha(target),'private_reply_files':len(list((root/'ctf_batches_private').glob('*.json')))}
    target=root/'ctf_summary_private.json';target.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n');os.chmod(target,0o600)
    print(json.dumps({'counts':counts,'logical_calls':rpc.logical,'http':rpc.http},sort_keys=True))
if __name__=='__main__':main()
