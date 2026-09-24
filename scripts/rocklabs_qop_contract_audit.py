"""Verify the observed July CTF V2 contract address/ABI using a read-only explorer."""
from __future__ import annotations
import argparse,hashlib,json,urllib.request
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise ValueError('preserve output')
address='0xe111180000d2663c0091e4f400237545b87b996b'
url='https://polygon.blockscout.com/api/v2/smart-contracts/'+address
req=urllib.request.Request(url,headers={'User-Agent':'Rocklabs-QOP-measurement/1.0'})
with urllib.request.urlopen(req,timeout=20) as f:blob=f.read()
data=json.loads(blob);abi=data.get('abi') or []
needed={('function','matchOrders'):7,('event','OrderFilled'):10,('event','OrdersMatched'):6}
found={f'{kind}:{name}':len([q for q in abi if q.get('type')==kind and q.get('name')==name and len(q.get('inputs',[]))==count])
       for (kind,name),count in needed.items()}
if not all(v==1 for v in found.values()):raise ValueError('ABI mismatch')
result={'status':'EXPLORER_VERIFIED_ABI_WITH_BYTECODE_LIMIT','chain_id':137,'observed_contract_address':address,
 'official_polymarket_contract_address':'https://github.com/Polymarket/ctf-exchange-v2/blob/main/README.md#deployed-contracts',
 'official_v2_event_interface':'https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/interfaces/ITrading.sol',
 'official_v2_match_logic':'https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/mixins/Trading.sol',
 'explorer_api':url,'explorer_response_sha256':hashlib.sha256(blob).hexdigest(),
 'explorer_name':data.get('name'),'is_verified':data.get('is_verified'),
 'is_fully_verified':data.get('is_fully_verified'),'verified_at':data.get('verified_at'),
 'compiler_version':data.get('compiler_version'),'abi_required_items':found,
 'sample_period':'2026-07-28 08:00-09:00 UTC',
 'limit':'Verified source and matching ABI precede the sample; is_fully_verified is false and no independent sample-block bytecode hash was obtained. Event/input reconciliation in fixed receipts is a separate empirical check.'}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'verified_at':result['verified_at'],'is_verified':result['is_verified'],'is_fully_verified':result['is_fully_verified'],'items':found}))
