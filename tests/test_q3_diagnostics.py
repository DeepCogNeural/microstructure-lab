import numpy as np
import pandas as pd

from cloblab.execution_labels import crossed_labels
from cloblab.q3_diagnostics import crossed_from_features, future_positions


def test_feature_identity_matches_visible_quotes():
    n = 60
    event = np.arange(n)
    bid = 100+event*0.01
    ask = bid+0.02+event*0.0001
    frame = pd.DataFrame({"symbol": ["X"]*n, "day": ["2017-01-02"]*n,
                          "segment": [0]*n, "event_index": event,
                          "timestamp_ns": event*1000,
                          "bid_px_1": bid, "ask_px_1": ask})
    mid = (bid+ask)/2
    spread = 10000*(ask-bid)/mid
    labels = crossed_labels(frame, 20, 0)
    endpoints = np.arange(n-20)
    markout = 10000*(mid[endpoints+20]/mid[endpoints]-1)
    for side, expected in ((1, labels.long_crossed_bps.iloc[endpoints]),
                           (-1, labels.short_crossed_bps.iloc[endpoints])):
        actual = crossed_from_features(markout, spread[endpoints], spread[endpoints+20], side)
        assert np.allclose(actual, expected.to_numpy(), atol=1e-9)


def test_future_match_requires_original_event_and_segment():
    event = np.arange(50)
    segment = np.zeros(50, dtype=int)
    segment[30:] = 1
    future, valid = future_positions(event, segment, [0, 15, 29], horizon=20)
    assert future.tolist() == [20, 35, 49]
    assert valid.tolist() == [True, False, False]
    event[20:] += 1
    _, valid = future_positions(event, segment, [0], horizon=20)
    assert valid.tolist() == [False]
