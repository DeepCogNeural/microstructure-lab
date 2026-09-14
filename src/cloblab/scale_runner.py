"""Frozen monthly tasks, bounded host-local execution and aggregate receipts."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import threading
import time

import numpy as np
import pandas as pd

from cloblab.evaluation import _fit_predict_linear, _score_predictions, _spearman_corr
from cloblab.licensed_experiment import prediction_quantiles
from cloblab.scale_cache import validate_cache
from cloblab.scale_common import atomic_json, digest, environment, file_hash, read_json, source_hash


def expand_tasks(config, manifest):
    tasks, substitutions = {}, []
    for symbol in config["dataset"]["symbols"]:
        days = sorted(p["day"] for p in manifest["partitions"] if p["symbol"] == symbol)
        months = sorted({d[:7] for d in days})
        chosen = {}
        for requested in config["evaluation"]["fixed_test_months"]:
            eligible = [m for m in months if m >= requested and sum(d[:7] < m for d in days) >= config["evaluation"]["minimum_train_trading_days"]]
            if not eligible:
                raise ValueError(f"no eligible replacement month: {symbol}/{requested}")
            month = eligible[0]
            chosen[requested] = month
            if month != requested:
                substitutions.append({"symbol": symbol, "requested": requested, "actual": month})
        representative = config["negative_controls"]["representative_month"]
        for requested, month in chosen.items():
            for horizon in config["dataset"]["horizons_events"]:
                variants = [("linear", None), ("xgboost", None)]
                if requested == representative:
                    variants += [("hist_gradient_boosting", None), ("xgboost", config["negative_controls"]["seed"])]
                    extra = config["negative_controls"]["extra_seed_check"]
                    if symbol == extra["symbol"] and horizon == extra["horizon_events"]:
                        variants += [("xgboost", s) for s in extra["seeds"]]
                for model, seed in variants:
                    task = {"symbol": symbol, "month": month, "horizon": horizon, "model": model,
                            "control_seed": seed, "config_hash": digest(config), "cache_hash": digest(manifest),
                            "source_hash": source_hash()}
                    key = digest(task)
                    tasks[key] = {"task_id": key, **task}
    return {"tasks": sorted(tasks.values(), key=lambda t: (t["symbol"], t["month"], t["horizon"], t["model"], t["control_seed"] or -1)),
            "substitutions": substitutions, "config_hash": digest(config), "cache_hash": digest(manifest)}


def load_fold(cache, manifest, task, features):
    label = f"markout_{task['horizon']}"
    columns = features + [label, "day", "event_index", "timestamp_ns", "segment"]
    train_parts, test_parts = [], []
    for p in manifest["partitions"]:
        if p["symbol"] != task["symbol"] or p["day"][:7] > task["month"]:
            continue
        path = Path(cache) / f"symbol={p['symbol']}" / f"day={p['day']}" / "features.parquet"
        frame = pd.read_parquet(path, columns=columns)
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=features + [label])
        (train_parts if p["day"][:7] < task["month"] else test_parts).append(frame)
    if not train_parts or not test_parts:
        raise ValueError("empty fold")
    train, test = pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)
    if train.empty or test.empty or train.day.max() >= test.day.min():
        raise ValueError("empty or noncausal monthly fold")
    if task["control_seed"] is not None:
        rng = np.random.default_rng(task["control_seed"])
        for _, positions in train.groupby("day", sort=True).indices.items():
            train.loc[positions, label] = rng.permutation(train.loc[positions, label].to_numpy())
    return train, test, label


def model_parameters(config, device, threads):
    if device != "cpu" and not (device == "cuda" or (device.startswith("cuda:") and device[5:].isdigit())):
        raise ValueError("device must be cpu, cuda, or cuda:N")
    ignore = {"scope", "device", "hyperparameter_search"}
    return {**{k: v for k, v in config["models"]["xgboost"].items() if k not in ignore}, "device": device, "n_jobs": threads}


class GPUUsage:
    """Sample this process only, not other users' device allocations."""
    def __init__(self):
        self.stop = threading.Event()
        self.peak_mib = None
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            try:
                output = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.DEVNULL, timeout=3)
                for line in output.splitlines():
                    pid, memory = line.split(",")
                    if int(pid) == os.getpid() and memory.strip().isdigit():
                        self.peak_mib = max(self.peak_mib or 0, int(memory))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self.stop.wait(0.5)


