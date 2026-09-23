"""Conditional FQ4 Transformer on the formal FQ2 200k causal endpoints."""
from __future__ import annotations

import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
import torch

from cloblab.sequence_transformer import CausalWindowTransformer
from run_sequence_ml_fq2 import endpoint_identity
from run_sequence_ml_v1 import day_scores, load_stock, sha


def _predictions(model: CausalWindowTransformer, values: np.ndarray,
                 mean: np.ndarray, scale: np.ndarray, batch_size: int,
                 device: torch.device) -> np.ndarray:
    model.eval()
    chunks = []
    with torch.inference_mode():
        for start in range(0, len(values), batch_size):
            x = torch.from_numpy((values[start:start + batch_size] - mean) / scale).to(device)
            chunks.append(model(x).cpu().numpy())
    return np.concatenate(chunks)


def _fit(seed: int, stock: dict, setup: dict, private: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    if setup["device"] != "cuda:0" or not torch.cuda.is_available():
        raise RuntimeError("FQ4 requires the declared CUDA device")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    device = torch.device(setup["device"])
    train, dev, evaluation = (stock[k] for k in ("train", "dev", "eval"))
    mean = train["x"].mean(axis=(0, 1), keepdims=True)
    scale = train["x"].std(axis=(0, 1), keepdims=True).clip(min=1e-6)
    target_mean = float(train["y"].mean())
    target_scale = max(float(train["y"].std()), 1e-6)
    x_train = torch.from_numpy((train["x"] - mean) / scale)
    y_train = torch.from_numpy((train["y"] - target_mean) / target_scale)
    x_dev = torch.from_numpy((dev["x"] - mean) / scale)
    y_dev = torch.from_numpy((dev["y"] - target_mean) / target_scale)
    model = CausalWindowTransformer(input_size=train["x"].shape[-1],
                                    context=train["x"].shape[1],
                                    width=setup["width"], heads=setup["heads"],
                                    layers=setup["layers"], feedforward=setup["feedforward"],
                                    dropout=setup["dropout"]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=setup["learning_rate"],
                                   weight_decay=setup["weight_decay"])
    best_loss, best_state, patience = float("inf"), None, 0
    curve = []
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    began = time.monotonic()
    for epoch in range(setup["epochs_max"]):
        model.train()
        order = torch.randperm(len(y_train), generator=torch.Generator().manual_seed(seed + epoch))
        total_loss = torch.zeros((), device=device)
        batches = 0
        for ids in order.split(setup["batch_size"]):
            optimizer.zero_grad(set_to_none=True)
            loss = ((model(x_train[ids].to(device)) - y_train[ids].to(device)) ** 2).mean()
            if not torch.isfinite(loss).item():
                raise ValueError(f"nonfinite Transformer loss seed={seed} epoch={epoch+1}")
            loss.backward()
            optimizer.step()
            total_loss += loss.detach()
            batches += 1
        model.eval()
        dev_loss = torch.zeros((), device=device)
        with torch.inference_mode():
            for start in range(0, len(y_dev), setup["batch_size"]):
                x = x_dev[start:start + setup["batch_size"]].to(device)
                y = y_dev[start:start + setup["batch_size"]].to(device)
                dev_loss += ((model(x) - y) ** 2).sum()
        torch.cuda.synchronize(device)
        dev_mse = float(dev_loss.item() / len(y_dev))
        curve.append({"epoch": epoch + 1,
                      "train_batch_mse_mean": float((total_loss / batches).item()),
                      "dev_mse": dev_mse})
        if dev_mse < best_loss - 1e-5:
            best_loss = dev_mse
            best_state = {name: tensor.detach().cpu().clone()
                          for name, tensor in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= setup["patience"]:
            break
    torch.cuda.synchronize(device)
    fit_seconds = time.monotonic() - began
    if best_state is None:
        raise ValueError("no finite dev checkpoint")
    model.load_state_dict(best_state)
    model_path = private / f"S1_history_transformer_seed{seed}.pt"
    torch.save({"state": best_state, "mean": mean, "scale": scale,
                "target_mean": target_mean, "target_scale": target_scale}, model_path)
    torch.cuda.synchronize(device)
    began = time.monotonic()
    pdev = _predictions(model, dev["x"], mean, scale, setup["batch_size"], device)
    peval = _predictions(model, evaluation["x"], mean, scale, setup["batch_size"], device)
    pdev = pdev * target_scale + target_mean
    peval = peval * target_scale + target_mean
    torch.cuda.synchronize(device)
    inference_seconds = time.monotonic() - began
    best_epoch = int(np.argmin([point["dev_mse"] for point in curve]) + 1)
    metrics = {"fit_seconds": fit_seconds, "inference_seconds": inference_seconds,
               "device_occupancy_seconds": fit_seconds + inference_seconds,
               "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
               "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
               "model_sha256": sha(model_path), "model_bytes": model_path.stat().st_size,
               "train_endpoints": len(train["y"]), "epochs_run": len(curve),
               "best_epoch": best_epoch, "learning_curve": curve,
               "trainable_parameters": sum(p.numel() for p in model.parameters()),
               "training_limited": len(curve) == setup["epochs_max"] and best_epoch == len(curve)}
    del model, optimizer, x_train, y_train, x_dev, y_dev
    torch.cuda.empty_cache()
    return pdev, peval, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/sequence_ml_fq4_v1.json"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fq2-report", type=Path, required=True)
    parser.add_argument("--fq2-private-predictions", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(args.config.read_text())
    if args.symbol not in frozen["symbols"] or args.private.exists() or args.aggregate.exists():
        raise ValueError("symbol outside protocol or output exists")
    gate = json.loads(Path("results/sequence_ml_fq4_v1/fq4_gate.json").read_text())
    if not gate["gate_triggered"] or sha(Path("results/sequence_ml_fq4_v1/fq4_gate.json")) != frozen["gate_sha256"]:
        raise ValueError("formal FQ4 gate did not trigger or changed")
    if (sha(Path("results/sequence_ml_fq2_v1/fq2_summary.json")) != frozen["fq2_summary_sha256"]
        or sha(Path("results/sequence_ml_fq3_v1/fq3_summary.json")) != frozen["fq3_summary_sha256"]):
        raise ValueError("formal source summary changed")
    base_path = Path("configs/sequence_ml_fq2_v1.json")
    if sha(base_path) != frozen["fq2_config_sha256"]:
        raise ValueError("FQ2 protocol changed")
    base = json.loads(base_path.read_text())
    if sha(args.cache / "manifest.json") != base["source_cache_manifest_sha256"]:
        raise ValueError("source cache mismatch")
    fixed = json.loads(args.fq2_report.read_text())
    if (fixed["stage"], fixed["symbol"], fixed["training_size_per_stock"],
        fixed["config_sha256"]) != ("FQ2", args.symbol, 200000, sha(base_path)):
        raise ValueError("fixed FQ2 receipt mismatch")
    if (fixed["cache_manifest_sha256"] != frozen["source_cache_manifest_sha256"]
        or sha(args.fq2_private_predictions) != fixed["private_predictions_sha256"]):
        raise ValueError("fixed FQ2 data/prediction receipt changed")
    config = dict(base)
    config["training_endpoints_per_stock_max"] = 200000
    started = time.monotonic()
    manifest = json.loads((args.cache / "manifest.json").read_text())
    stock, exclusions, hashes = load_stock(args.cache, manifest, args.symbol, config)
    if len(stock["train"]["y"]) != 200000:
        raise ValueError("formal 200k endpoint count changed")
    identity = endpoint_identity(stock["train"]["day"], stock["train"]["event_index"])
    if identity != fixed["training_endpoint_identity_sha256"]:
        raise ValueError("training endpoint identity differs from FQ2")
    with np.load(args.fq2_private_predictions, allow_pickle=False) as old:
        for split in ("dev", "eval"):
            for field in ("y", "day", "event_index"):
                if not np.array_equal(stock[split][field], old[f"{split}_{field}"]):
                    raise ValueError(f"{split} {field} scoring row identity changed")
    args.private.mkdir(parents=True)
    scores, costs, predictions = [], {}, {}
    for seed in frozen["transformer"]["seeds"]:
        pdev, peval, cost = _fit(seed, stock, frozen["transformer"], args.private)
        arm = f"S1_history_transformer_seed{seed}"
        costs[arm] = cost
        predictions[arm] = {"dev": pdev, "eval": peval}
        for split, pred in (("dev", pdev), ("eval", peval)):
            for row in day_scores(stock[split]["y"], pred, stock[split]["day"]):
                scores.append({"symbol": args.symbol, "arm": arm, "split": split, **row})
        print(json.dumps({"symbol": args.symbol, "arm": arm,
                          "fit_seconds": cost["fit_seconds"],
                          "epochs": cost["epochs_run"]}), flush=True)
    private_predictions = args.private / "predictions.npz"
    np.savez_compressed(private_predictions,
                        **{f"{split}_{field}": stock[split][field]
                           for split in ("dev", "eval")
                           for field in ("y", "day", "event_index")},
                        **{f"{split}_{arm}": pred[split]
                           for arm, pred in predictions.items()
                           for split in ("dev", "eval")})
    report = {"stage": "FQ4", "retrospective_only": True,
              "symbol": args.symbol, "training_size_per_stock": 200000,
              "config_sha256": sha(args.config),
              "gate_sha256": frozen["gate_sha256"],
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cache_manifest_sha256": sha(args.cache / "manifest.json"),
              "fq2_report_sha256": sha(args.fq2_report),
              "fq2_private_predictions_sha256": sha(args.fq2_private_predictions),
              "training_endpoint_identity_sha256": identity,
              "feature_hashes_by_day": hashes,
              "selection_counts": {split: len(data["y"]) for split, data in stock.items()},
              "eligibility": exclusions, "scores": scores, "costs": costs,
              "private_predictions_sha256": sha(private_predictions),
              "wall_seconds": time.monotonic() - started,
              "gpu_device_occupancy_seconds": sum(c["device_occupancy_seconds"] for c in costs.values()),
              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                        (1 if sys.platform == "darwin" else 1024),
              "software": {"python": sys.version.split()[0], "torch": torch.__version__},
              "limits": "Exposed 2017 dates; same 200k training/scoring identities as FQ2; no unseen confirmation, fill, or profit claim."}
    args.aggregate.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.aggregate.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=int) + "\n")
    os.replace(tmp, args.aggregate)
    print(json.dumps({"symbol": args.symbol, "status": "complete",
                      "wall_seconds": report["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
