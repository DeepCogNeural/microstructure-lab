"""Build private receipt-verified selected-token QOP development rows and quote tape."""
from __future__ import annotations
import argparse,bisect,collections,hashlib,json,statistics,datetime
from decimal import Decimal
from pathlib import Path
from audit_qop_outcometick_r0 import rows,verify
from qop_observer_diagnostic import audit_receipt,endpoint,dec

p=argparse.ArgumentParser()
p.add_argument('--sample-root',type=Path,required=True)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--selection-private',type=Path,required=True)
p.add_argument('--receipt-cache',type=Path,required=True)
p.add_argument('--out-private',type=Path,required=True)
p.add_argument('--out-public',type=Path,required=True)
a=p.parse_args()
if a.out_private.exists() or a.out_public.exists():raise ValueError('preserve output')
verify(a.sample_root,a.archive)
selection=json.loads(a.selection_private.read_text());events=selection['events']
slugs={e['market']['slug'] for e in events}
market_by_slug={e['market']['slug']:e['market'] for e in events}
needed={t['hash'] for e in events for t in e['transactions']}
print_groups=collections.defaultdict(list)
flow=collections.defaultdict(list)
for row in rows(a.sample_root,'last_trade_price'):
    if row['slug'] not in slugs:continue
    token=str(row['asset_id']);flow[(row['slug'],token)].append(row)
    h=row.get('payload',{}).get('transaction_hash')
    if h and h.lower() in needed:print_groups[h.lower()].append(row)
quote=collections.defaultdict(list)
quote_reversals=collections.defaultdict(list);last_quote_recv={}
for row in rows(a.sample_root,'best_bid_ask'):
    if row['slug'] in slugs and str(row['asset_id'])==str(market_by_slug[row['slug']]['token_ids'][0]):
        key=(row['slug'],str(row['asset_id']))
        if key in last_quote_recv and row['recv_ms']<last_quote_recv[key]:quote_reversals[key].append(row['recv_ms'])
        last_quote_recv[key]=row['recv_ms']
        quote[key].append(row)
book=collections.defaultdict(list)
for row in rows(a.sample_root,'book'):
    if row['slug'] in slugs and str(row['asset_id'])==str(market_by_slug[row['slug']]['token_ids'][0]):
        book[(row['slug'],str(row['asset_id']))].append(row)
for d in (quote,book,flow):
    for key in d:d[key].sort(key=lambda x:x['recv_ms'])
fail=collections.Counter();transaction_stats=collections.Counter();leg_rows=[];one_to_many=0;buy_sell=collections.Counter()
source_to_receive=[];source_minus_block=[];contracts=set()
for event_idx,e in enumerate(events):
    m=e['market'];slug=m['slug'];target=str(m['token_ids'][0]);alt=str(m['token_ids'][1]);
    for t in e['transactions']:
        h=t['hash'];cache=a.receipt_cache/(h.removeprefix('0x')+'.json')
        if not cache.exists():fail['receipt_not_fetched']+=1;continue
        item=json.loads(cache.read_text())
        if not item.get('complete'):fail['receipt_http_failed']+=1;continue
        transaction_stats['receipts_complete']+=1
        matched=[];errors=[]
        for pr in print_groups[h]:
            try:matched.append((pr,audit_receipt({'print':{'transaction_hash':h},'tx':item['tx'],'logs':item['logs']},pr)))
            except (ValueError,KeyError,TypeError,AssertionError) as exc:errors.append(type(exc).__name__+': '+str(exc))
        if not matched:
            fail['no_unique_receipt_compatible_print']+=1
            if errors:fail['example_'+errors[0][:75]]+=1
            continue
        # Duplicate identical disclosures collapse. Differing anchors or tokens remain ambiguous.
        signatures={(pr['recv_ms'],str(pr['asset_id']),pr['payload'].get('side'),str(pr['payload'].get('size'))) for pr,_ in matched}
        if len(signatures)!=1:
            fail['multiple_compatible_print_anchors']+=1;continue
        pr,rec=matched[0];transaction_stats['joined_unique_hashes']+=1
        one_to_many+=len(rec['legs'])>1
        contracts.add((item['tx']['to'].get('hash') if isinstance(item['tx']['to'],dict) else item['tx']['to']).lower())
        source_to_receive.append(pr['recv_ms']-pr['event_ts_ms'])
        try:
            block_ms=int(datetime.datetime.fromisoformat(item['tx']['timestamp'].replace('Z','+00:00')).timestamp()*1000)
            source_minus_block.append(pr['event_ts_ms']-block_ms)
        except (KeyError,ValueError,TypeError):transaction_stats['block_timestamp_unparseable']+=1
        print_token=str(pr['asset_id'])
        if print_token not in (target,alt):fail['print_token_outside_event']+=1;continue
        target_legs=[leg for leg in rec['legs'] if (leg['target'] and print_token==target) or (not leg['target'] and print_token==alt)]
        transaction_stats['target_leg_hashes']+=bool(target_legs)
        for leg_idx,leg in enumerate(target_legs):
            buy_sell['BUY' if leg['sign']==1 else 'SELL']+=1
            base={'event_idx':event_idx,'market_start_sec':m['start_sec'],'hash':h,'leg_idx':leg_idx,
                  'print_token':'target' if print_token==target else 'complement','print_recv_ms':pr['recv_ms'],
                  'shares':str(leg['shares']),'price':str(leg['price']),'sign':leg['sign'],'fee_raw':str(leg['fee_raw']),
                  'quote':{},'failure':{}}
            key=(slug,target);series=quote[key];times=[x['recv_ms'] for x in series]
            for age in (1000,250):
                for horizon in (5000,30000):
                    k=f'{age}_{horizon}'
                    pre,e0,a0=endpoint(series,times,pr['recv_ms'],True,age)
                    post,e1,a1=endpoint(series,times,pr['recv_ms']+horizon,False,age)
                    errs=[z for z in (e0,e1) if z]
                    if pr['recv_ms']+horizon>m['end_sec']*1000:errs.append('past_scheduled_end')
                    if any(pr['recv_ms']-1000<=t<=pr['recv_ms']+horizon for t in quote_reversals[key]):errs.append('receive_clock_reversal')
                    base['failure'][k]=errs
                    base['quote'][k]={'pre_age_ms':a0,'post_age_ms':a1}
                    if not errs:
                        G=Decimal(100)*leg['sign']*(pre-leg['price'])
                        D=Decimal(100)*leg['sign']*(post-pre)
                        N=G+D
                        base['quote'][k].update({'G':str(G),'D':str(D),'N':str(N),'pre_mid':str(pre),'post_mid':str(post)})
            leg_rows.append(base)
