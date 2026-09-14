from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TreeModelConfig:
    max_depth: int = 3
    min_samples_leaf: int = 25
    n_estimators: int = 200
    learning_rate: float = 0.03
    random_state: int = 0


def fit_predict_tree(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    feature_cols: list[str],
    label_col: str,
    config: TreeModelConfig | None = None,
) -> np.ndarray:
    """Fit a small gradient-boosted tree regressor for markout prediction.

    The import is intentionally local so the core replay/data package remains
    usable without the optional ML dependency.
    """

    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "tree baseline requires scikit-learn; install with `pip install -e '.[ml]'`"
        ) from exc

    cfg = config or TreeModelConfig()
    model = HistGradientBoostingRegressor(
        max_depth=cfg.max_depth,
        min_samples_leaf=cfg.min_samples_leaf,
        max_iter=cfg.n_estimators,
        learning_rate=cfg.learning_rate,
        random_state=cfg.random_state,
    )
    model.fit(train[feature_cols].astype(float), train[label_col].astype(float))
    return model.predict(test[feature_cols].astype(float))
