"""Strict paired aggregation for the conditional formal FQ4 Transformer."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from aggregate_sequence_ml_fq2 import bootstrap


SEEDS = (7, 17, 29)
BASE = "B1_history_xgboost"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cells(report: dict, split: str, arms: set[str]) -> dict:
    cells = {}
    for row in report["scores"]:
        if row["split"] != split or row["arm"] not in arms:
            continue
        key = (row["day"], row["arm"])
        if key in cells:
            raise ValueError(f"duplicate score cell {key}")
        cells[key] = row
    return cells


def _contrast(s1: np.ndarray, comparator: np.ndarray, dates: list[str], symbols: list[str]) -> dict:
    delta = s1 - comparator
    return {"mean_delta_ic": float(delta.mean()),
            "ci95_date_block5": bootstrap(dates, delta.mean(axis=1), 5),
            "month_delta_ic": {m: float(delta[[d.startswith(m) for d in dates]].mean())
                               for m in sorted({d[:7] for d in dates})},
            "stock_delta_ic": {s: float(delta[:, i].mean()) for i, s in enumerate(symbols)},
            "leave_one_stock_out_delta_ic": {s: float(np.delete(delta, i, axis=1).mean())
                                               for i, s in enumerate(symbols)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fq4-reports", type=Path, default=Path("results/sequence_ml_fq4_v1"))
    ap.add_argument("--fq2-reports", type=Path, default=Path("results/sequence_ml_fq2_v1"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve existing FQ4 summary")
    config_path = Path("configs/sequence_ml_fq4_v1.json")
    cfg = json.loads(config_path.read_text())
    fq2_summary = args.fq2_reports / "fq2_summary.json"
    fq3_summary = Path("results/sequence_ml_fq3_v1/fq3_summary.json")
    gate_path = args.fq4_reports / "fq4_gate.json"
    if (sha(fq2_summary) != cfg["fq2_summary_sha256"]
        or sha(fq3_summary) != cfg["fq3_summary_sha256"]
        or sha(gate_path) != cfg["gate_sha256"]
        or not json.loads(gate_path.read_text())["gate_triggered"]):
        raise ValueError("frozen formal source/gate mismatch")
    q2 = json.loads(fq2_summary.read_text())
    level = q2["levels"]["200000"]
    symbols = cfg["symbols"]
    arms = [BASE] + [f"S0_history_gru_seed{s}" for s in SEEDS] + [f"S1_history_transformer_seed{s}" for s in SEEDS]
    q2_arms, q4_arms = set(arms[:4]), set(arms[4:])
    q4_reports, hashes, costs = {}, {}, {}
    for symbol in symbols:
        q4_path = args.fq4_reports / f"fq4_transformer_{symbol}.json"
        q2_path = args.fq2_reports / f"fq2_200000_{symbol}_a1.json"
        q4, q2_stock = json.loads(q4_path.read_text()), json.loads(q2_path.read_text())
        # FQ4 used the original FQ2 run receipt. The public FQ2 copy redacts
        # only gpu_device_name and binds that original with its raw hash.
        if q2_stock.get("public_redactions") != ["gpu_device_name"]:
            raise ValueError(f"FQ2 redaction lineage mismatch {symbol}")
        if ((q4["stage"], q4["symbol"], q4["training_size_per_stock"], q4["config_sha256"],
             q4["gate_sha256"], q4["cache_manifest_sha256"], q4["fq2_report_sha256"])
            != ("FQ4", symbol, 200000, sha(config_path), cfg["gate_sha256"],
                cfg["source_cache_manifest_sha256"], q2_stock["private_raw_receipt_sha256"])):
            raise ValueError(f"FQ4 identity mismatch {symbol}")
        if (q4["training_endpoint_identity_sha256"] != q2_stock["training_endpoint_identity_sha256"]
            or q4["selection_counts"] != q2_stock["selection_counts"]
            or set(q4["costs"]) != q4_arms):
            raise ValueError(f"FQ4 endpoint/model mismatch {symbol}")
        for arm in q4_arms:
            if q4["costs"][arm]["train_endpoints"] != 200000:
                raise ValueError(f"training size mismatch {symbol}/{arm}")
        q4_reports[symbol] = (q4, q2_stock)
        hashes[symbol] = {"fq4": sha(q4_path), "fq2_fixed_public": sha(q2_path),
                          "fq2_fixed_private_raw": q2_stock["private_raw_receipt_sha256"]}
        costs[symbol] = q4["costs"]
    commits = {pair[0]["source_commit"] for pair in q4_reports.values()}
    if len(commits) != 1:
        raise ValueError("mixed FQ4 runner commits")
    by_split = {}
    for split, date_key, cell_key, row_key in (("dev", "dev_dates", "dev_cells_per_arm", "dev_rows_per_arm"),
                                                ("eval", "evaluation_dates", "evaluation_cells_per_arm", "evaluation_rows_per_arm")):
        dates = level[date_key]
        score = {arm: np.full((len(dates), len(symbols)), np.nan) for arm in arms}
        counts = np.zeros((len(dates), len(symbols)), dtype=np.int64)
        undefined = []
        for si, symbol in enumerate(symbols):
            q4, q2_stock = q4_reports[symbol]
            c2, c4 = _cells(q2_stock, split, q2_arms), _cells(q4, split, q4_arms)
            if set(c2) != {(d, a) for d in dates for a in q2_arms} or set(c4) != {(d, a) for d in dates for a in q4_arms}:
                raise ValueError(f"incomplete declared stock/day cells {split}/{symbol}")
            for di, day in enumerate(dates):
                n = c2[(day, BASE)]["n"]
                if any(c[(day, arm)]["n"] != n for c, eligible in ((c2, q2_arms), (c4, q4_arms)) for arm in eligible):
                    raise ValueError(f"scoring row count mismatch {split}/{day}/{symbol}")
                counts[di, si] = n
                for arm in arms:
                    row = (c2 if arm in q2_arms else c4)[(day, arm)]
                    if row["ic"] is None:
                        undefined.append({"split": split, "day": day, "symbol": symbol,
                                          "arm": arm, "reason": row.get("undefined_reason")})
                    else:
                        score[arm][di, si] = row["ic"]
        if counts.sum() != level[row_key] or len(dates) * len(symbols) != level[cell_key]:
            raise ValueError(f"FQ4 denominator differs from FQ2 {split}")
        result = {"dates": dates, "cells_per_arm": int(counts.size), "rows_per_arm": int(counts.sum()),
                  "undefined_cells": undefined, "full_denominator_result": None}
        if not undefined:
            s0 = np.mean([score[f"S0_history_gru_seed{s}"] for s in SEEDS], axis=0)
            s1 = np.mean([score[f"S1_history_transformer_seed{s}"] for s in SEEDS], axis=0)
            result["full_denominator_result"] = {
                "mean_ic": {a: float(score[a].mean()) for a in arms},
                "S0_seed_mean_ic": float(s0.mean()), "S1_seed_mean_ic": float(s1.mean()),
                "S1_seed_mean_vs_B1": _contrast(s1, score[BASE], dates, symbols) if split == "eval" else {"mean_delta_ic": float((s1-score[BASE]).mean())},
                "S1_seed_mean_vs_S0_seed_mean": _contrast(s1, s0, dates, symbols) if split == "eval" else {"mean_delta_ic": float((s1-s0).mean())},
                "S1_each_seed_vs_S0_seed_mean": {str(s): _contrast(score[f"S1_history_transformer_seed{s}"], s0, dates, symbols)
                                                 for s in SEEDS} if split == "eval" else {},
            }
        by_split[split] = result
    summary = {"stage": "FQ4", "retrospective_only": True,
               "config_sha256": sha(config_path), "gate_sha256": cfg["gate_sha256"],
               "fq2_summary_sha256": sha(fq2_summary), "fq3_summary_sha256": sha(fq3_summary),
               "source_commit": commits.pop(), "cache_manifest_sha256": cfg["source_cache_manifest_sha256"],
               "symbols": symbols, "train_endpoints_per_stock": 200000,
               "dev": by_split["dev"], "evaluation": by_split["eval"],
               "training_limited": {symbol: {arm: costs[symbol][arm]["training_limited"] for arm in q4_arms}
                                    for symbol in symbols},
               "fit_seconds_by_arm": {arm: sum(costs[s][arm]["fit_seconds"] for s in symbols) for arm in q4_arms},
               "inference_seconds_by_arm": {arm: sum(costs[s][arm]["inference_seconds"] for s in symbols) for arm in q4_arms},
               "gpu_device_occupancy_seconds": sum(q4_reports[s][0]["gpu_device_occupancy_seconds"] for s in symbols),
               "task_wall_seconds": sum(q4_reports[s][0]["wall_seconds"] for s in symbols),
               "peak_gpu_allocated_bytes": max(costs[s][a]["gpu_peak_allocated_bytes"] for s in symbols for a in q4_arms),
               "input_receipt_sha256": hashes,
               "limits": "All evaluation dates/stocks exposed; mean of seed ICs, not IC of averaged predictions. No independent, fill, or profit claim."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"dev_cells": summary["dev"]["cells_per_arm"],
                      "evaluation_cells": summary["evaluation"]["cells_per_arm"],
                      "s1_vs_s0": None if summary["evaluation"]["full_denominator_result"] is None else
                      summary["evaluation"]["full_denominator_result"]["S1_seed_mean_vs_S0_seed_mean"]["mean_delta_ic"]}))


if __name__ == "__main__":
    main()
