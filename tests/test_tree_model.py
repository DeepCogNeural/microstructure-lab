import numpy as np
import pandas as pd

from cloblab.models import TreeModelConfig, fit_predict_tree


def test_tree_model_returns_finite_predictions():
    x = np.linspace(-2.0, 2.0, 200)
    train = pd.DataFrame({"x": x, "y": x**2 + 0.1 * x})
    test = pd.DataFrame({"x": [-1.5, 0.0, 1.5]})
    pred = fit_predict_tree(
        train,
        test,
        feature_cols=["x"],
        label_col="y",
        config=TreeModelConfig(min_samples_leaf=5, n_estimators=50),
    )
    assert pred.shape == (3,)
    assert np.isfinite(pred).all()
