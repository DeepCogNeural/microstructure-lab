from __future__ import annotations

import pandas as pd


def walk_forward_splits(
    data: pd.DataFrame,
    *,
    time_col: str = "local_ts",
    min_train_size: int,
    test_size: int,
    n_splits: int,
    embargo: str | pd.Timedelta = "0s",
) -> list[tuple[list[int], list[int]]]:
    """Return anchored walk-forward splits using only past rows for training."""

    if min_train_size <= 0 or test_size <= 0 or n_splits <= 0:
        raise ValueError("min_train_size, test_size, and n_splits must be positive")
    if time_col not in data.columns:
        raise ValueError(f"missing time column: {time_col}")

    ordered = data.copy()
    ordered[time_col] = pd.to_datetime(ordered[time_col], utc=True)
    ordered = ordered.sort_values(time_col)
    ordered_indices = list(ordered.index)
    embargo_delta = pd.Timedelta(embargo)

    splits: list[tuple[list[int], list[int]]] = []
    for split_number in range(n_splits):
        train_end = min_train_size + split_number * test_size
        if train_end >= len(ordered_indices):
            break
        train_idx = ordered_indices[:train_end]
        train_max_ts = ordered.loc[train_idx, time_col].max()
        test_candidates = ordered.loc[ordered_indices[train_end:]]
        if embargo_delta > pd.Timedelta(0):
            test_candidates = test_candidates[test_candidates[time_col] > train_max_ts + embargo_delta]
        test_idx = list(test_candidates.index[:test_size])
        if len(test_idx) < test_size:
            break
        splits.append((train_idx, test_idx))
    return splits

