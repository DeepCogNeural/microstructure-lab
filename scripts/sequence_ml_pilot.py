"""Read-only Q1 cache identity and small causal-window resource pilot.

Writes aggregate counts only; no licensed rows or row predictions are exported.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import pandas as pd

from cloblab.sequence_ml import FEATURES, IDENTITY, index_day, scoring_endpoints, window


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--day", default="2017-01-02")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    manifest_path = args.cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    partitions = manifest["partitions"]
    identity_counts = Counter((p["symbol"], p["day"]) for p in partitions)
    if any(n != 1 for n in identity_counts.values()):
        raise ValueError("duplicate stock/day partition")
    for p in partitions:
        path = args.cache / f"symbol={p['symbol']}" / f"day={p['day']}" / "features.parquet"
        if file_sha256(path) != p["features_sha256"]:
            raise ValueError(f"feature cache hash mismatch: {p['symbol']}/{p['day']}")
    month_counts = Counter(p["day"][:7] for p in partitions)
    selected = [p for p in partitions if p["day"] == args.day]
    if len(selected) != len(manifest["sources"]):
        raise ValueError("pilot day does not cover every source stock")
    checks = []
    for p in sorted(selected, key=lambda x: x["symbol"]):
        path = args.cache / f"symbol={p['symbol']}" / f"day={p['day']}" / "features.parquet"
        frame = pd.read_parquet(path, columns=list(IDENTITY) + list(FEATURES) + ["markout_20"])
        if len(frame) != p["rows"]:
            raise ValueError("cache row count mismatch")
        index = index_day(frame)
        score = scoring_endpoints(frame, index)
        if len(score):
            assert window(frame, int(score[0])).shape == (32, len(FEATURES))
        checks.append({"symbol": p["symbol"], "states": len(frame),
                       **index.counts, "stride20_scorable": len(score),
                       "features_sha256": p["features_sha256"]})
    report = {
        "kind": "Q1 metadata audit and one-day resource/correctness pilot",
        "retrospective_only": True,
        "manifest_sha256": file_sha256(manifest_path),
        "cache_config_hash": manifest["config_hash"],
        "cache_source_hash": manifest["source_hash"],
        "source_files": {symbol: {"sha256": src["sha256"], "bytes": src["bytes"]}
                         for symbol, src in manifest["sources"].items()},
        "partition_count": len(partitions),
        "verified_feature_partitions": len(partitions),
        "stock_count": len(manifest["sources"]),
        "date_min": min(p["day"] for p in partitions),
        "date_max": max(p["day"] for p in partitions),
        "month_partition_counts": dict(sorted(month_counts.items())),
        "pilot_day": args.day,
        "pilot": checks,
        "pilot_wall_seconds": time.monotonic() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "limitations": "All cached feature partitions were freshly rehashed; full raw files were not rehashed. Only one day's rows were examined. No market model fit or GPU use. The development period was previously exposed.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"partition_count": report["partition_count"], "pilot_day": args.day,
                      "states": sum(p["states"] for p in checks),
                      "scorable": sum(p["scorable"] for p in checks),
                      "wall_seconds": report["pilot_wall_seconds"]}))


if __name__ == "__main__":
    main()
