"""Outcome-blind all-day event/hash selection for QOP development batch."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from audit_qop_outcometick_r0 import rows, verify, DAY_START, DAY_END

SEED = 'qop-batch-20260923-v1'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sample-root',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--old-fixed-private',type=Path,required=True)
    p.add_argument('--out-private',type=Path,required=True)
    p.add_argument('--out-public',type=Path,required=True)
    a=p.parse_args()
    if a.out_private.exists() or a.out_public.exists():raise ValueError('preserve selection')
    verify(a.sample_root,a.archive)
    old=json.loads(a.old_fixed_private.read_text())
    old_hashes={x['transaction_hash'].lower() for x in old['fixed_20']}
    markets=[{k:x[k] for k in ('slug','condition_id','token_ids','start_sec','end_sec')}
             for x in rows(a.sample_root,'markets') if DAY_START<=x['start_sec'] and x['end_sec']<=DAY_END]
    coverage=defaultdict(lambda:defaultdict(lambda:[0,10**30,0]))
    for kind in ('book','best_bid_ask','last_trade_price'):
        for x in rows(a.sample_root,kind):
            c=coverage[x['slug']][kind]; t=x['event_ts_ms'];c[0]+=1;c[1]=min(c[1],t);c[2]=max(c[2],t)
    eligible=[]
    for m in markets:
        c=coverage[m['slug']];start=m['start_sec']*1000;end=m['end_sec']*1000
        if ('last_trade_price' in c and all(k in c and c[k][1]<=start+30000 and c[k][2]>=end-30000 for k in ('book','best_bid_ask'))):
            eligible.append(m)
    eligible.sort(key=lambda m:(m['start_sec'],m['condition_id']))
    # Uniform metadata-only phase; never chosen by markout, direction or model result.
    positions=[1+3*i for i in range(96) if 1+3*i<len(eligible)]
    chosen=[eligible[j] for j in positions]
    token_map={m['slug']:set(map(str,m['token_ids'])) for m in chosen}
    groups=defaultdict(lambda:defaultdict(list))
    for x in rows(a.sample_root,'last_trade_price'):
        if x['slug'] not in token_map or str(x['asset_id']) not in token_map[x['slug']]:continue
        h=x.get('payload',{}).get('transaction_hash')
        if not h or h.lower() in old_hashes:continue
        groups[x['slug']][h.lower()].append({
            'slug':x['slug'],'asset_id':str(x['asset_id']),'recv_ms':x['recv_ms'],
            'event_ts_ms':x['event_ts_ms'],'side':x['payload'].get('side'),
            'size':str(x['payload'].get('size')),'hash':h.lower()})
    selection=[];counts=[]
    for m in chosen:
        gg=groups[m['slug']]
        ranked=sorted(gg,key=lambda h:(hashlib.sha256((SEED+'|'+m['condition_id']+'|'+h).encode()).hexdigest(),h))
        kept=ranked[:20]
        selection.append({'market':m,'transactions':[{'hash':h,'prints':sorted(gg[h],key=lambda x:(x['recv_ms'],x['asset_id'],x['side'] or ''))} for h in kept]})
        counts.append({'eligible_hashes':len(ranked),'selected_hashes':len(kept),'both_token_prints':sum(len(set(x['asset_id'] for x in gg[h]))==2 for h in kept)})
    private={'seed':SEED,'phase':'eligible_positions_1_mod_3','eligible_market_count':len(eligible),
             'selected_positions':positions,'old_fixed_excluded_hash_count':len(old_hashes),'events':selection}
    a.out_private.write_text(json.dumps(private,sort_keys=True,separators=(',',':'))+'\n')
    digest=hashlib.sha256(a.out_private.read_bytes()).hexdigest()
    public={'status':'FROZEN_BEFORE_NEW_RECEIPT_OR_PRICE_OUTCOME','development_source':'OutcomeTick samples-2026-09-08',
            'archive_sha256':'9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506',
            'selection_seed':SEED,'eligible_market_count':len(eligible),'event_sampling':'positions 1,4,...,286 sorted by (start_sec, condition_id) after first/last 30s coverage screen',
            'selected_events':len(chosen),'candidate_hashes':sum(x['eligible_hashes'] for x in counts),
            'selected_new_hashes':sum(x['selected_hashes'] for x in counts),
            'events_with_20_hashes':sum(x['selected_hashes']==20 for x in counts),
            'both_token_print_hashes':sum(x['both_token_prints'] for x in counts),
            'old_fixed_hashes_excluded':len(old_hashes),'private_selection_sha256':digest,
            'coverage_note':'first/last presence screen, not middle completeness',
            'outcome_blind':'selection used only event identity, presence, token and transaction hash; no price, future quote or receipt outcome'}
    a.out_public.write_text(json.dumps(public,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:public[k] for k in ('eligible_market_count','selected_events','candidate_hashes','selected_new_hashes','both_token_print_hashes')}))
if __name__=='__main__':main()
