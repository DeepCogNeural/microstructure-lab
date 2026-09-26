"""Fixed three-hour retrospective gross settlement value; only aggregates public."""
from __future__ import annotations
import argparse, collections, hashlib, json, resource, time
from decimal import Decimal, localcontext
from pathlib import Path
D=Decimal
DATES=('2026-07-28','2026-07-29','2026-07-30')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): raise ValueError('preserve existing output: '+p.name)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def gross(price,sign,payout):
    q,y=D(str(price)),D(str(payout))
    if not q.is_finite() or not y.is_finite() or not 0<=q<=1 or not 0<=y<=1 or sign not in (-1,1): raise ValueError('invalid economics')
    return D(100)*sign*(y-q)
def up_equivalent(q,sign,is_up): return (q,sign) if is_up else (D(1)-q,-sign)
def bucket(q): return min(4,int(q*5))
def label_value(x):
    if x['identity_status']!='verified' or x['label_status']!='verified_binary': return None
    n0,n1,den=x['payout_vector']; idx=x['up_outcome_index']
    if idx not in (0,1) or den<=0 or n0+n1!=den or n0 not in (0,den) or n1 not in (0,den): raise ValueError('bad verified payout')
    y=D(x['payout_vector'][idx])/D(den)
    if y!=D(str(x['y'])): raise ValueError('label direction mismatch')
    return y

def summary(rows):
    if not rows:return {'events':0,'groups':0,'legs':0,'shares':'0','total_cents':'0','share_weighted_cents':None,'event_equal_cents':None}
    vol=sum((r['shares'] for r in rows),D(0));val=sum((r['value'] for r in rows),D(0));ev=collections.defaultdict(list)
    for r in rows:ev[r['slot']].append(r)
    means=[sum((r['value'] for r in rr),D(0))/sum((r['shares'] for r in rr),D(0)) for rr in ev.values()]
    return {'events':len(ev),'groups':len({r['group'] for r in rows}),'legs':len(rows),'shares':str(vol),'total_cents':str(val),'share_weighted_cents':float(val/vol),'event_equal_cents':float(sum(means,D(0))/len(means))}
def hierarchy(rows):
    days={date:summary([r for r in rows if r['date']==date]) for date in DATES}
    vals=[v['event_equal_cents'] for v in days.values()]
    return {'days':days,'three_day_equal_cents':sum(vals)/3 if all(v is not None for v in vals) else None,'all_legs':summary(rows)}

