import numpy as np
import pandas as pd
import pytest

from cloblab.sequence_ml import FEATURES, index_day, scoring_endpoints, window


def make_day(n=80):
    f = pd.DataFrame({"symbol": ["X"]*n, "day": ["2017-01-02"]*n,
                      "segment": [0]*n, "event_index": np.arange(n),
                      "timestamp_ns": np.arange(n)*1000,
                      "markout_20": np.arange(n, dtype=float)})
    for j, name in enumerate(FEATURES):
        f[name] = np.arange(n, dtype=float)+j
    return f


def test_future_label_filter_does_not_change_history():
    f = make_day()
    a = index_day(f)
    assert a.counts["valid_windows"] == 49
    assert a.counts["scorable"] == 49
    original = window(f, 50)
    f.loc[:49, "markout_20"] = np.nan
    b = index_day(f)
    assert np.array_equal(a.endpoints, b.endpoints)
    assert np.array_equal(original, window(f, 50))
    assert b.counts["scorable"] == 30


def test_future_state_perturbation_cannot_change_past_window():
    f = make_day()
    before = window(f, 50)
    f.loc[51:, FEATURES[0]] = 99999
    assert np.array_equal(before, window(f, 50))
    assert 50 in index_day(f).endpoints


def test_event_gap_and_nonfinite_state_break_windows():
    f = make_day()
    f.loc[40:, "event_index"] += 1
    f.loc[55, FEATURES[1]] = np.nan
    idx = index_day(f)
    assert 40 not in idx.endpoints
    assert 55 not in idx.endpoints
    assert 79 not in idx.endpoints
    assert 39 in idx.endpoints


def test_score_on_original_event_index_stride():
    f = make_day()
    f.loc[:, "event_index"] += 101
    idx = index_day(f)
    selected = scoring_endpoints(f, idx, stride=20)
    assert f.event_index.iloc[selected].tolist() == [140, 160, 180]


def test_reject_reordered_event_identity():
    f = make_day()
    f.loc[41, "event_index"] = 40
    with pytest.raises(ValueError, match="duplicate event identity"):
        index_day(f)


def test_model_serialization_round_trip(tmp_path):
    # The Q1 pilot uses this cheap model to check the save/restore contract.
    from sklearn.linear_model import Ridge
    import joblib

    x = np.arange(50, dtype=float).reshape(10, 5)
    y = np.arange(10, dtype=float)
    model = Ridge(alpha=1.0).fit(x, y)
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    assert np.array_equal(model.predict(x), joblib.load(path).predict(x))
