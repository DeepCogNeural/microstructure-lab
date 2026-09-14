import numpy as np
import pandas as pd

from cloblab.advanced_features import (
    add_causal_trade_activity_features,
    add_microstructure_features,
    add_rolling_activity_features,
)


def test_microprice_and_ofi_are_causal_from_current_and_lagged_book():
    frame = pd.DataFrame(
        {
            "bid_px_1": [100.0, 100.0, 101.0],
            "ask_px_1": [101.0, 101.0, 102.0],
            "bid_sz_1": [10.0, 12.0, 8.0],
            "ask_sz_1": [10.0, 8.0, 9.0],
        }
    )
    out = add_microstructure_features(frame)
    assert np.isnan(out.loc[0, "ofi_l1"])
    assert np.isclose(out.loc[1, "microprice"], 100.6)
    assert np.isclose(out.loc[1, "ofi_l1"], 4.0)
    assert np.isclose(out.loc[1, "ofi_l1_norm"], 0.2)


def test_rolling_activity_uses_backward_window():
    frame = pd.DataFrame(
        {
            "local_ts": pd.date_range("2026-01-01", periods=4, freq="1s", tz="UTC"),
            "trade_sign": [1, -1, 1, 1],
            "trade_size": [1.0, 2.0, 1.0, 2.0],
        }
    )
    out = add_rolling_activity_features(frame, window="2s")
    assert np.isclose(out.loc[0, "trade_imbalance_2s"], 1.0)
    assert np.isclose(out.loc[1, "trade_imbalance_2s"], -1.0 / 3.0)
    assert out.loc[2, "trade_intensity_2s"] == 3.0


def test_trade_activity_alignment_excludes_future_and_left_window_boundary():
    decisions = pd.DataFrame(
        {
            "local_ts": pd.date_range("2026-01-01", periods=3, freq="1s", tz="UTC"),
            "symbol": ["BTC-USD"] * 3,
        }
    )
    trades = pd.DataFrame(
        {
            "local_ts": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:01Z",
                    "2026-01-01T00:00:03Z",
                ]
            ),
            "symbol": ["BTC-USD"] * 3,
            "side": ["buy", "sell", "buy"],
            "size": [1.0, 3.0, 10.0],
        }
    )

    out = add_causal_trade_activity_features(decisions, trades, window="2s")

    assert np.isclose(out.loc[1, "trade_imbalance_2s"], -0.5)
    assert out.loc[1, "trade_intensity_2s"] == 2.0
    assert out.loc[2, "trade_imbalance_2s"] == -1.0
    assert out.loc[2, "trade_intensity_2s"] == 1.0
