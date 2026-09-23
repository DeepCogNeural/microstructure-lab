import hashlib
import numpy as np
import pytest

from run_polymarket_pm1b_dev import arrays, market_mse


def test_market_equal_mse_differs_from_row_mean():
    target = np.zeros(4)
    pred = np.array([1., 1., 1., 0.])
    market = np.array(["btc-updown-5m-1"]*3+["eth-updown-15m-2"])
    decision = np.array(["2026-08-21T00:00:00+00:00"]*4)
    score = market_mse(target, pred, market, decision)
    assert score["market_mean_mse"] == pytest.approx(.5)
    assert score["row_mean_mse_descriptive"] == pytest.approx(.75)
    assert score["markets"] == 2


def test_future_capture_must_be_strictly_after_decision(tmp_path):
    path = tmp_path/"target.npz"
    payload = dict(repricing=np.array([0.1], dtype=np.float32),
                   probability=np.array([0.5], dtype=np.float32),
                   history=np.zeros((1, 8, 11), dtype=np.float32),
                   market=np.array(["btc-updown-5m-1"]),
                   decision_utc=np.array(["2026-08-21T00:00:00+00:00"]),
                   future_capture_utc=np.array(["2026-08-21T00:00:00+00:00"]))
    np.savez_compressed(path, **payload)
    expected = {"private_target_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "eligible_opportunities": 1, "eligible_markets": 1}
    with pytest.raises(ValueError, match="future capture"):
        arrays(path, expected)
