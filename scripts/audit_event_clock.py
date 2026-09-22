"""Check source clock units, date mapping, monotonicity and observed precision."""
import argparse
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
from cloblab.scale_common import read_json,file_hash


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',required=True);p.add_argument('--out',default='results/wselob_research_audit_v1');a=p.parse_args()
 c=read_json('configs/wselob_research_audit_v1.json');sources=read_json('configs/wselob_sources_v1.json')['files'];rows=[]
 for symbol,src in sources.items():
  path=Path(a.raw)/src['filename']
  if file_hash(path)!=src['sha256']:raise ValueError('raw source changed')
  with h5py.File(path,'r') as handle:
   for key in sorted(handle):
    day=pd.Timestamp(key[1:]).strftime('%Y-%m-%d')
    if day[:7] not in c['months'] and day not in c['later_dates']:continue
    records=handle[key+'/table'][:];t=records['time'];delta=np.diff(t);positive=delta[delta>0]
    if (delta<0).any():raise ValueError('nonmonotonic event clock')
    matches=set(pd.to_datetime(t,unit='ns',utc=True).tz_convert('Europe/Warsaw').strftime('%Y-%m-%d'))=={day}
    if not matches:raise ValueError('source day disagrees with event clock')
    rows.append(dict(symbol=symbol,day=day,source_messages=len(t),field='time',storage_unit='ns_since_epoch',priority_field_used=False,monotonic=True,zero_adjacent=int((delta==0).sum()),adjacent_pairs=len(delta),min_positive_delta_ns=int(positive.min()) if len(positive) else None,positive_delta_gcd_ns=int(np.gcd.reduce(positive)) if len(positive) else None,timezone='Europe/Warsaw',source_day_matches=matches))
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);pd.DataFrame(rows).to_csv(out/'event_clock_precision.csv',index=False)
 print(f'{len(rows)} source-day clock checks')

if __name__=='__main__':main()
