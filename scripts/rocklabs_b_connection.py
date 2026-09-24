"""Bounded read-only identity, CTF payout, and causal quote audit for frozen Rocklabs B cohort."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path

import zstandard as zstd

CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
USDC_E = '2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
RPC = 'https://polygon-bor-rpc.publicnode.com'
PRIVATE = Path('_private/rocklabs/2026-09-23/b_connection_v1')
PUBLIC = Path('results/rocklabs_qop_b_connection_v1')
RAW = Path('_private/rocklabs/2026-09-23')
SOURCES = {
    '2026-07-28': RAW / 'sample-2026-07-28-0800/clob.jsonl.zst',
    '2026-07-29': RAW / 'validation-windows/raw/2026-07-29/0800.jsonl.zst',
    '2026-07-30': RAW / 'validation-windows/raw/2026-07-30/0800.jsonl.zst',
}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')
    os.chmod(path, 0o600)


def curl_json(url, *, body=None):
    args = ['curl', '-sSL', '--max-time', '20', '-H', 'User-Agent: Mozilla/5.0', '-H', 'Accept: application/json']
    if body is not None:
        args += ['-H', 'Content-Type: application/json', '--data-binary', '@-']
    args += ['-w', '\n%{http_code}', url]
    for attempt in range(2):
        p = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                           text=True, capture_output=True, timeout=25)
        try:
            raw, code = p.stdout.rsplit('\n', 1)
            if p.returncode == 0 and code == '200':
                return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest(), attempt + 1
        except (ValueError, json.JSONDecodeError):
            pass
        time.sleep(attempt + .3)
    return None, None, 2


def iso_ms(s):
    try:
        return int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)
    except (AttributeError, ValueError):
        return None


def parse_json_list(x):
    try:
        y = json.loads(x) if isinstance(x, str) else x
        return y if isinstance(y, list) else None
    except ValueError:
        return None


def rpc_calls(records):
    calls = []
    metadata = {}
    for i, r in enumerate(records):
        condition = r['clob_condition_candidate'][2:]
        for slot in (1, 2):
            data = '0x856296f7' + '0' * 64 + condition + f'{slot:064x}'
            metadata[len(calls) + 1] = (i, 'collection', slot)
            calls.append({'jsonrpc': '2.0', 'id': len(calls) + 1, 'method': 'eth_call',
                          'params': [{'to': CTF, 'data': data}, 'latest']})
        for kind, selector, slot in [('num0', '0x0504c814', 0), ('num1', '0x0504c814', 1), ('den', '0xdd34de67', None)]:
            data = selector + condition + (f'{slot:064x}' if slot is not None else '')
            metadata[len(calls) + 1] = (i, kind, None)
            calls.append({'jsonrpc': '2.0', 'id': len(calls) + 1, 'method': 'eth_call',
                          'params': [{'to': CTF, 'data': data}, 'latest']})
    results = {}
    hashes = []
    nrequests = 0
    for offset in range(0, len(calls), 50):
        payload, h, n = curl_json(RPC, body=calls[offset:offset + 50])
        nrequests += n
        hashes.append(h)
        if isinstance(payload, list):
            results.update({x.get('id'): x.get('result') for x in payload if isinstance(x, dict)})
    position_calls = []
    for call_id, (i, kind, slot) in list(metadata.items()):
        if kind != 'collection':
            continue
        col = results.get(call_id)
        if not isinstance(col, str) or len(col) != 66:
            continue
        data = '0x39dd7530' + USDC_E.lower().rjust(64, '0') + col[2:]
        reqid = len(calls) + len(position_calls) + 1
        metadata[reqid] = (i, 'position', slot)
        position_calls.append({'jsonrpc': '2.0', 'id': reqid, 'method': 'eth_call',
                               'params': [{'to': CTF, 'data': data}, 'latest']})
    for offset in range(0, len(position_calls), 50):
        payload, h, n = curl_json(RPC, body=position_calls[offset:offset + 50])
        nrequests += n
        hashes.append(h)
        if isinstance(payload, list):
            results.update({x.get('id'): x.get('result') for x in payload if isinstance(x, dict)})
    out = [dict() for _ in records]
    for call_id, (i, kind, slot) in metadata.items():
        value = results.get(call_id)
        try:
            parsed = int(value, 16)
        except (ValueError, TypeError):
            parsed = None
        out[i][kind + (str(slot) if slot is not None else '')] = parsed
    return out, hashes, nrequests


def finite(x):
    try:
        y = float(x)
        return y if math.isfinite(y) else None
    except (ValueError, TypeError):
        return None


def last_record(rows, kind, t, max_age):
    if not rows:
        return None, 'no_record'
    latest = max(x[0] for x in rows)
    same = [x[1] for x in rows if x[0] == latest]
    if len({json.dumps(x, sort_keys=True) for x in same}) > 1:
        return None, 'same_receive_time_conflict'
    age = t - latest
    if age < 0 or age > max_age:
        return None, 'stale'
    x = same[-1]
    if kind == 'bbo':
        bid, ask = finite(x.get('best_bid')), finite(x.get('best_ask'))
        if bid is None or ask is None or not 0 < bid < ask < 1:
            return None, 'invalid_or_crossed_bbo'
        return {'bid': bid, 'ask': ask, 'age_ms': age}, 'ok'
    bids, asks = x.get('bids') or [], x.get('asks') or []
    if not bids or not asks:
        return None, 'empty_book_side'
    parsed_bids = [(finite(q.get('price')), finite(q.get('size'))) for q in bids]
    parsed_asks = [(finite(q.get('price')), finite(q.get('size'))) for q in asks]
    if any(p is None or s is None or not 0 < p < 1 or s <= 0 for p, s in parsed_bids + parsed_asks):
        return None, 'invalid_book_levels'
    bid, ask = max(p for p, _ in parsed_bids), min(p for p, _ in parsed_asks)
    if bid >= ask:
        return None, 'crossed_book'
    return {'bid': bid, 'ask': ask, 'age_ms': age}, 'ok'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=('identity', 'quote'), required=True)
    args = ap.parse_args()
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest = json.loads((PUBLIC / 'manifest.json').read_text())
    frozen_path = PRIVATE / 'fixed_32.json'
    if digest(frozen_path) != manifest['private_fixed_cohort_sha256']:
        raise ValueError('Frozen roster checksum mismatch')
    frozen = json.loads(frozen_path.read_text())
    if len(frozen) != 32 or len({r['event_slug'] for r in frozen}) != 32:
        raise ValueError('Frozen cohort unexpected')
    for src in manifest['sources']:
        if digest(SOURCES[src['date']]) != src['clob_sha256']:
            raise ValueError('CLOB source checksum mismatch')
    if args.phase == 'identity':
        rows = []
        nrequests = 0
        for r in frozen:
            item = dict(r)
            gamma, gh, n = curl_json('https://gamma-api.polymarket.com/events/slug/' + r['event_slug'])
            nrequests += n
            item['gamma_sha256'] = gh
            item['gamma_status'] = 'ok' if isinstance(gamma, dict) else 'unavailable'
            market = None
            if isinstance(gamma, dict) and gamma.get('slug') == r['event_slug']:
                markets = [m for m in gamma.get('markets', []) if m.get('slug') == r['event_slug']]
                if len(markets) == 1:
                    market = markets[0]
            if market is not None:
                item['gamma_market_sha256'] = hashlib.sha256(json.dumps(market, sort_keys=True).encode()).hexdigest()
                item['gamma_condition_match'] = market.get('conditionId', '').lower() == r['clob_condition_candidate'].lower()
                item['gamma_tokens'] = parse_json_list(market.get('clobTokenIds'))
                item['gamma_outcomes'] = parse_json_list(market.get('outcomes'))
                item['gamma_tokens_match'] = set(map(str, item['gamma_tokens'] or [])) == set(map(str, r['tokens_unordered']))
                item['planned_end_ms'] = iso_ms(market.get('endDate'))
                item['gamma_event_end_ms'] = iso_ms(gamma.get('endDate'))
                item['end_match'] = item['planned_end_ms'] == item['gamma_event_end_ms'] == r['provisional_end_sec_from_slug'] * 1000
                if item['gamma_outcomes'] == ['Up', 'Down'] and item['gamma_tokens_match']:
                    item['up_token'] = str(item['gamma_tokens'][0])
                    item['down_token'] = str(item['gamma_tokens'][1])
            item['clob_by_token'] = []
            for token in r['tokens_unordered']:
                c, h, n = curl_json('https://clob.polymarket.com/markets-by-token/' + str(token))
                nrequests += n
                item['clob_by_token'].append({'token': str(token), 'sha256': h,
                    'condition_match': isinstance(c, dict) and c.get('condition_id', '').lower() == r['clob_condition_candidate'].lower(),
                    'both_tokens_match': isinstance(c, dict) and {str(c.get('primary_token_id')), str(c.get('secondary_token_id'))} == set(map(str, r['tokens_unordered']))})
            rows.append(item)
        payouts, rpc_hashes, rpc_n = rpc_calls(frozen)
        nrequests += rpc_n
        for item, payout in zip(rows, payouts):
            item['ctf'] = payout
            up = item.get('up_token')
            down = item.get('down_token')
            item['ctf_token_match'] = up is not None and down is not None and str(payout.get('position1')) == up and str(payout.get('position2')) == down
            vector = (payout.get('num0'), payout.get('num1'), payout.get('den'))
            item['label'] = 'Up' if vector == (1, 0, 1) else ('Down' if vector == (0, 1, 1) else None)
            item['identity_gate'] = all([item.get('gamma_condition_match'), item.get('gamma_tokens_match'), item.get('end_match'),
                item.get('ctf_token_match'), len(item['clob_by_token']) == 2,
                all(x['condition_match'] and x['both_tokens_match'] for x in item['clob_by_token'])])
            item['label_gate'] = item['identity_gate'] and item['label'] is not None
        save(PRIVATE / 'identity_32.json', rows)
        save(PRIVATE / 'identity_network.json', {'http_requests': nrequests, 'rpc_response_sha256': rpc_hashes,
                                                   'identity_table_sha256': digest(PRIVATE / 'identity_32.json')})
        print(json.dumps({'events': len(rows), 'identity_gate': sum(x['identity_gate'] for x in rows),
                          'label_gate': sum(x['label_gate'] for x in rows), 'http_requests': nrequests}))
        return
    rows = json.loads((PRIVATE / 'identity_32.json').read_text())
    if len(rows) != 32:
        raise ValueError('Identity table unexpected')
    bydate = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if r['identity_gate']:
            bydate[r['date']].append((i, r))
    for date, group in bydate.items():
        target = {r['up_token']: (i, r) for i, r in group}
        latest = {i: {'bbo': [], 'book': []} for i, _ in group}
        with zstd.open(SOURCES[date], 'rt') as f:
            for raw in f:
                outer = json.loads(raw)
                recv = iso_ms(outer.get('timestamp'))
                if recv is None:
                    continue
                try:
                    decoded = json.loads(outer['content'])
                except (KeyError, TypeError, ValueError):
                    continue
                for event in decoded if isinstance(decoded, list) else [decoded]:
                    if not isinstance(event, dict):
                        continue
                    typ = event.get('event_type')
                    if typ == 'price_change':
                        candidates = [('bbo', x) for x in event.get('price_changes', [])]
                    elif typ == 'book':
                        candidates = [('book', event)]
                    else:
                        continue
                    for kind, x in candidates:
                        hit = target.get(str(x.get('asset_id')))
                        if hit is None:
                            continue
                        i, cohort = hit
                        t = cohort['decision_ms_from_slug']
                        if recv > t:
                            continue
                        arr = latest[i][kind]
                        if not arr or recv > arr[0][0]:
                            latest[i][kind] = [(recv, x)]
                        elif recv == arr[0][0]:
                            arr.append((recv, x))
        for i, r in group:
            for kind, age in [('bbo', 1000), ('book', 5000)]:
                value, status = last_record(latest[i][kind], kind, r['decision_ms_from_slug'], age)
                r[kind + '_value'] = value
                r[kind + '_status'] = status
                r[kind + '_record_count_at_latest_recv'] = len(latest[i][kind])
    for r in rows:
        for kind in ('bbo', 'book'):
            r.setdefault(kind + '_status', 'identity_unverified')
            r.setdefault(kind + '_value', None)
        r['paired_bbo_gate'] = bool(r['label_gate'] and r['bbo_status'] == 'ok')
        r['paired_book_gate'] = bool(r['label_gate'] and r['book_status'] == 'ok')
    save(PRIVATE / 'auditable_32.json', rows)
    summary = {}
    for date in SOURCES:
        subset = [r for r in rows if r['date'] == date]
        summary[date] = {'frozen_events': len(subset), 'identity_verified': sum(r['identity_gate'] for r in subset),
            'binary_payout_verified': sum(r['label_gate'] for r in subset),
            'direct_bbo_valid': sum(r['bbo_status'] == 'ok' for r in subset),
            'full_book_top_valid': sum(r['book_status'] == 'ok' for r in subset),
            'label_and_bbo': sum(r['paired_bbo_gate'] for r in subset),
            'label_and_book': sum(r['paired_book_gate'] for r in subset),
            'bbo_failures': dict(collections.Counter(r['bbo_status'] for r in subset if r['bbo_status'] != 'ok')),
            'book_failures': dict(collections.Counter(r['book_status'] for r in subset if r['book_status'] != 'ok'))}
    public = {'status': 'BOUNDED_B_CONNECTION_AUDIT', 'cohort_events': len(rows), 'by_date': summary,
        'private_auditable_32_sha256': digest(PRIVATE / 'auditable_32.json'),
        'private_identity_32_sha256': digest(PRIVATE / 'identity_32.json'),
        'private_fixed_32_sha256': digest(PRIVATE / 'fixed_32.json'),
        'network': json.loads((PRIVATE / 'identity_network.json').read_text()),
        'label_publication_time': 'unknown',
        'caveat': 'Post hoc onchain payout labels and received-record quotes; no point-in-time label availability or maker match-time certificate.'}
    save(PUBLIC / 'summary.json', public)
    os.chmod(PUBLIC / 'summary.json', 0o644)
    print(json.dumps({'events': len(rows), 'by_date': summary}))


if __name__ == '__main__':
    main()
