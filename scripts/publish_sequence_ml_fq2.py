"""Publish validated infrastructure-neutral FQ2 aggregate receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--config', type=Path, default=Path('configs/sequence_ml_fq2_v1.json'))
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError('preserve existing public FQ2 receipts')
    cfg = json.loads(args.config.read_text())
    expected = {f'fq2_{size}_{symbol}_a1.json' for size in cfg['training_sizes_per_stock']
                for symbol in cfg['symbols']}
    actual = {p.name for p in args.raw.glob('*.json')}
    if actual != expected:
        raise ValueError(f'incomplete/extra FQ2 receipt set: missing={sorted(expected-actual)} extra={sorted(actual-expected)}')
    reports = {}
    for name in sorted(expected):
        path = args.raw / name
        report = json.loads(path.read_text())
        if report['stage'] != 'FQ2' or report['config_sha256'] != sha(args.config):
            raise ValueError(f'protocol identity mismatch: {name}')
        if 'gpu_device_name' not in report:
            raise ValueError(f'missing expected hardware redaction field: {name}')
        report.pop('gpu_device_name')
        report['private_raw_receipt_sha256'] = sha(path)
        report['public_redactions'] = ['gpu_device_name']
        reports[name] = report
    args.out.mkdir(parents=True)
    for name, report in reports.items():
        (args.out / name).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'complete', 'public_reports': len(reports)}))


if __name__ == '__main__':
    main()
