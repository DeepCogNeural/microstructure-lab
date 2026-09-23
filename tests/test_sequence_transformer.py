import torch
import pytest

from cloblab.sequence_transformer import CausalWindowTransformer


def test_window_shape_batch_isolation_and_gradients():
    torch.manual_seed(7)
    model = CausalWindowTransformer(dropout=0.0)
    model.eval()
    x = torch.randn(3, 32, 5)
    assert model(x).shape == (3,)
    torch.testing.assert_close(model(x)[:1], model(x[:1]), atol=1e-6, rtol=1e-6)
    with pytest.raises(ValueError):
        model(torch.randn(3, 33, 5))
    model.train()
    model(x).square().mean().backward()
    assert model.input_projection.weight.grad is not None
    assert model.input_projection.weight.grad.abs().sum() > 0


def test_strict_causal_attention_mask():
    model = CausalWindowTransformer(context=4, dropout=0.0)
    expected = torch.tensor([[0, 1, 1, 1], [0, 0, 1, 1],
                             [0, 0, 0, 1], [0, 0, 0, 0]], dtype=torch.bool)
    torch.testing.assert_close(model.causal_mask, expected)