def finite_json(value):
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite_json(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def completed(folder, task):
    path = folder / "status.json"
    if not path.exists():
        return False
    status = read_json(path)
    if status["task"] != task:
        raise ValueError("stale task receipt")
    if status["state"] != "complete":
        return False
    for name, sha in status["artifacts"].items():
        if file_hash(folder / name) != sha:
            raise ValueError(f"task artifact hash mismatch: {name}")
    return True


def run_task(task, config, manifest, cache, out, device="cpu", threads=1, resume=False, retry_failed=False):
    folder = Path(out) / "tasks" / task["task_id"]
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if completed(folder, task):
            if not resume:
                raise ValueError("completed task exists; use --resume")
            return "skipped"
        status_path = folder / "status.json"
        attempt = 1
        if status_path.exists():
            previous = read_json(status_path)
            if not retry_failed:
                raise ValueError("incomplete/failed task requires --retry-failed")
            attempt = previous.get("attempt", 1) + 1
            atomic_json(folder / f"attempt-{attempt-1}.json", previous)
        started = time.monotonic()
        status = {"task": task, "state": "running", "attempt": attempt, "pid": os.getpid(), "device": device}
        atomic_json(status_path, status)
        telemetry = GPUUsage()
        if device.startswith("cuda"):
            telemetry.thread.start()
        try:
            features = config["features"]["primary_set"]
            train, test, label = load_fold(cache, manifest, task, features)
            loaded = time.monotonic()
            gains, parameters = {}, {}
            fit_started = time.monotonic()
            if task["model"] == "xgboost":
                from xgboost import XGBRegressor
                parameters = model_parameters(config, device, threads)
                model = XGBRegressor(**parameters)
                model.fit(train[features], train[label])
                # XGBoost otherwise warns and silently falls back to CPU.
                fitted = json.loads(model.get_booster().save_config())
                actual_device = fitted["learner"]["generic_param"]["device"]
                if device.startswith("cuda") and not actual_device.startswith("cuda"):
                    raise RuntimeError("requested CUDA but XGBoost fell back to CPU")
                trained = time.monotonic()
                prediction = model.predict(test[features])
                raw_gain = model.get_booster().get_score(importance_type="gain")
                total = sum(raw_gain.values())
                gains = {f: raw_gain.get(f, 0) / total if total else 0 for f in features}
                parameters["actual_device"] = actual_device
            elif task["model"] == "hist_gradient_boosting":
                from sklearn.ensemble import HistGradientBoostingRegressor
                parameters = {k: v for k, v in config["models"][task["model"]].items() if k not in ("scope", "representative_month", "n_estimators")}
                parameters["max_iter"] = config["models"][task["model"]]["n_estimators"]
                model = HistGradientBoostingRegressor(**parameters)
                model.fit(train[features], train[label])
                trained = time.monotonic()
                prediction = model.predict(test[features])
            else:
                # Existing ridge's centered train-only scaling, unchanged.
                prediction = _fit_predict_linear(train, test, features, label)
                trained = time.monotonic()
                parameters = config["models"]["linear"]
            predicted = time.monotonic()
            if not np.isfinite(prediction).all():
                raise ValueError("nonfinite predictions")
            actual = test[label].to_numpy()
            metrics = _score_predictions(prediction, actual, 1.0)
            selected = abs(prediction) > 1
            metrics["selected_midpoint_diagnostic_bps"] = float(np.mean(np.sign(prediction[selected]) * actual[selected])) if selected.any() else None
            q, _ = prediction_quantiles(pd.DataFrame({"fold": 1, "prediction_bps": prediction, "realized_markout_bps": actual}))
            metrics["prediction_decile_monotonicity"] = float((q.avg_realized_markout_bps.diff().dropna() >= 0).mean()) if len(q) > 1 else None
            atomic_json(folder / "metrics.json", finite_json({**metrics, "train_rows": len(train), "train_days": sorted(train.day.unique()), "test_days": sorted(test.day.unique()), "gain": gains, "deciles": q.to_dict("records")}))
            # Local-only predictions support paired-device and row-pooled diagnostics.
            temp = folder / "predictions.tmp.npz"
            np.savez_compressed(temp, prediction=prediction, actual=actual,
                                timestamp_ns=test.timestamp_ns.to_numpy(), event_index=test.event_index.to_numpy())
            os.replace(temp, folder / "predictions.npz")
            telemetry.stop.set()
            if telemetry.thread.is_alive():
                telemetry.thread.join(timeout=4)
            atomic_json(folder / "resource.json", {"load_seconds": loaded-started,
                        "train_seconds": trained-fit_started, "predict_seconds": predicted-trained,
                        "wall_seconds": time.monotonic()-started, "train_rows": len(train), "test_rows": len(test),
                        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "peak_gpu_memory_mib_sampled": telemetry.peak_mib, "threads": threads,
                        "device": device, "environment": environment(), "parameters": parameters})
            artifacts = {name: file_hash(folder/name) for name in ("metrics.json", "resource.json", "predictions.npz")}
            atomic_json(status_path, {**status, "state": "complete", "artifacts": artifacts})
            return "complete"
        except BaseException as exc:
            telemetry.stop.set()
            atomic_json(status_path, {**status, "state": "failed", "error": repr(exc), "wall_seconds": time.monotonic()-started})
            raise


def summarize_blocks(frame, group):
    metrics = ["ic", "direction_accuracy", "cost_coverage", "selected_midpoint_diagnostic_bps", "prediction_decile_monotonicity"]
    return frame.groupby(group, dropna=False)[metrics].mean().reset_index().merge(
        frame.groupby(group, dropna=False).size().rename("symbol_month_blocks").reset_index(), on=group)


def aggregate(plan, roots, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows, resources, gains, deciles, duplicate = [], [], [], [], []
    missing, pooled = [], {}
    for task in plan["tasks"]:
        found = []
        for root in roots:
            folder = Path(root) / "tasks" / task["task_id"]
            if completed(folder, task):
                found.append(folder)
        if not found:
            missing.append(task["task_id"])
            continue
        first = read_json(found[0] / "metrics.json")
        for folder in found[1:]:
            other = read_json(folder / "metrics.json")
            if other != first:
                raise ValueError(f"disagreeing duplicate task: {task['task_id']}")
            duplicate.append(task["task_id"])
        identity = {k: task[k] for k in ("task_id", "symbol", "month", "horizon", "model", "control_seed")}
        rows.append({**identity, **{k: v for k, v in first.items() if k not in ("gain", "deciles", "train_days", "test_days")}})
        pooled.setdefault((task["model"], task["horizon"], task["control_seed"]), []).append(found[0]/"predictions.npz")
        resources.append({**identity, **read_json(found[0]/"resource.json")})
        gains.extend({**identity, "feature": f, "normalized_gain": v} for f, v in first["gain"].items())
        deciles.extend({**identity, **d} for d in first["deciles"])
    atomic_json(out / "run_manifest.json", {"planned": len(plan["tasks"]), "completed": len(rows), "missing": missing, "duplicates": duplicate, "substitutions": plan["substitutions"], "config_hash": plan["config_hash"], "cache_hash": plan["cache_hash"], "source_hash": source_hash(), "complete": not missing,
                "attribution": "Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1; CC BY 4.0. Replay, features and evaluation added. As-is; no endorsement.",
                "limitations": "Dependent overlapping message-horizon midpoint labels; selected midpoint diagnostic is not execution PnL."})
    if not rows:
        raise ValueError("no completed tasks")
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "model_metrics_by_symbol_month.csv", index=False)
    summarize_blocks(frame, ["symbol", "model", "horizon", "control_seed"]).to_csv(out / "model_metrics_by_symbol.csv", index=False)
    summarize_blocks(frame, ["model", "horizon", "control_seed"]).to_csv(out / "model_metrics_overall.csv", index=False)
    # HistGB has a narrower scope. Publish a matched-month comparison explicitly.
    comparable = frame.merge(frame[frame.model == "hist_gradient_boosting"][["symbol", "month", "horizon"]], on=["symbol", "month", "horizon"])
    summarize_blocks(comparable, ["model", "horizon", "control_seed"]).to_csv(out / "model_metrics_common_month.csv", index=False)
    frame[frame.control_seed.notna()].to_csv(out / "negative_control_summary.csv", index=False)
    pd.DataFrame(gains).to_csv(out / "xgboost_feature_importance.csv", index=False)
    pd.DataFrame(deciles).to_csv(out / "prediction_deciles.csv", index=False)
    for r in resources:
        r["environment"] = json.dumps(r["environment"], sort_keys=True)
        r["parameters"] = json.dumps(r["parameters"], sort_keys=True)
    pd.DataFrame(resources).to_csv(out / "resource_metrics.csv", index=False)
    pooled_rows = []
    for (model, horizon, seed), paths in pooled.items():
        predictions, actuals = [], []
        for path in paths:
            with np.load(path) as arrays:
                predictions.append(arrays["prediction"])
                actuals.append(arrays["actual"])
        pooled_rows.append({"model": model, "horizon": horizon, "control_seed": seed,
                            **_score_predictions(np.concatenate(predictions), np.concatenate(actuals), 1.0)})
    pd.DataFrame(pooled_rows).to_csv(out / "model_metrics_pooled_secondary.csv", index=False)
    if missing:
        raise ValueError(f"incomplete experiment: {len(missing)} missing tasks; partial aggregates explicitly marked")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--models", nargs="+")
    p.add_argument("--task-id", nargs="+")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--plan-only", action="store_true")
    p.add_argument("--allow-partial-cache", action="store_true")
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--aggregate", nargs="+")
    p.add_argument("--max-hours", type=float, default=8)
    a = p.parse_args()
    if not 1 <= a.threads <= 24:
        raise ValueError("threads must be 1..24")
    config = read_json(a.config)
    # Each host invocation verifies transferred content before execution.
    manifest = validate_cache(a.cache, config, a.allow_partial_cache)
    plan = expand_tasks(config, manifest)
    output = Path(a.out)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "task_manifest.json").exists() and read_json(output/"task_manifest.json") != plan:
        raise ValueError("output task manifest mismatch")
    atomic_json(output/"task_manifest.json", plan)
    if a.aggregate:
        aggregate(plan, a.aggregate, output)
        return
    if a.plan_only:
        print(f"planned {len(plan['tasks'])} tasks", flush=True)
        return
    selected = [t for t in plan["tasks"] if (not a.models or t["model"] in a.models) and (not a.task_id or t["task_id"] in a.task_id)]
    if not selected or (a.task_id and set(a.task_id) != {t["task_id"] for t in selected}):
        raise ValueError("task selection empty or unknown task IDs")
    if a.worker:
        if len(selected) != 1:
            raise ValueError("worker requires exactly one task")
        print(run_task(selected[0], config, manifest, a.cache, output, a.device, a.threads, a.resume, a.retry_failed), flush=True)
        return
    started = time.monotonic()
    counts = {"complete": 0, "skipped": 0, "failed": 0, "not_started": len(selected)}
    for task in selected:
        if time.monotonic()-started >= a.max_hours*3600:
            break
        if a.resume and completed(output/"tasks"/task["task_id"], task):
            counts["skipped"] += 1
        else:
            command = [sys.executable, "-m", "cloblab.scale_runner", "--config", a.config, "--cache", a.cache,
                       "--out", a.out, "--device", a.device, "--threads", str(a.threads), "--task-id", task["task_id"], "--worker"]
            for flag in ("resume", "retry_failed", "allow_partial_cache"):
                if getattr(a, flag):
                    command.append("--" + flag.replace("_", "-"))
            env = {**os.environ, "OMP_NUM_THREADS": str(a.threads), "OPENBLAS_NUM_THREADS": str(a.threads), "MKL_NUM_THREADS": str(a.threads)}
            result = subprocess.run(command, env=env)
            counts["complete" if result.returncode == 0 else "failed"] += 1
        counts["not_started"] -= 1
        atomic_json(output / "progress.json", {**counts, "wall_seconds": time.monotonic()-started, "last_task": task["task_id"]})
        print(json.dumps({**counts, "last_task": task["task_id"]}), flush=True)
        if counts["failed"]:
            raise RuntimeError("task failed; remaining tasks preserved for explicit resume/retry")


if __name__ == "__main__":
    main()
