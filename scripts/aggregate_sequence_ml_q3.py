"""Full-denominator aggregation of the predeclared Q3 diagnostics."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict(values):
    defined = [v for v in values if v is not None]
    return {"declared_cells": len(values), "defined_cells": len(defined),
            "full_denominator_mean": float(np.mean(defined)) if len(defined) == len(values) and values else None,
            "defined_cells_mean_descriptive": float(np.mean(defined)) if defined else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", type=Path, default=Path("results/sequence_ml_v1"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    base_path, q3_path = Path("configs/sequence_ml_v1.json"), Path("configs/sequence_ml_q3_v1.json")
    base, q3 = json.loads(base_path.read_text()), json.loads(q3_path.read_text())
    if sha(base_path) != q3["base_config_sha256"]:
        raise ValueError("base protocol changed")
    symbols, months = base["symbols"], q3["updated_models"]["evaluation_months"]
    arms = [q3["baseline"]]+[f"{q3['sequence']}_seed{s}" for s in q3["sequence_seeds"]]
    update_reports = {}
    for month in months:
        for symbol in symbols:
            path = args.reports / f"q3_update_{month}_{symbol}.json"
            r = json.loads(path.read_text())
            if r["symbol"] != symbol or r["evaluation_month"] != month or r["q3_config_sha256"] != sha(q3_path):
                raise ValueError("update receipt identity mismatch")
            if set(r["scores"]) != set(arms):
                raise ValueError("missing updated model")
            update_reports[(month, symbol)] = r
    if len({r["source_commit"] for r in update_reports.values()}) != 1:
        raise ValueError("mixed update source commits")
    diagnostic_reports = {}
    for symbol in symbols:
        path = args.reports / f"q3_diagnostic_{symbol}.json"
        r = json.loads(path.read_text())
        if r["symbol"] != symbol or r["q3_config_sha256"] != sha(q3_path):
            raise ValueError("diagnostic identity mismatch")
        diagnostic_reports[symbol] = r
    # Every date/stock/model has exactly one fixed and one updated score.
    time_cells = defaultdict(list)
    time_daily = defaultdict(dict)
    for (month, symbol), report in update_reports.items():
        for arm in arms:
            fixed, updated = report["scores"][arm]["fixed"], report["scores"][arm]["updated"]
            if len(fixed) != len(updated):
                raise ValueError("unpaired day scores")
            for f, u in zip(fixed, updated):
                if f["day"] != u["day"] or f["n"] != u["n"] or f["ic"] is None or u["ic"] is None:
                    raise ValueError("unpaired or undefined time score")
                key = (month, f["day"], symbol, arm)
                if key in time_daily:
                    raise ValueError("duplicate time score")
                time_daily[key] = {"fixed_ic": f["ic"], "updated_ic": u["ic"], "n": f["n"]}
                time_cells[(month, arm)].append(u["ic"]-f["ic"])
    dates = sorted({day for _, day, _, _ in time_daily})
    for month in months:
        month_dates = [d for d in dates if d.startswith(month)]
        for arm in arms:
            if len(time_cells[(month, arm)]) != len(month_dates)*len(symbols):
                raise ValueError("incomplete time denominator")
    time_summary = {month: {arm: {"updated_minus_fixed_ic": float(np.mean(time_cells[(month, arm)])),
                                  "cells": len(time_cells[(month, arm)]),
                                  "fixed_ic": float(np.mean([v["fixed_ic"] for (m, _, _, a), v in time_daily.items() if m == month and a == arm])),
                                  "updated_ic": float(np.mean([v["updated_ic"] for (m, _, _, a), v in time_daily.items() if m == month and a == arm]))}
                           for arm in arms} for month in months}
    state_records = defaultdict(dict)
    execution_records = defaultdict(list)
    common_selected = []
    for symbol, report in diagnostic_reports.items():
        for row in report["state_scores"]:
            key = (row["day"], symbol, row["state"])
            if row["model"] in state_records[key]:
                raise ValueError("duplicate state score")
            state_records[key][row["model"]] = row
        for row in report["execution"]:
            execution_records[row["model"]].append(row)
        common_selected.extend(report["common_selected"])
    expected_state = len(dates)*len(symbols)*2
    if len(state_records) != expected_state:
        raise ValueError("incomplete state cell denominator")
    state_summary = {}
    for state in ("high_activity", "low_activity"):
        subset = [cell for (day, symbol, label), cell in sorted(state_records.items()) if label == state]
        for cell in subset:
            if set(arms+["S0_seed_mean"]) != set(cell):
                raise ValueError("state model denominator mismatch")
        baseline_ic = [cell[q3["baseline"]]["ic"] for cell in subset]
        gru_ic = [cell["S0_seed_mean"]["ic"] for cell in subset]
        delta = [g-b if g is not None and b is not None else None for g, b in zip(gru_ic, baseline_ic)]
        state_summary[state] = {"baseline_ic": strict(baseline_ic), "gru_seed_mean_ic": strict(gru_ic),
                                "paired_delta_ic": strict(delta),
                                "rows_total": sum(cell[q3["baseline"]]["n"] for cell in subset),
                                "undefined_reasons": [dict(day=day, symbol=symbol,
                                                           baseline=state_records[(day, symbol, state)][q3["baseline"]]["undefined_reason"],
                                                           gru=state_records[(day, symbol, state)]["S0_seed_mean"]["undefined_reason"])
                                                      for day in dates for symbol in symbols
                                                      if state_records[(day, symbol, state)][q3["baseline"]]["ic"] is None
                                                      or state_records[(day, symbol, state)]["S0_seed_mean"]["ic"] is None]}
    execution_summary = {}
    for model in [q3["baseline"]]+[f"{q3['sequence']}_seed{s}" for s in q3["sequence_seeds"]]+["S0_seed_mean"]:
        rows = execution_records[model]
        if len(rows) != len(dates)*len(symbols):
            raise ValueError("incomplete execution denominator")
        selected = sum(row["selected"] for row in rows)
        common = sum(row["common_opportunities"] for row in rows)
        visible = [row["crossed_bps"] for row in rows]
        defined = [row for row in rows if row["crossed_bps"] is not None]
        execution_summary[model] = {"stock_day_cells": len(rows), "common_opportunities": common,
                                    "selected": selected, "pooled_coverage": selected/common if common else None,
                                    "equal_stock_day_crossed": strict(visible),
                                    "pooled_selected_crossed_descriptive":
                                        sum(row["crossed_bps"]*row["selected"] for row in defined)/selected if selected else None,
                                    "undefined_cells": [dict(day=r["day"], symbol=r["symbol"], reason=r["undefined_reason"])
                                                        for r in rows if r["crossed_bps"] is None]}
    if len(common_selected) != len(dates)*len(symbols):
        raise ValueError("incomplete common-selected denominator")
    summary = {"stage": q3["stage"], "retrospective_only": True,
               "q3_config_sha256": sha(q3_path), "fixed_runner_commit": json.loads((args.reports/"q2_summary.json").read_text())["scientific_commit"],
               "updated_runner_commit": next(iter(update_reports.values()))["source_commit"],
               "dates": dates, "symbols": symbols,
               "updated_fit_cells": len(update_reports),
               "updated_wall_seconds": sum(r["wall_seconds"] for r in update_reports.values()),
               "updated_fit_seconds": {arm: sum(r["costs"][arm]["fit_seconds"] for r in update_reports.values()) for arm in arms},
               "updated_training_limited": {f"{month}/{symbol}": {arm:r["costs"][arm].get("training_limited") for arm in arms if arm.startswith("S0")}
                                            for (month,symbol),r in update_reports.items()},
               "time_fixed_vs_updated": time_summary, "state": state_summary,
               "execution": execution_summary,
               "common_selected_count": sum(r["both_selected"] for r in common_selected),
               "input_update_hashes": {f"{month}/{symbol}": sha(args.reports/f"q3_update_{month}_{symbol}.json") for month,symbol in update_reports},
               "input_diagnostic_hashes": {symbol: sha(args.reports/f"q3_diagnostic_{symbol}.json") for symbol in symbols},
               "limitations": "All dates exposed; time refits add newer training information; state strata are descriptive; crossing uses visible quotes without actual fills, fees, impact or inventory. Undefined cells are explicit, never silently dropped."}
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"updated_fit_cells": summary["updated_fit_cells"],
                      "state_delta": {k:v["paired_delta_ic"] for k,v in state_summary.items()},
                      "execution": {k:(v["selected"],v["pooled_selected_crossed_descriptive"]) for k,v in execution_summary.items()}}))


if __name__ == "__main__":
    main()
