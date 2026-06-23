from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from cloblab.book import L2Book, replay_l2_events
from cloblab.cli import run_sample_pipeline
from cloblab.costs import sweep_visible_depth


def _events() -> pd.DataFrame:
    ts = pd.Timestamp("2026-01-01T00:00:00Z")
    return pd.DataFrame(
        [
            {
                "exchange_ts": ts,
                "local_ts": ts,
                "symbol": "BTC-USD",
                "sequence": 1,
                "side": "bid",
                "price": "100.00",
                "size": "2.0",
            },
            {
                "exchange_ts": ts,
                "local_ts": ts,
                "symbol": "BTC-USD",
                "sequence": 2,
                "side": "ask",
                "price": "101.00",
                "size": "1.5",
            },
            {
                "exchange_ts": ts,
                "local_ts": ts,
                "symbol": "BTC-USD",
                "sequence": 3,
                "side": "ask",
                "price": "102.00",
                "size": "2.0",
            },
        ]
    )


class L2ReplayAndCostTests(unittest.TestCase):
    def test_replay_builds_book_and_produces_stable_state_hashes(self) -> None:
        first = replay_l2_events(_events(), tick_size="0.01", lot_size="0.00000001")
        second = replay_l2_events(_events(), tick_size="0.01", lot_size="0.00000001")

        self.assertEqual(first.snapshots.iloc[-1]["best_bid"], 100.0)
        self.assertEqual(first.snapshots.iloc[-1]["best_ask"], 101.0)
        self.assertEqual(first.snapshots["state_hash"].tolist(), second.snapshots["state_hash"].tolist())

    def test_replay_rejects_sequence_gap_without_silent_book_state(self) -> None:
        events = _events()
        events.loc[2, "sequence"] = 5

        with self.assertRaisesRegex(ValueError, "sequence gap"):
            replay_l2_events(events, tick_size="0.01", lot_size="0.00000001")

    def test_l2_book_rejects_crossed_books_and_negative_size(self) -> None:
        book = L2Book(symbol="BTC-USD", tick_size="0.01", lot_size="0.00000001")
        book.apply_level("bid", "100.00", "1.0")
        with self.assertRaisesRegex(ValueError, "crossed book"):
            book.apply_level("ask", "99.00", "1.0")
        with self.assertRaisesRegex(ValueError, "negative"):
            book.apply_level("bid", "100.00", "-1.0")

    def test_visible_depth_sweep_reports_cost_proxy_not_fill_claim(self) -> None:
        replay = replay_l2_events(_events(), tick_size="0.01", lot_size="0.00000001")
        snapshot = replay.snapshots.iloc[-1]

        result = sweep_visible_depth(snapshot, side="buy", size=2.0, fee_bps=1.0)

        self.assertAlmostEqual(result.filled_size, 2.0)
        self.assertAlmostEqual(result.average_price, 101.25)
        self.assertGreater(result.total_cost_bps, 0.0)
        self.assertEqual(result.assumption, "visible_depth_sweep_cost_proxy")

    def test_offline_demo_pipeline_writes_visible_depth_cost_report(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = run_sample_pipeline(out_dir=Path(tmp), rows=90, levels=3, horizon=10, cost_bps=1.0)

            cost_report = pd.read_csv(paths["cost_sweep"])

        self.assertIn("total_cost_bps", cost_report.columns)
        self.assertEqual(cost_report.loc[0, "assumption"], "visible_depth_sweep_cost_proxy")


if __name__ == "__main__":
    unittest.main()