def analyze(evidence,roster,labels):
    token={};payout={str(r['slot']):label_value(r) for r in labels}
    for slot,e in roster.items():
        for field,is_up in [('up_token',True),('down_token',False)]:
            tok=e[field]
            if tok in token:raise ValueError('duplicate roster token')
            token[tok]=(slot,e,is_up)
    rows=[];exclusions=collections.Counter();funnel={};seen={};missing=[]
    for date,x in evidence.items():
        joins={(j[2],j[3],j[4]) for j in x['joined_print_indices']};groups={}
        for g in x['groups']:
            k=(g['tx'],g['contract'],g['match_log_index'])
            if k in groups and g!=groups[k]:raise ValueError('conflicting duplicate group')
            groups[k]=g
        if not joins<=groups.keys():raise ValueError('joined group missing')
        count=collections.Counter();known=D(0);selected={h for vals in x['selected_24_by_category'].values() for h in vals} if date==DATES[0] else set()
        for k in sorted(joins):
            g=groups[k];count['candidate_groups']+=1;count['candidate_legs']+=len(g['maker_legs'])
            known+=sum((D(l['shares']) for l in g['maker_legs']),D(0))
            if g['failure'] or g['taker'] is None:raise ValueError('invalid joined group')
            taker=g['taker'];tt=str(taker['decoded']['tokenId']);meta=token.get(tt)
            why=None
            if meta is None:why='taker_token_not_verified'
            else:
                slot,event,_=meta
                if event['date']!=date or x['token_slug'].get(tt)!=event['slug']:why='event_identity_mismatch'
                if taker['chain_id']!=137 or taker['contract']!=g['contract']:why='chain_contract_mismatch'
                for leg in g['maker_legs']:
                    lm=token.get(leg['token'])
                    if lm is None:why='maker_token_not_verified';break
                    if lm[0]!=slot or lm[1]['condition_id']!=event['condition_id']:why='cross_condition_group';break
                    if x['token_slug'].get(leg['token'])!=event['slug']:why='maker_metadata_mismatch';break
            if why:
                exclusions[why+'_groups']+=1;exclusions[why+'_legs']+=len(g['maker_legs']);continue
            count['role_identity_verified_groups']+=1
            for leg in g['maker_legs']:
                key=tuple(leg['key']);finger=(leg['token'],leg['shares'],leg['price'],leg['sign'])
                if key[:3]!=(137,g['contract'],g['tx']) or key[3]==taker['log_index']:raise ValueError('bad maker key/taker included')
                if key in seen:
                    if seen[key]!=finger:raise ValueError('conflicting duplicate leg')
                    count['duplicate_legs']+=1;continue
                seen[key]=finger
                v,q=D(leg['shares']),D(leg['price']);sign=leg['sign'];is_up=token[leg['token']][2]
                if not v.is_finite() or v<=0:raise ValueError('bad shares')
                gross(q,sign,0)
                count['deduplicated_role_verified_legs']+=1
                yup=payout.get(slot)
                if yup is None:
                    lo=min(gross(q,sign,0),gross(q,sign,1))*v;hi=max(gross(q,sign,0),gross(q,sign,1))*v
                    missing.append({'slot':slot,'shares':v,'lo':lo,'hi':hi});continue
                y=yup if is_up else 1-yup;c=gross(q,sign,y);qu,du=up_equivalent(q,sign,is_up)
                # Decimal prices were cached to 28 digits; compare within sub-attocent rounding.
                if abs(c-gross(qu,du,yup))>D('1e-24'):raise ValueError('complement invariance failed')
                rows.append({'date':date,'slot':slot,'group':k,'key':key,'shares':v,'price':q,'sign':sign,'is_up':is_up,'up_price':qu,'up_sign':du,'cents':c,'value':v*c,'selected_receipt':g['tx'] in selected})
                count['payout_joined_legs']+=1
        count.update({'target_print_records':len(x['prints']),'joined_print_records':len(x['joined_print_indices']),'unjoined_print_records':len(x['unmatched']),'active_events':len(x['active_slugs'])})
        funnel[date]={**dict(count),'candidate_known_shares':str(known)}
    agg={'status':'COMPLETE_MEASURABLE_SUBSET','evidence_class':'RETROSPECTIVE_OFFLINE','funnel':funnel,'excluded':dict(exclusions),'measurement':hierarchy(rows)}
    agg['direction']={name:hierarchy([r for r in rows if r['up_sign']==s]) for name,s in [('up_equivalent_buy',1),('up_equivalent_sell',-1)]}
    agg['price_bins']={name:hierarchy([r for r in rows if bucket(r['up_price'])==i]) for i,name in enumerate(['[0,.2)','[.2,.4)','[.4,.6)','[.6,.8)','[.8,1]'])}
    events=collections.defaultdict(list)
    for r in rows:events[r['slot']].append(r)
    events_order=sorted(events,key=lambda s:(events[s][0]['date'],int(s)))
    agg['event_aggregates']=[{'ordinal':i+1,'date':events[s][0]['date'],**summary(events[s])} for i,s in enumerate(events_order)]
    if events:
        big=max(events,key=lambda s:sum((r['shares'] for r in events[s]),D(0)))
        absbig=max(events,key=lambda s:abs(sum((r['value'] for r in events[s]),D(0))))
        # Also distinguish a large raw value from the actual hierarchical-weight contribution.
        def contribution(s):
            rr=events[s];n=sum(events[t][0]['date']==rr[0]['date'] for t in events)
            return sum((r['value'] for r in rr),D(0))/sum((r['shares'] for r in rr),D(0))/n/3
        primarybig=max(events,key=lambda s:abs(contribution(s)))
        agg['sensitivity']={name:{'removed_ordinal':events_order.index(s)+1,**hierarchy([r for r in rows if r['slot']!=s])} for name,s in [('drop_largest_shares_event',big),('drop_largest_absolute_total_cents_event',absbig),('drop_largest_absolute_primary_contribution_event',primarybig)]}
        total=sum((r['shares'] for r in rows),D(0))
        agg['concentration']={'largest_event_share_fraction':float(sum((r['shares'] for r in events[big]),D(0))/total),'largest_absolute_primary_contribution_cents':float(contribution(primarybig))}
    agg['missing_payment_known_legs']={'legs':len(missing),'shares':str(sum((r['shares'] for r in missing),D(0))),'total_cents_lower':str(sum((r['lo'] for r in missing),D(0))),'total_cents_upper':str(sum((r['hi'] for r in missing),D(0)))}
    agg['independently_receipt_checked_structural_examples']={'groups':len({r['group'] for r in rows if r['selected_receipt']}),'legs':sum(r['selected_receipt'] for r in rows),'note':'Fixed 24 pilot cases only; full population uses inherited event mechanism, not independent receipt audit.'}
    agg['limits']=['Three exposed activity-selected hours, not all makers or full days.','Gross value relative to settlement excludes fees, inventory basis, hedges, early exits, rebates and capital costs.','Unjoined print quantities do not establish missing maker quantities; no whole-population bounds.','Fewer than five events in any displayed stratum cannot support a stable pattern.','CTF binding inherits both-token collection/position and USDC.e collateral verification; historical label availability unknown.']
    return agg,rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--public',type=Path,required=True);ap.add_argument('--private',type=Path,required=True);a=ap.parse_args();start=time.monotonic();cpu=time.process_time()
    manifest=read(a.repo/'results/polymarket_settlement_external_v1/overnight_extension_manifest.json')
    for rel,expected in manifest['sources'].items():
        if sha(a.repo/rel)!=expected['sha256']:raise ValueError('input hash mismatch '+rel)
    b=a.repo/'_private/rocklabs/2026-09-23';paths={DATES[0]:b/'identification_v1_private.json',**{d:b/'validation-windows'/d/'identification_private.json' for d in DATES[1:]}}
    p=a.repo/'_private/polymarket_multiday_price_v1'
    agg,rows=analyze({d:read(path) for d,path in paths.items()},read(p/'roster_private.json'),read(p/'ctf_labels_private.json'))
    private=[{k:(str(v) if isinstance(v,D) else v) for k,v in row.items()} for row in rows]
    dump(a.private,private);agg['private_rows_sha256']=sha(a.private);agg['script_sha256']=sha(Path(__file__));agg['manifest_sha256']=sha(a.repo/'results/polymarket_settlement_external_v1/overnight_extension_manifest.json')
    agg['resources']={'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,'max_rss_platform_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'network_requests':0,'raw_hour_reads':0,'input_cache_bytes':sum(v['bytes'] for v in manifest['sources'].values())}
    dump(a.public,agg);print(json.dumps({'status':agg['status'],'measurement':agg['measurement'],'exclusions':agg['excluded']}))
if __name__=='__main__':main()
