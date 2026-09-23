"""Frozen rolling refits for Q3, paired to the exact fixed Q2 event rows."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from scripts.run_sequence_ml_v1 import day_scores, fit_gru, fit_tabular, load_stock, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--month", required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--fixed-private", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve completed update receipt")
    base_path, q3_path = Path("configs/sequence_ml_v1.json"), Path("configs/sequence_ml_q3_v1.json")
    base, q3 = json.loads(base_path.read_text()), json.loads(q3_path.read_text())
    if sha(base_path) != q3["base_config_sha256"]:
        raise ValueError("Q3 base protocol hash mismatch")
    if args.month not in q3["updated_models"]["evaluation_months"] or args.symbol not in base["symbols"]:
        raise ValueError("unplanned stock/month")
    settings = q3["updated_models"][args.month]
    config = copy.deepcopy(base)
    config["train_months"] = settings["train_months"]
    config["dev_month"] = settings["dev_month"]
    config["evaluation_months"] = [args.month]
    manifest_path = args.cache / "manifest.json"
    if sha(manifest_path) != base["source_cache_manifest_sha256"]:
        raise ValueError("source cache manifest mismatch")
    started = time.monotonic()
    stock, exclusions, feature_hashes = load_stock(args.cache, json.loads(manifest_path.read_text()), args.symbol, config)
    with np.load(args.fixed_private / "predictions.npz") as fixed:
        mask = np.char.startswith(fixed["eval_day"].astype(str), args.month)
        if not np.array_equal(fixed["eval_day"][mask], stock["eval"]["day"]) or not np.array_equal(fixed["eval_event_index"][mask], stock["eval"]["event_index"]) or not np.array_equal(fixed["eval_y"][mask], stock["eval"]["y"]):
            raise ValueError("fixed and updated evaluation rows or labels differ")
        fixed_predictions = {arm: fixed[f"eval_{arm}"][mask].copy() for arm in
                             [q3["baseline"]] + [f"{q3['sequence']}_seed{s}" for s in q3["sequence_seeds"]]}
    args.private.mkdir(parents=True, exist_ok=True)
    arms = [(q3["baseline"], lambda: fit_tabular(q3["baseline"], stock, config, args.private))]
    arms += [(f"{q3['sequence']}_seed{seed}", lambda seed=seed: fit_gru(seed, stock, config, args.private))
             for seed in q3["sequence_seeds"]]
    scores, costs, predictions = {}, {}, {}
    for arm, fit in arms:
        _, pred, cost = fit()
        predictions[arm] = pred
        costs[arm] = cost
        scores[arm] = {"updated": day_scores(stock["eval"]["y"], pred, stock["eval"]["day"]),
                       "fixed": day_scores(stock["eval"]["y"], fixed_predictions[arm], stock["eval"]["day"])}
        print(json.dumps({"symbol": args.symbol, "month": args.month, "arm": arm,
                          "fit_seconds": cost["fit_seconds"], "epochs": cost.get("epochs_run")}), flush=True)
    private_pred = args.private / "updated_predictions.npz"
    np.savez_compressed(private_pred, day=stock["eval"]["day"], event_index=stock["eval"]["event_index"],
                        actual=stock["eval"]["y"], **predictions)
    report = {"stage": q3["stage"], "symbol": args.symbol, "evaluation_month": args.month,
              "retrospective_only": True, "base_config_sha256": sha(base_path),
              "q3_config_sha256": sha(q3_path),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cache_manifest_sha256": sha(manifest_path), "feature_hashes_by_day": feature_hashes,
              "train_endpoints": len(stock["train"]["y"]), "dev_endpoints": len(stock["dev"]["y"]),
              "evaluation_endpoints": len(stock["eval"]["y"]), "eligibility": exclusions,
              "scores": scores, "costs": costs,
              "private_predictions_sha256": sha(private_pred),
              "wall_seconds": time.monotonic()-started,
              "limitations": "Rolling historical refit, not new final or causal estimate of decay; fixed/updated rows matched exactly."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"symbol": args.symbol, "month": args.month, "status": "complete",
                      "wall_seconds": report["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
