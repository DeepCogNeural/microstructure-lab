from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from cloblab.splits import walk_forward_splits


def run_baseline(
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
) -> dict[str, Any]:
    """Run a simple linear walk-forward baseline plus shuffled-label control.

    If `label_time_col` is available, training rows whose future label endpoint
    reaches the test window are purged from each fold.
    """

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
    if not splits:
        raise ValueError("walk-forward split produced no folds")

    rng = np.random.default_rng(random_seed)
    predictions: list[float] = []
    actuals: list[float] = []
    control_predictions: list[float] = []
    folds: list[dict[str, Any]] = []

    for train_idx, test_idx in splits:
        train = frame.loc[train_idx]
        test = frame.loc[test_idx]
        train_n_before_label_purge = len(train)
        max_train_label_ts_before = None
        if label_time_col is not None:
            test_start_ts = test[time_col].min()
            max_train_label_ts_before = train[label_time_col].max()
            train = train[train[label_time_col] < test_start_ts]
        if len(train) < max(2, len(feature_cols) + 1):
            continue

        pred = _fit_predict_linear(train, test, feature_cols, label_col)
        shuffled = train.copy()
        shuffled[label_col] = rng.permutation(shuffled[label_col].to_numpy())
        control_pred = _fit_predict_linear(shuffled, test, feature_cols, label_col)
        predictions.extend(pred.tolist())
        control_predictions.extend(control_pred.tolist())
        actuals.extend(test[label_col].astype(float).tolist())
        folds.append(
            {
                "train_n_before_label_purge": int(train_n_before_label_purge),
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

    metrics = _score_predictions(predictions, actuals, cost_bps)
    control_metrics = _score_predictions(control_predictions, actuals, cost_bps)
    buckets = _bucket_average_markout(predictions, actuals)
    return {
        "metrics": metrics,
        "negative_control": control_metrics,
        "buckets": buckets,
        "feature_cols": feature_cols,
        "label_col": label_col,
        "label_time_col": label_time_col,
        "cost_bps": cost_bps,
        "folds": folds,
    }


def _infer_label_time_col(label_col: str) -> str | None:
    match = re.match(r"^markout(?:_bps)?_(\d+)s$", label_col)
    if not match:
        return None
    return f"future_ts_{match.group(1)}s"


def _fit_predict_linear(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
) -> np.ndarray:
    x_train = train[feature_cols].astype(float).to_numpy()
    y_train = train[label_col].astype(float).to_numpy()
    x_test = test[feature_cols].astype(float).to_numpy()

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std[std == 0] = 1.0
    x_train_scaled = (x_train - mean) / std
    x_test_scaled = (x_test - mean) / std

    y_mean = y_train.mean()
    y_centered = y_train - y_mean
    ridge = 1e-6 * np.eye(x_train_scaled.shape[1])
    coef = np.linalg.solve(x_train_scaled.T @ x_train_scaled + ridge, x_train_scaled.T @ y_centered)
    return x_test_scaled @ coef + y_mean


def _score_predictions(predictions: list[float], actuals: list[float], cost_bps: float) -> dict[str, float | int]:
    pred = np.asarray(predictions, dtype=float)
    actual = np.asarray(actuals, dtype=float)
    valid = np.isfinite(pred) & np.isfinite(actual)
    pred = pred[valid]
    actual = actual[valid]
    if len(actual) == 0:
        return {"n_test": 0, "ic": math.nan, "direction_accuracy": math.nan, "cost_coverage": math.nan}

    ic = _spearman_corr(pred, actual)
    nonzero = actual != 0
    direction_accuracy = float((np.sign(pred[nonzero]) == np.sign(actual[nonzero])).mean()) if nonzero.any() else math.nan
    selected = np.abs(pred) > cost_bps
    signed_after_cost = np.sign(pred[selected]) * actual[selected] - cost_bps if selected.any() else np.array([])
    return {
        "n_test": int(len(actual)),
        "ic": float(ic) if pd.notna(ic) else math.nan,
        "direction_accuracy": direction_accuracy,
        "cost_coverage": float(selected.mean()),
        "mean_abs_markout_bps": float(np.mean(np.abs(actual))),
        "mean_signed_markout_after_cost_bps": float(signed_after_cost.mean()) if len(signed_after_cost) else math.nan,
    }


def _spearman_corr(pred: np.ndarray, actual: np.ndarray) -> float:
    pred_rank = pd.Series(pred).rank(method="average")
    actual_rank = pd.Series(actual).rank(method="average")
    if pred_rank.nunique() < 2 or actual_rank.nunique() < 2:
        return math.nan
    corr = pred_rank.corr(actual_rank, method="pearson")
    return float(corr) if pd.notna(corr) else math.nan


def _bucket_average_markout(predictions: list[float], actuals: list[float], bins: int = 5) -> list[dict[str, float | int | str]]:
    frame = pd.DataFrame({"prediction": predictions, "markout_bps": actuals}).dropna()
    if frame.empty or frame["prediction"].nunique() < 2:
        return []
    labels = pd.qcut(frame["prediction"], q=min(bins, frame["prediction"].nunique()), duplicates="drop")
    grouped = frame.groupby(labels, observed=True)
    return [
        {
            "prediction_bucket": str(bucket),
            "count": int(len(group)),
            "avg_prediction_bps": float(group["prediction"].mean()),
            "avg_markout_bps": float(group["markout_bps"].mean()),
        }
        for bucket, group in grouped
    ]
