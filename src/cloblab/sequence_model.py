"""First-round sequence model; one fixed 32-state unidirectional GRU."""
from __future__ import annotations

import torch
from torch import nn


class GRURegressor(nn.Module):
    def __init__(self, input_size: int = 5, hidden_size: int = 64):
        super().__init__()
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden_size,
                          num_layers=1, batch_first=True, bidirectional=False)
        self.readout = nn.Linear(hidden_size, 1)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        if states.ndim != 3 or states.size(-1) != self.gru.input_size:
            raise ValueError("expected (batch, context, features)")
        # No hidden state is passed between endpoints: every prediction sees
        # exactly the provided causal window.
        output, _ = self.gru(states)
        return self.readout(output[:, -1]).squeeze(-1)
