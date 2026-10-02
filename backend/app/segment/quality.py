"""Diagnostic metrics only: no automatic splitting or merging.

Undefined metrics return None (JSON null), so small/empty groups do not get
misleading perfect scores. All stochastic entry points default to params.SEED.
"""
from collections import Counter
from itertools import combinations
import math

import numpy as np
from sklearn import config_context
from sklearn.metrics import adjusted_rand_score, silhouette_samples

from app.segment import l1, params


def cohesion(vectors, centroid=None) -> float | None:
    """Mean document-to-centroid cosine; infer the mean centroid if omitted.

    Convert float16 inputs in batches, never the full document matrix.
    Zero vectors/centroids contribute zero cosine.
    """
    if not len(vectors):
        return None
    if centroid is None:
        total = np.zeros(vectors.shape[1], dtype=np.float64)
        for start in range(0, len(vectors), params.MINIBATCH):
            total += np.asarray(vectors[start:start + params.MINIBATCH], dtype=np.float32).sum(axis=0, dtype=np.float64)
        centroid = total / len(vectors)
    centroid = np.asarray(centroid, dtype=np.float32)
    norm = np.linalg.norm(centroid)
    if not norm:
        return 0.0
    centroid = centroid / norm
    total = 0.0
    for start in range(0, len(vectors), params.MINIBATCH):
        batch = np.asarray(vectors[start:start + params.MINIBATCH], dtype=np.float32)
        norms = np.linalg.norm(batch, axis=1)
        cosines = np.divide(batch @ centroid, norms, out=np.zeros(len(batch), dtype=np.float32), where=norms != 0)
        total += np.clip(cosines, -1, 1).sum(dtype=np.float64)
    return float(total / len(vectors))


def _aligned_labels(vectors, labels):
    labels = np.asarray(labels)
    if labels.ndim != 1 or len(labels) != len(vectors):
        raise ValueError('labels must align with vector rows')
    return labels


def boundary(vectors, labels, rng=None, *, target_label=None) -> float | None:
    """Negative cosine-silhouette ratio on at most WARD_SAMPLE random rows.

    Supply all competing clusters, even when requesting a single target_label.
    A target absent from the sample, or an unscorable sample, returns None.
    Reuse the same RNG seed for comparable per-cluster samples.
    """
    labels = _aligned_labels(vectors, labels)
    rng = np.random.default_rng(params.SEED) if rng is None else rng
    size = min(len(labels), params.WARD_SAMPLE)
    indices = rng.choice(len(labels), size=size, replace=False)
    sampled_labels = labels[indices]
    if not 1 < len(np.unique(sampled_labels)) < size:
        return None
    sample = np.asarray(vectors[indices], dtype=np.float32)
    # sklearn chunks pairwise distances; keep even the capped sample from
    # allocating a dense 20,000 x 20,000 distance matrix.
    with config_context(working_memory=64):
        scores = silhouette_samples(sample, sampled_labels, metric='cosine')
    if target_label is not None:
        scores = scores[sampled_labels == target_label]
    return float(np.mean(scores < 0)) if len(scores) else None


def resample_ari(vectors, labels, level='L1', recluster=None, rng=None) -> float | None:
    """Mean ARI against original labels on 80% subsets without replacement.

    L1 defaults to l1.cluster with the original number of clusters. L2 requires
    recluster(indices, rng) -> labels in *indices order*. The callback can map
    indices to SegmentInput.ids and use nouns; labels need not retain original
    cluster numbering. Repeats and fractions come exclusively from params.
    """
    if level not in params.ARI_RESAMPLE:
        raise ValueError('level must be L1 or L2')
    if level == 'L2' and recluster is None:
        raise ValueError('L2 requires a recluster callback')
    labels = _aligned_labels(vectors, labels)
    size = int(len(labels) * params.RESAMPLE_FRAC)
    k = len(np.unique(labels))
    if size < 2 or (recluster is None and size < k):
        return None
    rng = np.random.default_rng(params.SEED) if rng is None else rng
    scores = []
    for _ in range(params.ARI_RESAMPLE[level]):
        indices = rng.choice(len(labels), size=size, replace=False)
        if recluster is None:
            predicted, _ = l1.cluster(vectors[indices], k, rng)
        else:
            predicted = recluster(indices, rng)
        predicted = np.asarray(predicted)
        if predicted.shape != (size,):
            raise ValueError('recluster must return one label per sampled row')
        scores.append(adjusted_rand_score(labels[indices], predicted))
    return float(np.mean(scores))


def npmi(words, documents) -> float | None:
    """Mean NPMI of the top ten unique words in the Persona document corpus.

    Counts are document presence, not token frequency. Unobserved pairs score
    -1; a pair present in every document scores 1 (the limiting convention).
    No corpus or fewer than two unique words yields None.
    """
    words = list(dict.fromkeys(words))[:params.CTFIDF_TOP]
    if len(words) < 2:
        return None
    vocabulary = set(words)
    singles, pairs = Counter(), Counter()
    count = 0
    for document in documents:
        present = vocabulary.intersection(document)
        singles.update(present)
        pairs.update(combinations(sorted(present), 2))
        count += 1
    if not count:
        return None
    scores = []
    for a, b in combinations(sorted(words), 2):
        joint = pairs[a, b]
        if not joint:
            scores.append(-1.0)
        elif joint == count:
            scores.append(1.0)
        else:
            scores.append(math.log(joint * count / (singles[a] * singles[b])) / -math.log(joint / count))
    return float(np.mean(scores))


def channel_distribution(documents) -> dict:
    """Collection source shares and the inclusive 80% channel-skew flag.

    Pass document rows (e.g. source.docs[id] for each cluster member), not IDs.
    Missing sources remain the empty-string channel used by SegmentInput.
    """
    counts = Counter(doc.get('source', '') for doc in documents)
    count = sum(counts.values())
    shares = {channel: n / count for channel, n in counts.items()}
    return dict(channels=shares, channel_skew=any(share >= params.CHANNEL_SKEW for share in shares.values()))


def flags(*, cohesion=None, boundary=None, ari=None, level='L1') -> list[str]:
    """Diagnostic codes: 분리 검토, 경계 검토, 불안정, respectively."""
    result = []
    if cohesion is not None and cohesion < params.COHESION_MIN:
        result.append('low_cohesion')
    if boundary is not None and boundary > params.BOUNDARY_MAX:
        result.append('high_boundary')
    if ari is not None and ari < params.ARI_MIN[level]:
        result.append('unstable')
    return result
