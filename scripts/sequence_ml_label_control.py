"""One diagnostic training-label permutation; never used for model selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from xgboost import XGBRegressor

from scripts.run_sequence_ml_v1 import day_scores, load_stock, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    config_path = Path("configs/sequence_ml_v1.json")
    config = json.loads(config_path.read_text())
    manifest_path = args.cache / "manifest.json"
    if sha(manifest_path) != config["source_cache_manifest_sha256"]:
        raise ValueError("cache manifest changed")
    symbol = "PEKAO"  # existing representative stock; not selected on new scores
    stock, _, _ = load_stock(args.cache, json.loads(manifest_path.read_text()), symbol, config)
    train = stock["train"]
    shuffled = train["y"].copy()
    rng = np.random.default_rng(7)
    for date in np.unique(train["day"]):
        ids = np.flatnonzero(train["day"] == date)
        shuffled[ids] = rng.permutation(shuffled[ids])
    model = XGBRegressor(objective="reg:squarederror", **config["xgboost"][0])
    model.fit(train["x"].reshape(len(shuffled), -1), shuffled)
    result = {}
    for split in ("dev", "eval"):
        data = stock[split]
        prediction = model.predict(data["x"].reshape(len(data["y"]), -1))
        rows = day_scores(data["y"], prediction, data["day"])
        if any(row["ic"] is None for row in rows):
            raise ValueError("undefined control IC")
        result[split] = {"day_scores": rows, "mean_day_ic": float(np.mean([row["ic"] for row in rows]))}
    receipt = {"kind": "post-fit pipeline diagnostic, not model selection or independent confirmation",
               "symbol": symbol, "arm": "B1_history_xgboost", "shuffle": "within_training_day",
               "permutation_seed": 7, "train_endpoints": len(shuffled),
               "config_sha256": sha(config_path), "cache_manifest_sha256": sha(manifest_path),
               "control_script_sha256": sha(Path(__file__)),
               "scientific_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "results": result,
               "interpretation_limit": "One shuffled-label control need not have IC exactly zero and cannot prove absence of every leakage mechanism."}
    if args.out.exists():
        raise ValueError("preserve completed control receipt")
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    print(json.dumps({split: result[split]["mean_day_ic"] for split in result}))


if __name__ == "__main__":
    main()
