"""Q3 past-activity and fixed visible-crossing diagnostics on Q2 event rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from cloblab.q3_diagnostics import crossed_from_features, future_positions
from cloblab.sequence_ml import FEATURES, IDENTITY, index_day, scoring_endpoints


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def stock_q2_report(folder, symbol):
    candidates = [p for p in folder.glob("q2_*.json")
                  if (record := json.loads(p.read_text())).get("symbol") == symbol
                  and "selection_counts" in record]
    if len(candidates) != 1:
        raise ValueError(f"expected one Q2 receipt for {symbol}, got {len(candidates)}")
    return json.loads(candidates[0].read_text())


def load_frame(cache, symbol, day, expected_sha):
    path = cache / f"symbol={symbol}" / f"day={day}" / "features.parquet"
    if sha(path) != expected_sha:
        raise ValueError(f"feature hash mismatch: {symbol}/{day}")
    return pd.read_parquet(path, columns=list(IDENTITY)+list(FEATURES)+["markout_20"])


def activity_threshold(cache, manifest, symbol, config):
    train_parts = sorted((p for p in manifest["partitions"] if p["symbol"] == symbol
                          and p["day"][:7] in config["train_months"]), key=lambda p: p["day"])
    quota = math.ceil(config["training_endpoints_per_stock_max"]/len(train_parts))
    rng = np.random.default_rng(config["training_sampling_seed"])
    duration_parts = []
    for p in train_parts:
        frame = load_frame(cache, symbol, p["day"], p["features_sha256"])
        index = index_day(frame)
        endpoints = index.endpoints[index.scorable]
        endpoints = np.sort(rng.choice(endpoints, size=min(quota, len(endpoints)), replace=False))
        timestamps = frame.timestamp_ns.to_numpy(dtype=np.int64)
        duration_parts.append(timestamps[endpoints]-timestamps[endpoints-(config["context_states"]-1)])
    durations = np.concatenate(duration_parts)
    cap = config["training_endpoints_per_stock_max"]
    if len(durations) > cap:
        keep = np.sort(rng.choice(len(durations), size=cap, replace=False))
        durations = durations[keep]
    if len(durations) != cap or not (durations > 0).any():
        raise ValueError("cannot freeze training activity median")
    return float(np.median(durations[durations > 0])), {"training_endpoints": len(durations),
                                                        "nonpositive_duration": int((durations <= 0).sum())}


def score_subset(y, pred, subset):
    values = y[subset]
    fitted = pred[subset]
    reason = None
    if len(values) < 3:
        reason = "too_few_rows"
    elif np.std(values) == 0:
        reason = "constant_label"
    elif np.std(fitted) == 0:
        reason = "constant_prediction"
    ic = None if reason else float(spearmanr(values, fitted).statistic)
    if ic is not None and not np.isfinite(ic):
        ic, reason = None, "undefined_spearman"
    return {"n": int(len(values)), "ic": ic, "undefined_reason": reason}


def execution_summary(pred, y, entry_spread, exit_spread, common):
    selected = common & (np.abs(pred) > 1.0)
    if not selected.any():
        return {"common_opportunities": int(common.sum()), "selected": 0,
                "coverage": 0.0 if common.any() else None,
                "crossed_bps": None, "gross_midpoint_bps": None,
                "entry_half_spread_bps": None, "exit_half_spread_bps": None,
                "undefined_reason": "no_threshold_selected_rows"}
    sign = np.sign(pred[selected])
    markout = y[selected]
    entry = entry_spread[selected]
    exit_ = exit_spread[selected]
    crossed = crossed_from_features(markout, entry, exit_, sign)
    gross = sign*markout
    entry_half = entry/2
    exit_half = exit_/2*(1+markout/10000)
    if not np.allclose(gross-entry_half-exit_half, crossed, atol=1e-10):
        raise ValueError("crossing accounting identity failed")
    return {"common_opportunities": int(common.sum()), "selected": int(selected.sum()),
            "coverage": float(selected.sum()/common.sum()) if common.any() else None,
            "crossed_bps": float(crossed.mean()), "gross_midpoint_bps": float(gross.mean()),
            "entry_half_spread_bps": float(entry_half.mean()),
            "exit_half_spread_bps": float(exit_half.mean()), "undefined_reason": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--q2-reports", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve completed Q3 diagnostic")
    base_path, q3_path = Path("configs/sequence_ml_v1.json"), Path("configs/sequence_ml_q3_v1.json")
    config, q3 = json.loads(base_path.read_text()), json.loads(q3_path.read_text())
    if sha(base_path) != q3["base_config_sha256"] or args.symbol not in config["symbols"]:
        raise ValueError("protocol mismatch")
    manifest_path = args.cache / "manifest.json"
    if sha(manifest_path) != config["source_cache_manifest_sha256"]:
        raise ValueError("cache manifest mismatch")
    manifest = json.loads(manifest_path.read_text())
    lookup = {(p["symbol"], p["day"]): p for p in manifest["partitions"]}
    threshold, threshold_counts = activity_threshold(args.cache, manifest, args.symbol, config)
    q2 = stock_q2_report(args.q2_reports, args.symbol)
    private_path = args.private / "predictions.npz"
    if sha(private_path) != q2["private_prediction_sha256"]:
        raise ValueError("private prediction hash differs from Q2 receipt")
    baseline = q3["baseline"]
    seeds = [f"{q3['sequence']}_seed{s}" for s in q3["sequence_seeds"]]
    with np.load(private_path) as fixed:
        day = fixed["eval_day"].astype(str).copy()
        event = fixed["eval_event_index"].copy()
        y = fixed["eval_y"].copy()
        preds = {name: fixed[f"eval_{name}"].copy() for name in [baseline]+seeds}
    preds["S0_seed_mean"] = np.mean([preds[s] for s in seeds], axis=0)
    if len(day) != q2["selection_counts"]["eval"]:
        raise ValueError("Q2 prediction denominator changed")
    state_rows, execution_rows, common_selected_rows, day_receipts = [], [], [], []
    for date in np.unique(day):
        ids = np.flatnonzero(day == date)
        p = lookup[(args.symbol, date)]
        frame = load_frame(args.cache, args.symbol, date, p["features_sha256"])
        index = index_day(frame)
        endpoints = scoring_endpoints(frame, index, config["event_stride_dev_and_eval"])
        if not np.array_equal(frame.event_index.to_numpy()[endpoints], event[ids]):
            raise ValueError(f"Q2 event row mismatch: {args.symbol}/{date}")
        actual_native = frame.markout_20.to_numpy(dtype=float)[endpoints]
        actual = actual_native.astype(np.float32)
        if not np.array_equal(actual, y[ids]):
            raise ValueError(f"Q2 target row mismatch: {args.symbol}/{date}")
        timestamp = frame.timestamp_ns.to_numpy(dtype=np.int64)
        duration = timestamp[endpoints]-timestamp[endpoints-(config["context_states"]-1)]
        high = (duration > 0) & (duration < threshold)
        low = duration >= threshold
        if np.any(high & low):
            raise ValueError("overlapping state slices")
        ev = frame.event_index.to_numpy(dtype=np.int64)
        seg = frame.segment.to_numpy(dtype=np.int64)
        future, matched = future_positions(ev, seg, endpoints, 20)
        future_safe = np.minimum(future, len(frame)-1)
        spread = frame.spread_bps.to_numpy(dtype=float)
        entry_spread = spread[endpoints]
        exit_spread = spread[future_safe]
        common = matched & np.isfinite(entry_spread) & np.isfinite(exit_spread) & np.isfinite(actual_native)
        day_receipts.append({"day": date, "prediction_rows": len(ids),
                             "nonpositive_duration": int((duration <= 0).sum()),
                             "high_activity": int(high.sum()), "low_activity": int(low.sum()),
                             "common_execution_rows": int(common.sum()),
                             "excluded_execution_rows": int(len(ids)-common.sum())})
        for name, prediction in preds.items():
            one = prediction[ids]
            for state, mask in (("high_activity", high), ("low_activity", low)):
                state_rows.append({"symbol": args.symbol, "day": date, "model": name,
                                   "state": state, **score_subset(actual, one, mask)})
            execution_rows.append({"symbol": args.symbol, "day": date, "model": name,
                                   **execution_summary(one, actual_native, entry_spread, exit_spread, common)})
        common_selected = common & (np.abs(preds[baseline][ids]) > 1) & (np.abs(preds["S0_seed_mean"][ids]) > 1)
        common_selected_rows.append({"symbol": args.symbol, "day": date,
                                     "both_selected": int(common_selected.sum()),
                                     "baseline": execution_summary(preds[baseline][ids], actual_native, entry_spread, exit_spread, common_selected),
                                     "gru_seed_mean": execution_summary(preds["S0_seed_mean"][ids], actual_native, entry_spread, exit_spread, common_selected)})
    report = {"stage": q3["stage"], "symbol": args.symbol, "retrospective_only": True,
              "q3_config_sha256": sha(q3_path), "base_config_sha256": sha(base_path),
              "diagnostic_script_sha256": sha(Path(__file__)),
              "crossing_library_sha256": sha(Path("src/cloblab/q3_diagnostics.py")),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cache_manifest_sha256": sha(manifest_path), "private_prediction_sha256": sha(private_path),
              "training_activity_median_ns": threshold, "training_activity_counts": threshold_counts,
              "model_names": list(preds), "day_receipts": day_receipts,
              "state_scores": state_rows, "execution": execution_rows,
              "common_selected": common_selected_rows,
              "limitations": "Historical state strata and visible crossing only; model-selected opportunities differ, no fee/impact/fill or cash PnL claim."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"symbol": args.symbol, "days": len(day_receipts),
                      "prediction_rows": len(day),
                      "common_execution_rows": sum(r["common_execution_rows"] for r in day_receipts)}))


if __name__ == "__main__":
    main()
