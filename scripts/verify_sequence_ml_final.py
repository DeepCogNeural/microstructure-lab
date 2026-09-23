"""Recompute final WSE package lineage and inventory public source/run/model hashes."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
OUT=Path('results/sequence_ml_final_v1')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(cond,msg):
    if not cond:raise ValueError(msg)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest-out',type=Path,default=OUT/'scientific_manifest.json');args=ap.parse_args()
    paths={s:Path(p) for s,p in {
        'Q1':'results/sequence_ml_v1/q1_pilot.json','FQ2':'results/sequence_ml_fq2_v1/fq2_summary.json',
        'FQ3':'results/sequence_ml_fq3_v1/fq3_summary.json','FQ4':'results/sequence_ml_fq4_v1/fq4_summary.json',
        'FQ4_gate':'results/sequence_ml_fq4_v1/fq4_gate.json','FQ5_source_audit':'results/sequence_ml_v1/q5_data_gate.json',
        'Q8':'results/sequence_ml_q8_v1/q8_summary.json','Q10':'results/sequence_ml_q10_v1/q10_summary.json',
        'Q11':'results/sequence_ml_q11_v1/q11_summary.json'}.items()}
    d={k:read(p) for k,p in paths.items()};render=read(OUT/'render_manifest.json')
    brief=Path('docs/SEQUENCE_ML_FINAL_RESEARCH_BRIEF.md')
    index=Path('docs/SEQUENCE_ML_FINAL_PACKAGE.md')
    recomputation_path=OUT/'recomputation.json';recomputation=read(recomputation_path)
    require(recomputation['result']=='ALL_SIX_BYTE_IDENTICAL' and set(recomputation['stages'])=={'FQ2','FQ3','FQ4','Q8','Q10','Q11'},'aggregate recomputation receipt')
    require(all(item['byte_identical'] and item['aggregate_sha256']==sha(paths[stage]) for stage,item in recomputation['stages'].items()),'aggregate recomputation identity')
    require(d['FQ5_source_audit']['verdict']=='PENDING_INDEPENDENT_CONFIRMATION' and not d['FQ5_source_audit']['outcomes_viewed'],'independent-data boundary')
    require(render['input_aggregate_sha256']=={k:sha(paths[k]) for k in ('FQ2','FQ3','FQ4','Q8','Q10','Q11')},'render aggregate lineage')
    require(len(render['figure_sha256'])==4 and all(sha(OUT/'figures'/name)==digest for name,digest in render['figure_sha256'].items()),'figure hashes')
    require(sha(OUT/'cost_table.csv')==render['cost_table_sha256'],'cost table hash')
    require(brief.exists() and index.exists(),'final documentation missing')
    cache=d['Q1']['manifest_sha256']
    require(d['FQ2']['source_cache_manifest_sha256']==cache and d['FQ4']['cache_manifest_sha256']==cache and d['Q8']['cache_manifest_sha256']==cache and d['Q10']['cache_manifest_sha256']==cache and d['Q11']['cache_manifest_sha256']==cache,'cache identity')
    require(d['FQ3']['fq3_config_sha256']==sha('configs/sequence_ml_fq3_v1.json') and d['FQ4']['gate_sha256']==sha(paths['FQ4_gate']) and d['FQ4_gate']['gate_triggered'],'formal gate lineage')
    cfg={s:Path(f'configs/sequence_ml_{s.lower()}_v1.json') for s in ('FQ2','FQ3','FQ4','Q8','Q10','Q11')}
    for s in ('FQ2','FQ4','Q8','Q10','Q11'):
        require(d[s]['config_sha256' if s!='FQ2' else 'config_sha256']==sha(cfg[s]),f'{s} config identity')
    q11cfg=read(cfg['Q11'])
    require((q11cfg['parent_Q8_summary_sha256'],q11cfg['parent_Q10_summary_sha256'])==(sha(paths['Q8']),sha(paths['Q10'])),'Q11 parent hashes')
    source_registry_path=Path('configs/wselob_sources_v1.json');source_registry=read(source_registry_path)
    require(q11cfg['source_registry_sha256']==sha(source_registry_path),'source registry')
    reports={};models={};private_predictions={};partition_hashes={}
    def add(stage,key,path,expected,model_field=True):
        require(sha(path)==expected,f'{stage} receipt changed: {key}')
        item=read(path);reports[f'{stage}/{key}']=expected
        if model_field:models[f'{stage}/{key}']={arm:cost['model_sha256'] for arm,cost in item['costs'].items()}
        if 'private_predictions_sha256' in item:private_predictions[f'{stage}/{key}']=item['private_predictions_sha256']
        return item
    # All sample-size, rolling, architecture, context, transfer and execution receipts.
    for size in (50000,100000,200000):
        for symbol in d['FQ2']['symbols']:
            add('FQ2',f'{size}/{symbol}',Path(f'results/sequence_ml_fq2_v1/fq2_{size}_{symbol}_a1.json'),d['FQ2']['input_run_sha256'][str(size)][symbol])
    for key,digest in d['FQ3']['input_update_hashes'].items():
        month,symbol=key.split('/');add('FQ3',key,Path(f'results/sequence_ml_fq3_v1/fq3_update_{month}_{symbol}.json'),digest)
    for symbol,digest in d['FQ3']['input_diagnostic_hashes'].items():
        add('FQ3_diagnostic',symbol,Path(f'results/sequence_ml_fq3_v1/fq3_diagnostic_{symbol}.json'),digest,False)
    for symbol,pair in d['FQ4']['input_receipt_sha256'].items():
        add('FQ4',symbol,Path(f'results/sequence_ml_fq4_v1/fq4_transformer_{symbol}.json'),pair['fq4'])
    for key,digest in d['Q8']['input_receipt_sha256'].items():
        context,symbol=key.split('/');add('Q8',key,Path(f'results/sequence_ml_q8_v1/q8_context{context}_{symbol}.json'),digest)
    for symbol,digest in d['Q10']['input_receipt_sha256'].items():
        report=add('Q10',symbol,Path(f'results/sequence_ml_q10_v1/q10_transfer_{symbol}.json'),digest)
        require(report['heldout_symbol']==symbol and len(report['source_symbols'])==4 and symbol not in report['source_symbols'],'Q10 source-only scope')
    for symbol,digest in d['Q11']['input_receipt_sha256'].items():
        report=add('Q11',symbol,Path(f'results/sequence_ml_q11_v1/q11_execution_{symbol}.json'),digest,False)
        require((report['q8_summary_sha256'],report['q10_summary_sha256'])==(sha(paths['Q8']),sha(paths['Q10'])),'Q11 parent report')
        q8_path=Path(f"results/sequence_ml_q8_v1/q8_context{report['q8_selected_context']}_{symbol}.json")
        q10_path=Path(f'results/sequence_ml_q10_v1/q10_transfer_{symbol}.json')
        require((report['q8_report_sha256'],report['q10_report_sha256'])==(sha(q8_path),sha(q10_path)),'Q11 source report hashes')
        require((report['q8_private_predictions_sha256'],report['q10_private_predictions_sha256'])==(
            read(q8_path)['private_predictions_sha256'],read(q10_path)['private_predictions_sha256']),'Q11 private prediction lineage')
        require(report['original_source_sha256']==source_registry['files'][symbol]['sha256'],'Q11 original source')
        partition_hashes[symbol]=report['source_partition_hashes']
        private_predictions[f'Q11_Q8/{symbol}']=report['q8_private_predictions_sha256']
        private_predictions[f'Q11_Q10/{symbol}']=report['q10_private_predictions_sha256']
    require(len(reports)==65 and sum(len(v) for v in models.values())==215,'run/model denominator')
    require(all(len(h)==64 for arms in models.values() for h in arms.values()),'model hash length')
    require(all(len(h)==64 for h in private_predictions.values()),'private prediction hash length')
    require(d['Q8']['evaluation']['128']['cells_per_arm']==315 and d['Q10']['cells_per_arm']==315 and d['Q11']['stock_day_cells']==315,'evaluation stock/day denominator')
    allocation={s:Path(f'results/sequence_ml_{s.lower()}_v1/{s.lower()}_gpu_allocation.json') for s in ('FQ2','FQ3','FQ4','Q8','Q10')}
    allocation['Q11']=Path('results/sequence_ml_q11_v1/q11_cpu_allocation.json')
    for stage,path in allocation.items():
        a=read(path);require(a['nonempty_stderr_count']==0 and a['task_count']>0,f'{stage} allocation completeness')
    branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()
    require(branch=='codex/quant-ai-ml-20260922','wrong scientific task branch')
    manifest={'stage':'FINAL_WSE_RETROSPECTIVE','branch':branch,
        'package_parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_commit':{**{s:d[s]['source_commit'] for s in ('FQ2','FQ4','Q8','Q10','Q11')},
                         'FQ3_updates':d['FQ3']['updated_runner_commit'],'FQ3_fixed':d['FQ3']['fixed_runner_commit']},
        'source_cache_manifest_sha256':cache,
        'original_source_registry_sha256':sha(source_registry_path),
        'original_source_sha256_from_receipts':{s:source_registry['files'][s]['sha256'] for s in d['Q10']['symbols']},
        'evaluation_partition_hashes_from_Q11_receipts':partition_hashes,
        'protocol_sha256':{s:sha(p) for s,p in cfg.items()},
        'run_receipt_sha256':reports,
        'model_sha256_from_receipts_not_fresh_model_rehash':models,
        'private_prediction_sha256_from_receipts_not_public_arrays':private_predictions,
        'aggregate_sha256':{s:sha(p) for s,p in paths.items()},
        'allocation_sha256':{s:sha(p) for s,p in allocation.items()},
        'output_sha256':{'brief':sha(brief),'index':sha(index),'recomputation':sha(recomputation_path),'render_manifest':sha(OUT/'render_manifest.json'),
                         'cost_table':sha(OUT/'cost_table.csv'),'figures':render['figure_sha256']},
        'limits':'2017 historical/exposed evaluation. Q5 source audit found no qualified independent cohort. Visible execution is not realized fill/PnL. Private data, rows, weights and scheduler logs excluded.'}
    path=args.manifest_out
    if path.exists():raise ValueError('preserve final scientific manifest')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'run_receipts':len(reports),'model_hashes':sum(len(v) for v in models.values()),'manifest_sha256':sha(path)}))
if __name__=='__main__':main()
