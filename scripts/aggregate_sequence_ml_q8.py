"""Strict common-cohort aggregation and April-only context choice for Q8."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from aggregate_sequence_ml_fq2 import bootstrap


ARMS = ("B1_history_xgboost", "S0_history_gru_seed7",
        "S0_history_gru_seed17", "S0_history_gru_seed29")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contrast(gru: np.ndarray, baseline: np.ndarray, dates: list[str], symbols: list[str]) -> dict:
    delta = gru-baseline
    return {"mean_delta_ic": float(delta.mean()),
            "ci95_date_block5": bootstrap(dates, delta.mean(axis=1), 5),
            "month_delta_ic": {m: float(delta[[d.startswith(m) for d in dates]].mean())
                               for m in sorted({d[:7] for d in dates})},
            "stock_delta_ic": {symbol: float(delta[:, i].mean()) for i, symbol in enumerate(symbols)}}


def _matrix(reports: dict, context: int, split: str, symbols: list[str]) -> dict:
    cells, dates, undefined = {}, set(), []
    for symbol in symbols:
        for row in reports[(context, symbol)]["scores"]:
            if row["split"] != split:
                continue
            key = (row["day"], symbol, row["arm"])
            if key in cells:
                raise ValueError(f"duplicate cell {context}/{split}/{key}")
            if row["arm"] not in ARMS:
                raise ValueError("unexpected arm")
            cells[key] = row
            dates.add(row["day"])
    dates = sorted(dates)
    expected = {(day, symbol, arm) for day in dates for symbol in symbols for arm in ARMS}
    if set(cells) != expected:
        raise ValueError(f"incomplete Q8 cells {context}/{split}")
    n = np.zeros((len(dates), len(symbols)), dtype=np.int64)
    values = {arm: np.full(n.shape, np.nan) for arm in ARMS}
    for di, day in enumerate(dates):
        for si, symbol in enumerate(symbols):
            n[di, si] = cells[(day, symbol, ARMS[0])]["n"]
            for arm in ARMS:
                row = cells[(day, symbol, arm)]
                if row["n"] != n[di, si]:
                    raise ValueError(f"different scoring count {context}/{split}/{day}/{symbol}")
                if row["ic"] is None:
                    undefined.append({"day": day, "symbol": symbol, "arm": arm,
                                      "reason": row.get("undefined_reason")})
                else:
                    values[arm][di, si] = row["ic"]
    result = {"dates": dates, "cells_per_arm": int(n.size), "rows_per_arm": int(n.sum()),
              "undefined_cells": undefined, "full_denominator_result": None}
    if not undefined:
        b1 = values[ARMS[0]]
        s0 = np.mean([values[a] for a in ARMS[1:]], axis=0)
        result["full_denominator_result"] = {
            "mean_ic": {arm: float(value.mean()) for arm, value in values.items()},
            "S0_seed_mean_ic": float(s0.mean()),
            "S0_seed_mean_vs_B1": _contrast(s0, b1, dates, symbols) if split == "eval" else
                {"mean_delta_ic": float((s0-b1).mean())},
            "S0_each_seed_vs_B1": {str(s): _contrast(values[f"S0_history_gru_seed{s}"], b1, dates, symbols)
                                    for s in (7, 17, 29)} if split == "eval" else {},
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("configs/sequence_ml_q8_v1.json"))
    ap.add_argument("--reports", type=Path, default=Path("results/sequence_ml_q8_v1"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve existing Q8 summary")
    config_path = args.config
    cfg = json.loads(config_path.read_text())
    contexts, symbols = cfg["contexts"], cfg["symbols"]
    reports, hashes = {}, {}
    for context in contexts:
        for symbol in symbols:
            path = args.reports / f"q8_context{context}_{symbol}.json"
            report = json.loads(path.read_text())
            if (report["stage"], report["context_states"], report["symbol"],
                report["config_sha256"], report["cache_manifest_sha256"],
                report["training_size_per_stock"], set(report["costs"])) != (
                    "Q8", context, symbol, sha(config_path), cfg["source_cache_manifest_sha256"],
                    cfg["train_endpoints_per_stock"], set(ARMS)):
                raise ValueError(f"Q8 receipt identity mismatch {context}/{symbol}")
            reports[(context, symbol)] = report
            hashes[f"{context}/{symbol}"] = sha(path)
    if len({r["source_commit"] for r in reports.values()}) != 1:
        raise ValueError("mixed Q8 runner commits")
    for symbol in symbols:
        ids = [reports[(context, symbol)]["endpoint_identity_sha256"] for context in contexts]
        if any(x != ids[0] for x in ids[1:]):
            raise ValueError(f"context endpoint identity mismatch {symbol}")
    dev = {str(context): _matrix(reports, context, "dev", symbols) for context in contexts}
    evaluation = {str(context): _matrix(reports, context, "eval", symbols) for context in contexts}
    first = contexts[0]
    for context in contexts[1:]:
        for split in (dev, evaluation):
            a, b = split[str(first)], split[str(context)]
            if (a["dates"], a["cells_per_arm"], a["rows_per_arm"]) != (b["dates"], b["cells_per_arm"], b["rows_per_arm"]):
                raise ValueError("different scored context denominators")
    if any(dev[str(context)]["full_denominator_result"] is None for context in contexts):
        selected, selection_reason = None, "undefined April dev cells; no context selected"
    else:
        dev_ic = {context: dev[str(context)]["full_denominator_result"]["S0_seed_mean_ic"]
                  for context in contexts}
        best = max(dev_ic.values())
        selected = min(context for context in contexts if dev_ic[context] >= best-1e-6)
        selection_reason = "Highest April dev equal-cell mean of three GRU seed ICs; <=1e-6 tie selects shorter context"
    summary = {"stage": "Q8", "retrospective_only": True,
               "config_sha256": sha(config_path),
               "source_commit": next(iter(reports.values()))["source_commit"],
               "cache_manifest_sha256": cfg["source_cache_manifest_sha256"],
               "common_eligibility_context": cfg["common_eligibility_context"],
               "train_endpoints_per_stock": cfg["train_endpoints_per_stock"],
               "symbols": symbols, "contexts": contexts,
               "dev": dev, "evaluation": evaluation,
               "selected_context_from_April_only": selected,
               "selection_reason": selection_reason,
               "training_limited": {f"{context}/{symbol}":
                                    {arm: reports[(context, symbol)]["costs"][arm]["training_limited"]
                                     for arm in ARMS[1:]}
                                    for context in contexts for symbol in symbols},
               "task_wall_seconds": sum(r["wall_seconds"] for r in reports.values()),
               "gpu_device_occupancy_seconds": sum(r["gpu_device_occupancy_seconds"] for r in reports.values()),
               "input_receipt_sha256": hashes,
               "limits": "All contexts share a 128-eligible cohort, distinct from FQ2's 32-state cohort. April-only choice, exposed 2017 evaluation, no independent/fill/profit claim."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"context_count": len(contexts), "selected_context": selected,
                      "dev_cells_per_arm": dev[str(first)]["cells_per_arm"],
                      "evaluation_cells_per_arm": evaluation[str(first)]["cells_per_arm"]}))


if __name__ == "__main__":
    main()
