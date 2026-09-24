"""Receive-clock QOP features, keeping each candidate direction separate and causal."""
from __future__ import annotations
import argparse,bisect,collections,hashlib,json
from decimal import Decimal
from pathlib import Path
from audit_qop_outcometick_r0 import rows,verify
from qop_observer_diagnostic import dec,quote_value,endpoint

p=argparse.ArgumentParser()
p.add_argument('--sample-root',type=Path,required=True)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--selection-private',type=Path,required=True)
p.add_argument('--build-private',type=Path,required=True)
p.add_argument('--out-private',type=Path,required=True)
p.add_argument('--out-public',type=Path,required=True)
a=p.parse_args()
if a.out_private.exists() or a.out_public.exists():raise ValueError('preserve output')
verify(a.sample_root,a.archive)
selection=json.loads(a.selection_private.read_text());built=json.loads(a.build_private.read_text())
events=selection['events'];slugs={e['market']['slug'] for e in events};meta={i:e['market'] for i,e in enumerate(events)}
first_by_slug={e['market']['slug']:str(e['market']['token_ids'][0]) for e in events}
bbo=collections.defaultdict(list);books=collections.defaultdict(list);prints=collections.defaultdict(list)
for kind,dest in (('best_bid_ask',bbo),('book',books),('last_trade_price',prints)):
    for x in rows(a.sample_root,kind):
        if x['slug'] not in slugs:continue
        if kind!='last_trade_price' and str(x['asset_id'])!=first_by_slug[x['slug']]:continue
        dest[x['slug']].append(x)
    for slug in dest:dest[slug].sort(key=lambda z:z['recv_ms'])
times={kind:{slug:[x['recv_ms'] for x in data] for slug,data in dest.items()} for kind,dest in (('bbo',bbo),('book',books),('print',prints))}

def asof_quote(slug,t,age_max=1000,strict=False):
    xs=bbo[slug];ts=times['bbo'][slug];j=bisect.bisect_left(ts,t) if strict else bisect.bisect_right(ts,t)
    if not j:return None,'missing_quote'
    stamp=ts[j-1]
    if t-stamp>age_max:return None,'stale_quote'
    group=xs[bisect.bisect_left(ts,stamp):j]
    if len({(str(x['payload'].get('best_bid')),str(x['payload'].get('best_ask'))) for x in group})!=1:return None,'same_receive_time_conflict'
    mid,err=quote_value(group[0])
    if err:return None,err
    bid=dec(group[0]['payload']['best_bid']);ask=dec(group[0]['payload']['best_ask'])
    return {'mid':mid,'bid':bid,'ask':ask,'age_ms':t-stamp},None

def asof_book(slug,t):
    xs=books[slug];ts=times['book'][slug];j=bisect.bisect_right(ts,t)
    if not j:return None,'missing_book'
    stamp=ts[j-1]
    if t-stamp>1000:return None,'stale_book'
    group=xs[bisect.bisect_left(ts,stamp):j]
    if len({json.dumps(x['payload'],sort_keys=True) for x in group})!=1:return None,'same_receive_time_book_conflict'
    try:
        b=max((dec(z['price']),dec(z['size'])) for z in group[0]['payload']['bids'] if dec(z['size'])>0)
        ask=min((dec(z['price']),dec(z['size'])) for z in group[0]['payload']['asks'] if dec(z['size'])>0)
    except (KeyError,ValueError,TypeError):return None,'invalid_book'
    if not (Decimal(0)<b[0]<ask[0]<Decimal(1)):return None,'invalid_book_prices'
    size_b,size_a=b[1],ask[1];total=size_b+size_a
    return {'top_depth':float(total),'imbalance':float((size_b-size_a)/total),'age_ms':t-stamp},None

def flow_window(slug,t,exclude_hash,window=30000):
    xs=prints[slug];ts=times['print'][slug];lo=bisect.bisect_left(ts,t-window);hi=bisect.bisect_right(ts,t)
    seen=set();signed=0.;unknown=0
    for x in xs[lo:hi]:
        h=x['payload'].get('transaction_hash')
        if not h or h == exclude_hash or h in seen:continue
        seen.add(h)
        side=x['payload'].get('side')
        if side not in ('BUY','SELL'):unknown+=1;continue
        try:size=float(dec(x['payload']['size']))
        except ValueError:unknown+=1;continue
        token_sign=1 if str(x['asset_id'])==first_by_slug[slug] else -1
        signed+=token_sign*(1 if side=='BUY' else -1)*size
    return signed,len(seen),unknown

