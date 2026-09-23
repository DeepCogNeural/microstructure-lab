"""Apply the frozen Transformer gate to formal FQ2/FQ3 retrospective evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate(fq2: dict, fq3: dict) -> dict:
    if fq2.get('stage')!='FQ2' or fq3.get('retrospective_only') is not True:
        raise ValueError('wrong formal stage identity')
    if fq3.get('updated_fit_cells')!=15 or len(fq3.get('input_diagnostic_hashes',{}))!=5:
        raise ValueError('FQ3 incomplete')
    level=fq2['levels']['200000']
    result=level['full_denominator_result']
    if result is None or level['undefined_cells']['dev'] or level['undefined_cells']['evaluation']:
        raise ValueError('FQ2 full-denominator result missing')
    paired=result['paired_vs_B1']
    main=paired['S0_seed_mean']
    seeds=[paired[f'S0_history_gru_seed{s}']['mean_delta_ic'] for s in (7,17,29)]
    months=main['month_delta']
    loso=main['leave_one_stock_out_delta']
    limits=[(stock,arm) for stock,arms in level['training_limited'].items()
            for arm,limited in arms.items() if limited]
    criteria={
        'formal_200k_complete':level['training_size_per_stock']==200000 and level['evaluation_cells_per_arm']==315,
        'gru_not_training_limited':not limits,
        'paired_delta_at_least_0_005':main['mean_delta_ic']>=.005,
        'all_three_seed_means_positive':all(v>0 for v in seeds),
        'at_least_two_retrospective_months_positive':sum(v>0 for v in months.values())>=2,
        'no_single_stock_determines_aggregate_sign':len(loso)==5 and all(v>0 for v in loso.values()),
        'fq3_formal_robustness_complete':fq3['updated_fit_cells']==15 and len(fq3['input_diagnostic_hashes'])==5,
    }
    return {'stage':'FQ4','retrospective_only':True,
            'gate_triggered':all(criteria.values()),'criteria':criteria,
            'paired_200k_delta_ic':main['mean_delta_ic'],
            'seed_paired_delta_ic':dict(zip(('7','17','29'),seeds)),
            'month_paired_delta_ic':months,'leave_one_stock_out_delta_ic':loso,
            'training_limited_stock_arms':limits,
            'limits':'Gate applies only to exposed 2017 dates and does not by itself prove unseen gain, economic value, or authorize architecture claims. Sequence correctness tests are a separate required pre-fit check.'}


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--fq2',type=Path,default=Path('results/sequence_ml_fq2_v1/fq2_summary.json'))
    ap.add_argument('--fq3',type=Path,default=Path('results/sequence_ml_fq3_v1/fq3_summary.json'))
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists():raise ValueError('preserve existing FQ4 gate receipt')
    report=gate(json.loads(args.fq2.read_text()),json.loads(args.fq3.read_text()))
    report['fq2_summary_sha256']=sha(args.fq2)
    report['fq3_summary_sha256']=sha(args.fq3)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'gate_triggered':report['gate_triggered'],'criteria':report['criteria']}))


if __name__=='__main__':main()
