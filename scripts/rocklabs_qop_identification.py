"""Aggregate-only Rocklabs CLOB/CTF V2 linkage audit; raw evidence stays private.

This is a measurement audit, not a markout or model scorer. The source inputs are
restricted to one preregistered BTC-5m hour and are never copied into Git.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,hashlib,json,re,statistics
from decimal import Decimal
from pathlib import Path
import zstandard as zstd

SHA={
 'clob.jsonl.zst':'0a86857c5192ef5771efe6383a85727a00afedf76a985da458972ea767c939e0',
 'onchain.jsonl.zst':'e44a1f03dca0c055102380c020d78d59a98ff8b019d85da49fc343d9a686547b',
 'polymarket_index.json':'8030460868aa5e5124c56c3062ad4fb0ffe753a6dca618629300cda089554391',
 'onchain_index.json':'70ce6a24bbadd790df8fb95b64c40c5049aaaf0777a5c7ee5e006d8228b03f5a'}
CONTRACTS={'0xe111180000d2663c0091e4f400237545b87b996b':'ctf_exchange_v2',
 '0xe2222d279d744050d28e00520010520000310f59':'neg_risk_ctf_exchange_v2'}
SIG={'OrderFilled':'OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)',
 'OrdersMatched':'OrdersMatched(bytes32,address,uint8,uint256,uint256,uint256)'}
SEED='rocklabs-qop-v1-examples:'

def stream(path):
    with zstd.open(path,'rt') as f:
        for i,line in enumerate(f):
            yield i,json.loads(line)

def content(x):
    c=x['content'];return json.loads(c) if isinstance(c,str) else c

def ms(x):
    if isinstance(x,(int,float)) or (isinstance(x,str) and x.isdigit()):return int(x)
    return int(dt.datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()*1000)

def amount(x):return Decimal(str(x))/Decimal(1000000)

def assets(e):
    # CTF V2 BUY: maker collateral, taker token. SELL: maker token, taker collateral.
    side=int(e['side']);maker=amount(e['makerAmountFilled']);taker=amount(e['takerAmountFilled'])
    if side==0 and taker>0:return taker,maker/taker,1
    if side==1 and maker>0:return maker,taker/maker,-1
    raise ValueError('invalid side/amount')

def main():
    p=argparse.ArgumentParser();p.add_argument('--sample',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--public',type=Path,required=True);a=p.parse_args()
    if a.private.exists() or a.public.exists():raise ValueError('preserve output')
    for name,h in SHA.items():
        if hashlib.sha256((a.sample/name).read_bytes()).hexdigest()!=h:raise ValueError('source hash mismatch: '+name)
    token_slug={};market_of={};metadata_conflicts=0
    for _,x in stream(a.sample/'clob.jsonl.zst'):
        if x['message_type']!='market_metadata':continue
        c=content(x)
        if not isinstance(c,dict) or 'btc-updown-5m-' not in str(c.get('event_slug','')):continue
        tok=str(c['token_id']);slug=str(c['event_slug']);market=str(c.get('market'))
        if tok in token_slug and token_slug[tok]!=slug:metadata_conflicts+=1
        token_slug[tok]=slug;market_of[tok]=market
    if metadata_conflicts:raise ValueError('token metadata conflicting')
    prints=[];all_prints=0;array_lines=0;array_items=0
    for line_idx,x in stream(a.sample/'clob.jsonl.zst'):
        c=content(x);ys=c if isinstance(c,list) else [c]
        if isinstance(c,list):array_lines+=1;array_items+=len(c)
        for sub_idx,y in enumerate(ys):
            if not isinstance(y,dict) or y.get('event_type')!='last_trade_price':continue
            all_prints+=1;tok=str(y.get('asset_id'))
            if tok not in token_slug:continue
            prints.append({'line':line_idx,'sub':sub_idx,'tx':str(y.get('transaction_hash','')).lower(),
                'token':tok,'slug':token_slug[tok],'market':str(y.get('market')),
                'side':str(y.get('side')),'size':str(y.get('size')),'price':str(y.get('price')),
                'inner_ms':ms(y.get('timestamp')),'recv_ms':ms(x['timestamp'])})
    active_slugs={x['slug'] for x in prints};active_tokens={t for t,s in token_slug.items() if s in active_slugs}
    prints=[x for x in prints if x['token'] in active_tokens]
    needed={x['tx'] for x in prints};logs=collections.defaultdict(list);all_log_counts=collections.Counter()
    for line_idx,x in stream(a.sample/'onchain.jsonl.zst'):
        c=content(x);kind=c.get('event_name')
        if kind not in ('OrderFilled','OrdersMatched'):continue
        all_log_counts[kind]+=1
        tx=str(c.get('tx_hash','')).lower()
        if tx in needed:
            logs[tx].append({'kind':kind,'contract':str(c.get('address','')).lower(),
                 'contract_name':c.get('contract_name'),'chain_id':c.get('chain_id'),
                 'signature':c.get('event_signature'),'log_index':int(str(c['log_index']),0),
                 'decoded':c.get('decoded') or {},'ts_block':c.get('ts_block'),
                 'ts_recv_ms':c.get('ts_recv_ms'),'line':line_idx})
    tx_groups=collections.defaultdict(list);group_failure=collections.Counter();all_groups=[]
    for tx,ls in logs.items():
        by_contract=collections.defaultdict(list)
        for q in ls:by_contract[q['contract']].append(q)
        for contract,seq in by_contract.items():
            seq.sort(key=lambda z:z['log_index']);pending=[]
            for q in seq:
                if q['kind']=='OrderFilled':pending.append(q);continue
                if contract not in CONTRACTS or q['contract_name']!=CONTRACTS[contract]:group_failure['contract_unknown_or_name_mismatch']+=1;pending=[];continue
                if any(z['chain_id']!=137 or z['signature']!=SIG[z['kind']] for z in pending+[q]):group_failure['abi_signature_or_chain_mismatch']+=1;pending=[];continue
                order_hash=str(q['decoded'].get('takerOrderHash','')).lower()
                taker=[z for z in pending if str(z['decoded'].get('orderHash','')).lower()==order_hash]
                other=[z for z in pending if str(z['decoded'].get('orderHash','')).lower()!=order_hash]
                fail=[]
                if len(taker)!=1:fail.append('taker_fill_not_unique')
                if not other:fail.append('no_candidate_maker_fills')
                if taker:
                    d=taker[0]['decoded'];m=q['decoded']
                    if str(d.get('tokenId'))!=str(m.get('tokenId')) or str(d.get('side'))!=str(m.get('side')):fail.append('matched_taker_token_side_mismatch')
                    if str(d.get('maker')).lower()!=str(m.get('takerOrderMaker')).lower():fail.append('matched_taker_maker_mismatch')
                    if str(d.get('makerAmountFilled'))!=str(m.get('makerAmountFilled')) or str(d.get('takerAmountFilled'))!=str(m.get('takerAmountFilled')):fail.append('matched_taker_amount_mismatch')
                legs=[]
                for z in other:
                    try:shares,price,sign=assets(z['decoded'])
                    except (ValueError,KeyError,ArithmeticError):fail.append('leg_asset_arithmetic');continue
                    if shares<=0 or not Decimal(0)<=price<=Decimal(1):fail.append('leg_invalid_price_or_shares');continue
                    legs.append({'key':(137,contract,tx,z['log_index']),'order_hash':str(z['decoded']['orderHash']).lower(),
                         'token':str(z['decoded']['tokenId']),'shares':str(shares),'price':str(price),'sign':sign,
                         'fee_raw':str(z['decoded'].get('fee'))})
                g={'tx':tx,'contract':contract,'match_log_index':q['log_index'],'taker':taker[0] if len(taker)==1 else None,
                   'maker_legs':legs,'failure':fail,'maker_fill_count':len(other),'all_fill_count':len(pending)}
                tx_groups[tx].append(g);all_groups.append(g)
                for reason in fail:group_failure[reason]+=1
                pending=[]
            if pending:group_failure['orphan_order_filled_after_last_match']+=len(pending)
    join_status=collections.Counter();matched_prints=[];unmatched=[];tx_prints=collections.defaultdict(list)
    for pr in prints:tx_prints[pr['tx']].append(pr)
    for pr in prints:
        candidates=[]
        for g in tx_groups.get(pr['tx'],[]):
            if g['failure'] or g['taker'] is None:continue
            d=g['taker']['decoded']
            try:shares,price,sign=assets(d)
            except (ValueError,KeyError,ArithmeticError):continue
            if (pr['token']==str(d.get('tokenId')) and pr['side']==('BUY' if sign==1 else 'SELL')
                and abs(shares-Decimal(pr['size']))<Decimal('0.000001')):
                candidates.append(g)
        if len(candidates)==1:
            g=candidates[0];join_status['unique']+=1;matched_prints.append((pr,g))
        elif not candidates:
            join_status['none']+=1;unmatched.append(pr)
        else:join_status['ambiguous']+=1;unmatched.append(pr)
    unique_groups={(g['tx'],g['contract'],g['match_log_index']):g for _,g in matched_prints}
    leg_by_key={leg['key']:leg for g in unique_groups.values() for leg in g['maker_legs']}
    print_group_counts=collections.Counter((g['tx'],g['contract'],g['match_log_index']) for _,g in matched_prints)
    order_to_tx=collections.defaultdict(set)
    for g in unique_groups.values():
        for leg in g['maker_legs']:order_to_tx[leg['order_hash']].add(g['tx'])
    repeated_orders={k for k,v in order_to_tx.items() if len(v)>1}
    categories=collections.defaultdict(set)
    for pr,g in matched_prints:
        tx=pr['tx']
        if len(g['maker_legs'])==1:categories['single_maker'].add(tx)
        if len(g['maker_legs'])>1:categories['multi_maker'].add(tx)
        if any(leg['token']!=pr['token'] for leg in g['maker_legs']):categories['complement_route'].add(tx)
        if any(leg['order_hash'] in repeated_orders for leg in g['maker_legs']):categories['repeated_maker_order'].add(tx)
    selected=[];selected_by={}
    for cat in ('single_maker','multi_maker','complement_route','repeated_maker_order'):
        candidates=sorted(categories[cat]-set(selected),key=lambda h:hashlib.sha256((SEED+h).encode()).hexdigest())
        take=candidates[:6];selected+=take;selected_by[cat]=take
    sample_lag=[p['recv_ms']-p['inner_ms'] for p,g in matched_prints]
    private={'source_hashes':SHA,'token_slug':token_slug,'active_slugs':sorted(active_slugs),'prints':prints,
             'groups':all_groups,'selected_24_by_category':selected_by,'unmatched':unmatched,
             'joined_print_indices':[(p['line'],p['sub'],g['tx'],g['contract'],g['match_log_index']) for p,g in matched_prints]}
    a.private.parent.mkdir(parents=True,exist_ok=True)
    a.private.write_text(json.dumps(private,separators=(',',':'))+'\n')
    pub={'status':'DEVELOPMENT_MEASUREMENT_ONLY','source_hashes':SHA,'metadata_btc5m_events':len(set(token_slug.values())),
         'active_btc5m_events':len(active_slugs),'active_tokens':len(active_tokens),'all_hour_clob_prints':all_prints,
         'target_clob_print_records':len(prints),'target_unique_tx_hashes':len(needed),
         'duplicate_print_records_by_tx':len(prints)-len(needed),'tx_with_multiple_prints':sum(len(v)>1 for v in tx_prints.values()),
         'clob_array_lines':array_lines,'clob_array_items':array_items,'hour_onchain_log_counts':dict(all_log_counts),
         'target_tx_with_any_chain_logs':len(logs),'target_tx_without_chain_logs':len(needed-set(logs)),
         'target_tx_economic_groups':len(all_groups),'groups_per_tx':dict(collections.Counter(len(v) for v in tx_groups.values())),
         'group_failure_reasons':dict(group_failure),'print_join_status':dict(join_status),
         'unique_joined_economic_groups':len(unique_groups),'groups_with_multiple_public_prints':sum(v>1 for v in print_group_counts.values()),
         'candidate_maker_legs_unique_chain_log_keys':len(leg_by_key),
         'candidate_maker_shares':str(sum((Decimal(z['shares']) for z in leg_by_key.values()),Decimal(0))),
         'candidate_maker_legs_complement_token_count':sum(sum(leg['token']!=pr['token'] for leg in g['maker_legs']) for pr,g in matched_prints),
         'joined_groups_with_complement_maker_leg':sum(any(leg['token']!=pr['token'] for leg in g['maker_legs']) for pr,g in matched_prints),
         'reused_maker_order_hashes_across_tx':len(repeated_orders),
         'fixed_examples_by_category':{k:len(v) for k,v in selected_by.items()},
         'fixed_examples_total':len(selected),'fixed_examples_private_sha256':hashlib.sha256(json.dumps(selected_by,sort_keys=True).encode()).hexdigest(),
         'unjoined_print_records':len(unmatched),'unjoined_private_sha256':hashlib.sha256(json.dumps(unmatched,sort_keys=True).encode()).hexdigest(),
         'source_to_receive_ms_min_median_max':[min(sample_lag),statistics.median(sample_lag),max(sample_lag)] if sample_lag else None,
         'private_evidence_sha256':hashlib.sha256(a.private.read_bytes()).hexdigest(),
         'role_note':'Event-derived candidate maker legs; independent input/receipt verification of fixed examples is separate. Contract ABI/event signature alone does not establish every per-leg match timestamp.'}
    a.public.parent.mkdir(parents=True,exist_ok=True)
    a.public.write_text(json.dumps(pub,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:pub[k] for k in ['target_clob_print_records','target_unique_tx_hashes','target_tx_economic_groups','print_join_status','candidate_maker_legs_unique_chain_log_keys','fixed_examples_by_category']}))
if __name__=='__main__':main()