private={'source':'OutcomeTick samples-2026-09-08','selection_sha256':hashlib.sha256(a.selection_private.read_bytes()).hexdigest(),
         'transaction_stats':dict(transaction_stats),'failures':dict(fail),'leg_rows':leg_rows}
a.out_private.write_text(json.dumps(private,separators=(',',':'))+'\n')
public={'status':'DEVELOPMENT_EXPANDED_RECEIPT_AND_QUOTE_BUILD','selected_events':len(events),'selected_new_hashes':len(needed),
        'receipts_complete':transaction_stats['receipts_complete'],'joined_unique_hashes':transaction_stats['joined_unique_hashes'],
        'target_leg_hashes':transaction_stats['target_leg_hashes'],'selected_token_legs':len(leg_rows),
        'target_leg_shares':str(sum((Decimal(z['shares']) for z in leg_rows),Decimal(0))),
        'selected_token_sides':dict(buy_sell),'multi_maker_hashes':one_to_many,'contract_count':len(contracts),
        'multi_log_page_receipts':sum((json.loads((a.receipt_cache/(h.removeprefix('0x')+'.json')).read_text()).get('logs') or {}).get('pages',0)>1 for h in needed if (a.receipt_cache/(h.removeprefix('0x')+'.json')).exists()),
        'source_to_receive_ms_min_median_max':[min(source_to_receive),statistics.median(source_to_receive),max(source_to_receive)] if source_to_receive else None,
        'source_minus_block_ms_min_median_max':[min(source_minus_block),statistics.median(source_minus_block),max(source_minus_block)] if source_minus_block else None,
        'receipt_failures':{k:v for k,v in fail.items() if not k.startswith('example_')},
        'quote_coverage':{f'{age}_{h}':{'eligible_legs':sum(not z['failure'][f'{age}_{h}'] for z in leg_rows),
           'eligible_events':len({z['event_idx'] for z in leg_rows if not z['failure'][f'{age}_{h}']}),
           'failure_reasons':dict(collections.Counter(reason for z in leg_rows for reason in z['failure'][f'{age}_{h}']))}
           for age in (1000,250) for h in (5000,30000)},
        'private_rows_sha256':hashlib.sha256(a.out_private.read_bytes()).hexdigest(),
        'note':'Only uniquely receipt-compatible public prints anchor passive target-token legs; no replacement hashes; missing values remain NA.'}
a.out_public.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:public[k] for k in ('receipts_complete','joined_unique_hashes','selected_token_legs','target_leg_shares')}))
