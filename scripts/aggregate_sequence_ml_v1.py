"""Strict five-stock paired aggregation of frozen retrospective sequence runs."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


ARMS = ("A0_current_ridge", "A1_current_xgboost", "B0_history_ridge",
        "B1_history_xgboost", "S0_history_gru_seed7", "S0_history_gru_seed17",
        "S0_history_gru_seed29")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_runs(folder, config):
    reports = []
    for symbol in config["symbols"]:
        candidates = list(folder.glob(f"q2_{symbol}*.json")) + list(folder.glob(f"q2_{symbol.lower()}*.json"))
        if len(candidates) != 1:
            raise ValueError(f"expected exactly one report for {symbol}, found {len(candidates)}")
        report = json.loads(candidates[0].read_text())
        if report["symbol"] != symbol or report["config_sha256"] != sha(Path("configs/sequence_ml_v1.json")):
            raise ValueError(f"run identity mismatch: {symbol}")
        reports.append(report)
    if len({r["code_commit"] for r in reports}) != 1:
        raise ValueError("runs use different scientific commits")
    return reports


def matrix(reports, split, symbols):
    lookup = defaultdict(dict)
    for report in reports:
        for row in report["scores"]:
            if row["split"] != split:
                continue
            key = (row["day"], row["arm"])
            if report["symbol"] in lookup[key]:
                raise ValueError("duplicate score cell")
            lookup[key][report["symbol"]] = row
    dates = sorted({day for day, arm in lookup})
    cube = {}
    count = {}
    for arm in ARMS:
        cells = []
        ns = []
        for date in dates:
            entries = lookup[(date, arm)]
            if set(entries) != set(symbols):
                raise ValueError(f"missing stock cell: {date}/{arm}")
            if any(entries[s]["ic"] is None for s in symbols):
                raise ValueError(f"undefined full-denominator IC: {date}/{arm}")
            cells.append([entries[s]["ic"] for s in symbols])
            ns.append([entries[s]["n"] for s in symbols])
        cube[arm] = np.asarray(cells, dtype=float)
        count[arm] = np.asarray(ns, dtype=np.int64)
    return dates, cube, count


def bootstrap(dates, daily_difference, block, draws=5000, seed=20260922):
    rng = np.random.default_rng(seed+block)
    months = defaultdict(list)
    for i, date in enumerate(dates):
        months[date[:7]].append(i)
    estimates = np.empty(draws)
    for draw in range(draws):
        chosen = []
        for idx in months.values():
            if len(idx) < block:
                raise ValueError("month shorter than bootstrap block")
            local = []
            while len(local) < len(idx):
                start = int(rng.integers(0, len(idx)-block+1))
                local.extend(idx[start:start+block])
            chosen.extend(local[:len(idx)])
        estimates[draw] = daily_difference[chosen].mean()
    return [float(x) for x in np.quantile(estimates, [0.025, 0.975])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", type=Path, default=Path("results/sequence_ml_v1"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    config_path = Path("configs/sequence_ml_v1.json")
    config = json.loads(config_path.read_text())
    reports = read_runs(args.reports, config)
    symbols = config["symbols"]
    dev_dates, dev, dev_n = matrix(reports, "dev", symbols)
    eval_dates, evaluation, eval_n = matrix(reports, "eval", symbols)
    cheap = ("B0_history_ridge", "B1_history_xgboost")
    dev_mean = {arm: float(dev[arm].mean()) for arm in ARMS}
    chosen = max(cheap, key=lambda arm: dev_mean[arm])
    score_mean = {arm: float(evaluation[arm].mean()) for arm in ARMS}
    monthly = {month: {arm: float(evaluation[arm][[d.startswith(month) for d in eval_dates]].mean())
                        for arm in ARMS}
               for month in sorted({d[:7] for d in eval_dates})}
    per_stock = {symbol: {arm: float(evaluation[arm][:, i].mean()) for arm in ARMS}
                 for i, symbol in enumerate(symbols)}
    paired = {}
    for arm in ARMS:
        if not arm.startswith("S0"):
            continue
        differences = evaluation[arm]-evaluation[chosen]
        date_diff = differences.mean(axis=1)
        paired[arm] = {"mean_delta_ic": float(date_diff.mean()),
                       "ci95_block5": bootstrap(eval_dates, date_diff, 5),
                       "ci95_block3": bootstrap(eval_dates, date_diff, 3),
                       "ci95_block10": bootstrap(eval_dates, date_diff, 10),
                       "month_delta": {month: float(date_diff[[d.startswith(month) for d in eval_dates]].mean())
                                       for month in monthly},
                       "stock_delta": {symbol: float(differences[:, i].mean()) for i, symbol in enumerate(symbols)}}
    gru_mean = np.mean([evaluation[arm] for arm in ARMS if arm.startswith("S0")], axis=0)
    difference = gru_mean-evaluation[chosen]
    date_difference = difference.mean(axis=1)
    paired["S0_seed_mean"] = {"mean_delta_ic": float(date_difference.mean()),
                              "ci95_block5": bootstrap(eval_dates, date_difference, 5),
                              "ci95_block3": bootstrap(eval_dates, date_difference, 3),
                              "ci95_block10": bootstrap(eval_dates, date_difference, 10),
                              "month_delta": {month: float(date_difference[[d.startswith(month) for d in eval_dates]].mean())
                                              for month in monthly},
                              "stock_delta": {symbol: float(difference[:, i].mean()) for i, symbol in enumerate(symbols)},
                              "leave_one_stock_out_delta": {symbol: float(np.delete(difference, i, axis=1).mean())
                                                            for i, symbol in enumerate(symbols)}}
    training_limited = {r["symbol"]: {arm: r["costs"][arm]["training_limited"]
                                       for arm in ARMS if arm.startswith("S0")}
                        for r in reports}
    summary = {
        "study": config["study"], "retrospective_only": True,
        "config_sha256": sha(config_path), "scientific_commit": reports[0]["code_commit"],
        "source_cache_manifest_sha256": config["source_cache_manifest_sha256"],
        "input_report_hashes": {r["symbol"]: sha(next(p for p in args.reports.glob("q2_*.json")
                                                      if json.loads(p.read_text()).get("symbol") == r["symbol"]))
                                for r in reports},
        "symbols": symbols, "dev_dates": dev_dates, "evaluation_dates": eval_dates,
        "dev_cells_per_arm": len(dev_dates)*len(symbols),
        "evaluation_cells_per_arm": len(eval_dates)*len(symbols),
        "dev_row_count_per_arm": int(dev_n[ARMS[0]].sum()),
        "evaluation_row_count_per_arm": int(eval_n[ARMS[0]].sum()),
        "training_endpoints_per_stock": {r["symbol"]: r["selection_counts"]["train"] for r in reports},
        "dev_mean_ic": dev_mean, "selected_cheap_history_baseline": chosen,
        "evaluation_mean_ic": score_mean, "evaluation_month_mean_ic": monthly,
        "evaluation_stock_mean_ic": per_stock, "paired_vs_selected_history": paired,
        "training_limited_flags": training_limited,
        "fit_seconds_by_arm": {arm: float(sum(r["costs"][arm]["fit_seconds"] for r in reports)) for arm in ARMS},
        "inference_seconds_by_arm": {arm: float(sum(r["costs"][arm]["inference_seconds"] for r in reports)) for arm in ARMS},
        "total_run_wall_seconds": float(sum(r["wall_seconds"] for r in reports)),
        "limitations": "All dates were previously exposed; intervals describe paired date variation conditional on fixed fitted models, not independent final confirmation. Four configured CPU threads per run; actual CPU core-hours were not measured."
    }
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"selected_baseline": chosen, "eval_cells": summary["evaluation_cells_per_arm"],
                      "paired_seed_mean": paired["S0_seed_mean"]}))


if __name__ == "__main__":
    main()
