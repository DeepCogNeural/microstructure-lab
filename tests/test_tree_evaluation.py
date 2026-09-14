import numpy as np
import pandas as pd

from cloblab.models import TreeModelConfig
from cloblab.tree_evaluation import run_tree_baseline


def test_tree_evaluation_runs_with_label_time_purge():
    n = 240
    ts = pd.date_range("2026-01-01", periods=n, freq="1s", tz="UTC")
    x = np.linspace(-2.0, 2.0, n)
    frame = pd.DataFrame(
        {
            "local_ts": ts,
            "future_ts_5s": ts + pd.Timedelta(seconds=5),
            "x": x,
            "markout_bps_5s": x**2 - 0.5,
        }
    )
    out = run_tree_baseline(
        frame,
        feature_cols=["x"],
        label_col="markout_bps_5s",
        min_train_size=120,
        test_size=30,
        n_splits=2,
        config=TreeModelConfig(min_samples_leaf=5, n_estimators=30),
    )
    assert out["model"] == "hist_gradient_boosting"
    assert out["metrics"]["n_test"] > 0
    assert out["folds"][0]["train_n_after_label_purge"] < out["folds"][0]["train_n_before_label_purge"]
