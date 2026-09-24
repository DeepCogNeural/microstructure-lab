"""Freeze label-blind seven-day event cohort and aggregate source/quote coverage."""
from __future__ import annotations
import argparse,collections,hashlib,json,os
from pathlib import Path
DAYS=('2026-07-27','2026-07-28','2026-07-29','2026-07-30','2026-07-31','2026-08-01','2026-08-02')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save_private(p,x):p.write_text(json.dumps(x,separators=(',',':'))+'\n');os.chmod(p,0o600)
def main():
 a=argparse.ArgumentParser();a.add_argument('--private-dir',type=Path,required=True);a.add_argument('--public-dir',type=Path,required=True);p=a.parse_args()
 root=p.private_dir;public=p.public_dir;public.mkdir(parents=True,exist_ok=True)
 if (root/'events_before_labels_private.json').exists():raise ValueError('refuse to overwrite prelabel event table')
 freeze=json.loads((root/'freeze_private.json').read_text());roster=json.loads((root/'roster_private.json').read_text())
 rows=[];receipts=[];hour_count=0;counts=collections.Counter();unknown=0
 for day in DAYS:
  for h in range(24):
   f=root/'hours'/f'{day}-{h:02d}.json'
   if not f.exists():raise ValueError('missing scanned hour')
   x=json.loads(f.read_text());hour_count+=1;rows.extend(x['events']);receipts.extend(x['source_receipts'])
   counts.update(x['counts']);unknown+=x['unknown_btc_metadata_count']
 if counts['invalid_receive_timestamp']:raise ValueError('invalid receive timestamp in target/metadata input')
 expected={z['path']:z['size_bytes'] for z in freeze['fixed_manifest_objects'] if z['path'].startswith('raw/20')}
 if {z['path']:z['size_bytes'] for z in receipts}!=expected:raise ValueError('scanned CLOB path/size mismatch')
 if len(receipts)!=len(expected) or sum(z['read_bytes'] for z in receipts)>112*2**30:raise ValueError('duplicate source or input budget exceeded')
 rows.sort(key=lambda z:z['slot'])
 if len(rows)!=2016 or [z['slot'] for z in rows]!=list(range(2016)) or set(roster)!={str(i) for i in range(2016)}:
  raise ValueError('fixed event roster mismatch')
 out=root/'events_before_labels_private.json';save_private(out,rows)
 by_day={}
 for day in DAYS:
  group=[z for z in rows if z['date']==day]
  if len(group)!=288:raise ValueError('date slot mismatch')
  by_day[day]={'calendar_slots':288,'gamma_confirmed_events':288,
      'inline_up_metadata_seen':sum(x['metadata_seen'] for x in group),
      'identity_conflicts':sum(x['identity_status']!='gamma_verified' for x in group),
      'bbo':dict(collections.Counter(x['bbo_status'] for x in group)),
      'history':dict(collections.Counter(x['history_status'] for x in group)),
      'snapshot_quantity':dict(collections.Counter(x['snapshot_status'] for x in group)),
      'price_eligible_before_labels':sum(x['p'] is not None and x['identity_status']=='gamma_verified' for x in group),
      'valid_snapshot_on_price_eligible':sum(x['p'] is not None and x['depth'] is not None and x['identity_status']=='gamma_verified' for x in group)}
 receipt_path=public/'source_read_receipts.json'
 receipt_path.write_text(json.dumps({'status':'SOURCE_READ_ONCE','source_zip_sha256':freeze['source_zip_sha256'],
     'source_manifest_sha256':freeze['source_manifest_sha256'],'clob_objects':len(receipts),
     'compressed_clob_bytes_read':sum(z['read_bytes'] for z in receipts),'object_receipts':sorted(receipts,key=lambda x:x['path'])},indent=2,sort_keys=True)+'\n')
 result={'status':'PRELABEL_COHORT_FROZEN','window_utc':'2026-07-27T00:00:00Z/2026-08-03T00:00:00Z',
     'source_zip_sha256':freeze['source_zip_sha256'],'source_manifest_sha256':freeze['source_manifest_sha256'],
     'gamma_cache_sha256':freeze['gamma_cache_sha256'],'gamma_requests':freeze['gamma_requests'],
     'gamma_valid_events':freeze['gamma_valid_events'],'gamma_invalid_reasons':freeze['gamma_invalid_reasons'],
     'hours_scanned':hour_count,'clob_objects_scanned':len(receipts),'compressed_clob_bytes_read':sum(z['read_bytes'] for z in receipts),
     'event_table_private_sha256':sha(out),'source_read_receipts_sha256':sha(receipt_path),
     'target_record_counts':dict(counts),'unknown_btc_metadata_lines_by_hour_sum':unknown,'by_day':by_day,
     'label_status':'not_opened_at_this_stage'}
 (public/'event_coverage_prelabel.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'events':len(rows),'price_eligible_by_day':{d:x['price_eligible_before_labels'] for d,x in by_day.items()},
                   'valid_snapshot_by_day':{d:x['valid_snapshot_on_price_eligible'] for d,x in by_day.items()},
                   'source_bytes':result['compressed_clob_bytes_read']},sort_keys=True))
if __name__=='__main__':main()
