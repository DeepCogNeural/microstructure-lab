"""Frozen leave-one-stock-out chronological folds for the optional transfer study."""
from pathlib import Path
import numpy as np
import pandas as pd


def load_transfer_fold(cache, manifest, held_out, month, features, horizon=20, seed=None):
    train, test = [], []
    columns = ["symbol", "day", "event_index", "timestamp_ns"] + features + [f"markout_{horizon}"]
    for part in manifest["partitions"]:
        is_train = part["symbol"] != held_out and part["day"][:7] < month
        is_test = part["symbol"] == held_out and part["day"][:7] == month
        if not (is_train or is_test):
            continue
        path = Path(cache)/f"symbol={part['symbol']}"/f"day={part['day']}"/"features.parquet"
        frame = pd.read_parquet(path, columns=columns)
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=features+[f"markout_{horizon}"])
        (train if is_train else test).append(frame)
    if not train or not test:
        raise ValueError("empty transfer fold")
    training, testing = pd.concat(train, ignore_index=True), pd.concat(test, ignore_index=True)
    if training.empty or testing.empty or held_out in set(training.symbol) or training.day.max() >= testing.day.min():
        raise ValueError("noncausal or non-held-out transfer fold")
    if seed is not None:
        rng = np.random.default_rng(seed)
        label = f"markout_{horizon}"
        for _, positions in training.groupby(["symbol", "day"], sort=True).indices.items():
            training.loc[positions, label] = rng.permutation(training.loc[positions, label].to_numpy())
    return training, testing
