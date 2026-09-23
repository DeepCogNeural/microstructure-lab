"""Aggregate, outcome-blind R0 inspection of the pinned OutcomeTick sample.

The receipt JSON is private: a list of {candidate_index, print, tx, logs} from
Blockscout's /api/v2/transactions/{hash} and /logs endpoints. Never commit it.
This program emits aggregate counts only; it does not compute markouts.
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter, defaultdict
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median

HASHES = {
    "markets": "4096a32ef2a42628a81a5d221b4e9c6f28fdebe26c805b835972dc490bcc3d88",
    "last_trade_price": "fd1daeb67f6fad96fed8586a261c1b17a06cb046c4a64e4c993b01cf86b385f8",
    "best_bid_ask": "14bf5b0dd04773df0fad953551556a9c333a2ba8b367e2b931306412e364b7fd",
    "book": "e54595d9bc2a4877bc38d5be0ea3a1e809f6027dc26a9776ba3b83816b2d7de7",
    "price_change": "3223b345614ac35433475b3eea59a3793061266041ed273b859afce3e4a8f2cd",
}
DAY_START = 1788825600
DAY_END = DAY_START + 86400


def rows(root: Path, kind: str):
    path = next((root / kind / "BTC-5m").glob("*.jsonl.gz"))
    with gzip.open(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def verify(root: Path, archive: Path):
    def digest(path):
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    assert digest(archive) == "9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506"
    for kind, expected in HASHES.items():
        assert digest(next((root / kind / "BTC-5m").glob("*.jsonl.gz"))) == expected


def select(root: Path):
    markets = [{k: r[k] for k in ("slug", "condition_id", "token_ids", "start_sec", "end_sec")}
               for r in rows(root, "markets") if r["start_sec"] >= DAY_START and r["end_sec"] <= DAY_END]
    coverage = defaultdict(lambda: defaultdict(lambda: [0, 10**30, 0]))
    for kind in ("book", "best_bid_ask", "last_trade_price"):
        for row in rows(root, kind):
            c = coverage[row["slug"]][kind]
            t = row["event_ts_ms"]
            c[0] += 1
            c[1] = min(c[1], t)
            c[2] = max(c[2], t)
    complete = []
    for m in markets:
        c = coverage[m["slug"]]
        start, end = m["start_sec"] * 1000, m["end_sec"] * 1000
        if ("last_trade_price" in c and all(k in c and c[k][1] <= start + 30000
                and c[k][2] >= end - 30000 for k in ("book", "best_bid_ask"))):
            complete.append(m)
    complete.sort(key=lambda m: (m["start_sec"], m["condition_id"]))
    chosen = complete[:3]
    tokens = {m["slug"]: m["token_ids"][0] for m in chosen}
    prints = [r for r in rows(root, "last_trade_price") if r["slug"] in tokens
              and r["asset_id"] == tokens[r["slug"]]
              and r.get("payload", {}).get("transaction_hash")]
    prints.sort(key=lambda r: (r["event_ts_ms"], r["slug"], r["payload"]["transaction_hash"]))
    fixed = sorted([r for side in ("BUY", "SELL")
                    for r in [p for p in prints if p["payload"].get("side") == side][:10]],
                   key=lambda r: (r["event_ts_ms"], r["slug"], r["payload"]["transaction_hash"]))
    assert len(fixed) == 20
    return chosen, fixed, len(complete), len(prints)


def receipt_audit(fixed, receipts):
    counts = Counter()
    maker_shares = Decimal(0)
    target_shares = Decimal(0)
    maker_order_hashes = []
    source_chain = []
    recv_source = []
    for i, (row, item) in enumerate(zip(fixed, receipts), 1):
        assert item["candidate_index"] == i
        assert item["print"]["transaction_hash"] == row["payload"]["transaction_hash"]
        counts["attempted_prints"] += 1
        tx = item.get("tx") or {}
        if tx.get("status") != "ok":
            counts["receipt_unmatched"] += 1
            continue
        params = {p["name"]: p["value"] for p in (tx.get("decoded_input") or {}).get("parameters", [])}
        if "makerOrders" not in params:
            counts["input_undecoded"] += 1
            continue
        events = []
        matches = []
        for log in (item.get("logs") or {}).get("items", []):
            dec = log.get("decoded") or {}
            name = dec.get("method_call", "").split("(")[0]
            if name in ("OrderFilled", "OrdersMatched"):
                (events if name == "OrderFilled" else matches).append(
                    {p["name"]: p["value"] for p in dec["parameters"]})
        if len(matches) != 1:
            counts["ambiguous_match_events"] += 1
            continue
        th = matches[0]["takerOrderHash"]
        maker = [e for e in events if e["orderHash"] != th]
        taker = [e for e in events if e["orderHash"] == th]
        if len(taker) != 1 or len(maker) != len(params["makerOrders"]):
            counts["contradictory_leg_counts"] += 1
            continue
        if not all(any(e["maker"].lower() == order[1].lower() and
                       e["tokenId"] == order[3] and e["side"] == order[6] and
                       Decimal(e["makerAmountFilled"]) == Decimal(amount)
                       for order, amount in zip(params["makerOrders"], params["makerFillAmounts"]))
                   for e in maker):
            counts["maker_input_mismatch"] += 1
            continue
        t = taker[0]
        token = row["asset_id"]
        side = row["payload"]["side"]
        size = (Decimal(t["takerAmountFilled"]) if t["side"] == "0"
                else Decimal(t["makerAmountFilled"])) / 1000000
        price = (Decimal(t["makerAmountFilled"]) / Decimal(t["takerAmountFilled"])
                 if t["side"] == "0" else
                 Decimal(t["takerAmountFilled"]) / Decimal(t["makerAmountFilled"]))
        if (t["tokenId"] != token or (t["side"] == "0") != (side == "BUY")
                or abs(size - Decimal(str(row["payload"]["size"]))) >= Decimal("0.000001")
                or abs(price - Decimal(str(row["payload"]["price"]))) >= Decimal("0.011")):
            counts["print_taker_mismatch"] += 1
            continue
        counts["receipt_joined_prints"] += 1
        counts["maker_legs"] += len(maker)
        counts["one_to_many_prints"] += len(maker) > 1
        for e in maker:
            maker_order_hashes.append(e["orderHash"])
            shares = (Decimal(e["takerAmountFilled"]) if e["side"] == "0"
                      else Decimal(e["makerAmountFilled"])) / 1000000
            maker_shares += shares
            if e["tokenId"] == token:
                counts["target_token_maker_legs"] += 1
                counts["target_token_maker_buy" if e["side"] == "0" else "target_token_maker_sell"] += 1
                target_shares += shares
        block_ms = int(__import__("datetime").datetime.fromisoformat(
            tx["timestamp"].replace("Z", "+00:00")).timestamp() * 1000)
        source_chain.append(row["event_ts_ms"] - block_ms)
        recv_source.append(row["recv_ms"] - row["event_ts_ms"])
    repeated = Counter(maker_order_hashes)
    counts["distinct_maker_orders"] = len(repeated)
    counts["repeated_maker_orders"] = sum(v > 1 for v in repeated.values())
    counts["legs_of_repeated_maker_orders"] = sum(v for v in repeated.values() if v > 1)
    counts["distinct_hashes"] = len({r["payload"]["transaction_hash"] for r in fixed})
    return {**counts, "maker_shares": str(maker_shares), "target_token_maker_shares": str(target_shares),
            "source_minus_chain_ms": [min(source_chain), median(source_chain), max(source_chain)],
            "recv_minus_source_ms": [min(recv_source), median(recv_source), max(recv_source)]}


def book_audit(root, fixed):
    keys = {(r["slug"], r["asset_id"]) for r in fixed}
    data = defaultdict(list)
    for kind in ("book", "best_bid_ask", "price_change"):
        for row in rows(root, kind):
            if kind == "price_change":
                for ch in row["payload"].get("price_changes", []):
                    key = (row["slug"], ch.get("asset_id"))
                    if key in keys:
                        data[(kind, key)].append((row["recv_ms"], row["event_ts_ms"], ch))
            else:
                key = (row["slug"], row.get("asset_id"))
                if key in keys:
                    data[(kind, key)].append((row["recv_ms"], row["event_ts_ms"], row["payload"]))
    for v in data.values():
        v.sort(key=lambda a: (a[0], a[1]))
    result = {}
    for kind in ("book", "best_bid_ask", "price_change"):
        pre_age, target_age, new_count, two_pre, two_target = [], [], 0, 0, 0
        for row in fixed:
            v = data[(kind, (row["slug"], row["asset_id"]))]
            times = [x[0] for x in v]
            t = row["recv_ms"]
            j = bisect.bisect_left(times, t)
            k = bisect.bisect_right(times, t + 5000)
            pre, target = (v[j - 1] if j else None), (v[k - 1] if k else None)
            if pre:
                pre_age.append(t - pre[0])
            if target:
                target_age.append(t + 5000 - target[0])
            new_count += k > j
            if kind == "book":
                two_pre += bool(pre and pre[2].get("bids") and pre[2].get("asks"))
                two_target += bool(target and target[2].get("bids") and target[2].get("asks"))
            if kind == "best_bid_ask":
                two_pre += bool(pre and pre[2].get("best_bid") and pre[2].get("best_ask"))
                two_target += bool(target and target[2].get("best_bid") and target[2].get("best_ask"))
        result[kind] = {"pre_found": len(pre_age), "pre_age_ms_min_median_max":
                        [min(pre_age), median(pre_age), max(pre_age)], "new_updates_within_5s": new_count,
                        "candidate_target_age_ms_min_median_max":
                        [min(target_age), median(target_age), max(target_age)],
                        "two_sided_pre": two_pre, "two_sided_candidate_target": two_target}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-root", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--receipts-private", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise ValueError("preserve existing audit")
    verify(a.sample_root, a.archive)
    markets, fixed, n_complete, n_trades = select(a.sample_root)
    receipts = json.loads(a.receipts_private.read_text())
    assert len(receipts) == 20
    result = {"source": "OutcomeTick samples-2026-09-08", "status": "DEVELOPMENT_SOURCE_AUDIT",
              "complete_market_count": n_complete, "selected_market_count": len(markets),
              "first_token_trade_count": n_trades, "fixed_buy_prints": 10, "fixed_sell_prints": 10,
              "actual_candidate_market_count": len({r["slug"] for r in fixed}),
              "receipt": receipt_audit(fixed, receipts), "book": book_audit(a.sample_root, fixed),
              "limits": "Availability around print receive time, not a certified match-time or replayed 5s maker target. No C/A/M values or markouts."}
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "complete", "receipt": result["receipt"]}))


if __name__ == "__main__":
    main()
