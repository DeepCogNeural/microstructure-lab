import json

import numpy as np
import pandas as pd
import pytest

pl = pytest.importorskip("polars")

from cloblab.cli import main
from cloblab.polars_cache import SUMMARY_COLUMNS, summarize_partitions, write_synthetic_cache
from cloblab.scale_common import file_hash

SYMBOLS = ["SYN-A", "SYN-B"]
DAYS = ["2026-01-05", "2026-01-06", "2026-01-07"]


def assert_same_summary(reference, other):
    assert list(other.columns) == SUMMARY_COLUMNS
    assert other.dtypes.equals(reference.dtypes)
    pd.testing.assert_frame_equal(other[["symbol", "day", "rows", "valid_rows"]],
                                  reference[["symbol", "day", "rows", "valid_rows"]])
    for column in ("max_abs_error_bps", "mean_abs_error_bps"):
        assert np.allclose(other[column], reference[column], equal_nan=True, rtol=1e-12, atol=1e-15)


@pytest.fixture
def cache(tmp_path):
    parts = write_synthetic_cache(tmp_path, SYMBOLS, DAYS, rows=80)
    # Make the finite-row filter matter: one NaN feature and one infinite feature.
    path = tmp_path/"symbol=SYN-A/day=2026-01-06/features.parquet"
    frame = pd.read_parquet(path)
    frame.loc[3, "ofi_l1_norm"] = np.nan
    frame.loc[7, "spread_bps"] = np.inf
    frame.to_parquet(path, index=False)
    parts[1]["features_sha256"] = file_hash(path)
    return tmp_path, parts


def test_polars_matches_pandas_reference(cache):
    root, parts = cache
    reference = summarize_partitions(root, parts, "pandas")
    summary = summarize_partitions(root, parts, "polars")
    assert len(reference) == len(SYMBOLS) * len(DAYS)
    assert (reference.rows == 80).all()
    valid = reference.set_index(["symbol", "day"]).valid_rows
    assert valid[("SYN-A", "2026-01-06")] == valid[("SYN-A", "2026-01-05")] - 2
    assert (reference.valid_rows <= reference.rows).all()
    assert np.isfinite(reference.max_abs_error_bps).all()
    assert_same_summary(reference, summary)


def test_empty_partition_is_kept_with_zero_rows(cache):
    root, parts = cache
    path = root/"symbol=SYN-B/day=2026-01-07/features.parquet"
    pd.read_parquet(path).head(0).to_parquet(path, index=False)
    parts[-1]["features_sha256"] = file_hash(path)
    reference = summarize_partitions(root, parts, "pandas")
    summary = summarize_partitions(root, parts, "polars")
    last = reference.iloc[-1]
    assert (last.symbol, last.day, last.rows, last.valid_rows) == ("SYN-B", "2026-01-07", 0, 0)
    assert np.isnan(last.max_abs_error_bps) and np.isnan(last.mean_abs_error_bps)
    assert_same_summary(reference, summary)


@pytest.mark.parametrize("engine", ["pandas", "polars"])
def test_missing_partition_and_changed_file_fail_for_both_engines(cache, engine):
    root, parts = cache
    missing = parts + [{"symbol": "SYN-A", "day": "2026-01-08"}]
    with pytest.raises(FileNotFoundError, match="missing cache partition"):
        summarize_partitions(root, missing, engine)
    changed = [dict(p) for p in parts]
    changed[0]["features_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        summarize_partitions(root, changed, engine)


def test_unknown_engine_rejected(cache):
    root, parts = cache
    with pytest.raises(ValueError, match="unknown engine"):
        summarize_partitions(root, parts, "spark")


def test_cli_engines_write_identical_csv(cache, tmp_path):
    root, parts = cache
    (root/"manifest.json").write_text(json.dumps({"partitions": parts}))
    outputs = {}
    for engine in ("pandas", "polars"):
        out = tmp_path/f"summary_{engine}.csv"
        assert main(["cache-summary", "--root", str(root), "--engine", engine, "--out", str(out)]) == 0
        outputs[engine] = pd.read_csv(out)
    assert_same_summary(outputs["pandas"], outputs["polars"])
