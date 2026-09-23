"""Recompute six public WSE aggregates byte-for-byte from public run receipts."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
STAGES={
 'FQ2':('scripts/aggregate_sequence_ml_fq2.py',['--reports','results/sequence_ml_fq2_v1']),
 'FQ3':('scripts/aggregate_sequence_ml_fq3.py',[]),
 'FQ4':('scripts/aggregate_sequence_ml_fq4.py',[]),
 'Q8':('scripts/aggregate_sequence_ml_q8.py',[]),
 'Q10':('scripts/aggregate_sequence_ml_q10.py',[]),
 'Q11':('scripts/aggregate_sequence_ml_q11.py',[]),
}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('results/sequence_ml_final_v1/recomputation.json'));a=ap.parse_args()
 if a.out.exists():raise ValueError('preserve existing recomputation receipt')
 results={}
 with tempfile.TemporaryDirectory() as tmp:
  for stage,(script,args) in STAGES.items():
   target=Path(f'results/sequence_ml_{stage.lower()}_v1/{stage.lower()}_summary.json')
   fresh=Path(tmp)/f'{stage.lower()}_summary.json'
   subprocess.run(['python3',script,*args,'--out',str(fresh)],check=True,capture_output=True,text=True)
   digest=sha(target)
   if sha(fresh)!=digest or fresh.read_bytes()!=target.read_bytes():raise ValueError(f'{stage} aggregate not byte identical')
   results[stage]={'aggregate_sha256':digest,'byte_identical':True}
 out={'stage':'FINAL_WSE_AGGREGATE_RECOMPUTATION','result':'ALL_SIX_BYTE_IDENTICAL','stages':results,
      'limits':'Uses public run receipts and deterministic aggregate code; does not rehash private model weights or original licensed rows.'}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'stages':len(results),'receipt_sha256':sha(a.out)}))
if __name__=='__main__':main()
