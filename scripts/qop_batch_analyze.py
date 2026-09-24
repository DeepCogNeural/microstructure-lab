"""Aggregate-only QOP expanded measurement, missingness and stability analysis."""
from __future__ import annotations
import argparse,collections,hashlib,json
from decimal import Decimal
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--build-private',type=Path,required=True)
p.add_argument('--features-private',type=Path,required=True)
p.add_argument('--selection-private',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():raise ValueError('preserve output')
build=json.loads(a.build_private.read_text());rows=build['leg_rows']
features=json.loads(a.features_private.read_text())['rows']
selection=json.loads(a.selection_private.read_text());events=selection['events']
assert len(features)==len(rows)

def fnum(x):return float(x)
def summary(seq,age=1000,horizon=5000):
    key=f'{age}_{horizon}'
    eligible=[x for x in seq if not x['failure'][key]]
    if not eligible:return {'legs':0,'events':0,'shares':'0','G':None,'D':None,'N':None}
    volume=sum(fnum(x['shares']) for x in eligible)
    out={'legs':len(eligible),'events':len({x['event_idx'] for x in eligible}),'shares':str(sum((Decimal(x['shares']) for x in eligible),Decimal(0)))}
    for v in ('G','D','N'):
        values=[fnum(x['quote'][key][v]) for x in eligible]
        out[v]={'share_weighted_mean_cents':sum(fnum(x['shares'])*fnum(x['quote'][key][v]) for x in eligible)/volume,
                'range_cents':[min(values),max(values)],
                'event_equal_mean_cents':sum(sum(fnum(x['shares'])*fnum(x['quote'][key][v]) for x in eligible if x['event_idx']==e)/sum(fnum(x['shares']) for x in eligible if x['event_idx']==e) for e in {x['event_idx'] for x in eligible})/out['events']}
    return out

selected_shares=sum((Decimal(x['shares']) for x in rows),Decimal(0))
full={f'{age}_{h}':summary(rows,age,h) for age in (1000,250) for h in (5000,30000)}
per_event=[]
for e in range(len(events)):
    ss=[x for x in rows if x['event_idx']==e]
    per_event.append({'event_index':e,'selected_legs':len(ss),'selected_shares':str(sum((Decimal(x['shares']) for x in ss),Decimal(0))),
                      'primary':summary(ss,1000,5000),'sensitivity':summary(ss,250,5000)})
primary=[x for x in rows if not x['failure']['1000_5000']]
sensitivity=[x for x in rows if not x['failure']['250_5000']]
common=[x for x in rows if not x['failure']['1000_5000'] and not x['failure']['250_5000']]
assert len(common)==len(sensitivity)
max_leg=max(primary,key=lambda x:Decimal(x['shares'])) if primary else None
volumes=collections.defaultdict(Decimal)
for x in primary:volumes[x['event_idx']]+=Decimal(x['shares'])
max_event=max(volumes,key=lambda e:volumes[e]) if volumes else None
failure={f'{age}_{h}':dict(collections.Counter(reason for x in rows for reason in x['failure'][f'{age}_{h}'])) for age in (1000,250) for h in (5000,30000)}
# Conservative price-only bounds on all receipt-joined selected-token legs; unavailable receipts
# have unknown shares and are outside this quantified denominator.
known_sum=Decimal(0);lower=Decimal(0);upper=Decimal(0)
for x in rows:
    shares=Decimal(x['shares']);q=Decimal(x['price']);d=x['sign'];known_sum+=shares
    lo,hi=(-q,1-q) if d==1 else (q-1,q)
    if x['failure']['1000_5000']:
        lower+=100*shares*lo;upper+=100*shares*hi
    else:
        n=Decimal(x['quote']['1000_5000']['N']);lower+=shares*n;upper+=shares*n
bounds={'known_selected_leg_shares':str(known_sum),
        'all_selected_legs_N5_share_weighted_cents_range_if_missing_mid_only_bounded_0_to_1':
        [str(lower/known_sum),str(upper/known_sum)] if known_sum else None}

# Shifted anchor labels and features are independently reconstructed in qop_batch_features.py.
shifted={}
for shift in ('-500','0','500'):
    subset=[x for x in features if x['shift'][shift]['labels'].get('5000')]
    w=sum(fnum(x['shares']) for x in subset)
    shifted[shift]={'eligible_legs':len(subset),'events':len({x['event_idx'] for x in subset}),
        'feature_available_1s':sum(bool(x['features'].get(f'{shift}_1000')) for x in subset),
        'feature_available_5s':sum(bool(x['features'].get(f'{shift}_5000')) for x in subset),
        'share_weighted_G_D_N_cents':{k:(sum(fnum(x['shares'])*fnum(x['shift'][shift]['labels']['5000'][k]) for x in subset)/w if w else None) for k in ('G','D','N')}}
common_shift=[x for x in features if all(x['shift'][s]['labels'].get('5000') for s in ('-500','0','500'))]
shifted['common_all_shifts']={'legs':len(common_shift),'events':len({x['event_idx'] for x in common_shift})}
for shift in ('-500','0','500'):
    w=sum(fnum(x['shares']) for x in common_shift)
    shifted['common_all_shifts'][shift]={k:(sum(fnum(x['shares'])*fnum(x['shift'][shift]['labels']['5000'][k]) for x in common_shift)/w if w else None) for k in ('G','D','N')}
exit_side=[x for x in features if x['shift']['0']['labels'].get('5000')]
exit_total=sum(fnum(x['shares']) for x in exit_side)
exit_mean=(sum(fnum(x['shares'])*fnum(x['shift']['0']['labels']['5000']['exit_side_cents']) for x in exit_side)/exit_total if exit_total else None)
fee=collections.defaultdict(Decimal)
for x in rows:fee['BUY' if x['sign']==1 else 'SELL']+=Decimal(x['fee_raw'])
blocks={f'{j*6:02d}-{(j+1)*6:02d}UTC':summary([x for x in rows if x['event_idx']//24==j]) for j in range(4)}
sides={'BUY':summary([x for x in rows if x['sign']==1]),'SELL':summary([x for x in rows if x['sign']==-1])}
result={'status':'DEVELOPMENT_MEASUREMENT_ONLY','source':'OutcomeTick samples-2026-09-08',
        'selected_events':len(events),'receipt_joined_selected_token_legs':len(rows),'receipt_joined_selected_token_shares':str(selected_shares),
        'coverage':full,'failure_reasons':failure,'common_age_sample':{'legs':len(common),'primary':summary(common,1000,5000),'sensitivity':summary(common,250,5000)},
        'by_event':per_event,'by_six_hour_block':blocks,'by_passive_side':sides,
        'concentration':{'largest_leg_shares':str(max_leg['shares']) if max_leg else None,
            'without_largest_leg':summary([x for x in rows if x is not max_leg]),
            'largest_primary_event_shares':str(volumes[max_event]) if max_event is not None else None,
            'without_largest_primary_event':summary([x for x in rows if x['event_idx']!=max_event])},
        'shifted_anchor_ms':shifted,'mid_quote_vs_exit_side':{'mid_N5_share_weighted_cents':full['1000_5000']['N']['share_weighted_mean_cents'] if full['1000_5000']['N'] else None,
            'exit_bid_for_buy_ask_for_sell_cents':exit_mean,'note':'quote arithmetic only; displayed size and executable exit unverified'},
        'selected_maker_fee_raw_by_side':{k:str(v) for k,v in fee.items()},'missing_price_bounds':bounds,
        'private_build_sha256':hashlib.sha256(a.build_private.read_bytes()).hexdigest(),
        'private_features_sha256':hashlib.sha256(a.features_private.read_bytes()).hexdigest(),
        'notes':['age filters select active observations; missing not zero','source-to-receive is not match-time error','no independent date or final opened']}
a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'legs':len(rows),'eligible_1000_5s':full['1000_5000']['legs'],'events_1000_5s':full['1000_5000']['events']}))
