"""Temperature scaling of logits derived from ensemble mean probabilities."""
import torch
from torch.nn import functional as F


def fit_temperature(logits, y) -> float:
    logits = torch.as_tensor(logits, dtype=torch.float32).detach()
    y = torch.as_tensor(y, dtype=torch.float32).detach()
    if logits.numel() == 0:
        return 1.
    # Binary/multilabel targets have independent outputs. Categorical targets
    # are integer class IDs, disambiguating the six-label semantic head.
    categorical = y.ndim == logits.ndim - 1
    log_t = torch.zeros((), requires_grad=True)
    optimizer = torch.optim.LBFGS([log_t], lr=.5, max_iter=40, line_search_fn='strong_wolfe')
    def objective():
        z = logits / log_t.clamp(-5, 5).exp()
        return F.cross_entropy(z, y.long()) if categorical else F.binary_cross_entropy_with_logits(z, y)
    baseline = float(objective().detach())
    def closure():
        optimizer.zero_grad()
        loss = objective()
        loss.backward()
        return loss
    optimizer.step(closure)
    return float(log_t.detach().clamp(-5, 5).exp()) if float(objective().detach()) <= baseline else 1.


def ece(probabilities, y, bins=15):
    p = torch.as_tensor(probabilities).detach()
    y = torch.as_tensor(y)
    if y.ndim == p.ndim - 1:
        confidence, pred = p.max(-1)
        correct = (pred == y).float()
    else:
        confidence = torch.maximum(p, 1 - p).flatten()
        correct = ((p >= .5) == (y >= .5)).float().flatten()
    if not confidence.numel():
        return None
    value = 0.
    for i in range(bins):
        mask = (confidence >= i / bins) & (confidence <= 1 if i == bins - 1 else confidence < (i + 1) / bins)
        if mask.any():
            value += float(mask.float().mean() * (confidence[mask].mean() - correct[mask].mean()).abs())
    return value
