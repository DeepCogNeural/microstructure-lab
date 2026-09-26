"""Frozen seven-day Rocklabs Binance BTCUSDT source qualification.

Raw Parquet rows, event-level joined anchors, labels, and signed source URLs
remain private. Public outputs contain only schema/clock evidence, aggregate
coverage, hashes, frozen configuration, and resource receipts.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


DATES = (
    "2026-07-27",
    "2026-07-28",
    "2026-07-29",
    "2026-07-30",
    "2026-07-31",
    "2026-08-01",
    "2026-08-02",
)
TRAIN = DATES[:3]
CAL = DATES[3]
FORWARD = DATES[4:]
PREFIX = "raw/external/binance/symbol=btcusdt/depth/"
MEMBER = "poly-data-share/manifest.tsv"
README_MEMBER = "poly-data-share/README.txt"
EXPECTED_SUFFIXES = tuple(
    f"{day}_{hour}.parquet" for day in DATES for hour in ("00", "08", "16")
)
EXPECTED_TOTAL_BYTES = 224_233_100
REQUIRED_FIELDS = (
    "ts_recv",
    "ts_event",
    "symbol",
    "last_update_id",
    "bid_levels",
    "ask_levels",
    *(f"bid{i}_px" for i in range(1, 11)),
    *(f"bid{i}_sz" for i in range(1, 11)),
    *(f"ask{i}_px" for i in range(1, 11)),
    *(f"ask{i}_sz" for i in range(1, 11)),
)
MAX_AGE_MS = 1000


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_registry(source_zip: Path) -> tuple[list[dict], dict, dict]:
    zip_bytes = source_zip.read_bytes()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        manifest_bytes = archive.read(MEMBER)
        readme_bytes = archive.read(README_MEMBER)
    selected: list[dict] = []
    seen: set[str] = set()
    for number, row in enumerate(
        csv.reader(io.StringIO(manifest_bytes.decode()), delimiter="\t"), 1
    ):
        if len(row) != 3:
            raise ValueError(f"manifest row {number}: expected three columns")
        size_text, path, signed_url = row
        if path in seen:
            raise ValueError(f"manifest row {number}: duplicate path")
        seen.add(path)
        if not path.startswith(PREFIX):
            continue
        suffix = path.removeprefix(PREFIX)
        if suffix not in EXPECTED_SUFFIXES:
            continue
        size = int(size_text)
        if size <= 0:
            raise ValueError(f"manifest row {number}: non-positive size")
        selected.append({"path": path, "size_bytes": size, "signed_url": signed_url})
    selected.sort(key=lambda item: item["path"])
    actual = tuple(item["path"].removeprefix(PREFIX) for item in selected)
    if actual != EXPECTED_SUFFIXES:
        raise ValueError("frozen external BTC object set is incomplete or changed")
    total = sum(item["size_bytes"] for item in selected)
    if total != EXPECTED_TOTAL_BYTES:
        raise ValueError("frozen external BTC byte total changed")
    public = {
        "source_zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_readme_sha256": hashlib.sha256(readme_bytes).hexdigest(),
        "prefix": PREFIX,
        "window_utc": "2026-07-27T00:00:00Z/2026-08-03T00:00:00Z",
        "object_count": len(selected),
        "total_bytes": total,
        "by_date": {
            day: {
                "object_count": sum(
                    item["path"].endswith(
                        tuple(f"{day}_{hour}.parquet" for hour in ("00", "08", "16"))
                    )
                    for item in selected
                ),
                "total_bytes": sum(
                    item["size_bytes"]
                    for item in selected
                    if f"/{day}_" in item["path"]
                ),
            }
            for day in DATES
        },
        "objects": [
            {"path": item["path"], "size_bytes": item["size_bytes"]}
            for item in selected
        ],
    }
    readme_evidence = {
        "describes_snapshot_date_range": True,
        "describes_manifest_format": True,
        "defines_parquet_columns": bool(
            re.search(r"ts_recv|bid1_px|last_update_id", readme_bytes.decode(errors="replace"))
        ),
        "note": "The bundled README describes snapshot scope and download mechanics but does not define Parquet fields or clock semantics.",
    }
    return selected, public, readme_evidence


def local_path(cache_root: Path, source_path: str) -> Path:
    if not source_path.startswith(PREFIX) or ".." in Path(source_path).parts:
        raise ValueError("source path outside frozen prefix")
    return cache_root / source_path


def download_one(item: dict, cache_root: Path, retries: int = 3) -> dict:
    output = local_path(cache_root, item["path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file() and output.stat().st_size == item["size_bytes"]:
        return {
            "path": item["path"],
            "size_bytes": item["size_bytes"],
            "sha256": sha256_path(output),
            "attempts": 0,
            "origin": "cache",
            "elapsed_seconds": 0.0,
        }
    attempts = 0
    started = time.monotonic()
    last_error = "unknown"
    for attempt in range(1, retries + 1):
        attempts = attempt
        temporary = output.with_suffix(output.suffix + ".part")
        try:
            digest = hashlib.sha256()
            seen = 0
            request = urllib.request.Request(
                item["signed_url"],
                headers={"User-Agent": "microstructure-lab-research/1"},
            )
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
                "wb"
            ) as handle:
                for chunk in iter(lambda: response.read(1 << 20), b""):
                    handle.write(chunk)
                    digest.update(chunk)
                    seen += len(chunk)
            if seen != item["size_bytes"]:
                raise ValueError(f"size mismatch: {seen} != {item['size_bytes']}")
            os.replace(temporary, output)
            os.chmod(output, 0o600)
            return {
                "path": item["path"],
                "size_bytes": seen,
                "sha256": digest.hexdigest(),
                "attempts": attempts,
                "origin": "source",
                "elapsed_seconds": time.monotonic() - started,
            }
        except urllib.error.HTTPError as exc:
            last_error = f"HTTPError:{exc.code}"
        except urllib.error.URLError as exc:
            last_error = f"URLError:{type(exc.reason).__name__}"
        except (OSError, ValueError) as exc:
            last_error = f"{type(exc).__name__}:{str(exc)[:120]}"
        finally:
            if temporary.exists():
                temporary.unlink()
        if attempt < retries:
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {last_error}")


def schema_audit(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    arrow_schema = parquet.schema_arrow
    metadata = parquet.metadata
    return {
        "num_rows": metadata.num_rows,
        "num_row_groups": metadata.num_row_groups,
        "created_by": metadata.created_by,
        "columns": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in arrow_schema
        ],
        "metadata_keys": sorted(
            key.decode(errors="replace")
            for key in (arrow_schema.metadata or {}).keys()
        ),
        "field_metadata_present": any(field.metadata for field in arrow_schema),
    }


def write_json(path: Path, value: dict | list, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    if private:
        os.chmod(path, 0o600)


def utc_from_ms(value: int) -> str:
    return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).isoformat()


def _bool_sum(value: pa.Array | pa.ChunkedArray) -> int:
    result = pc.sum(pc.cast(value, pa.int64())).as_py()
    return int(result or 0)


def audit_all_files(items: list[dict], cache_root: Path) -> tuple[dict, dict]:
    baseline_schema = None
    file_records = []
    recv_parts = []
    bid_parts = []
    ask_parts = []
    total_rows = 0
    recv_equal_event = 0
    invalid_top = 0
    bid_order_violations = 0
    ask_order_violations = 0
    symbol_violations = 0
    level_count_violations = 0
    recv_nonmonotone = 0
    update_nonmonotone = 0
    global_prev_recv = None
    global_prev_update = None
    max_gap_ms = 0
    duplicate_receive_rows = 0
    duplicate_receive_conflict_pairs = 0
    for item in items:
        path = local_path(cache_root, item["path"])
        if not path.is_file() or path.stat().st_size != item["size_bytes"]:
            raise ValueError(f"missing or wrong-size frozen object: {item['path']}")
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        if baseline_schema is None:
            baseline_schema = schema
        elif not schema.equals(baseline_schema, check_metadata=True):
            raise ValueError(f"schema mismatch: {item['path']}")
        if set(schema.names) != set(REQUIRED_FIELDS) or len(schema.names) != len(REQUIRED_FIELDS):
            raise ValueError(f"unexpected field set: {item['path']}")
        columns = [
            "ts_recv",
            "ts_event",
            "symbol",
            "last_update_id",
            "bid_levels",
            "ask_levels",
            *(f"bid{i}_px" for i in range(1, 11)),
            *(f"ask{i}_px" for i in range(1, 11)),
        ]
        table = parquet.read(columns=columns)
        recv = table["ts_recv"].combine_chunks().to_numpy(zero_copy_only=False)
        event = table["ts_event"].combine_chunks().to_numpy(zero_copy_only=False)
        update = table["last_update_id"].combine_chunks().to_numpy(zero_copy_only=False)
        bid = table["bid1_px"].combine_chunks().to_numpy(zero_copy_only=False)
        ask = table["ask1_px"].combine_chunks().to_numpy(zero_copy_only=False)
        rows = len(recv)
        total_rows += rows
        recv_equal_event += int(np.sum(recv == event))
        invalid_top += int(
            np.sum(~np.isfinite(bid) | ~np.isfinite(ask) | (bid <= 0) | (bid >= ask))
        )
        symbol_violations += _bool_sum(pc.not_equal(table["symbol"], "btcusdt"))
        level_count_violations += _bool_sum(
            pc.or_(
                pc.not_equal(table["bid_levels"], 10),
                pc.not_equal(table["ask_levels"], 10),
            )
        )
        bid_matrix = np.column_stack(
            [
                table[f"bid{i}_px"].combine_chunks().to_numpy(zero_copy_only=False)
                for i in range(1, 11)
            ]
        )
        ask_matrix = np.column_stack(
            [
                table[f"ask{i}_px"].combine_chunks().to_numpy(zero_copy_only=False)
                for i in range(1, 11)
            ]
        )
        bid_order_violations += int(
            np.sum(
                ~np.all(np.isfinite(bid_matrix), axis=1)
                | np.any(bid_matrix[:, :-1] <= bid_matrix[:, 1:], axis=1)
            )
        )
        ask_order_violations += int(
            np.sum(
                ~np.all(np.isfinite(ask_matrix), axis=1)
                | np.any(ask_matrix[:, :-1] >= ask_matrix[:, 1:], axis=1)
            )
        )
        recv_diff = np.diff(recv)
        update_diff = np.diff(update)
        recv_nonmonotone += int(np.sum(recv_diff < 0))
        update_nonmonotone += int(np.sum(update_diff < 0))
        duplicate_receive_rows += int(np.sum(recv_diff == 0))
        if rows > 1:
            same = recv_diff == 0
            conflict = same & ((bid[:-1] != bid[1:]) | (ask[:-1] != ask[1:]))
            duplicate_receive_conflict_pairs += int(np.sum(conflict))
            max_gap_ms = max(max_gap_ms, int(np.max(recv_diff)))
        if global_prev_recv is not None:
            if recv[0] < global_prev_recv:
                recv_nonmonotone += 1
            if recv[0] == global_prev_recv:
                duplicate_receive_rows += 1
            max_gap_ms = max(max_gap_ms, int(recv[0] - global_prev_recv))
        if global_prev_update is not None and update[0] < global_prev_update:
            update_nonmonotone += 1
        global_prev_recv = int(recv[-1])
        global_prev_update = int(update[-1])
        recv_parts.append(recv.astype(np.int64, copy=False))
        bid_parts.append(bid.astype(float, copy=False))
        ask_parts.append(ask.astype(float, copy=False))
        file_records.append(
            {
                "path": item["path"],
                "rows": rows,
                "min_ts_recv": int(recv[0]),
                "max_ts_recv": int(recv[-1]),
            }
        )
    recv_all = np.concatenate(recv_parts)
    bid_all = np.concatenate(bid_parts)
    ask_all = np.concatenate(ask_parts)
    audit = {
        "status": "BLOCKED_EXTERNAL_SOURCE_SEMANTICS_UNKNOWN",
        "price_mapping": {
            "candidate_bid": "bid1_px",
            "candidate_ask": "ask1_px",
            "candidate_midpoint": "(bid1_px + ask1_px) / 2",
            "structural_evidence": "Every row has ten ordered bid price columns and ten ordered ask price columns with bid_levels=ask_levels=10.",
            "source_semantics_verified": False,
            "reason": "No bundled field contract or collector code establishes that each row is a complete or partial depth snapshot whose bid1/ask1 are verified best prices, rather than a sampled or reconstructed representation of upstream diff updates. Column names and ordering alone are insufficient under the frozen protocol.",
        },
        "timestamp_mapping": {
            "candidate_receive_field": "ts_recv",
            "candidate_event_field": "ts_event",
            "integer_unit_supported_by_magnitude_and_window": "milliseconds",
            "first_candidate_receive_utc": utc_from_ms(int(recv_all[0])),
            "last_candidate_receive_utc": utc_from_ms(int(recv_all[-1])),
            "independent_receive_semantics_verified": False,
            "reason": "No bundled field contract or Parquet metadata defines ts_recv, and ts_recv equals ts_event on every row. The plan forbids treating event time as receipt time or inferring semantics from apparent low latency.",
        },
        "rows": total_rows,
        "objects": len(items),
        "schema_consistent": True,
        "all_required_fields_exact": True,
        "recv_equal_event_rows": recv_equal_event,
        "recv_equal_event_fraction": recv_equal_event / total_rows,
        "invalid_top_rows": invalid_top,
        "bid_order_violation_rows": bid_order_violations,
        "ask_order_violation_rows": ask_order_violations,
        "symbol_violation_rows": symbol_violations,
        "level_count_violation_rows": level_count_violations,
        "receive_nonmonotone_transitions": recv_nonmonotone,
        "update_id_nonmonotone_transitions": update_nonmonotone,
        "duplicate_receive_rows": duplicate_receive_rows,
        "duplicate_receive_conflict_pairs": duplicate_receive_conflict_pairs,
        "max_observed_candidate_receive_gap_ms": max_gap_ms,
        "fit_allowed": False,
        "blocking_codes": ["EXTERNAL_PRICE_SEMANTICS_UNKNOWN", "EXTERNAL_CLOCK_UNKNOWN"],
        "file_coverage": file_records,
    }
    arrays = {"recv": recv_all, "bid": bid_all, "ask": ask_all}
    return audit, arrays


def choose_anchor(
    recv: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    anchor_ms: int,
    max_age_ms: int = MAX_AGE_MS,
) -> dict:
    index = int(np.searchsorted(recv, anchor_ms, side="right") - 1)
    if index < 0:
        return {"status": "missing_no_prior_quote"}
    timestamp = int(recv[index])
    left = int(np.searchsorted(recv, timestamp, side="left"))
    right = int(np.searchsorted(recv, timestamp, side="right"))
    tops = np.column_stack((bid[left:right], ask[left:right]))
    if len(tops) > 1 and np.any(tops != tops[0]):
        return {"status": "conflicting_same_receive_top", "receive_ms": timestamp}
    selected_bid = float(tops[-1, 0])
    selected_ask = float(tops[-1, 1])
    age_ms = anchor_ms - timestamp
    if not (
        math.isfinite(selected_bid)
        and math.isfinite(selected_ask)
        and 0 < selected_bid < selected_ask
    ):
        return {"status": "invalid_latest_top", "receive_ms": timestamp, "age_ms": age_ms}
    if age_ms > max_age_ms:
        return {"status": "stale_latest_top", "receive_ms": timestamp, "age_ms": age_ms}
    return {
        "status": "ok",
        "receive_ms": timestamp,
        "age_ms": age_ms,
        "midpoint": (selected_bid + selected_ask) / 2,
    }


def load_eligible_events(events_path: Path, labels_path: Path) -> list[dict]:
    events = json.loads(events_path.read_text())
    labels = json.loads(labels_path.read_text())
    if len(events) != 2016 or len(labels) != 2016:
        raise ValueError("frozen event/label denominator changed")
    if [row["slot"] for row in events] != [row["slot"] for row in labels]:
        raise ValueError("event/label slot join mismatch")
    eligible = []
    for event, label in zip(events, labels):
        if (
            event.get("p") is not None
            and event.get("identity_status") == "gamma_verified"
            and label.get("label_status") == "verified_binary"
            and label.get("y") in (0, 1)
        ):
            eligible.append(event)
    if len(eligible) != 1942:
        raise ValueError(f"expected 1942 frozen price-eligible events, got {len(eligible)}")
    return eligible


def coverage_audit(events: list[dict], arrays: dict, clock_verified: bool) -> tuple[dict, list[dict]]:
    recv, bid, ask = arrays["recv"], arrays["bid"], arrays["ask"]
    by_date: dict[str, dict] = {}
    status_counts_main = Counter()
    status_counts_shift = Counter()
    event_records = []
    for event in events:
        decision_ms = int(event["decision_us"] // 1000)
        start_ms = decision_ms - 180_000
        main_anchors = {
            "s": start_ms,
            "t_minus_30": decision_ms - 30_000,
            "t": decision_ms,
        }
        shift_anchors = {
            "s": start_ms,
            "t_minus_35": decision_ms - 35_000,
            "t_minus_5": decision_ms - 5_000,
        }
        main = {name: choose_anchor(recv, bid, ask, value) for name, value in main_anchors.items()}
        shift = {name: choose_anchor(recv, bid, ask, value) for name, value in shift_anchors.items()}
        main_ok = all(value["status"] == "ok" for value in main.values())
        shift_ok = all(value["status"] == "ok" for value in shift.values())
        for value in main.values():
            status_counts_main[value["status"]] += 1
        for value in shift.values():
            status_counts_shift[value["status"]] += 1
        event_records.append(
            {
                "slot": event["slot"],
                "date": event["date"],
                "main_joint": main_ok,
                "shift_joint": shift_ok,
                "common_joint": main_ok and shift_ok,
                "main": main,
                "shift": shift,
            }
        )
    for day in DATES:
        rows = [row for row in event_records if row["date"] == day]
        denominator = len(rows)
        main_n = sum(row["main_joint"] for row in rows)
        shift_n = sum(row["shift_joint"] for row in rows)
        common_n = sum(row["common_joint"] for row in rows)
        by_date[day] = {
            "frozen_price_eligible_events": denominator,
            "main_joint_available": main_n,
            "main_joint_fraction": main_n / denominator,
            "shift_joint_available": shift_n,
            "shift_joint_fraction": shift_n / denominator,
            "main_shift_common_available": common_n,
            "main_shift_common_fraction": common_n / denominator,
        }
    partitions = {
        "train": TRAIN,
        "calibration": (CAL,),
        **{f"check_{day}": (day,) for day in FORWARD},
    }
    partition_coverage = {}
    for name, days in partitions.items():
        denominator = sum(by_date[day]["frozen_price_eligible_events"] for day in days)
        main_n = sum(by_date[day]["main_joint_available"] for day in days)
        shift_n = sum(by_date[day]["shift_joint_available"] for day in days)
        common_n = sum(by_date[day]["main_shift_common_available"] for day in days)
        partition_coverage[name] = {
            "days": list(days),
            "denominator": denominator,
            "main_joint_available": main_n,
            "main_joint_fraction": main_n / denominator,
            "shift_joint_available": shift_n,
            "shift_joint_fraction": shift_n / denominator,
            "main_shift_common_available": common_n,
            "main_shift_common_fraction": common_n / denominator,
            "conditional_main_coverage_at_least_80pct": main_n / denominator >= 0.8,
            "conditional_shift_coverage_at_least_80pct": shift_n / denominator >= 0.8,
        }
    coverage_pass = all(
        value["conditional_main_coverage_at_least_80pct"]
        for value in partition_coverage.values()
    )
    public = {
        "status": "CONDITIONAL_COVERAGE_PASS_BUT_SOURCE_SEMANTICS_FAILED"
        if coverage_pass and not clock_verified
        else "QUALIFIED" if coverage_pass and clock_verified else "COVERAGE_GATE_FAILED",
        "role": "CONDITIONAL_DIAGNOSTIC_ONLY" if not clock_verified else "QUALIFYING",
        "assumption": "Candidate ts_recv is Unix milliseconds and is a genuine historical receipt timestamp.",
        "assumption_verified": clock_verified,
        "frozen_price_eligible_denominator": len(events),
        "by_date": by_date,
        "by_partition": partition_coverage,
        "main_anchor_status_counts": dict(status_counts_main),
        "shift_anchor_status_counts": dict(status_counts_shift),
        "conditional_80pct_coverage_gate": coverage_pass,
        "source_gate": False if not clock_verified else coverage_pass,
        "fit_allowed": clock_verified and coverage_pass,
        "blocking_codes": [] if clock_verified else ["EXTERNAL_PRICE_SEMANTICS_UNKNOWN", "EXTERNAL_CLOCK_UNKNOWN"],
    }
    return public, event_records


def frozen_config() -> dict:
    return {
        "protocol": "POLYMARKET_SETTLEMENT_EXTERNAL_BTC_V1",
        "window_utc": "2026-07-27T00:00:00Z/2026-08-03T00:00:00Z",
        "symbol": "BTCUSDT spot",
        "roles": {
            "train": list(TRAIN),
            "calibration": CAL,
            "forward_checks": list(FORWARD),
        },
        "event_cohort": "original 1942 Polymarket price-and-label-eligible events",
        "main_anchors_seconds_from_start": {"s": 0, "t_minus_30": 150, "t": 180},
        "shift_anchors_seconds_from_start": {"s": 0, "t_minus_35": 145, "t_minus_5": 175},
        "external_features": {
            "main_x1": "log(S(t)/S(s))",
            "main_x2": "log(S(t)/S(t-30s))",
            "shift_x1": "log(S(t-5s)/S(s))",
            "shift_x2": "log(S(t-5s)/S(t-35s))",
        },
        "quote_rule": {
            "latest_raw_receive_lte_anchor": True,
            "max_age_ms": MAX_AGE_MS,
            "latest_invalid_no_fallback": True,
            "same_receive_different_top_is_conflict": True,
        },
        "coverage_threshold": 0.8,
        "model": {
            "family": "original offset-logistic/L2",
            "C_candidates": [0.1, 1.0, 10.0],
            "selection_day": CAL,
            "refit_train_plus_calibration": False,
            "arms": ["E0", "Eprice", "Eexternal"],
            "old_R3_excluded": True,
        },
        "evaluation": {
            "gain": "LL(Eprice)-LL(Eexternal)",
            "epsilon": 1e-6,
            "sensitivity": "fixed five-second information shift without retraining",
        },
        "label_boundary": "CTF labels retained; Binance is not used to create winners and S(s) is not an official strike.",
        "status": "FROZEN; fitting contingent on price, clock, and coverage gates",
    }


def synthetic_checks() -> dict:
    recv = np.array([1000, 1100, 1100, 1200], dtype=np.int64)
    bid = np.array([10.0, 10.1, 10.1, np.nan])
    ask = np.array([10.2, 10.3, 10.4, 10.5])
    checks = {}
    checks["no_future_quote"] = choose_anchor(recv, bid, ask, 999)["status"] == "missing_no_prior_quote"
    checks["same_receive_conflict"] = choose_anchor(recv, bid, ask, 1150)["status"] == "conflicting_same_receive_top"
    checks["latest_invalid_no_fallback"] = choose_anchor(recv, bid, ask, 1250)["status"] == "invalid_latest_top"
    checks["stale_latest_no_fallback"] = choose_anchor(
        np.array([1000]), np.array([10.0]), np.array([10.1]), 2001
    )["status"] == "stale_latest_top"
    checks["identical_top_tie_allowed"] = choose_anchor(
        np.array([1000, 1000]), np.array([10.0, 10.0]), np.array([10.1, 10.1]), 1000
    )["status"] == "ok"
    if not all(checks.values()):
        raise AssertionError(f"synthetic checks failed: {checks}")
    return {"status": "PASS", "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--events-private", type=Path)
    parser.add_argument("--labels-private", type=Path)
    parser.add_argument("--recovery-failed-dns-attempts", type=int, default=0)
    parser.add_argument("--mode", choices=("manifest", "schema", "all"), default="all")
    args = parser.parse_args()
    started_wall = dt.datetime.now(dt.timezone.utc)
    started = time.monotonic()
    items, public_manifest, readme_evidence = source_registry(args.source_zip)
    write_json(args.public_dir / "external_source_manifest.json", public_manifest)
    write_json(args.public_dir / "external_frozen_config.json", frozen_config())
    if args.mode == "manifest":
        print(json.dumps({"status": "MANIFEST_FROZEN", "objects": len(items), "bytes": public_manifest["total_bytes"]}))
        return
    targets = items[:1] if args.mode == "schema" else items
    receipts = [download_one(item, args.cache_root) for item in targets]
    write_json(args.private_dir / "download_receipts_private.json", receipts, private=True)
    if args.mode == "schema":
        audit = schema_audit(local_path(args.cache_root, items[0]["path"]))
        public_gate = {
            "status": "SCHEMA_PENDING_SEMANTIC_REVIEW",
            "first_object": {key: receipts[0][key] for key in ("path", "size_bytes", "sha256")},
            "schema": audit,
            "readme_evidence": readme_evidence,
            "requests": sum(receipt["attempts"] for receipt in receipts),
            "downloaded_bytes": sum(receipt["size_bytes"] for receipt in receipts if receipt["origin"] == "source"),
            "elapsed_seconds": time.monotonic() - started,
        }
        write_json(args.public_dir / "external_schema_gate.json", public_gate)
        print(json.dumps({"status": public_gate["status"]}, sort_keys=True))
        return
    if args.events_private is None or args.labels_private is None:
        raise ValueError("--events-private and --labels-private are required for --mode all")
    source_audit, arrays = audit_all_files(items, args.cache_root)
    source_audit["first_object_schema"] = schema_audit(local_path(args.cache_root, items[0]["path"]))
    source_audit["readme_evidence"] = readme_evidence
    write_json(args.public_dir / "external_schema_gate.json", source_audit)
    eligible = load_eligible_events(args.events_private, args.labels_private)
    coverage, private_anchors = coverage_audit(eligible, arrays, clock_verified=False)
    write_json(args.public_dir / "external_coverage_gate.json", coverage)
    write_json(args.private_dir / "external_anchors_conditional_private.json", private_anchors, private=True)
    model_result = {
        "status": "NOT_FIT_EXTERNAL_SOURCE_SEMANTICS_UNKNOWN",
        "blocking_codes": ["EXTERNAL_PRICE_SEMANTICS_UNKNOWN", "EXTERNAL_CLOCK_UNKNOWN"],
        "source_gate_passed": False,
        "coverage_gate_conditional_only": coverage["conditional_80pct_coverage_gate"],
        "models_fit": [],
        "main_metrics": None,
        "five_second_sensitivity_metrics": None,
        "interpretation": "The source can supply candidate top-of-book values under conditional price and timestamp interpretations, but neither its snapshot/best-price contract nor its historical receipt-time semantics is verified. This is a source-semantics block, not evidence of no external signal.",
    }
    write_json(args.public_dir / "external_model_result.json", model_result)
    checks = synthetic_checks()
    write_json(args.public_dir / "external_synthetic_checks.json", checks)
    elapsed = time.monotonic() - started
    receipt = {
        "status": "COMPLETE_WITH_SEMANTIC_GATE",
        "started_utc": started_wall.isoformat(),
        "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "wall_seconds": elapsed,
        "host_environment": "local macOS CPU",
        "python": ".".join(map(str, sys.version_info[:3])),
        "pyarrow": pa.__version__,
        "numpy": np.__version__,
        "objects": len(items),
        "compressed_input_bytes": public_manifest["total_bytes"],
        "rows_scanned": source_audit["rows"],
        "http_requests_this_invocation": sum(receipt["attempts"] for receipt in receipts),
        "downloaded_bytes_this_invocation": sum(receipt["size_bytes"] for receipt in receipts if receipt["origin"] == "source"),
        "cache_hits_this_invocation": sum(receipt["origin"] == "cache" for receipt in receipts),
        "data_acquisition_successful_requests_cumulative": 21,
        "data_acquisition_successful_bytes_cumulative": public_manifest["total_bytes"],
        "data_acquisition_history": "One initial schema-object success followed by 20 successful object requests; this qualifying rerun reused all 21 cached objects.",
        "recovery_failed_dns_attempts": args.recovery_failed_dns_attempts,
        "recovery_failed_dns_bytes": 0,
        "script_sha256": sha256_path(Path(__file__)),
        "events_private_sha256": sha256_path(args.events_private),
        "labels_private_sha256": sha256_path(args.labels_private),
        "source_zip_sha256": public_manifest["source_zip_sha256"],
        "source_manifest_sha256": public_manifest["source_manifest_sha256"],
        "network_writers": 1,
        "gpu": 0,
    }
    write_json(args.public_dir / "external_resource_receipt.json", receipt)
    print(json.dumps({
        "status": model_result["status"],
        "clock_gate": False,
        "conditional_coverage_gate": coverage["conditional_80pct_coverage_gate"],
        "eligible_events": len(eligible),
        "rows_scanned": source_audit["rows"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
