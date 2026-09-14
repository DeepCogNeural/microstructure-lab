from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cloblab.evaluation import _bucket_average_markout, _infer_label_time_col, _score_predictions
from cloblab.models import TreeModelConfig, fit_predict_tree
from cloblab.splits import walk_forward_splits


def run_tree_baseline(
    data: pd.DataFrame,
    *,
    feature_cols: list[str],
    label_col: str,
    time_col: str = "local_ts",
    min_train_size: int = 100,
    test_size: int = 50,
    n_splits: int = 3,
    cost_bps: float = 1.0,
    random_seed: int = 0,
    label_time_col: str | None = None,
    config: TreeModelConfig | None = None,
) -> dict[str, Any]:
    """Leakage-controlled walk-forward tree baseline plus shuffled-label control."""

    label_time_col = label_time_col or _infer_label_time_col(label_col)
    required = set(feature_cols + [label_col, time_col])
    if label_time_col is not None:
        required.add(label_time_col)
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    frame = data.copy()
    frame[time_col] = pd.to_datetime(frame[time_col], utc=True)
    dropna_cols = feature_cols + [label_col]
    if label_time_col is not None:
        frame[label_time_col] = pd.to_datetime(frame[label_time_col], utc=True)
        dropna_cols.append(label_time_col)
    frame = frame.dropna(subset=dropna_cols).sort_values(time_col)
    if len(frame) < min_train_size + test_size:
        raise ValueError("not enough rows for the requested walk-forward split")

    splits = walk_forward_splits(
        frame,
        time_col=time_col,
        min_train_size=min_train_size,
        test_size=test_size,
        n_splits=n_splits,
    )
    rng = np.random.default_rng(random_seed)
    predictions: list[float] = []
    control_predictions: list[float] = []
    actuals: list[float] = []
    prediction_rows: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []

    for fold_number, (train_idx, test_idx) in enumerate(splits, start=1):
        train = frame.loc[train_idx]
        test = frame.loc[test_idx]
        before = len(train)
        max_train_label_ts_before = None
        if label_time_col is not None:
            test_start = test[time_col].min()
            max_train_label_ts_before = train[label_time_col].max()
            train = train[train[label_time_col] < test_start]
        if len(train) < max(2, len(feature_cols) + 1):
            continue

        pred = fit_predict_tree(
            train,
            test,
            feature_cols=feature_cols,
            label_col=label_col,
            config=config,
        )
        shuffled = train.copy()
        shuffled[label_col] = rng.permutation(shuffled[label_col].to_numpy())
        control = fit_predict_tree(
            shuffled,
            test,
            feature_cols=feature_cols,
            label_col=label_col,
            config=config,
        )
        predictions.extend(pred.tolist())
        control_predictions.extend(control.tolist())
        actuals.extend(test[label_col].astype(float).tolist())
        for timestamp, prediction, control_prediction, actual in zip(
            test[time_col],
            pred,
            control,
            test[label_col].astype(float),
            strict=True,
        ):
            prediction_rows.append(
                {
                    "fold": fold_number,
                    "local_ts": timestamp.isoformat(),
                    "prediction_bps": float(prediction),
                    "control_prediction_bps": float(control_prediction),
                    "realized_markout_bps": float(actual),
                }
            )
        folds.append(
            {
                "train_n_before_label_purge": int(before),
                "train_n_after_label_purge": int(len(train)),
                "test_n": int(len(test)),
                "test_start_ts": test[time_col].min().isoformat(),
                "test_end_ts": test[time_col].max().isoformat(),
                "max_train_feature_ts": train[time_col].max().isoformat(),
                "max_train_label_ts": train[label_time_col].max().isoformat()
                if label_time_col is not None
                else None,
                "max_train_label_ts_before_purge": max_train_label_ts_before.isoformat()
                if max_train_label_ts_before is not None
                else None,
                "label_time_col": label_time_col,
            }
        )

    if not predictions:
        raise ValueError("no folds had enough label-purged training rows")

    return {
        "model": "hist_gradient_boosting",
        "metrics": _score_predictions(predictions, actuals, cost_bps),
        "negative_control": _score_predictions(control_predictions, actuals, cost_bps),
        "buckets": _bucket_average_markout(predictions, actuals),
        "feature_cols": feature_cols,
        "label_col": label_col,
        "label_time_col": label_time_col,
        "cost_bps": cost_bps,
        "folds": folds,
        "predictions": prediction_rows,
    }
