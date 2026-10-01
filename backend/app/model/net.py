"""Logit-based losses and probability-facing multitask models."""
import torch
from torch import nn
from torch.nn import functional as F

HEADS = dict(anchor=1, sem=6, situation=1, signal=5, reason=4)
BINARY = ('anchor', 'sem', 'situation')


class MultiHeadMLP(nn.Module):
    def __init__(self, linear=False):
        super().__init__()
        self.body = nn.Identity() if linear else nn.Sequential(
            nn.LayerNorm(1032), nn.Linear(1032, 512), nn.GELU(), nn.Dropout(.2),
            nn.Linear(512, 256), nn.GELU(), nn.Dropout(.2))
        self.heads = nn.ModuleDict({k: nn.Linear(1032 if linear else 256, n) for k, n in HEADS.items()})

    def forward(self, x):
        """Return logits for stable BCE/CE; probabilities applies activations."""
        hidden = self.body(x)
        return {k: head(hidden) for k, head in self.heads.items()}

    def probabilities(self, x):
        return probabilities(self(x))


def probabilities(logits):
    return {k: v.sigmoid() if k in BINARY else v.softmax(-1) for k, v in logits.items()}


def masked_loss(out, targets, masks, weights, pos_weight):
    total = next(iter(out.values())).sum() * 0
    for name, logits in out.items():
        mask = masks[name].bool()
        if not mask.any():
            continue
        y, z, w = targets[name][mask], logits[mask], weights[mask]
        loss = (F.binary_cross_entropy_with_logits(z, y, reduction='none',
                pos_weight=pos_weight.get(name)).mean(-1) if name in BINARY
                else -(y * F.log_softmax(z, dim=-1)).sum(-1))
        total = total + (loss * w).sum() / w.sum().clamp_min(1)
    return total
