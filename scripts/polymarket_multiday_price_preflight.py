"""Aggregate the frozen seven-day Rocklabs source manifest before any data extraction.

The source ZIP is private. This script never emits the signed URL column or raw rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

DATES = (
    "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
    "2026-07-31", "2026-08-01", "2026-08-02",
)
ROLES = ("train", "train", "train", "calibration", "forward_1", "forward_2", "forward_3")
MAX_COMPRESSED_BYTES = 96 * 2**30
MANIFEST_MEMBER = "poly-data-share/manifest.tsv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(path: str):
    match = re.fullmatch(r"raw/(\d{4}-\d{2}-\d{2})/[^/]+", path)
    if match:
        return match.group(1), "clob"
    match = re.fullmatch(r"raw/(onchain|_index)/(\d{4}-\d{2}-\d{2})/[^/]+", path)
    if match:
        return match.group(2), "index" if match.group(1) == "_index" else "onchain"
    return None


def aggregate(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        manifest_bytes = archive.read(MANIFEST_MEMBER)
    groups = {d: {k: {"objects": 0, "bytes": 0} for k in ("clob", "onchain", "index")}
              for d in DATES}
    seen = set()
    canonical_clob_bytes = 0
    canonical_clob_objects = 0
    for number, row in enumerate(csv.reader(io.StringIO(manifest_bytes.decode()), delimiter="\t"), 1):
        if len(row) != 3:
            raise ValueError(f"manifest row {number}: expected three columns")
        size_text, path, _signed_url = row
        if path in seen:
            raise ValueError(f"manifest row {number}: duplicate path")
        seen.add(path)
        item = classify(path)
        if item is None or item[0] not in groups:
            continue
        size = int(size_text)
        if size < 0:
            raise ValueError(f"manifest row {number}: negative size")
        date, kind = item
        groups[date][kind]["objects"] += 1
        groups[date][kind]["bytes"] += size
        if kind == "clob" and re.fullmatch(rf"raw/{date}/\d{{4}}\.jsonl\.zst", path):
            canonical_clob_objects += 1
            canonical_clob_bytes += size
    totals = {kind: {key: sum(groups[d][kind][key] for d in DATES)
                     for key in ("objects", "bytes")}
              for kind in ("clob", "onchain", "index")}
    total_bytes = sum(v["bytes"] for v in totals.values())
    return {
        "status": "ACCESS_OR_BUDGET_BLOCKED" if total_bytes > MAX_COMPRESSED_BYTES else "BUDGET_PREFLIGHT_PASS",
        "window_utc": "2026-07-27T00:00:00Z/2026-08-03T00:00:00Z",
        "market_family": "Polymarket BTC 5-minute Up/Down",
        "roles": dict(zip(DATES, ROLES)),
        "budget_compressed_bytes": MAX_COMPRESSED_BYTES,
        "window_source_bytes": total_bytes,
        "window_source_objects": sum(v["objects"] for v in totals.values()),
        "window_excess_bytes": max(0, total_bytes - MAX_COMPRESSED_BYTES),
        "canonical_clob": {"objects": canonical_clob_objects, "bytes": canonical_clob_bytes,
                           "excess_bytes_alone": max(0, canonical_clob_bytes - MAX_COMPRESSED_BYTES)},
        "by_kind": totals,
        "by_date": groups,
        "source_zip_sha256": sha256(zip_bytes),
        "source_manifest_sha256": sha256(manifest_bytes),
        "scope": "manifest-only preflight; no compressed market object scanned or model fitted",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_zip", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = aggregate(args.source_zip.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "window_source_objects", "window_source_bytes", "window_excess_bytes")}))


if __name__ == "__main__":
    main()
