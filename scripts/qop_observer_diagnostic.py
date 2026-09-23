"""Frozen OutcomeTick R0 receipt/quote diagnostic; no match-time or execution claim.

Private input is the exact 20-receipt cache from R0. Public output is aggregate only.
Run --self-test before --sample-root. Never publish row-level output.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path

from audit_qop_outcometick_r0 import rows, select, verify

RECEIPTS_SHA = "b92d7d641274641e8d7dbd8ac428a685a08e19f45ab3a5e61a58a3352d951f26"
INDEX_SHA = "cbde4ec0ac85a9b6e73b6d5c2c4fd4d7f728014ee968e5eb65f445f83d40f054"
AGES = (1000, 250)
HORIZON_MS = 5000
SCALE = Decimal(1000000)


def dec(value):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("non-numeric value")
    if not x.is_finite():
        raise ValueError("non-finite value")
    return x


def addr(value):
    return (value.get("hash") if isinstance(value, dict) else value or "").lower()


def params(log):
    return {p["name"]: p["value"] for p in log["decoded"]["parameters"]}


def event_name(log):
    return ((log.get("decoded") or {}).get("method_call") or "").split("(")[0]


def assets(event):
    maker, taker = dec(event["makerAmountFilled"]), dec(event["takerAmountFilled"])
    if maker <= 0 or taker <= 0:
        raise ValueError("nonpositive settlement")
    side = str(event["side"])
    if side == "0":
        return taker / SCALE, maker / taker, 1
    if side == "1":
        return maker / SCALE, taker / maker, -1
    raise ValueError("unknown side")


def unique_matching(orders, fills, fees, events):
    """Consume exactly one exchange OrderFilled event per maker input."""
    if len(orders) != len(fills) or len(orders) != len(fees) or len(orders) != len(events):
        raise ValueError("maker input/event count mismatch")
    choices = []
    for order, fill, fee in zip(orders, fills, fees):
        c = [j for j, event in enumerate(events)
             if addr(event["maker"]) == addr(order[1])
             and str(event["tokenId"]) == str(order[3])
             and str(event["side"]) == str(order[6])
             and dec(event["makerAmountFilled"]) == dec(fill)
             and dec(event["fee"]) == dec(fee)]
        choices.append(c)
    solutions = []
    def visit(i, used, assignment):
        if len(solutions) > 1:
            return
        if i == len(choices):
            solutions.append(assignment[:]); return
        for j in choices[i]:
            if j not in used:
                visit(i + 1, used | {j}, assignment + [j])
    visit(0, set(), [])
    if len(solutions) != 1:
        raise ValueError("maker matching absent or ambiguous")
    return [events[j] for j in solutions[0]]


def audit_receipt(item, row):
    if item["print"]["transaction_hash"] != row["payload"]["transaction_hash"]:
        raise ValueError("print/receipt hash mismatch")
    tx, log_page = item["tx"], item["logs"]
    if tx.get("status") != "ok" or log_page.get("next_page_params") is not None:
        raise ValueError("failed or incomplete receipt")
    decoded = tx.get("decoded_input") or {}
    if not decoded.get("method_call", "").startswith("matchOrders("):
        raise ValueError("unexpected call")
    inp = {p["name"]: p["value"] for p in decoded["parameters"]}
    needed = {"conditionId", "takerOrder", "makerOrders", "takerFillAmount", "makerFillAmounts", "takerFeeAmount", "makerFeeAmounts"}
    if not needed <= inp.keys():
        raise ValueError("incomplete decoded input")
    if str(inp["conditionId"]).lower() != str(row["payload"]["market"]).lower():
        raise ValueError("condition ID mismatch")
    contract = addr(tx["to"])
    if not contract:
        raise ValueError("missing contract")
    logs = [x for x in log_page["items"] if addr(x["address"]) == contract]
    matched = [params(x) for x in logs if event_name(x) == "OrdersMatched"]
    filled = [params(x) for x in logs if event_name(x) == "OrderFilled"]
    if len(matched) != 1:
        raise ValueError("OrdersMatched event count")
    th = str(matched[0]["takerOrderHash"]).lower()
    takers = [e for e in filled if str(e["orderHash"]).lower() == th]
    makers = [e for e in filled if str(e["orderHash"]).lower() != th]
    if len(takers) != 1 or len(makers) != len(inp["makerOrders"]):
        raise ValueError("taker/maker event count")
    taker = takers[0]
    order = inp["takerOrder"]
    if (addr(taker["maker"]) != addr(order[1]) or str(taker["tokenId"]) != str(order[3])
            or str(taker["side"]) != str(order[6])
            or dec(taker["makerAmountFilled"]) != dec(inp["takerFillAmount"])
            or dec(taker["fee"]) != dec(inp["takerFeeAmount"])):
        raise ValueError("taker input/event mismatch")
    if (str(matched[0]["tokenId"]) != str(taker["tokenId"])
            or str(matched[0]["side"]) != str(taker["side"])):
        raise ValueError("match/taker mismatch")
    ordered = unique_matching(inp["makerOrders"], inp["makerFillAmounts"], inp["makerFeeAmounts"], makers)
    qty, taker_price, sign = assets(taker)
    if str(taker["tokenId"]) != str(row["asset_id"]) or (sign == 1) != (row["payload"]["side"] == "BUY"):
        raise ValueError("print token/side mismatch")
    size_delta = qty - dec(row["payload"]["size"])
    if abs(size_delta) >= Decimal("0.000001"):
        raise ValueError("print/taker size mismatch")
    legs = []
    for e in ordered:
        q, price, d = assets(e)
        legs.append({"target": str(e["tokenId"]) == str(row["asset_id"]), "shares": q,
                     "price": price, "sign": d, "fee_raw": dec(e["fee"])})
    return {"legs": legs, "taker_price": taker_price, "print_price": dec(row["payload"]["price"]),
            "size_delta": size_delta}


def quote_value(row):
    try:
        bid, ask = dec(row["payload"]["best_bid"]), dec(row["payload"]["best_ask"])
    except (KeyError, ValueError):
        return None, "non_numeric"
    if not (Decimal(0) < bid < ask < Decimal(1)):
        return None, "empty_or_invalid_quote"
    return (bid + ask) / 2, None


def endpoint(series, times, cutoff, strict, age_limit):
    j = bisect_left(times, cutoff) if strict else bisect_right(times, cutoff)
    if not j:
        return None, "missing_quote", None
    timestamp = times[j - 1]
    same = [x for x in series[bisect_left(times, timestamp):j]]
    if len({(str(x["payload"].get("best_bid")), str(x["payload"].get("best_ask"))) for x in same}) != 1:
        return None, "same_receive_time_conflict", cutoff - timestamp
    age = cutoff - timestamp
    if age > age_limit:
        return None, "stale_quote", age
    value, error = quote_value(same[0])
    return value, error, age


def weighted(rows, key):
    if not rows:
        return None
    denom = sum((r["shares"] for r in rows), Decimal(0))
    vals = [r[key] for r in rows]
    return {"n": len(rows), "shares": str(denom), "weighted_mean_cents": str(sum((r["shares"] * r[key] for r in rows), Decimal(0)) / denom),
            "range_cents": [str(min(vals)), str(max(vals))]}


def summarize(rows):
    return {k: weighted(rows, k) for k in ("G", "D", "N")}


def self_test():
    assert assets({"makerAmountFilled":"400000", "takerAmountFilled":"1000000", "side":"0"}) == (Decimal(1),Decimal("0.4"),1)
    assert assets({"makerAmountFilled":"1000000", "takerAmountFilled":"400000", "side":"1"}) == (Decimal(1),Decimal("0.4"),-1)
    assert quote_value({"payload":{"best_bid":"0", "best_ask":"0.6"}})[0] is None
    assert quote_value({"payload":{"best_bid":"0.4", "best_ask":"1"}})[0] is None
    assert quote_value({"payload":{"best_bid":"0.6", "best_ask":"0.4"}})[0] is None
    assert quote_value({"payload":{"best_bid":"0.4", "best_ask":"0.6"}})[0] == Decimal("0.5")
    q = [{"recv_ms":100,"payload":{"best_bid":"0.4","best_ask":"0.6"}}]
    assert endpoint(q,[100],100,True,1000)[1] == "missing_quote"
    assert endpoint(q,[100],101,True,1000)[0] == Decimal("0.5")
    assert endpoint(q,[100],101,True,0)[1] == "stale_quote"
    assert endpoint(q+[{"recv_ms":100,"payload":{"best_bid":"0.3","best_ask":"0.6"}}],[100,100],101,True,1000)[1] == "same_receive_time_conflict"
    order = [None,"0xabc",None,"1",None,None,"0"]
    event = {"maker":"0xabc","tokenId":"1","side":"0","makerAmountFilled":"400000","fee":"0"}
    assert len(unique_matching([order],["400000"],["0"],[event])) == 1
    try:
        unique_matching([order,order],["400000"]*2,["0"]*2,[event,event])
    except ValueError:
        pass
    else:
        raise AssertionError("ambiguous matching accepted")
    assert Decimal("100") * (Decimal("0.5") - Decimal("0.4")) == Decimal("10")
    print("synthetic tests passed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--sample-root", type=Path)
    ap.add_argument("--archive", type=Path)
    ap.add_argument("--receipts-private", type=Path)
    ap.add_argument("--fixed-private", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--private-out", type=Path)
    a = ap.parse_args()
    if a.self_test:
        self_test(); return
    if any(v is None for v in (a.sample_root,a.archive,a.receipts_private,a.fixed_private,a.out,a.private_out)):
        ap.error("sample, archive, private inputs, and both outputs required")
    if a.out.exists() or a.private_out.exists():
        raise ValueError("preserve existing output")
    if sha256(a.receipts_private.read_bytes()).hexdigest() != RECEIPTS_SHA or sha256(a.fixed_private.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError("private R0 inputs changed")
    verify(a.sample_root,a.archive)
    markets,fixed,complete_count,_ = select(a.sample_root)
    private_index = json.loads(a.fixed_private.read_text())
    if len(fixed) != 20 or len(private_index["fixed_20"]) != 20:
        raise ValueError("fixed denominator changed")
    for original,row in zip(private_index["fixed_20"],fixed):
        if original["transaction_hash"] != row["payload"]["transaction_hash"] or original["recv_ms"] != row["recv_ms"]:
            raise ValueError("fixed candidate changed")
    receipts = json.loads(a.receipts_private.read_text())
    if len(receipts) != 20:
        raise ValueError("receipt count changed")
    joins, exclusions = [], Counter()
    for i,(item,row) in enumerate(zip(receipts,fixed),1):
        if item.get("candidate_index") != i:
            raise ValueError("receipt order changed")
        try:
            joins.append(audit_receipt(item,row))
        except ValueError as e:
            joins.append(None); exclusions[str(e)] += 1
    keys = {(r["slug"],r["asset_id"]) for r in fixed}
    bbo = defaultdict(list)
    last_recv = {}
    reversals = defaultdict(list)
    for row in rows(a.sample_root,"best_bid_ask"):
        key = (row["slug"],row["asset_id"])
        if key not in keys:
            continue
        if key in last_recv and row["recv_ms"] < last_recv[key]:
            reversals[key].append(row["recv_ms"])
        last_recv[key] = row["recv_ms"]
        bbo[key].append(row)
    for key in keys:
        bbo[key].sort(key=lambda x:x["recv_ms"])
    market_by_slug = {m["slug"]:m for m in markets}
    market_label = {slug:f"M{i+1}" for i,slug in enumerate(sorted({r["slug"] for r in fixed}, key=lambda s:(market_by_slug[s]["start_sec"],market_by_slug[s]["condition_id"])))}
    diagnostics = []
    print_diffs = []
    maker_price_diffs = []
    fee_raw_by_side = defaultdict(Decimal)
    selected_count = 0
    for i,(row,join) in enumerate(zip(fixed,joins),1):
        if join is None:
            diagnostics.append({"candidate_index":i,"status":"receipt_excluded"}); continue
        print_diffs.append(join["print_price"]-join["taker_price"])
        key = (row["slug"],row["asset_id"])
        r = row["recv_ms"]
        times = [x["recv_ms"] for x in bbo[key]]
        base_error = None
        if r + HORIZON_MS > market_by_slug[row["slug"]]["end_sec"]*1000:
            base_error = "past_scheduled_end"
        if any(r-1000 <= t <= r+HORIZON_MS for t in reversals[key]):
            base_error = "receive_clock_reversal"
        for leg in join["legs"]:
            if not leg["target"]:
                continue
            selected_count += 1
            maker_price_diffs.append(join["print_price"]-leg["price"])
            fee_raw_by_side["buy" if leg["sign"] == 1 else "sell"] += leg["fee_raw"]
            entry = {"candidate_index":i,"market":market_label[row["slug"]],"shares":leg["shares"],"fee_raw":leg["fee_raw"],
                     "sign":leg["sign"],"price":leg["price"],"recv_ms":r,"age":{},"values":{},"failure":{}}
            for age in AGES:
                pre, e0, a0 = endpoint(bbo[key],times,r,True,age)
                post, e1, a1 = endpoint(bbo[key],times,r+HORIZON_MS,False,age)
                entry["age"][str(age)] = [a0,a1]
                errors = [x for x in (base_error,e0,e1) if x]
                entry["failure"][str(age)] = errors
                if not errors:
                    G = leg["sign"]*(pre-leg["price"])*100
                    D = leg["sign"]*(post-pre)*100
                    N = leg["sign"]*(post-leg["price"])*100
                    assert G+D == N
                    entry["values"][str(age)] = {"G":G,"D":D,"N":N}
            diagnostics.append(entry)
    def collect(age):
        out = []
        for x in diagnostics:
            v = x.get("values",{}).get(str(age))
            if v is not None:
                out.append({**v,"shares":x["shares"],"market":x["market"],"candidate_index":x["candidate_index"]})
        return out
    def public(age):
        vals = collect(age)
        biggest = max(vals,key=lambda x:x["shares"]) if vals else None
        without = [x for x in vals if x is not biggest]
        return {"eligible_legs":len(vals),"distinct_prints":len({x["candidate_index"] for x in vals}),
                "distinct_markets":len({x["market"] for x in vals}),"summary":summarize(vals),
                "by_market":{m:summarize([x for x in vals if x["market"]==m]) for m in market_label.values()},
                "largest_leg_shares":str(biggest["shares"]) if biggest else None,
                "without_largest_leg":summarize(without),
                "failure_counts":dict(Counter(reason for x in diagnostics for reason in x.get("failure",{}).get(str(age),[])))}
    common_rows = [x for x in diagnostics if "250" in x.get("values",{}) and "1000" in x.get("values",{})]
    result = {"status":"DEVELOPMENT_OBSERVER_DIAGNOSTIC / NOT_ACTIONABLE_QOP",
              "source":"OutcomeTick samples-2026-09-08", "source_archive_sha256":"9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506",
              "fixed_prints":20,"coverage_screened_markets":complete_count,"coverage_screen_note":"first/last-30-second presence only; no middle completeness certification",
              "candidate_markets":len(market_label),"receipt_joined_prints":sum(x is not None for x in joins),"receipt_exclusion_counts":dict(exclusions),
              "selected_token_passive_legs":selected_count,"print_minus_taker_price_range": [str(min(print_diffs)),str(max(print_diffs))] if print_diffs else None,
              "print_minus_maker_leg_price_range": [str(min(maker_price_diffs)),str(max(maker_price_diffs))] if maker_price_diffs else None,
              "nonzero_print_taker_price_differences":sum(x != 0 for x in print_diffs),
              "nonzero_print_maker_leg_price_differences":sum(x != 0 for x in maker_price_diffs),
              "selected_maker_fee_raw_by_side":{k:str(v) for k,v in fee_raw_by_side.items()},
              "print_price_semantics":"not established as per-leg or VWAP; receipt leg prices used; no verified print tick/rounding rule", "fee_note":"raw receipt fee field excluded from gross cents/share; fee denomination not inferred",
              "ages_ms":{"1000":public(1000),"250":public(250)},
              "common_eligible_legs":len(common_rows),"common_1000":summarize([{**x["values"]["1000"],"shares":x["shares"]} for x in common_rows]),
              "common_250":summarize([{**x["values"]["250"],"shares":x["shares"]} for x in common_rows]),
              "limits":"Receive-clock gross descriptive values only; no pre-trade predictability, cancellation lead time, executable P&L, or original 5s match-time study pass."}
    a.private_out.write_text(json.dumps(diagnostics,default=str,indent=2)+"\n")
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"receipt_joined":result["receipt_joined_prints"],"selected_legs":selected_count,"eligible_1000":result["ages_ms"]["1000"]["eligible_legs"],"eligible_250":result["ages_ms"]["250"]["eligible_legs"]}))

if __name__ == "__main__":
    main()
