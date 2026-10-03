"""Deterministic CPU ensemble training; no label, vector, or network writes."""
from dataclasses import dataclass
import json

import numpy as np
import torch

from app.config import settings
from app.label import rule
from app.model.calibrate import ece, fit_temperature
from app.model.features import CHANNELS
from app.model.net import BINARY, HEADS, MultiHeadMLP, masked_loss, probabilities

SIGNALS = ('pain', 'unmet', 'workaround', 'delight', 'none')
REASONS = ('ad', 'no_needs', 'pure_criticism', 'other')


@dataclass
class Targets:
    values: dict
    hard: dict
    masks: dict
    weights: torch.Tensor
    doc_ids: np.ndarray
    grades: np.ndarray
    channels: np.ndarray

    def take(self, indices):
        return Targets(*[{k: v[indices] for k, v in d.items()} for d in
                         (self.values, self.hard, self.masks)], self.weights[indices],
                       self.doc_ids[indices], self.grades[indices], self.channels[indices])


def build_targets(final_rows, jev_cache=None) -> Targets:
    """Use accepted automatic rows or human rows, retaining IDs for alignment.

    Both votes come from the final row's durable snapshot, independent of the
    current cache identity. The optional cache argument is ignored for callers
    using the previous API. Missing categorical labels are masked.
    """
    rows = [dict(r) for r in final_rows]
    rows = [r for r in rows if r['source'] == 'human' or
            (r['source'] in ('agreed', 'gpt_only') and r.get('route') == 'accepted')]
    values = {k: torch.zeros(len(rows), n) for k, n in HEADS.items()}
    hard = {k: v.clone() for k, v in values.items()}
    masks = {k: torch.zeros(len(rows), dtype=torch.bool) for k in HEADS}
    weights, grades = [], []
    for i, row in enumerate(rows):
        tags = json.loads(row['tags_json'])
        binary = dict(anchor=int(tags['anchor']), **tags['sem'], situation=int(tags['situation']))
        level = rule.grade(binary)
        grades.append(level)
        human = row['source'] == 'human'
        weights.append(3. if human else 1.)
        vote = {} if human else json.loads(row['votes_json'])['jev']
        if hasattr(vote, 'model_dump'):
            vote = vote.model_dump()
        gpt = tags if human else json.loads(row['votes_json'])['gpt']
        gpt_binary = dict(anchor=int(gpt['anchor']), **gpt['sem'], situation=int(gpt['situation']))
        for head, fields in [('anchor', ('anchor',)), ('sem', rule.SEM), ('situation', ('situation',))]:
            hard[head][i] = torch.tensor([binary[k] for k in fields])
            values[head][i] = hard[head][i] if human else torch.tensor([
                (vote['probs'][k] + gpt_binary[k]) / 2 if vote else gpt_binary[k]
                for k in fields])
            masks[head][i] = head == 'anchor' or bool(tags['anchor'])
        for head, classes, field, eligible in [('signal', SIGNALS, 'signal', level != 'non'),
                                               ('reason', REASONS, 'reason_code', level == 'non')]:
            label = row.get(field) if human else gpt.get(field)
            final_label = row.get(field)
            if final_label in classes:
                hard[head][i, classes.index(final_label)] = 1
            if eligible and label in classes and final_label in classes:
                values[head][i, classes.index(label)] = 1
                masks[head][i] = True
                if head == 'reason' and vote:
                    p = torch.tensor([vote.get('reason_probs', {}).get(k, 0.) for k in classes])
                    if p.sum() > 0:
                        values[head][i] = (values[head][i] + p / p.sum()) / 2
    return Targets(values, hard, masks, torch.tensor(weights),
                   np.array([r['doc_id'] for r in rows]), np.array(grades),
                   np.array([r.get('channel', 'unknown') for r in rows]))


