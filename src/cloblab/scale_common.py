"""Small shared primitives for immutable inputs and atomic run receipts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def source_hash():
    return digest({p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob("*.py"))})


def capture(command):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def environment():
    packages = {}
    for name in ("numpy", "pandas", "pyarrow", "scikit-learn", "xgboost", "h5py", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    commit = capture(["git", "rev-parse", "HEAD"])
    deployment = Path("SOURCE_MANIFEST.json")
    if commit is None and deployment.exists():
        commit = read_json(deployment)["git_commit"]
    return {"hostname": platform.node(), "python": platform.python_version(),
            "platform": platform.platform(), "logical_cpus": os.cpu_count(),
            "cpu": capture(["lscpu"]), "memory": capture(["free", "-b"]),
            "gpu": capture(["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,driver_version", "--format=csv"]),
            "git_commit": commit, "source_hash": source_hash(),
            "packages": packages,
            "allocation": {k: os.environ[k] for k in ("SLURM_JOB_ID", "SLURM_JOB_GPUS", "CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS") if k in os.environ}}
