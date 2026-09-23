"""Outcome-blind PM0 audit of a pinned public PolyOrderbooks Zenodo release."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from cloblab.polymarket_l2 import audit_snapshot

FILES = ('updown_5m.parquet', 'updown_15m.parquet', 'updown_4h.parquet')
COLS = ('market_slug', 'coin', 'contract_length', 'token_id', 'outcome', 'market_end_at',
        'captured_at', 'seconds_to_close', 'bid_prices', 'bid_sizes', 'ask_prices',
        'ask_sizes', 'best_bid', 'best_ask', 'crossed')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--zenodo-record', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError('audit output already exists; preserve it')
    record = json.loads(args.zenodo_record.read_text())
    if record['doi'] != '10.5281/zenodo.22084977' or record['metadata']['license']['id'] != 'cc-by-4.0':
        raise ValueError('unexpected version DOI or license')
    zenodo_files = {f['key']: f for f in record['files']}
    source = {}
    global_counts = Counter()
    per_file = {}
    market = {}
    seen = set()
    times_by_token = defaultdict(list)
    paired_top = defaultdict(dict)
    seconds_to_close = defaultdict(list)
    first_capture = None
    last_capture = None
    for name in FILES:
        path = args.data / name
        if not path.is_file():
            raise ValueError(f'missing {path}')
        expected_md5 = zenodo_files[name]['checksum'].removeprefix('md5:')
        if hashlib.md5(path.read_bytes()).hexdigest() != expected_md5:
            raise ValueError(f'Zenodo MD5 mismatch: {name}')
        pqfile = pq.ParquetFile(path)
        counters = Counter()
        row_index = 0
        for batch in pqfile.iter_batches(batch_size=5000, columns=list(COLS)):
            columns = batch.to_pydict()
            for values in zip(*(columns[c] for c in COLS)):
                row = dict(zip(COLS, values))
                flags = audit_snapshot(row)
                counters['rows'] += 1
                for flag, value in vars(flags).items():
                    if value:
                        counters[flag] += 1
                slug, token = row['market_slug'], row['token_id']
                captured = row['captured_at']
                end = row['market_end_at']
                if captured is None or end is None or captured.tzinfo is None or end.tzinfo is None:
                    counters['missing_or_naive_timestamp'] += 1
                    raise ValueError(f'missing/naive timestamp: {name}/{row_index}')
                first_capture = captured if first_capture is None else min(first_capture, captured)
                last_capture = captured if last_capture is None else max(last_capture, captured)
                identity = (token, captured)
                if identity in seen:
                    counters['duplicate_token_capture'] += 1
                seen.add(identity)
                times_by_token[token].append(captured)
                seconds_to_close[row['contract_length']].append(row['seconds_to_close'])
                true_seconds = (end - captured).total_seconds()
                if (row['seconds_to_close'] is None or not math.isfinite(row['seconds_to_close'])
                        or abs(true_seconds - row['seconds_to_close']) > .001):
                    counters['seconds_to_close_mismatch'] += 1
                if captured >= end:
                    counters['at_or_after_market_end'] += 1
                elif flags.valid_midpoint:
                    counters['valid_preclose_midpoint'] += 1
                info = market.setdefault(slug, {'coin': row['coin'], 'contract_length': row['contract_length'],
                                                'market_end_at': end, 'first_capture': captured,
                                                'last_capture': captured, 'tokens': {}})
                if (info['coin'], info['contract_length'], info['market_end_at']) != (
                    row['coin'], row['contract_length'], end):
                    counters['market_metadata_conflict'] += 1
                info['first_capture'] = min(info['first_capture'], captured)
                info['last_capture'] = max(info['last_capture'], captured)
                previous = info['tokens'].setdefault(token, row['outcome'])
                if previous != row['outcome']:
                    counters['token_outcome_mapping_conflict'] += 1
                if flags.valid_midpoint and row['outcome'] in ('Up', 'Down'):
                    key = (slug, captured)
                    if row['outcome'] in paired_top[key]:
                        counters['duplicate_outcome_at_capture'] += 1
                    paired_top[key][row['outcome']] = (row['best_bid'], row['best_ask'])
                row_index += 1
        if counters['rows'] != pqfile.metadata.num_rows:
            raise ValueError(f'Parquet row count mismatch: {name}')
        source[name] = {'bytes': path.stat().st_size, 'sha256': sha(path),
                        'zenodo_md5': expected_md5, 'rows': pqfile.metadata.num_rows,
                        'schema': str(pqfile.schema_arrow)}
        per_file[name] = dict(sorted(counters.items()))
        global_counts.update(counters)
    cadence = Counter()
    for token, times in times_by_token.items():
        times.sort()
        for a, b in zip(times, times[1:]):
            dt = (b - a).total_seconds()
            if dt <= 0:
                cadence['nonpositive_or_duplicate_gap'] += 1
            elif dt > 1:
                cadence['gap_gt_1s'] += 1
            elif dt < 1:
                cadence['subsecond_gap'] += 1
            else:
                cadence['exactly_1s_gap'] += 1
    pair_counts = Counter()
    mid_sum_errors = []
    for by_outcome in paired_top.values():
        if set(by_outcome) != {'Up', 'Down'}:
            continue
        pair_counts['same_capture_clean_pairs'] += 1
        up_bid, up_ask = by_outcome['Up']
        down_bid, down_ask = by_outcome['Down']
        pair_counts['sum_bids_gt_1'] += up_bid + down_bid > 1 + 1e-9
        pair_counts['sum_asks_lt_1'] += up_ask + down_ask < 1 - 1e-9
        mid_sum_errors.append(abs((up_bid + up_ask + down_bid + down_ask) / 2 - 1))
    first_day = Counter(v['first_capture'].date().isoformat() for v in market.values())
    end_day = Counter(v['market_end_at'].date().isoformat() for v in market.values())
    output = {
        'stage': 'PM0', 'outcome_blind': True,
        'dataset': {'concept_doi': '10.5281/zenodo.22084114', 'version_doi': record['doi'],
                    'version': record['metadata']['version'], 'license': 'CC BY 4.0',
                    'zenodo_record_id': record['id'], 'record_json_sha256': sha(args.zenodo_record),
                    'source_files': source},
        'identity': {'unique_markets': len(market),
                     'unique_tokens': len(times_by_token),
                     'coins': sorted({v['coin'] for v in market.values()}),
                     'contract_lengths': sorted({v['contract_length'] for v in market.values()}),
                     'markets_by_coin': dict(sorted(Counter(v['coin'] for v in market.values()).items())),
                     'markets_by_contract_length': dict(sorted(Counter(v['contract_length'] for v in market.values()).items())),
                     'market_token_count': dict(sorted(Counter(len(v['tokens']) for v in market.values()).items())),
                     'first_capture_utc': first_capture.isoformat(), 'last_capture_utc': last_capture.isoformat(),
                     'markets_by_first_capture_date_utc': dict(sorted(first_day.items())),
                     'markets_by_end_date_utc': dict(sorted(end_day.items()))},
        'integrity': {'overall': dict(sorted(global_counts.items())), 'by_file': per_file,
                      'cadence_gap_counts': dict(sorted(cadence.items())),
                      'same_capture_complement_quote_checks': dict(sorted(pair_counts.items())),
                      'same_capture_abs_mid_sum_minus_1_quantiles': {
                          'p50': float(np.quantile(mid_sum_errors, .5)) if mid_sum_errors else None,
                          'p95': float(np.quantile(mid_sum_errors, .95)) if mid_sum_errors else None},
                      'seconds_to_close_quantiles_by_length': {length: {
                          'p00': float(np.quantile(vals, 0)), 'p10': float(np.quantile(vals, .1)),
                          'p50': float(np.quantile(vals, .5)), 'p90': float(np.quantile(vals, .9)),
                          'p100': float(np.quantile(vals, 1))} for length, vals in seconds_to_close.items()}},
        'timestamp_semantics': 'captured_at is collector snapshot time in UTC, not exchange event time; sparse changed-book rows may have >1s gaps without proving missing capture. market_end_at is scheduled resolution time.',
        'limits': 'No terminal outcome values read. Captured markets are sampled over a short Aug 2026 window; 1-second/sparse snapshots cannot prove exact passive fills or queue position.'
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'complete', 'rows': global_counts['rows'], 'markets': len(market),
                      'valid_midpoint_rows': global_counts['valid_midpoint'],
                      'first_capture_utc': output['identity']['first_capture_utc'],
                      'last_capture_utc': output['identity']['last_capture_utc']}))


if __name__ == '__main__':
    main()