def stratified_split(t, seed=42):
    """80/10/10 by grade × channel; largest remainders handle small strata."""
    rng = np.random.default_rng(seed)
    groups = {}
    for i, key in enumerate(zip(t.grades, t.channels)):
        groups.setdefault(key, []).append(i)
    groups = [rng.permutation(g) for _, g in sorted(groups.items())]
    result = {}
    total = len(t.doc_ids)
    for name, count in [('train', int(.8 * total)), ('validation', int(.1 * total))]:
        sizes = np.array([len(g) for g in groups])
        quotas = sizes * count / max(1, sizes.sum())
        allocation = np.floor(quotas).astype(int)
        for j in np.argsort(-(quotas - allocation), kind='stable')[:count - allocation.sum()]:
            allocation[j] += 1
        result[name] = np.concatenate([g[:n] for g, n in zip(groups, allocation)]).astype(int)
        groups = [g[n:] for g, n in zip(groups, allocation)]
    result['calibration'] = np.concatenate(groups).astype(int)
    return result


def _pos_weights(t):
    result = {}
    for k in BINARY:
        y = t.hard[k][t.masks[k]]
        positives = y.sum(0)
        result[k] = ((len(y) - positives) / positives.clamp_min(1)).clamp_min(1)
    return result


def train_member(X, T, seed=42, bootstrap=False, linear=False, *,
                 max_epochs=30, splits=None, enabled=None):
    """Return the best validation state_dict; bootstrap only the training fold."""
    if not 1 <= max_epochs <= 30:
        raise ValueError('max_epochs must be between 1 and 30')
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    X = torch.as_tensor(X, dtype=torch.float32)
    splits = stratified_split(T) if splits is None else splits
    base = splits['train']
    validation = splits['validation']
    if not len(base) or not len(validation):
        raise ValueError('Training and validation splits must be nonempty')
    train_t = T.take(base)
    enabled = {k: int(train_t.masks[k].sum()) >= settings.head_min_samples for k in HEADS} if enabled is None else enabled
    model = MultiHeadMLP(linear=linear)
    for k, active in enabled.items():
        if not active:
            for p in model.heads[k].parameters():
                p.data.zero_()
                p.requires_grad_(False)
    masked = {k: v & enabled[k] for k, v in T.masks.items()}
    pos_weight = _pos_weights(train_t)
    indices = rng.choice(base, len(base), replace=True) if bootstrap else base.copy()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    best, best_loss, stale = None, float('inf'), 0
    for _ in range(max_epochs):
        model.train()
        for batch in np.array_split(rng.permutation(indices), max(1, int(np.ceil(len(indices) / 256)))):
            optimizer.zero_grad()
            loss = masked_loss(model(X[batch]), {k: v[batch] for k, v in T.values.items()},
                               {k: v[batch] for k, v in masked.items()}, T.weights[batch], pos_weight)
            if loss.requires_grad:
                loss.backward()
                optimizer.step()
        model.eval()
        with torch.no_grad():
            loss = float(masked_loss(model(X[validation]), {k: v[validation] for k, v in T.values.items()},
                                    {k: v[validation] for k, v in masked.items()}, T.weights[validation], pos_weight))
        if loss < best_loss:
            best_loss, stale = loss, 0
            best = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale == 3:
                break
    return best


def _grade_predictions(probs):
    tags = torch.cat([probs['anchor'], probs['sem'], probs['situation']], -1).numpy()
    return np.array([max(p, key=p.get) for row in tags
                     if (p := rule.grade_probs(dict(zip(rule.GRADE_FIELDS, row))))])


def _logits(p, name):
    p = p.clamp(1e-6, 1 - 1e-6)
    return torch.logit(p) if name in BINARY else p.log()


@dataclass
class EnsembleResult:
    members: list
    metrics: dict
    perHead: dict
    temperatures: dict
    splits: dict
    doc_ids: np.ndarray

    def predict(self, X):
        x = torch.as_tensor(X, dtype=torch.float32)
        outputs = []
        with torch.no_grad():
            for i, state in enumerate(self.members):
                model = MultiHeadMLP(linear=i == 3).eval()
                model.load_state_dict(state)
                outputs.append(model.probabilities(x))
        stacked = {k: torch.stack([o[k] for o in outputs]) for k in HEADS}
        mean = {k: v.mean(0) for k, v in stacked.items()}
        calibrated = probabilities({k: _logits(v, k) / self.temperatures[k] for k, v in mean.items()})
        grades = _grade_predictions(calibrated)
        member_grades = np.stack([_grade_predictions(o) for o in outputs])
        return dict(probabilities=calibrated, mean=mean,
                    std={k: v.std(0, correction=0) for k, v in stacked.items()}, grades=grades,
                    grade_disagreement=(member_grades != grades).mean(0), members=outputs)


