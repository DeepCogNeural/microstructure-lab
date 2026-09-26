"""Minimal synthetic counterexamples for the frozen external BTC join."""
import importlib.util
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "polymarket_external_btc.py"
SPEC = importlib.util.spec_from_file_location("polymarket_external_btc", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_no_future_and_stale_latest_no_fallback():
    recv = np.array([1000, 1100], dtype=np.int64)
    bid = np.array([10.0, 10.1])
    ask = np.array([10.2, 10.3])
    assert MODULE.choose_anchor(recv, bid, ask, 999)["status"] == "missing_no_prior_quote"
    assert MODULE.choose_anchor(recv, bid, ask, 2101)["status"] == "stale_latest_top"


def test_latest_invalid_does_not_backfill_old_valid():
    recv = np.array([1000, 1100], dtype=np.int64)
    bid = np.array([10.0, np.nan])
    ask = np.array([10.2, 10.3])
    assert MODULE.choose_anchor(recv, bid, ask, 1150)["status"] == "invalid_latest_top"


def test_equal_receive_conflict_and_identical_top_tie():
    recv = np.array([1000, 1000], dtype=np.int64)
    assert MODULE.choose_anchor(
        recv, np.array([10.0, 10.0]), np.array([10.1, 10.2]), 1000
    )["status"] == "conflicting_same_receive_top"
    result = MODULE.choose_anchor(
        recv, np.array([10.0, 10.0]), np.array([10.1, 10.1]), 1000
    )
    assert result["status"] == "ok"
    assert result["midpoint"] == 10.05


def test_frozen_configuration_does_not_change_dates_or_model_candidates():
    config = MODULE.frozen_config()
    assert config["roles"]["train"] == ["2026-07-27", "2026-07-28", "2026-07-29"]
    assert config["roles"]["calibration"] == "2026-07-30"
    assert config["roles"]["forward_checks"] == ["2026-07-31", "2026-08-01", "2026-08-02"]
    assert config["model"]["C_candidates"] == [0.1, 1.0, 10.0]
    assert config["model"]["old_R3_excluded"] is True
