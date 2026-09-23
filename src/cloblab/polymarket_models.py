"""Market-equal scoring and same-information PM1A history classifier."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import torch
from torch import nn


class HistoryGRU(nn.Module):
    def __init__(self, input_size: int, hidden_size: int):
        super().__init__()
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, state = self.gru(x)
        return self.head(state[-1]).squeeze(-1)


def market_equal_weights(market: np.ndarray) -> np.ndarray:
    names, inverse, counts = np.unique(market, return_inverse=True, return_counts=True)
    if len(names) == 0:
        raise ValueError('empty market set')
    weights = 1.0 / counts[inverse]
    return weights * (len(weights) / weights.sum())


def market_scores(label: np.ndarray, prediction: np.ndarray,
                  market: np.ndarray, clip: float) -> dict:
    if len(label) != len(prediction) or len(label) != len(market):
        raise ValueError('score identity length mismatch')
    if not np.isfinite(prediction).all():
        raise ValueError('nonfinite probabilities')
    pred = np.clip(prediction.astype(float), clip, 1 - clip)
    loss = -(label * np.log(pred) + (1 - label) * np.log1p(-pred))
    brier = (pred - label) ** 2
    by_market = defaultdict(list)
    for i, name in enumerate(market):
        by_market[str(name)].append(i)
    if any(np.unique(label[indices]).size != 1 for indices in by_market.values()):
        raise ValueError('terminal labels differ within market')
    market_loss = {key:float(loss[idx].mean()) for key,idx in by_market.items()}
    market_brier = {key:float(brier[idx].mean()) for key,idx in by_market.items()}
    return {'market_mean_log_loss':float(np.mean(list(market_loss.values()))),
            'market_mean_brier':float(np.mean(list(market_brier.values()))),
            'markets':len(by_market), 'opportunities':len(label),
            '_market_log_loss':market_loss, '_market_brier':market_brier}


def market_paired_bootstrap(first: dict, second: dict, *, seed: int,
                            draws: int = 5000) -> dict:
    """Second minus first over the same markets; negative is improvement."""
    ids = sorted(first)
    if ids != sorted(second):
        raise ValueError('paired market identities differ')
    delta = np.asarray([second[key] - first[key] for key in ids])
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for draw in range(draws):
        means[draw] = delta[rng.integers(0, len(delta), len(delta))].mean()
    return {'market_mean_delta':float(delta.mean()),
            'market_bootstrap_ci95':[float(x) for x in np.quantile(means,[.025,.975])],
            'paired_markets':len(ids),
            'positive_market_differences':int((delta > 0).sum()),
            'negative_market_differences':int((delta < 0).sum()),
            'zero_market_differences':int((delta == 0).sum())}
