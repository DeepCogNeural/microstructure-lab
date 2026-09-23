import torch

from cloblab.sequence_model import GRURegressor


def test_gru_tiny_batch_updates_overfits_and_restores(tmp_path):
    torch.set_num_threads(1)
    torch.manual_seed(7)
    x = torch.randn(12, 32, 5)
    y = 0.7*x[:, -1, 0] - 0.4*x[:, -1, 1]
    model = GRURegressor()
    before_weight = model.readout.weight.detach().clone()
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    first = None
    for _ in range(150):
        opt.zero_grad()
        loss = ((model(x)-y)**2).mean()
        if first is None:
            first = loss.item()
        loss.backward()
        opt.step()
    final = ((model(x)-y)**2).mean().item()
    assert final < first/20, (first, final)
    assert not torch.equal(before_weight, model.readout.weight)
    saved = tmp_path / "gru.pt"
    torch.save(model.state_dict(), saved)
    restored = GRURegressor()
    restored.load_state_dict(torch.load(saved, weights_only=True))
    model.eval()
    restored.eval()
    with torch.no_grad():
        assert torch.equal(model(x), restored(x))


def test_no_state_carries_between_predictions():
    torch.manual_seed(17)
    model = GRURegressor().eval()
    x = torch.randn(2, 32, 5)
    with torch.no_grad():
        separate = torch.stack([model(x[i:i+1])[0] for i in range(2)])
        together = model(x)
    assert torch.equal(separate, together)