def _metrics(probs, t, enabled):
    result = {}
    for k, p in probs.items():
        mask = t.masks[k]
        y = t.hard[k][mask]
        p = p[mask]
        if not enabled[k] or not len(y):
            result[k] = dict(acc=None, f1=None, ece=None)
            continue
        if k in BINARY:
            pred, truth = p >= .5, y >= .5
            tp = (pred & truth).sum(0).float()
            denominator = pred.sum(0) + truth.sum(0)
            f1 = torch.where(denominator > 0, 2 * tp / denominator, 1.).mean()
            acc = (pred == truth).float().mean()
            error = ece(p, y)
        else:
            pred, truth = p.argmax(-1), y.argmax(-1)
            scores = []
            for c in range(HEADS[k]):
                denominator = (pred == c).sum() + (truth == c).sum()
                if denominator:
                    scores.append(2 * ((pred == c) & (truth == c)).sum() / denominator)
            f1 = torch.stack(scores).mean()
            acc = (pred == truth).float().mean()
            error = ece(p, truth)
        result[k] = dict(acc=float(acc), f1=float(f1), ece=error)
    return result


def train_ensemble(X, T, *, seed=42, max_epochs=30) -> EnsembleResult:
    """X must be aligned with T.doc_ids (after build_targets eligibility filtering).

    Split indices refer to returned doc_ids after zero-vector exclusion. Metrics
    use validation hard labels; temperatures use only calibration hard labels.
    """
    x = np.asarray(X, dtype=np.float32)
    if x.shape != (len(T.doc_ids), 1032) or not np.isfinite(x).all():
        raise ValueError('Expected finite 1032-column features aligned with Targets')
    keep = np.flatnonzero(np.any(x[:, :1024] != 0, axis=1))
    if len(keep) < 10:
        raise ValueError('At least 10 documents with nonzero embeddings are required')
    x, t = x[keep], T.take(keep)
    # LabelStore rows have no channel column; features carry the crawl channel.
    channels = t.channels.astype(object)
    for i in np.flatnonzero(channels == 'unknown'):
        one_hot = x[i, 1024:1029]
        if not np.isin(one_hot, [0, 1]).all() or one_hot.sum() != 1:
            raise ValueError('Channel metadata or a valid channel one-hot is required')
        channels[i] = CHANNELS[int(one_hot.argmax())]
    t.channels = channels
    splits = stratified_split(t, seed)
    counts = {k: int(t.masks[k][splits['train']].sum()) for k in HEADS}
    enabled = {k: n >= settings.head_min_samples for k, n in counts.items()}
    members = [train_member(x, t, seed + i, i < 3, i == 3, max_epochs=max_epochs,
                            splits=splits, enabled=enabled) for i in range(4)]
    result = EnsembleResult(members, {}, {}, dict.fromkeys(HEADS, 1.), splits, t.doc_ids)
    calibration = splits['calibration']
    ct = t.take(calibration)
    means = result.predict(x[calibration])['mean']
    for k in HEADS:
        mask = ct.masks[k]
        if enabled[k] and mask.any():
            y = ct.hard[k][mask]
            result.temperatures[k] = fit_temperature(_logits(means[k][mask], k),
                                                     y if k in BINARY else y.argmax(-1))
    validation = splits['validation']
    vt = t.take(validation)
    pred = result.predict(x[validation])
    result.perHead = {k: dict(n=counts[k], trained=enabled[k],
                            reason=None if enabled[k] else 'insufficient_samples', **v)
                      for k, v in _metrics(pred['probabilities'], vt, enabled).items()}
    grade_available = all(enabled[k] for k in BINARY)
    result.metrics = dict(grade_accuracy=float((pred['grades'] == vt.grades).mean()) if grade_available else None,
                          members=[dict(perHead=_metrics(o, vt, enabled),
                                        grade_accuracy=float((_grade_predictions(o) == vt.grades).mean()) if grade_available else None)
                                   for o in pred['members']], evaluation_split='validation')
    return result
