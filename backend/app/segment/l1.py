"""Deterministic L1 clustering of normalized float16 input vectors."""
import numpy as np
from scipy.cluster.hierarchy import linkage
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

from app.segment import params


def _shape(vectors):
    if vectors.ndim != 2 or not vectors.shape[0] or not vectors.shape[1]:
        raise ValueError('Expected a nonempty matrix of vectors')
    return vectors.shape[0]


def _seed(rng):
    return int(rng.integers(np.iinfo(np.int32).max))


def suggest_k(vectors, rng) -> dict:
    """Scan inclusive K_RANGE on one random sample; ties favor smaller k.

    Dendrogram rows are the last 30 SciPy linkage rows, in merge order:
    [left node, right node, distance, leaf count]. Node IDs refer to the
    sampled linkage tree. Only k < sample size can have a silhouette.
    """
    n = _shape(vectors)
    size = min(n, params.WARD_SAMPLE)
    candidates = range(params.K_RANGE[0], min(params.K_RANGE[1], size - 1) + 1)
    if not candidates:
        raise ValueError('Too few vectors to score any k in K_RANGE')
    sample = (vectors if n <= size else vectors[rng.choice(n, size=size, replace=False)])
    sample = np.asarray(sample, dtype=np.float32)
    merges = linkage(sample, method='ward')
    silhouettes, inertia = {}, {}
    seed = _seed(rng)
    for k in candidates:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(sample)
        count = len(np.unique(model.labels_))
        silhouettes[k] = (float(silhouette_score(sample, model.labels_))
                          if 1 < count < size else -1.0)
        inertia[k] = float(model.inertia_)
    return dict(k=max(silhouettes, key=silhouettes.get), silhouette=silhouettes,
                inertia=inertia, dendrogram=merges[-30:].tolist(), sample=size)


def cluster(vectors, k, rng) -> tuple[np.ndarray, np.ndarray]:
    """Return labels where i means CL{i}, and correspondingly ordered centers.

    IDs descend by final assignment size; equal sizes retain model-label order.
    Above KMEANS_FULL_MAX, train once through shuffled rows with partial_fit
    and predict in original order, converting only each batch to float32.
    """
    n = _shape(vectors)
    if not isinstance(k, (int, np.integer)) or not 1 <= k <= n:
        raise ValueError('k must be an integer between 1 and the document count')
    seed = _seed(rng)
    if n <= params.KMEANS_FULL_MAX:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed)
        labels = model.fit_predict(np.asarray(vectors, dtype=np.float32))
    else:
        if k > params.MINIBATCH:
            raise ValueError('k cannot exceed the streaming batch size')
        model = MiniBatchKMeans(n_clusters=k, batch_size=params.MINIBATCH,
                               n_init=5, random_state=seed)
        order = rng.permutation(n)
        for start in range(0, n, params.MINIBATCH):
            batch = np.asarray(vectors[order[start:start + params.MINIBATCH]], dtype=np.float32)
            model.partial_fit(batch)
        del order, batch
        labels = np.empty(n, dtype=np.int32)
        for start in range(0, n, params.MINIBATCH):
            batch = np.asarray(vectors[start:start + params.MINIBATCH], dtype=np.float32)
            labels[start:start + len(batch)] = model.predict(batch)
    sizes = np.bincount(labels, minlength=k)
    order = np.argsort(-sizes, kind='stable')
    renumber = np.empty(k, dtype=np.int32)
    renumber[order] = np.arange(k)
    return renumber[labels], model.cluster_centers_[order]
