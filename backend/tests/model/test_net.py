import torch
import pytest


def setup_module():
    torch.manual_seed(12)
    torch.set_num_threads(2)


@pytest.mark.parametrize('linear', [False, True])
def test_forward_shapes(linear):
    from app.model.net import MultiHeadMLP
    model = MultiHeadMLP(linear=linear)
    out = model(torch.randn(7, 1032))
    assert {k: tuple(v.shape) for k, v in out.items()} == {
        'anchor': (7, 1), 'sem': (7, 6), 'situation': (7, 1),
        'signal': (7, 5), 'reason': (7, 4)}
    probs = model.probabilities(torch.randn(7, 1032))
    assert all(((p >= 0) & (p <= 1)).all() for p in probs.values())
    assert torch.allclose(probs['signal'].sum(1), torch.ones(7))
    assert torch.allclose(probs['reason'].sum(1), torch.ones(7))


def test_mask_zero_grad():
    from app.model.net import MultiHeadMLP, masked_loss
    model = MultiHeadMLP().eval()
    x = torch.randn(4, 1032)
    target = {k: torch.zeros_like(v) for k, v in model(x).items()}
    masks = {k: torch.ones(4, dtype=torch.bool) for k in target}
    masks['sem'][0] = False
    grads = []
    for value in (0., 1.):
        model.zero_grad()
        target['sem'][0] = value
        masked_loss(model(x), target, masks, torch.ones(4), {}).backward()
        grads.append(torch.cat([p.grad.flatten() for p in model.parameters()]))
    assert torch.equal(*grads)
