"""Frozen PM1B train/dev repricing study; final remains closed."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import resource
import sys
import time

import joblib
import numpy as np
import torch
from xgboost import XGBRegressor

from cloblab.polymarket_models import HistoryGRU, market_equal_weights, market_paired_bootstrap


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def arrays(path: Path, expected: dict) -> dict:
    if sha(path) != expected["private_target_sha256"]:
        raise ValueError("private PM1B target array changed")
    with np.load(path, allow_pickle=False) as f:
        out = {key: f[key].copy() for key in f.files}
    n = len(out["repricing"])
    if n != expected["eligible_opportunities"] or len(set(out["market"])) != expected["eligible_markets"]:
        raise ValueError("PM1B denominator changed")
    if out["history"].shape != (n, 8, 11) or any(len(out[key]) != n for key in
        ("probability", "market", "decision_utc", "future_capture_utc")):
        raise ValueError("PM1B row/history identity changed")
    if not np.isfinite(out["history"]).all() or not np.isfinite(out["repricing"]).all():
        raise ValueError("nonfinite PM1B input/target")
    if np.max(np.abs(out["repricing"])) > 1:
        raise ValueError("invalid repricing magnitude")
    for decision_text, future_text in zip(out["decision_utc"], out["future_capture_utc"]):
        decision, future = datetime.fromisoformat(str(decision_text)), datetime.fromisoformat(str(future_text))
        if not decision < future <= decision + timedelta(seconds=15):
            raise ValueError("future capture violates frozen horizon")
        if decision + timedelta(seconds=15) - future > timedelta(seconds=5):
            raise ValueError("future capture violates target staleness")
    return out


def market_mse(target: np.ndarray, prediction: np.ndarray, market: np.ndarray,
               decision_utc: np.ndarray) -> dict:
    if len(target) != len(prediction) or len(target) != len(market):
        raise ValueError("score identity mismatch")
    if not np.isfinite(prediction).all():
        raise ValueError("nonfinite repricing prediction")
    loss = (prediction.astype(float)-target.astype(float))**2
    by_market = defaultdict(list)
    for i, name in enumerate(market):
        by_market[str(name)].append(i)
    per_market = {name: float(loss[idx].mean()) for name, idx in by_market.items()}
    by_date = defaultdict(list)
    by_length = defaultdict(list)
    straddling_utc_markets = 0
    for name, idx in by_market.items():
        dates = {str(decision_utc[i])[:10] for i in idx}
        if len(dates) > 1:
            straddling_utc_markets += 1
        match = re.search(r"-updown-(5m|15m|4h)-", name)
        if not match:
            raise ValueError("unknown contract length in market identity")
        by_date[min(dates)].append(per_market[name])
        by_length[match.group(1)].append(per_market[name])
    return {"market_mean_mse": float(np.mean(list(per_market.values()))),
            "row_mean_mse_descriptive": float(loss.mean()),
            "markets": len(by_market), "opportunities": len(loss),
            "markets_with_decisions_spanning_utc_dates": straddling_utc_markets,
            "by_date_descriptive": {d: {"markets": len(v), "market_mean_mse": float(np.mean(v))}
                                    for d, v in sorted(by_date.items())},
            "by_contract_length_descriptive": {k: {"markets": len(v), "market_mean_mse": float(np.mean(v))}
                                               for k, v in sorted(by_length.items())},
            "_market_mse": per_market}


def _xgb(settings: dict) -> XGBRegressor:
    return XGBRegressor(objective="reg:squarederror", n_estimators=settings["n_estimators"],
                        max_depth=settings["max_depth"], learning_rate=settings["learning_rate"],
                        min_child_weight=settings["min_child_weight"], subsample=settings["subsample"],
                        colsample_bytree=settings["colsample_bytree"], reg_lambda=settings["reg_lambda"],
                        n_jobs=settings["n_jobs"], random_state=settings["random_state"],
                        tree_method="hist")


def _gru_predict(model: HistoryGRU, history: np.ndarray, mean: np.ndarray, scale: np.ndarray,
                 target_mean: float, target_scale: float, batch: int) -> np.ndarray:
    model.eval()
    out = []
    with torch.inference_mode():
        for start in range(0, len(history), batch):
            x = torch.from_numpy(((history[start:start+batch]-mean)/scale).astype(np.float32))
            out.append(model(x).numpy())
    return np.concatenate(out)*target_scale+target_mean


def _fit_gru(seed: int, train: dict, dev: dict, settings: dict, private: Path) -> tuple[np.ndarray,dict]:
    torch.set_num_threads(4)
    torch.manual_seed(seed)
    train_hist, dev_hist = train["history"], dev["history"]
    mean = train_hist.mean(axis=(0, 1), keepdims=True)
    scale = train_hist.std(axis=(0, 1), keepdims=True).clip(min=1e-6)
    target_mean = float(train["repricing"].mean())
    target_scale = max(float(train["repricing"].std()), 1e-6)
    xt = torch.from_numpy(((train_hist-mean)/scale).astype(np.float32))
    yt = torch.from_numpy(((train["repricing"]-target_mean)/target_scale).astype(np.float32))
    wt = torch.from_numpy(market_equal_weights(train["market"]).astype(np.float32))
    model = HistoryGRU(11, settings["hidden_size"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                                   weight_decay=settings["weight_decay"])
    best, best_state, patience = float("inf"), None, 0
    curve = []
    began = time.monotonic()
    for epoch in range(settings["max_epochs"]):
        model.train()
        order = torch.randperm(len(yt), generator=torch.Generator().manual_seed(seed+epoch))
        weighted_loss, total_weight = 0.0, 0.0
        for ids in order.split(settings["batch_size"]):
            optimizer.zero_grad(set_to_none=True)
            error = (model(xt[ids])-yt[ids])**2
            loss = (error*wt[ids]).sum()/wt[ids].sum()
            if not torch.isfinite(loss).item():
                raise ValueError(f"nonfinite PM1B GRU loss at epoch {epoch+1}")
            loss.backward(); optimizer.step()
            weighted_loss += float((error.detach()*wt[ids]).sum().item())
            total_weight += float(wt[ids].sum().item())
        pdev = _gru_predict(model, dev_hist, mean, scale,
                            target_mean, target_scale, settings["batch_size"])
        dev_score = market_mse(dev["repricing"], pdev, dev["market"], dev["decision_utc"])["market_mean_mse"]
        curve.append({"epoch": epoch+1, "train_standardized_weighted_mse": weighted_loss/total_weight,
                      "dev_market_mse_probability_points2": dev_score})
        if dev_score < best - 1e-8:
            best = dev_score
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= settings["patience"]:
            break
    fit_seconds = time.monotonic()-began
    if best_state is None:
        raise ValueError("no finite PM1B GRU checkpoint")
    model.load_state_dict(best_state)
    path = private/f"B3_gru_seed{seed}.pt"
    torch.save({"state": best_state, "mean": mean, "scale": scale,
                "target_mean": target_mean, "target_scale": target_scale}, path)
    began = time.monotonic()
    pred = _gru_predict(model, dev_hist, mean, scale,
                        target_mean, target_scale, settings["batch_size"])
    inference_seconds = time.monotonic()-began
    best_epoch = int(np.argmin([r["dev_market_mse_probability_points2"] for r in curve])+1)
    return pred, {"fit_seconds": fit_seconds, "inference_seconds": inference_seconds,
                  "epochs_run": len(curve), "best_epoch": best_epoch,
                  "training_limited": len(curve)==settings["max_epochs"] and best_epoch==len(curve),
                  "learning_curve": curve, "model_sha256": sha(path),
                  "trainable_parameters": sum(p.numel() for p in model.parameters())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.private.exists() or args.out.exists():
        raise ValueError("preserve existing PM1B dev attempt")
    began = time.monotonic()
    cfg_path = Path("configs/polymarket_pm1b_model_v1.json")
    cfg = json.loads(cfg_path.read_text())
    parent = Path("configs/polymarket_pm1b_v1.json")
    if sha(parent) != cfg["parent_horizon_config_sha256"]:
        raise ValueError("PM1B horizon protocol changed")
    train_manifest = Path("results/polymarket_pm1b_v1/train_build_manifest.json")
    dev_manifest = Path("results/polymarket_pm1b_v1/dev_build_manifest.json")
    if (sha(train_manifest) != cfg["train_target_manifest_sha256"]
        or sha(dev_manifest) != cfg["dev_target_manifest_sha256"]):
        raise ValueError("PM1B private target manifest changed")
    train, dev = arrays(args.train, json.loads(train_manifest.read_text())), arrays(args.dev, json.loads(dev_manifest.read_text()))
    if set(train["market"]) & set(dev["market"]):
        raise ValueError("market leakage across train/dev")
    args.private.mkdir(parents=True)
    predictions = {"B0_zero_repricing": np.zeros(len(dev["repricing"]), dtype=float)}
    costs = {"B0_zero_repricing": {"fit_seconds": 0.0, "inference_seconds": 0.0}}
    weights = market_equal_weights(train["market"])
    for arm, xtr, xdv, settings in (
        ("B1_current_state", train["history"][:, -1, :10], dev["history"][:, -1, :10], cfg["B1"]),
        ("B2_same_history", train["history"].reshape(len(train["repricing"]), -1),
         dev["history"].reshape(len(dev["repricing"]), -1), cfg["B2"])):
        model = _xgb(settings)
        tick = time.monotonic(); model.fit(xtr, train["repricing"], sample_weight=weights)
        fit = time.monotonic()-tick; tick = time.monotonic()
        predictions[arm] = model.predict(xdv)
        costs[arm] = {"fit_seconds": fit, "inference_seconds": time.monotonic()-tick}
        path = args.private/f"{arm}.joblib"; joblib.dump(model, path)
        costs[arm]["model_sha256"] = sha(path)
    for seed in cfg["B3"]["seeds"]:
        arm = f"B3_gru_seed{seed}"
        predictions[arm], costs[arm] = _fit_gru(seed, train, dev, cfg["B3"], args.private)
        print(json.dumps({"arm": arm, "fit_seconds": costs[arm]["fit_seconds"],
                          "epochs_run": costs[arm]["epochs_run"]}), flush=True)
    predictions["B3_seed_mean"] = np.mean([predictions[f"B3_gru_seed{s}"] for s in cfg["B3"]["seeds"]], axis=0)
    scores = {arm: market_mse(dev["repricing"], pred, dev["market"], dev["decision_utc"])
              for arm, pred in predictions.items()}
    paired = {arm+"_minus_B0": market_paired_bootstrap(scores["B0_zero_repricing"]["_market_mse"],
                                                         scores[arm]["_market_mse"], seed=20260923)
              for arm in scores if arm != "B0_zero_repricing"}
    paired["B2_minus_B1"] = market_paired_bootstrap(scores["B1_current_state"]["_market_mse"],
                                                     scores["B2_same_history"]["_market_mse"], seed=20260924)
    paired["B3_seed_mean_minus_B2"] = market_paired_bootstrap(scores["B2_same_history"]["_market_mse"],
                                                               scores["B3_seed_mean"]["_market_mse"], seed=20260925)
    preferred = scores["B3_seed_mean"]["market_mean_mse"] <= 0.99*scores["B2_same_history"]["market_mean_mse"]
    for arm in scores:
        scores[arm].pop("_market_mse")
    pred_path = args.private/"dev_predictions.npz"
    np.savez_compressed(pred_path, market=dev["market"], target=dev["repricing"],
                        **{arm: pred for arm, pred in predictions.items()})
    report = {"stage": "PM1B", "status": "DEV_ONLY_FINAL_CLOSED",
              "model_config_sha256": sha(cfg_path), "horizon_config_sha256": sha(parent),
              "train_manifest_sha256": sha(train_manifest), "dev_manifest_sha256": sha(dev_manifest),
              "train_private_sha256": sha(args.train), "dev_private_sha256": sha(args.dev),
              "train_markets": len(set(train["market"])), "train_opportunities": len(train["repricing"]),
              "dev_markets": len(set(dev["market"])), "dev_opportunities": len(dev["repricing"]),
              "scores": scores, "paired_market_mse": paired, "costs": costs,
              "dev_prefers_B3_over_B2_at_1pct": bool(preferred),
              "dev_predictions_private_sha256": sha(pred_path),
              "wall_seconds": time.monotonic()-began,
              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                        (1 if sys.platform == "darwin" else 1024),
              "limits": "Train/dev only; final repricing target remains closed. Market bootstrap conditional on four sampled UTC dates; no terminal information, exact exchange/fill/PnL, or WSE confirmation claim."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"status": report["status"], "dev_markets": report["dev_markets"],
                      "dev_mse": {arm: score["market_mean_mse"] for arm, score in scores.items()}}))


if __name__ == "__main__":
    main()
