"""Partition-level summaries of the day-partitioned feature cache.

The cache written by ``cloblab.scale_cache`` stores one ``features.parquet``
per ``symbol=<S>/day=<D>`` folder. This module computes one summary row per
partition with two engines:

- ``pandas`` (default, reference): reads each partition with
  ``pd.read_parquet`` in a Python loop, the pattern used by the existing
  research readers.
- ``polars`` (optional): builds one lazy query over all partitions with
  ``pl.scan_parquet`` and collects it once, so Parquet projection pushdown and
  the multi-threaded engine do the scan.

The aggregate mirrors the per-partition algebra check inside
``cloblab.research_diagnostics.clock_and_quotes``: total rows, rows whose
primary features are all finite, and the max/mean absolute error of the
identity ``microprice_minus_mid_bps == 0.5 * spread_bps * top_imbalance`` on
those finite rows. Both engines must return identical frames; the polars engine
does not change any scientific definition.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import time
from typing import Iterable

import numpy as np
import pandas as pd

from cloblab.later_confirmation import FEATURES
from cloblab.scale_common import file_hash

SUMMARY_COLUMNS = ["symbol", "day", "rows", "valid_rows", "max_abs_error_bps", "mean_abs_error_bps"]
READ_COLUMNS = ["symbol", "day"] + FEATURES
ENGINES = ("pandas", "polars")


def partition_paths(root: str | Path, partitions: Iterable[dict]) -> list[tuple[dict, Path]]:
    """Resolve manifest partitions to feature files, failing on missing or changed files.

    Missing partitions raise ``FileNotFoundError`` for both engines; a partition
    is never silently dropped from the denominator. When a partition carries
    ``features_sha256`` the file hash is checked, as the existing readers do.
    """

    resolved = []
    seen = set()
    for part in partitions:
        key = (part["symbol"], part["day"])
        if key in seen:
            raise ValueError(f"duplicate cache partition: {key}")
        seen.add(key)
        path = Path(root) / f"symbol={part['symbol']}" / f"day={part['day']}" / "features.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"missing cache partition: {part['symbol']}/{part['day']}")
        if "features_sha256" in part and file_hash(path) != part["features_sha256"]:
            raise ValueError(f"cache hash mismatch: {key}")
        resolved.append((part, path))
    if not resolved:
        raise ValueError("no cache partitions selected")
    return resolved


def _finalize(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    frame = frame.astype({"symbol": object, "day": object, "rows": "int64", "valid_rows": "int64",
                          "max_abs_error_bps": "float64", "mean_abs_error_bps": "float64"})
    return frame.sort_values(["symbol", "day"], ignore_index=True)


def summarize_partitions_pandas(root: str | Path, partitions: Iterable[dict]) -> pd.DataFrame:
    """Reference engine: one ``pd.read_parquet`` per partition."""

    rows = []
    for part, path in partition_paths(root, partitions):
        f = pd.read_parquet(path, columns=READ_COLUMNS)
        if len(f) and (set(f.symbol) != {part["symbol"]} or set(f.day) != {part["day"]}):
            raise ValueError(f"partition identity: {part['symbol']}/{part['day']}")
        valid = np.isfinite(f[FEATURES].astype("float64")).all(axis=1)
        error = (f.loc[valid, "microprice_minus_mid_bps"]
                 - 0.5 * f.loc[valid, "spread_bps"] * f.loc[valid, "top_imbalance"]).abs()
        rows.append({"symbol": part["symbol"], "day": part["day"], "rows": len(f),
                     "valid_rows": int(valid.sum()),
                     "max_abs_error_bps": float(error.max()) if len(error) else np.nan,
                     "mean_abs_error_bps": float(error.mean()) if len(error) else np.nan})
    return _finalize(rows)


def scan_partitions_polars(resolved: list[tuple[dict, Path]]):
    """Return one lazy polars query over partitions from ``partition_paths``.

    Each file is scanned with ``hive_partitioning=False`` because the files
    already contain ``symbol`` and ``day`` columns, and only ``READ_COLUMNS``
    are selected so the Parquet reader skips the other column chunks. Columns
    are cast to an explicit schema per file before concatenation, so a file
    whose writer inferred a different type (for example an empty partition)
    cannot change the combined schema. A literal ``partition`` index ties each
    row back to its manifest entry, which keeps empty partitions in the result.
    """

    import polars as pl

    schema = {"symbol": pl.String, "day": pl.String, **{c: pl.Float64 for c in FEATURES}}
    frames = []
    for index, (_, path) in enumerate(resolved):
        frames.append(
            pl.scan_parquet(path, hive_partitioning=False)
            .select(READ_COLUMNS)
            .cast(schema)
            .with_columns(pl.lit(index, dtype=pl.Int64).alias("partition"))
        )
    return pl.concat(frames, how="vertical")


def summarize_partitions_polars(root: str | Path, partitions: Iterable[dict]) -> pd.DataFrame:
    """Optional engine: one lazy polars query, collected once."""

    import polars as pl

    resolved = partition_paths(root, partitions)
    # A null feature (pandas NaN written through pyarrow) counts as non-finite.
    valid = pl.all_horizontal([pl.col(c).is_finite().fill_null(False) for c in FEATURES])
    error = (pl.col("microprice_minus_mid_bps") - 0.5 * pl.col("spread_bps") * pl.col("top_imbalance")).abs()
    stats = (
        scan_partitions_polars(resolved)
        .with_columns(valid.alias("valid"), error.alias("error"))
        .group_by("partition")
        .agg(
            pl.len().alias("rows"),
            pl.col("valid").sum().alias("valid_rows"),
            pl.col("error").filter(pl.col("valid")).max().alias("max_abs_error_bps"),
            pl.col("error").filter(pl.col("valid")).mean().alias("mean_abs_error_bps"),
            pl.col("symbol").unique().alias("symbols"),
            pl.col("day").unique().alias("days"),
        )
        .collect()
    )
    found = {r["partition"]: r for r in stats.iter_rows(named=True)}
    rows = []
    for index, (part, _) in enumerate(resolved):
        r = found.get(index)
        if r is None:
            rows.append({"symbol": part["symbol"], "day": part["day"], "rows": 0, "valid_rows": 0,
                         "max_abs_error_bps": np.nan, "mean_abs_error_bps": np.nan})
            continue
        if r["symbols"] != [part["symbol"]] or r["days"] != [part["day"]]:
            raise ValueError(f"partition identity: {part['symbol']}/{part['day']}")
        rows.append({"symbol": part["symbol"], "day": part["day"], "rows": r["rows"],
                     "valid_rows": r["valid_rows"],
                     "max_abs_error_bps": np.nan if r["max_abs_error_bps"] is None else r["max_abs_error_bps"],
                     "mean_abs_error_bps": np.nan if r["mean_abs_error_bps"] is None else r["mean_abs_error_bps"]})
    return _finalize(rows)


def summarize_partitions(root: str | Path, partitions: Iterable[dict], engine: str = "pandas") -> pd.DataFrame:
    """Dispatch to the pandas reference or the optional polars engine."""

    if engine == "pandas":
        return summarize_partitions_pandas(root, partitions)
    if engine == "polars":
        return summarize_partitions_polars(root, partitions)
    raise ValueError(f"unknown engine: {engine}; expected one of {ENGINES}")


def write_synthetic_cache(root: str | Path, symbols: Iterable[str], days: Iterable[str], rows: int = 120) -> list[dict]:
    """Write a cache-shaped fixture from the synthetic order book; not market data.

    Each partition is ``make_synthetic_order_book`` output passed through the
    cache feature definition ``cloblab.licensed_experiment.prepare``. Returns
    manifest-style partition entries with ``features_sha256``.
    """

    from cloblab.licensed_experiment import prepare
    from cloblab.samples import make_synthetic_order_book

    columns = ["symbol", "day", "segment", "event_index", "timestamp_ns"] + FEATURES + ["markout_10", "markout_20", "markout_50"]
    parts = []
    for symbol in symbols:
        for day in days:
            snapshots, _ = make_synthetic_order_book(rows=rows, levels=10, symbol=symbol, start=f"{day}T00:00:00Z")
            snapshots = snapshots.assign(day=day, segment=0, event_index=np.arange(len(snapshots)),
                                         timestamp_ns=snapshots.exchange_ts.astype("int64"))
            features = prepare(snapshots, [10, 20, 50])[columns]
            path = Path(root) / f"symbol={symbol}" / f"day={day}" / "features.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            features.to_parquet(path, index=False, compression="zstd")
            parts.append({"symbol": symbol, "day": day, "features_sha256": file_hash(path)})
    return parts


def benchmark_engines(partitions: int = 200, rows: int = 2000, repeats: int = 3) -> dict:
    """Time both engines on a synthetic fixture; the ratio is hardware-dependent.

    Returns best-of-``repeats`` wall seconds per engine. Nothing is written
    outside a temporary directory, and no machine description is recorded.
    """

    days = [str(d.date()) for d in pd.bdate_range("2026-01-01", periods=partitions)]
    timings = {}
    with tempfile.TemporaryDirectory() as tmp:
        # Drop hashes so the timing covers the Parquet read and aggregate only.
        parts = [{"symbol": p["symbol"], "day": p["day"]} for p in write_synthetic_cache(tmp, ["SYN"], days, rows=rows)]
        for engine in ENGINES:
            best = float("inf")
            for _ in range(repeats):
                started = time.perf_counter()
                summarize_partitions(tmp, parts, engine)
                best = min(best, time.perf_counter() - started)
            timings[engine] = best
    return {"partitions": partitions, "rows_per_partition": rows, "seconds": timings,
            "pandas_over_polars": timings["pandas"] / timings["polars"]}
