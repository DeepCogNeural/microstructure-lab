from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from cloblab.evaluation import run_baseline
from cloblab.features import build_features
from cloblab.labels import build_markout_labels
from cloblab.samples import make_synthetic_order_book
from cloblab.splits import walk_forward_splits


def _snapshots() -> pd.DataFrame:
    ts = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="1s")
    rows = []
    for i, t in enumerate(ts):
        mid = 100.0 + i
        rows.append(
            {
                "exchange_ts": t,
                "local_ts": t,
                "symbol": "BTC-USD",
                "bid_px_1": mid - 0.5,
                "bid_sz_1": 10 + i,
                "ask_px_1": mid + 0.5,
                "ask_sz_1": 8 + i,
                "bid_px_2": mid - 1.0,
                "bid_sz_2": 5,
                "ask_px_2": mid + 1.0,
                "ask_sz_2": 5,
            }
        )
    return pd.DataFrame(rows)


class FeatureLabelSplitTests(unittest.TestCase):
    def test_recent_trade_imbalance_uses_only_current_and_past_trades(self) -> None:
        snapshots = _snapshots()
        trades = pd.DataFrame(
            [
                {
                    "exchange_ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "local_ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "symbol": "BTC-USD",
                    "side": "buy",
                    "price": 100.5,
                    "size": 1.0,
                },
                {
                    "exchange_ts": pd.Timestamp("2026-01-01T00:00:02Z"),
                    "local_ts": pd.Timestamp("2026-01-01T00:00:02Z"),
                    "symbol": "BTC-USD",
                    "side": "sell",
                    "price": 101.5,
                    "size": 9.0,
                },
            ]
        )

        features = build_features(snapshots, trades, depth_levels=2, recent_window="2s")

        at_first_snapshot = features.loc[features["local_ts"] == snapshots.loc[0, "local_ts"]].iloc[0]
        self.assertEqual(at_first_snapshot["recent_trade_buy_size"], 1.0)
        self.assertEqual(at_first_snapshot["recent_trade_sell_size"], 0.0)
        self.assertGreater(at_first_snapshot["recent_trade_imbalance"], 0.0)

    def test_markout_label_uses_first_future_midprice_at_or_after_horizon(self) -> None:
        features = build_features(_snapshots(), pd.DataFrame(), depth_levels=2)

        labeled = build_markout_labels(features, horizons_seconds=(1, 3))

        first = labeled.iloc[0]
        self.assertAlmostEqual(first["markout_1s"], 1.0)
        self.assertAlmostEqual(first["markout_bps_1s"], 100.0)
        self.assertEqual(first["future_ts_3s"], pd.Timestamp("2026-01-01T00:00:03Z"))
        self.assertAlmostEqual(first["markout_3s"], 3.0)

    def test_walk_forward_splits_never_train_on_or_after_test_time(self) -> None:
        data = pd.DataFrame(
            {
                "local_ts": pd.date_range("2026-01-01T00:00:00Z", periods=30, freq="1s"),
                "x": np.arange(30),
            }
        )

        splits = walk_forward_splits(data, min_train_size=12, test_size=5, n_splits=3)

        self.assertEqual(len(splits), 3)
        for train_idx, test_idx in splits:
            train_ts = data.loc[train_idx, "local_ts"]
            test_ts = data.loc[test_idx, "local_ts"]
            self.assertLess(train_ts.max(), test_ts.min())
            self.assertTrue(set(train_idx).isdisjoint(set(test_idx)))

    def test_sample_pipeline_runs_baseline_and_negative_control(self) -> None:
        snapshots, trades = make_synthetic_order_book(rows=90, levels=3)
        features = build_features(snapshots, trades, depth_levels=3)
        labeled = build_markout_labels(features, horizons_seconds=(1, 5, 10, 60))

        result = run_baseline(
            labeled.dropna(subset=["markout_bps_10s"]),
            feature_cols=["top_imbalance", "depth_imbalance", "spread_bps", "recent_trade_imbalance"],
            label_col="markout_bps_10s",
            time_col="local_ts",
            min_train_size=30,
            test_size=15,
            n_splits=2,
            cost_bps=1.0,
            random_seed=7,
        )

        self.assertIn("metrics", result)
        self.assertIn("negative_control", result)
        self.assertGreaterEqual(result["metrics"]["n_test"], 1)
        self.assertIn("direction_accuracy", result["metrics"])
        self.assertIn("ic", result["metrics"])

    def test_baseline_purges_training_rows_whose_label_reaches_test_window(self) -> None:
        local_ts = pd.date_range("2026-01-01T00:00:00Z", periods=20, freq="1s")
        data = pd.DataFrame(
            {
                "local_ts": local_ts,
                "x": np.arange(20, dtype=float),
                "markout_bps_5s": np.arange(20, dtype=float),
                "future_ts_5s": local_ts + pd.Timedelta(seconds=5),
            }
        )

        result = run_baseline(
            data,
            feature_cols=["x"],
            label_col="markout_bps_5s",
            min_train_size=10,
            test_size=5,
            n_splits=1,
        )

        fold = result["folds"][0]
        self.assertEqual(fold["train_n_before_label_purge"], 10)
        self.assertEqual(fold["train_n_after_label_purge"], 5)
        self.assertLess(pd.Timestamp(fold["max_train_label_ts"]), pd.Timestamp(fold["test_start_ts"]))


if __name__ == "__main__":
    unittest.main()
