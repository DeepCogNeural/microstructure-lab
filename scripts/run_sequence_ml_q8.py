"""Q8 matched-context B1/GRU experiment on one 128-eligible causal cohort."""
from __future__ import annotations

import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import argparse
import copy
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
import torch

from run_sequence_ml_fq2 import endpoint_identity, fit_gru_gpu
from run_sequence_ml_v1 import day_scores, fit_tabular, load_stock, sha


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("configs/sequence_ml_q8_v1.json"))
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--context", type=int, required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--aggregate", type=Path, required=True)
    args = ap.parse_args()
    frozen = json.loads(args.config.read_text())
    if (args.symbol not in frozen["symbols"] or args.context not in frozen["contexts"]
        or args.private.exists() or args.aggregate.exists()):
        raise ValueError("symbol/context outside protocol or output already exists")
    base_path = Path("configs/sequence_ml_fq2_v1.json")
    if sha(base_path) != frozen["parent_formal_FQ2_config_sha256"]:
        raise ValueError("formal FQ2 protocol changed")
    if sha(args.cache / "manifest.json") != frozen["source_cache_manifest_sha256"]:
        raise ValueError("source cache changed")
    if not torch.cuda.is_available():
        raise RuntimeError("Q8 requires declared GPU")
    base = json.loads(base_path.read_text())
    config = copy.deepcopy(base)
    config["training_endpoints_per_stock_max"] = frozen["train_endpoints_per_stock"]
    config["context_states"] = frozen["common_eligibility_context"]
    started = time.monotonic()
    manifest = json.loads((args.cache / "manifest.json").read_text())
    full, exclusions, feature_hashes = load_stock(args.cache, manifest, args.symbol, config)
    if len(full["train"]["y"]) != frozen["train_endpoints_per_stock"]:
        raise ValueError("fewer than 200k common 128-eligible training endpoints")
    identities = {split: endpoint_identity(data["day"], data["event_index"])
                  for split, data in full.items()}
    stock = {split: {key: value[:, -args.context:, :]
                     if key == "x" else value
                     for key, value in data.items()}
             for split, data in full.items()}
    if any(stock[split]["x"].shape[1] != args.context for split in stock):
        raise ValueError("incorrect context slice")
    args.private.mkdir(parents=True)
    predictions, scores, costs = {}, [], {}
    for arm, fit in [("B1_history_xgboost", lambda: fit_tabular("B1_history_xgboost", stock, config, args.private))] + [
        (f"S0_history_gru_seed{s}", lambda seed=s: fit_gru_gpu(seed, stock, config, args.private))
        for s in frozen["gru_seeds"]
    ]:
        pdev, peval, cost = fit()
        predictions[arm] = {"dev": pdev, "eval": peval}
        costs[arm] = cost
        for split, pred in (("dev", pdev), ("eval", peval)):
            for row in day_scores(stock[split]["y"], pred, stock[split]["day"]):
                scores.append({"symbol": args.symbol, "context": args.context,
                               "arm": arm, "split": split, **row})
        print(json.dumps({"symbol": args.symbol, "context": args.context,
                          "arm": arm, "fit_seconds": cost["fit_seconds"],
                          "epochs": cost.get("epochs_run")}), flush=True)
    private_predictions = args.private / "predictions.npz"
    np.savez_compressed(private_predictions,
                        **{f"{split}_{field}": stock[split][field]
                           for split in ("dev", "eval")
                           for field in ("y", "day", "event_index")},
                        **{f"{split}_{arm}": pred[split]
                           for arm, pred in predictions.items()
                           for split in ("dev", "eval")})
    report = {"stage": "Q8", "retrospective_only": True,
              "symbol": args.symbol, "context_states": args.context,
              "common_eligibility_context": frozen["common_eligibility_context"],
              "training_size_per_stock": frozen["train_endpoints_per_stock"],
              "config_sha256": sha(args.config),
              "parent_FQ2_config_sha256": sha(base_path),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cache_manifest_sha256": sha(args.cache / "manifest.json"),
              "endpoint_identity_sha256": identities,
              "feature_hashes_by_day": feature_hashes,
              "selection_counts": {split: len(data["y"]) for split, data in stock.items()},
              "eligibility": exclusions, "scores": scores, "costs": costs,
              "private_predictions_sha256": sha(private_predictions),
              "wall_seconds": time.monotonic() - started,
              "gpu_device_occupancy_seconds": sum(c.get("device_occupancy_seconds", 0) for c in costs.values()),
              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                        (1 if sys.platform == "darwin" else 1024),
              "software": {"python": sys.version.split()[0], "torch": torch.__version__},
              "limits": "Common 128-eligible cohort differs from FQ2 32-state cohort. Historical exposed dates only; no independent/fill/profit claim."}
    args.aggregate.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.aggregate.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=int)+"\n")
    os.replace(tmp, args.aggregate)
    print(json.dumps({"symbol": args.symbol, "context": args.context,
                      "status": "complete", "wall_seconds": report["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
