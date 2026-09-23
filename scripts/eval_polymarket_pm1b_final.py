"""One-time PM1B repricing final score using frozen train/dev-fitted models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import joblib
import numpy as np
import torch

from cloblab.polymarket_models import HistoryGRU, market_paired_bootstrap
from run_polymarket_pm1b_dev import arrays, market_mse, sha, _gru_predict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", type=Path, required=True)
    ap.add_argument("--final-build-manifest", type=Path, required=True)
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--dev-report", type=Path, required=True)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve original PM1B final result")
    cfg_path = Path("configs/polymarket_pm1b_model_v1.json")
    cfg = json.loads(cfg_path.read_text())
    horizon_path = Path("configs/polymarket_pm1b_v1.json")
    if sha(horizon_path) != cfg["parent_horizon_config_sha256"]:
        raise ValueError("horizon protocol changed")
    dev_report = json.loads(args.dev_report.read_text())
    final_manifest = json.loads(args.final_build_manifest.read_text())
    if (dev_report["status"] != "DEV_ONLY_FINAL_CLOSED"
        or dev_report["model_config_sha256"] != sha(cfg_path)
        or dev_report["horizon_config_sha256"] != sha(horizon_path)):
        raise ValueError("dev model/protocol mismatch")
    if (final_manifest["group"] != "final"
        or final_manifest["protocol_sha256"] != sha(horizon_path)
        or final_manifest["horizon_audit_sha256"] != json.loads(horizon_path.read_text())["horizon_audit_sha256"]):
        raise ValueError("final target build/protocol mismatch")
    if sha(args.final) != final_manifest["private_target_sha256"]:
        raise ValueError("final target array hash mismatch")
    train_manifest = json.loads(Path("results/polymarket_pm1b_v1/train_build_manifest.json").read_text())
    dev_manifest = json.loads(Path("results/polymarket_pm1b_v1/dev_build_manifest.json").read_text())
    train = arrays(args.train, train_manifest)
    dev = arrays(args.dev, dev_manifest)
    final = arrays(args.final, final_manifest)
    if (sha(args.train) != dev_report["train_private_sha256"]
        or sha(args.dev) != dev_report["dev_private_sha256"]):
        raise ValueError("train/dev fit inputs changed")
    if set(final["market"]) & (set(train["market"]) | set(dev["market"])):
        raise ValueError("final market overlaps train/dev")
    started = time.monotonic()
    predictions = {"B0_zero_repricing": np.zeros(len(final["repricing"]), dtype=float)}
    for arm in ("B1_current_state", "B2_same_history"):
        path = args.models/f"{arm}.joblib"
        if sha(path) != dev_report["costs"][arm]["model_sha256"]:
            raise ValueError(f"fitted XGB hash mismatch {arm}")
        model = joblib.load(path)
        x = final["history"][:, -1, :10] if arm == "B1_current_state" else final["history"].reshape(len(final["repricing"]), -1)
        predictions[arm] = model.predict(x)
    for seed in cfg["B3"]["seeds"]:
        arm = f"B3_gru_seed{seed}"
        path = args.models/f"{arm}.pt"
        if sha(path) != dev_report["costs"][arm]["model_sha256"]:
            raise ValueError(f"fitted GRU hash mismatch {arm}")
        stored = torch.load(path, map_location="cpu", weights_only=False)
        model = HistoryGRU(11, cfg["B3"]["hidden_size"])
        model.load_state_dict(stored["state"])
        predictions[arm] = _gru_predict(model, final["history"], stored["mean"], stored["scale"],
                                         stored["target_mean"], stored["target_scale"], cfg["B3"]["batch_size"])
    predictions["B3_seed_mean"] = np.mean([predictions[f"B3_gru_seed{s}"] for s in cfg["B3"]["seeds"]], axis=0)
    scores = {arm: market_mse(final["repricing"], pred, final["market"], final["decision_utc"])
              for arm, pred in predictions.items()}
    paired = {arm+"_minus_B0": market_paired_bootstrap(scores["B0_zero_repricing"]["_market_mse"],
                                                         scores[arm]["_market_mse"], seed=20260926)
              for arm in scores if arm != "B0_zero_repricing"}
    paired["B2_minus_B1"] = market_paired_bootstrap(scores["B1_current_state"]["_market_mse"],
                                                     scores["B2_same_history"]["_market_mse"], seed=20260927)
    paired["B3_seed_mean_minus_B2"] = market_paired_bootstrap(scores["B2_same_history"]["_market_mse"],
                                                               scores["B3_seed_mean"]["_market_mse"], seed=20260928)
    for arm in scores:
        scores[arm].pop("_market_mse")
    report = {"stage": "PM1B", "status": "FINAL_SCORED_ONCE",
              "external_domain_narrow_pilot": True,
              "model_config_sha256": sha(cfg_path), "dev_report_sha256": sha(args.dev_report),
              "final_build_manifest_sha256": sha(args.final_build_manifest),
              "final_private_target_sha256": sha(args.final),
              "final_markets": len(set(final["market"])), "final_opportunities": len(final["repricing"]),
              "scores": scores, "paired_market_mse": paired,
              "dev_prefers_B3_over_B2_at_1pct": dev_report["dev_prefers_B3_over_B2_at_1pct"],
              "inference_wall_seconds": time.monotonic()-started,
              "limits": "One partial final UTC date of sampled sparse books; market bootstrap conditions on that date. Snapshot repricing only, not terminal information, exact fills/PnL or WSE independent confirmation."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"status": report["status"], "final_markets": report["final_markets"],
                      "final_mse": {arm: score["market_mean_mse"] for arm, score in scores.items()}}))


if __name__ == "__main__":
    main()