def feature(slug,r,d,cut_before_ms,exclude_hash):
    cutoff=r-cut_before_ms
    curr,e0=asof_quote(slug,cutoff)
    prev,e1=asof_quote(slug,cutoff-30000)
    book,e2=asof_book(slug,cutoff)
    if e0 or e1 or e2:return None,[x for x in (e0,e1,e2) if x]
    f_signed,count,unk=flow_window(slug,cutoff,exclude_hash)
    if unk:return None,['unknown_public_flow_side_or_size']
    remain=(int(market_by_slug[slug]['end_sec'])*1000-cutoff)/1000
    if remain<=0:return None,['past_scheduled_end']
    # Both possible candidate directions are evaluated with the same public state.
    return {'M0':[float(d),float(curr['mid']),float(curr['ask']-curr['bid']),remain,curr['age_ms'],book['top_depth']],
            'M1':[float(d),float(curr['mid']),float(curr['ask']-curr['bid']),remain,curr['age_ms'],book['top_depth'],
                  float(d*(curr['mid']-prev['mid'])),d*book['imbalance']],
            'M2':[float(d),float(curr['mid']),float(curr['ask']-curr['bid']),remain,curr['age_ms'],book['top_depth'],
                  float(d*(curr['mid']-prev['mid'])),d*book['imbalance'],d*f_signed,float(count)],
            'ages':{'quote_ms':curr['age_ms'],'book_ms':book['age_ms'],'history_ms':prev['age_ms']}},[]
market_by_slug={e['market']['slug']:e['market'] for e in events}
counts=collections.Counter();out=[]
for row in built['leg_rows']:
    idx=row['event_idx'];m=meta[idx];slug=m['slug'];r=row['print_recv_ms'];d=row['sign'];q=dec(row['price'])
    record={k:row[k] for k in ('event_idx','hash','leg_idx','shares','price','sign','fee_raw','print_recv_ms')}
    record['shift']={};record['features']={};record['feature_failure']={}
    for shift in (-500,0,500):
        rr=r+shift;key=str(shift)
        rec={'labels':{},'failures':{}}
        for horizon in (5000,30000):
            pre,e0=asof_quote(slug,rr,strict=True)
            post,e1=asof_quote(slug,rr+horizon)
            errs=[x for x in (e0,e1) if x]
            if rr+horizon>m['end_sec']*1000:errs.append('past_scheduled_end')
            rec['failures'][str(horizon)]=errs
            if not errs:
                G=Decimal(100)*d*(dec(pre['mid'])-q)
                D=Decimal(100)*d*(dec(post['mid'])-dec(pre['mid']))
                rec['labels'][str(horizon)]={'G':str(G),'D':str(D),'N':str(G+D),
                    'exit_side_cents':str(Decimal(100)*d*(dec(post['bid'] if d==1 else post['ask'])-q))}
        record['shift'][key]=rec
        for cut in (1000,5000):
            buy,e_buy=feature(slug,rr,1,cut,row['hash'])
            sell,e_sell=feature(slug,rr,-1,cut,row['hash'])
            f,e=(buy,e_buy) if d==1 else (sell,e_sell)
            record.setdefault('candidate_features',{})[f'{key}_{cut}']={'BUY':buy,'SELL':sell}
            record['features'][f'{key}_{cut}']=f
            record['feature_failure'][f'{key}_{cut}']=e
            if f:counts[f'feature_{key}_{cut}']+=1
    out.append(record)
private={'source':'OutcomeTick samples-2026-09-08','selection_sha256':built['selection_sha256'],
         'build_private_sha256':hashlib.sha256(a.build_private.read_bytes()).hexdigest(),'rows':out}
a.out_private.write_text(json.dumps(private,separators=(',',':'))+'\n')
public={'status':'DEVELOPMENT_CAUSAL_FEATURE_BUILD','all_selected_token_legs':len(out),
        'feature_available_counts':dict(counts),
        'main_5s_label_count':sum(bool(x['shift']['0']['labels'].get('5000')) for x in out),
        'common_model_ready_legs':sum(bool(x['shift']['0']['labels'].get('5000')) and all(x['features'].get(f'0_{c}') for c in (1000,5000)) for x in out),
        'feature_failure_counts':dict(collections.Counter(reason for x in out for c in ('0_1000','0_5000') for reason in x['feature_failure'][c])),
        'private_feature_rows_sha256':hashlib.sha256(a.out_private.read_bytes()).hexdigest(),
        'note':'All features use public rows received at or before r minus cutoff; later receipt identity, maker price and size are labels/accounting only. Snapshot depths are age-limited snapshots, not exact replay.'}
a.out_public.write_text(json.dumps(public,sort_keys=True,indent=2)+'\n')
print(json.dumps({k:public[k] for k in ('all_selected_token_legs','main_5s_label_count','common_model_ready_legs')}))
