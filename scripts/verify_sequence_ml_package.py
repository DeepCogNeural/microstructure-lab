"""Build and verify the public Q6 source/data/model/run hash inventory."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('results/sequence_ml_v1')
OUT = ROOT / 'q6_scientific_manifest.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name: str) -> dict:
    return json.loads((ROOT / name).read_text())


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], text=True).strip()


def main() -> None:
    q1, q2, q3 = read('q1_pilot.json'), read('q2_summary.json'), read('q3_summary.json')
    render = read('q6_render_manifest.json')
    assert sha(ROOT / 'q2_summary.json') == render['source_aggregate_sha256']['q2_summary']
    assert sha(ROOT / 'q3_summary.json') == render['source_aggregate_sha256']['q3_summary']
    for name, expected in render['figures_sha256'].items():
        assert sha(ROOT / 'figures' / name) == expected
    assert sha(ROOT / 'cost_table.csv') == render['cost_table_sha256']
    q2_reports = sorted(ROOT.glob('q2_*.json'))
    q2_reports = [p for p in q2_reports if p.stem not in ('q2_summary', 'q2_label_control_pekao')]
    q3_updates = sorted(ROOT.glob('q3_update_*.json'))
    q3_diagnostics = sorted(ROOT.glob('q3_diagnostic_*.json'))
    assert len(q2_reports) == 5 and len(q3_updates) == 15 and len(q3_diagnostics) == 5
    for report in q2_reports + q3_updates + q3_diagnostics:
        assert read(report.name)['cache_manifest_sha256'] == q1['manifest_sha256']
    assert q2['source_cache_manifest_sha256'] == q1['manifest_sha256']
    receipt_hashes = {p.name: sha(p) for p in q2_reports + q3_updates + q3_diagnostics}
    assert all(q2['input_report_hashes'][read(p.name)['symbol']] == sha(p) for p in q2_reports)
    raw_source = {s: d['sha256'] for s, d in q1['source_files'].items()}
    model_hashes = {
        'q2': {read(p.name)['symbol']: {arm: cost['model_sha256'] for arm, cost in read(p.name)['costs'].items()} for p in q2_reports},
        'q3_updates': {p.stem.removeprefix('q3_update_'): {arm: cost['model_sha256'] for arm, cost in read(p.name)['costs'].items()} for p in q3_updates},
    }
    assert all(len(v) == 7 for v in model_hashes['q2'].values())
    assert all(len(v) == 4 for v in model_hashes['q3_updates'].values())
    manifest = {
        'stage': 'Q6',
        'branch': git('branch', '--show-current'),
        'package_parent_commit': git('rev-parse', 'HEAD'),
        'source_commits': {
            'q1': 'a7e21922f029bb6542acf387a40c0baa5e285e5b',
            'q2_frozen_runner': q2['scientific_commit'],
            'q2_aggregate': '6969ea0188962b61871263a0dcc34077ea49d9b1',
            'q3_frozen_runner': '0f17ab665eaf11280efde3ac8a57a7b0a2bbe51b',
            'q3_diagnostic': '8e75af1e63af51a1219e746cd5fa6b5cf939ad3b',
            'q3_aggregate': '93c31d271b21773d74e115d89e7c6273bb0ea059',
            'q4_gate': '0c454e4a1f28d0960ad15ca03780c586209b0358',
            'q5_audit': git('rev-parse', 'HEAD'),
        },
        'data': {
            'wselob_v1_raw_source_sha256_from_prior_receipts_not_locally_rehashed': raw_source,
            'verified_local_feature_cache_manifest_sha256': q1['manifest_sha256'],
            'cache_source_hash': q1['cache_source_hash'],
            'q2_config_sha256': q2['config_sha256'],
            'q3_config_sha256': q3['q3_config_sha256'],
        },
        'model_sha256_from_aggregate_receipts': model_hashes,
        'run_receipt_sha256': receipt_hashes,
        'aggregate_sha256': {name: sha(ROOT / name) for name in ('q1_pilot.json', 'q2_summary.json', 'q2_label_control_pekao.json', 'q3_summary.json', 'q4_gate.json', 'q5_data_gate.json')},
        'q6_output_sha256': {
            'research_brief': sha(Path('docs/SEQUENCE_ML_RESEARCH_BRIEF.md')),
            'render_manifest': sha(ROOT / 'q6_render_manifest.json'),
            'cost_table': sha(ROOT / 'cost_table.csv'),
            'figures': render['figures_sha256'],
        },
        'recomputation': 'Q2 and Q3 CPU aggregate scripts reran locally; before/after summary SHA-256 matched. No model refit or new final outcomes in Q6.',
        'limits': 'Historical exposed 2017 aggregate receipts; no independent final, profitable crossing, or CPU core-hour claim. Raw files, model weights and row predictions are not committed.',
    }
    assert manifest['branch'] == 'codex/quant-ai-ml-20260922'
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'manifest_sha256': sha(OUT), 'q2_reports': len(q2_reports), 'q3_updates': len(q3_updates), 'q3_diagnostics': len(q3_diagnostics), 'model_hashes': sum(map(len, model_hashes['q2'].values())) + sum(map(len, model_hashes['q3_updates'].values()))}))


if __name__ == '__main__':
    main()
