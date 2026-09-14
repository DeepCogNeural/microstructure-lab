"""Run only preregistered same-host and two-GPU comparisons."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.stats import spearmanr

from cloblab.scale_cache import validate_cache
from cloblab.scale_common import atomic_json, digest, environment, read_json, source_hash
from cloblab.scale_runner import finite_json, run_task


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["cpu-gpu", "two-gpu"], required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--allow-partial-cache", action="store_true", help="Representative systems smoke only")
    a = p.parse_args()
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=True)
    config = read_json(a.config)
    manifest = validate_cache(a.cache, config, a.allow_partial_cache)
    plan = {"config_hash": digest(config), "cache_hash": digest(manifest)}
    tasks = []
    for symbol in (["PEKAO"] if a.mode == "cpu-gpu" else ["PEKAO", "KGHM"]):
        days = [part["day"] for part in manifest["partitions"] if part["symbol"] == symbol]
        if not any(d[:7] == "2017-06" for d in days) or sum(d[:7] < "2017-06" for d in days) < 40:
            raise ValueError("benchmark representative month requires explicit substitution review")
        task = {"symbol": symbol, "month": "2017-06", "horizon": 20, "model": "xgboost", "control_seed": None,
                **plan, "source_hash": source_hash()}
        tasks.append({"task_id": digest(task), **task})
    def run(name, task, device):
        output = root / name
        # Benchmark outputs are new, so timings cannot accidentally measure resume skips.
        if (output / "tasks" / task["task_id"] / "status.json").exists():
            raise ValueError("benchmark run exists: choose a fresh output directory")
        started = time.monotonic()
        # Fresh subprocess keeps task RSS and GPU telemetry independent across trials.
        spec = {"task": task, "config": config, "manifest": manifest, "cache": a.cache,
                "out": str(output), "device": device, "threads": a.threads}
        atomic_json(root/f"{name}-spec.json", spec)
        env = {**os.environ, **{key: str(a.threads) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}
        subprocess.run([sys.executable, "-c", "import sys; from cloblab.scale_common import read_json; from cloblab.scale_runner import run_task; run_task(**read_json(sys.argv[1]))", str(root/f"{name}-spec.json")], check=True, env=env)
        folder = output / "tasks" / task["task_id"]
        return {"name": name, "task_id": task["task_id"], "device": device,
                "end_to_end_seconds": time.monotonic()-started,
                "resource": read_json(folder/"resource.json"), "metrics": read_json(folder/"metrics.json")}
    if a.mode == "cpu-gpu":
        cpu = run("cpu", tasks[0], "cpu")
        gpu = run("gpu", tasks[0], "cuda:0")
        with np.load(root/"cpu"/"tasks"/tasks[0]["task_id"]/"predictions.npz") as c, np.load(root/"gpu"/"tasks"/tasks[0]["task_id"]/"predictions.npz") as g:
            for col in ("actual", "event_index", "timestamp_ns"):
                np.testing.assert_array_equal(c[col], g[col])
            rank = float(spearmanr(c["prediction"], g["prediction"]).statistic)
        drift = gpu["metrics"]["ic"] - cpu["metrics"]["ic"]
        result = {"mode": a.mode, "cpu": cpu, "gpu": gpu, "prediction_spearman": rank,
                  "ic_difference": drift,
                  "direction_accuracy_difference": gpu["metrics"]["direction_accuracy"]-cpu["metrics"]["direction_accuracy"],
                  "training_speedup": cpu["resource"]["train_seconds"]/gpu["resource"]["train_seconds"],
                  "task_wall_speedup": cpu["resource"]["wall_seconds"]/gpu["resource"]["wall_seconds"],
                  "drift_policy": "Stop expansion if prediction Spearman < 0.98 or absolute IC drift > 0.01; numerical, not quality selection.",
                  "drift_pass": rank >= 0.98 and abs(drift) <= 0.01}
    else:
        started = time.monotonic()
        serial = [run(f"serial-{i}", task, "cuda:0") for i, task in enumerate(tasks)]
        serial_seconds = time.monotonic()-started
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, f"parallel-{i}", task, f"cuda:{i}") for i, task in enumerate(tasks)]
            parallel = [f.result() for f in futures]
        parallel_seconds = time.monotonic()-started
        result = {"mode": a.mode, "serial": serial, "parallel": parallel,
                  "serial_seconds": serial_seconds, "parallel_seconds": parallel_seconds,
                  "throughput_speedup": serial_seconds/parallel_seconds,
                  "allocated_gpu_hours_upper_bound": (serial_seconds+parallel_seconds)*2/3600}
    atomic_json(root/"benchmark.json", finite_json({**result, "environment": environment(), "config_hash": plan["config_hash"], "cache_hash": plan["cache_hash"]}))
    if a.mode == "cpu-gpu" and not result["drift_pass"]:
        raise RuntimeError("CPU/GPU drift exceeded preregistered engineering check; stop expansion")


if __name__ == "__main__":
    main()
