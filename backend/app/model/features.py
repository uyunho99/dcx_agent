"""Feature order is a persisted model contract; rows always follow docs."""
import numpy as np

CHANNELS = ('naver_cafe', 'naver_blog', 'youtube', 'ppomppu', 'clien')
INPUT_DIM = 1032


def build_features(docs, vectors) -> np.ndarray:
    """Accept a VectorStore, ID mapping, or aligned 1024-column array.

    Missing embeddings stay zero so training can exclude them without shifting
    labels. Crawl source/fetch_level are supported; callers join the Jev vote
    truncated flag as jev_truncated before constructing features.
    """
    docs = [dict(d) for d in docs]
    if hasattr(vectors, 'iter_shards'):
        ids, array = vectors.get([d['doc_id'] for d in docs])
        vectors = dict(zip(ids, array))
    if isinstance(vectors, dict):
        array = np.asarray([vectors.get(d['doc_id'], np.zeros(1024)) for d in docs], dtype=np.float32)
    else:
        array = np.asarray(vectors, dtype=np.float32)
    if not docs:
        return np.empty((0, INPUT_DIM), dtype=np.float32)
    if array.shape != (len(docs), 1024) or not np.isfinite(array).all():
        raise ValueError('Expected finite, aligned 1024-dimensional embeddings')
    result = np.zeros((len(docs), INPUT_DIM), dtype=np.float32)
    result[:, :1024] = array
    for i, doc in enumerate(docs):
        result[i, 1024 + CHANNELS.index(doc.get('channel', doc.get('source')))] = 1
        result[i, 1029:] = (np.log1p(len(doc.get('body') or '')),
                            bool(doc.get('is_snippet', doc.get('fetch_level') == 'snippet')), bool(doc.get('jev_truncated', False)))
    return result
