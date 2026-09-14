"""Day-partitioned WSELOB replay and immutable causal feature cache."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path
import resource
import time

import h5py
import pandas as pd

from cloblab.scientific_identity import scientific_config
from cloblab.licensed_experiment import prepare
from cloblab.scale_common import atomic_json, digest, environment, file_hash, read_json, source_hash
from cloblab.wselob import reconstruct


def parquet_write(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    frame.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)


def prepare_day(item):
    raw, root, symbol, key, identity, config = item
    started = time.monotonic()
    day = pd.Timestamp(key[1:]).strftime("%Y-%m-%d")
    folder = Path(root) / f"symbol={symbol}" / f"day={day}"
    receipt = folder / "receipt.json"
    if receipt.exists():
        old = read_json(receipt)
        if old["identity"] != identity:
            raise ValueError(f"stale cache identity: {symbol}/{day}")
        for name in ("snapshots", "features"):
            if file_hash(folder / f"{name}.parquet") != old[f"{name}_sha256"]:
                raise ValueError(f"cache content changed: {symbol}/{day}/{name}")
        return {**old, "skipped": True}
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with h5py.File(raw, "r") as f:
            records = f[key + "/table"][:]
        snapshots, audit = reconstruct(records, day, symbol)
        features = prepare(snapshots, config["dataset"]["horizons_events"])
        columns = ["symbol", "day", "segment", "event_index", "timestamp_ns"] + config["features"]["primary_set"] + [f"markout_{h}" for h in config["dataset"]["horizons_events"]]
        features = features[columns]
        parquet_write(snapshots, folder / "snapshots.parquet")
        parquet_write(features, folder / "features.parquet")
        out = {"identity": identity, "symbol": symbol, "day": day, "audit": audit,
               "snapshots_sha256": file_hash(folder / "snapshots.parquet"),
               "features_sha256": file_hash(folder / "features.parquet"),
               "snapshot_bytes": (folder / "snapshots.parquet").stat().st_size,
               "feature_bytes": (folder / "features.parquet").stat().st_size,
               "rows": len(features), "schema": {c: str(t) for c, t in features.dtypes.items()},
               "wall_seconds": time.monotonic() - started,
               "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        atomic_json(receipt, out)
        return out
    except Exception as exc:
        atomic_json(folder / "failure.json", {"identity": identity, "error": repr(exc)})
        raise


def build_cache(config, sources, raw, out, workers=5, symbols=None, max_days=None):
    started = time.monotonic()
    if not 1 <= workers <= 24:
        raise ValueError("preparation workers must be 1..24")
    out = Path(out)
    selected = symbols or config["dataset"]["symbols"]
    source_files, tasks = {}, []
    code = source_hash()
    for symbol in selected:
        src = sources["files"][symbol]
        path = Path(raw) / src["filename"]
        if path.stat().st_size != src["bytes"] or file_hash(path) != src["sha256"]:
            raise ValueError(f"official source hash/size mismatch: {symbol}")
        source_files[symbol] = src
        with h5py.File(path, "r") as f:
            keys = sorted(f)
        keys = [k for k in keys if config["dataset"]["date_start"] <= pd.Timestamp(k[1:]).strftime("%Y-%m-%d") <= config["dataset"]["date_end"]]
        if max_days:
            keys = keys[:max_days]
        if not keys:
            raise ValueError(f"no source days: {symbol}")
        identity = {"raw_sha256": src["sha256"], "config_hash": digest(scientific_config(config)), "source_hash": code}
        tasks.extend((str(path), str(out), symbol, key, identity, config) for key in keys)
    # Persist the full denominator before any reconstruction; failed days cannot disappear.
    atomic_json(out / "preparation_plan.json", {"tasks": [{"symbol": t[2], "key": t[3]} for t in tasks], "sources": source_files, "config_hash": digest(scientific_config(config)), "source_hash": code})
    partitions = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for receipt in pool.map(prepare_day, tasks, chunksize=1):
            partitions.append(receipt)
            print(f"prepared {len(partitions)}/{len(tasks)} {receipt['symbol']} {receipt['day']} rows={receipt['rows']} skipped={receipt.get('skipped', False)}", flush=True)
    # Runtime telemetry is excluded from the semantic identity, for stable cold/warm hashes.
    manifest = {"version": 2, "config_hash": digest(scientific_config(config)), "source_hash": code,
                "attribution": sources["attribution"], "sources": source_files,
                "partial": bool(max_days or set(selected) != set(config["dataset"]["symbols"])),
                "partitions": [{k: p[k] for k in ("symbol", "day", "rows", "features_sha256", "snapshots_sha256", "schema")} for p in partitions]}
    atomic_json(out / "manifest.json", manifest)
    atomic_json(out / "preparation_resource.json", {"environment": environment(), "workers": workers,
                "wall_seconds": time.monotonic() - started, "partitions": len(partitions),
                "skipped": sum(p.get("skipped", False) for p in partitions),
                "source_bytes": sum(s["bytes"] for s in source_files.values()),
                "source_rows": sum(p["audit"]["source_rows"] for p in partitions),
                "rows": sum(p["rows"] for p in partitions),
                "snapshot_bytes": sum(p["snapshot_bytes"] for p in partitions),
                "feature_bytes": sum(p["feature_bytes"] for p in partitions),
                "max_worker_peak_rss_kib": max(p["peak_rss_kib"] for p in partitions)})
    return manifest


def validate_cache(root, config, allow_partial=False):
    root = Path(root)
    manifest = read_json(root / "manifest.json")
    expected_config = digest(scientific_config(config)) if manifest.get("version", 1) >= 2 else digest(config)
    if manifest["config_hash"] != expected_config or manifest["source_hash"] != source_hash():
        raise ValueError("stale cache config/source hash")
    if manifest["partial"] and not allow_partial:
        raise ValueError("partial cache cannot represent the full experiment")
    seen = set()
    for p in manifest["partitions"]:
        key = (p["symbol"], p["day"])
        if key in seen:
            raise ValueError("duplicate cache partition")
        seen.add(key)
        path = root / f"symbol={p['symbol']}" / f"day={p['day']}" / "features.parquet"
        if file_hash(path) != p["features_sha256"]:
            raise ValueError(f"cache hash mismatch: {key}")
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--sources", required=True)
    p.add_argument("--raw", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--max-days", type=int)
    a = p.parse_args()
    build_cache(read_json(a.config), read_json(a.sources), a.raw, a.out, a.workers, a.symbols, a.max_days)


if __name__ == "__main__":
    main()
