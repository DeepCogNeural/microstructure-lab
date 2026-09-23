"""Small causal-window Transformer for the conditional formal FQ4 study."""
from __future__ import annotations

import torch
from torch import nn


class CausalWindowTransformer(nn.Module):
    def __init__(self, input_size: int = 5, context: int = 32,
                 width: int = 64, heads: int = 4, layers: int = 2,
                 feedforward: int = 128, dropout: float = 0.1):
        super().__init__()
        if width % heads or context < 1:
            raise ValueError("invalid width, heads, or context")
        self.input_size = input_size
        self.context = context
        self.input_projection = nn.Linear(input_size, width)
        self.position = nn.Embedding(context, width)
        block = nn.TransformerEncoderLayer(d_model=width, nhead=heads,
                                           dim_feedforward=feedforward,
                                           dropout=dropout, activation="gelu",
                                           batch_first=True, norm_first=False)
        self.encoder = nn.TransformerEncoder(block, num_layers=layers,
                                             enable_nested_tensor=False)
        self.readout = nn.Linear(width, 1)
        self.register_buffer("causal_mask", torch.triu(torch.ones(context, context,
                                                                    dtype=torch.bool), diagonal=1),
                             persistent=False)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        if states.ndim != 3 or states.size(1) != self.context or states.size(2) != self.input_size:
            raise ValueError("expected (batch, frozen context, causal features)")
        positions = torch.arange(self.context, device=states.device)
        x = self.input_projection(states) + self.position(positions)[None]
        x = self.encoder(x, mask=self.causal_mask)
        return self.readout(x[:, -1]).squeeze(-1)
