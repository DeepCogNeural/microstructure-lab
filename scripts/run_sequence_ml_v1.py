"""Per-stock retrospective five-arm sequence study; private row outputs stay ignored."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor
import torch

from cloblab.sequence_ml import FEATURES, IDENTITY, index_day, scoring_endpoints
from cloblab.sequence_model import GRURegressor


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def split_month(month, config):
    if month in config["train_months"]:
        return "train"
    if month == config["dev_month"]:
        return "dev"
    if month in config["evaluation_months"]:
        return "eval"
    return None


def load_stock(cache, manifest, symbol, config):
    relevant = sorted((p for p in manifest["partitions"] if p["symbol"] == symbol
                       and split_month(p["day"][:7], config)), key=lambda p: p["day"])
    if not relevant:
        raise ValueError(f"no partitions for {symbol}")
    train_days = sum(split_month(p["day"][:7], config) == "train" for p in relevant)
    quota = math.ceil(config["training_endpoints_per_stock_max"] / train_days)
    rng = np.random.default_rng(config["training_sampling_seed"])
    arrays = defaultdict(lambda: defaultdict(list))
    exclusions = defaultdict(lambda: defaultdict(int))
    hashes = {}
    for p in relevant:
        path = cache / f"symbol={symbol}" / f"day={p['day']}" / "features.parquet"
        if sha(path) != p["features_sha256"]:
            raise ValueError(f"cache feature hash mismatch: {symbol}/{p['day']}")
        frame = pd.read_parquet(path, columns=list(IDENTITY)+list(FEATURES)+["markout_20"])
        index = index_day(frame, config["context_states"])
        split = split_month(p["day"][:7], config)
        for key, value in index.counts.items():
            exclusions[split][key] += value
        endpoints = index.endpoints[index.scorable]
        if split == "train":
            endpoints = np.sort(rng.choice(endpoints, size=min(quota, len(endpoints)), replace=False))
        else:
            endpoints = scoring_endpoints(frame, index, config["event_stride_dev_and_eval"])
        if len(endpoints) == 0:
            raise ValueError(f"no selected endpoints: {symbol}/{p['day']}")
        values = frame[list(FEATURES)].to_numpy(dtype=np.float32)
        positions = endpoints[:, None] + np.arange(1-config["context_states"], 1)[None, :]
        history = values[positions]
        arrays[split]["x"].append(history)
        arrays[split]["y"].append(frame.markout_20.to_numpy(dtype=np.float32)[endpoints])
        arrays[split]["day"].append(np.repeat(p["day"], len(endpoints)))
        arrays[split]["event_index"].append(frame.event_index.to_numpy(dtype=np.int64)[endpoints])
        hashes[p["day"]] = p["features_sha256"]
    out = {}
    for split, contents in arrays.items():
        out[split] = {key: np.concatenate(pieces) for key, pieces in contents.items()}
    cap = config["training_endpoints_per_stock_max"]
    if len(out["train"]["y"]) > cap:
        keep = np.sort(rng.choice(len(out["train"]["y"]), size=cap, replace=False))
        out["train"] = {key: val[keep] for key, val in out["train"].items()}
    return out, exclusions, hashes


def day_scores(y, prediction, day):
    rows = []
    for date in np.unique(day):
        sel = day == date
        actual, pred = y[sel], prediction[sel]
        reason = None
        if len(actual) < 3:
            reason = "too_few_rows"
        elif np.std(actual) == 0:
            reason = "constant_label"
        elif np.std(pred) == 0:
            reason = "constant_prediction"
        ic = None if reason else float(spearmanr(actual, pred).statistic)
        if ic is not None and not np.isfinite(ic):
            ic, reason = None, "undefined_spearman"
        rows.append({"day": str(date), "n": int(sel.sum()), "ic": ic,
                     "undefined_reason": reason, "prediction_std_bps": float(np.std(pred)),
                     "mse_bps2": float(np.mean((pred-actual)**2))})
    return rows


def fit_tabular(arm, stock, config, private):
    train, dev, evaluation = (stock[k] for k in ("train", "dev", "eval"))
    historical = arm.startswith("B")
    x_train = train["x"].reshape(len(train["y"]), -1) if historical else train["x"][:, -1]
    x_dev = dev["x"].reshape(len(dev["y"]), -1) if historical else dev["x"][:, -1]
    x_eval = evaluation["x"].reshape(len(evaluation["y"]), -1) if historical else evaluation["x"][:, -1]
    if "ridge" in arm:
        model = make_pipeline(StandardScaler(), Ridge(alpha=config["ridge_alpha"][0]))
    else:
        model = XGBRegressor(objective="reg:squarederror", **config["xgboost"][0])
    began = time.monotonic()
    model.fit(x_train, train["y"])
    fit_seconds = time.monotonic()-began
    began = time.monotonic()
    pdev, peval = model.predict(x_dev), model.predict(x_eval)
    inference_seconds = time.monotonic()-began
    path = private / f"{arm}.joblib"
    joblib.dump(model, path)
    return pdev, peval, {"fit_seconds": fit_seconds, "inference_seconds": inference_seconds,
                         "model_sha256": sha(path), "model_bytes": path.stat().st_size,
                         "train_endpoints": len(train["y"]),
                         "parameters": {"ridge_alpha": config["ridge_alpha"][0], "scaler": "train_only"}
                         if "ridge" in arm else config["xgboost"][0]}


def predict_gru(model, x, mu, sigma, batch_size):
    predictions = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(x), batch_size):
            batch = torch.from_numpy((x[start:start+batch_size]-mu)/sigma)
            predictions.append(model(batch).numpy())
    return np.concatenate(predictions)


def fit_gru(seed, stock, config, private):
    setup = config["gru"]
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    train, dev, evaluation = (stock[k] for k in ("train", "dev", "eval"))
    mu = train["x"].mean(axis=(0, 1), keepdims=True)
    sigma = train["x"].std(axis=(0, 1), keepdims=True).clip(min=1e-6)
    target_mu, target_sigma = float(train["y"].mean()), max(float(train["y"].std()), 1e-6)
    x_train = torch.from_numpy((train["x"]-mu)/sigma)
    y_train = torch.from_numpy((train["y"]-target_mu)/target_sigma)
    x_dev = torch.from_numpy((dev["x"]-mu)/sigma)
    y_dev = torch.from_numpy((dev["y"]-target_mu)/target_sigma)
    model = GRURegressor(hidden_size=setup["hidden_size"])
    opt = torch.optim.AdamW(model.parameters(), lr=setup["learning_rate"], weight_decay=setup["weight_decay"])
    best, best_state, patience = float("inf"), None, 0
    curve = []
    began = time.monotonic()
    for epoch in range(setup["epochs_max"]):
        model.train()
        order = torch.randperm(len(y_train), generator=torch.Generator().manual_seed(seed+epoch))
        losses = []
        for batch_ids in order.split(setup["batch_size"]):
            opt.zero_grad()
            loss = ((model(x_train[batch_ids])-y_train[batch_ids])**2).mean()
            if not torch.isfinite(loss):
                raise ValueError(f"nonfinite GRU loss: seed={seed}, epoch={epoch}")
            loss.backward()
            opt.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            dev_losses = [float(((model(x_dev[k:k+setup["batch_size"]])-y_dev[k:k+setup["batch_size"]])**2).sum())
                          for k in range(0, len(y_dev), setup["batch_size"])]
        dev_mse = sum(dev_losses)/len(y_dev)
        curve.append({"epoch": epoch+1, "train_batch_mse_mean": float(np.mean(losses)), "dev_mse": dev_mse})
        if dev_mse < best-1e-5:
            best, best_state, patience = dev_mse, copy.deepcopy(model.state_dict()), 0
        else:
            patience += 1
        if patience >= setup["patience"]:
            break
    fit_seconds = time.monotonic()-began
    model.load_state_dict(best_state)
    path = private / f"S0_history_gru_seed{seed}.pt"
    torch.save({"state": model.state_dict(), "mu": mu, "sigma": sigma,
                "target_mu": target_mu, "target_sigma": target_sigma}, path)
    began = time.monotonic()
    pdev = predict_gru(model, dev["x"], mu, sigma, setup["batch_size"])*target_sigma+target_mu
    peval = predict_gru(model, evaluation["x"], mu, sigma, setup["batch_size"])*target_sigma+target_mu
    inference_seconds = time.monotonic()-began
    best_epoch = int(np.argmin([item["dev_mse"] for item in curve])+1)
    return pdev, peval, {"fit_seconds": fit_seconds, "inference_seconds": inference_seconds,
                         "model_sha256": sha(path), "model_bytes": path.stat().st_size,
                         "train_endpoints": len(train["y"]), "epochs_run": len(curve),
                         "best_epoch": best_epoch, "learning_curve": curve,
                         "trainable_parameters": sum(p.numel() for p in model.parameters()),
                         "training_limited": len(curve) == setup["epochs_max"] and best_epoch == len(curve)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("configs/sequence_ml_v1.json"))
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--aggregate", type=Path, required=True)
    args = ap.parse_args()
    config = json.loads(args.config.read_text())
    if args.symbol not in config["symbols"]:
        raise ValueError("symbol not in frozen protocol")
    if args.aggregate.exists():
        raise ValueError("aggregate output already exists; preserve original run")
    manifest_path = args.cache / "manifest.json"
    if sha(manifest_path) != config["source_cache_manifest_sha256"]:
        raise ValueError("source cache manifest differs from frozen protocol")
    args.private.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text())
    started = time.monotonic()
    stock, exclusions, hashes = load_stock(args.cache, manifest, args.symbol, config)
    predictions, scores, costs = {}, [], {}
    for arm in config["arms"]:
        if arm.startswith("S0"):
            variants = [(f"{arm}_seed{seed}", lambda seed=seed: fit_gru(seed, stock, config, args.private))
                        for seed in config["gru"]["seeds"]]
        else:
            variants = [(arm, lambda arm=arm: fit_tabular(arm, stock, config, args.private))]
        for name, fit in variants:
            pdev, peval, cost = fit()
            predictions[name] = {"dev": pdev, "eval": peval}
            costs[name] = cost
            for split, pred in (("dev", pdev), ("eval", peval)):
                for row in day_scores(stock[split]["y"], pred, stock[split]["day"]):
                    scores.append({"symbol": args.symbol, "arm": name, "split": split, **row})
            print(json.dumps({"symbol": args.symbol, "arm": name,
                              "fit_seconds": cost["fit_seconds"], "epochs": cost.get("epochs_run")}), flush=True)
    # Ignored local artifact for paired Q3 execution and receipt reaggregation.
    private_predictions = args.private / "predictions.npz"
    np.savez_compressed(private_predictions,
                        **{f"{split}_{field}": stock[split][field] for split in ("dev", "eval") for field in ("y", "day", "event_index")},
                        **{f"{split}_{name}": pred[split] for name, pred in predictions.items() for split in ("dev", "eval")})
    report = {"study": config["study"], "symbol": args.symbol,
              "retrospective_only": True, "config_sha256": sha(args.config),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cache_manifest_sha256": sha(manifest_path), "feature_hashes_by_day": hashes,
              "selection_counts": {split: len(data["y"]) for split, data in stock.items()},
              "eligibility": exclusions, "scores": scores, "costs": costs,
              "private_prediction_sha256": sha(private_predictions),
              "wall_seconds": time.monotonic()-started,
              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == "darwin" else 1024),
              "software": {"python": sys.version.split()[0], "torch": torch.__version__},
              "limitations": "All dates are previously exposed; rows overlap; no independent confirmation or trading-PnL claim."}
    args.aggregate.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.aggregate.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=int)+"\n")
    os.replace(tmp, args.aggregate)
    print(json.dumps({"symbol": args.symbol, "status": "complete", "wall_seconds": report["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
