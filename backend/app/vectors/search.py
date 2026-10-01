"""Batched cosine search with bounded per-query candidate lists."""
import numpy as np

from app.vectors.store import VectorStore


def cosine_topk(store: VectorStore, queries: np.ndarray, top_k: int,
                allow: set[str] | None, exclude: set[str]) -> list[list[tuple[str, float]]]:
    queries = np.asarray(queries, dtype=np.float32)
    if queries.ndim != 2 or not np.isfinite(queries).all():
        raise ValueError('Queries must be a finite [n, dim] matrix')
    results = [[] for _ in queries]
    if top_k <= 0 or not len(queries) or allow == set():
        return results
    norms = np.linalg.norm(queries, axis=1, keepdims=True)
    normalized = np.divide(queries, norms, out=np.zeros_like(queries), where=norms != 0)
    for ids, vectors, failed in store.iter_shards():
        if vectors.shape[1] != queries.shape[1]:
            raise ValueError('Query dimension does not match store')
        lengths = np.linalg.norm(vectors, axis=1)
        valid = (lengths > 0) & np.isfinite(lengths) & ~failed
        valid &= np.array([doc_id not in exclude and (allow is None or doc_id in allow)
                           for doc_id in ids], dtype=bool)
        rows = np.flatnonzero(valid)
        if not len(rows):
            continue
        scores = normalized @ (vectors[rows] / lengths[rows, None]).T
        for i, row_scores in enumerate(scores):
            if norms[i, 0] == 0:
                continue
            order = np.argsort(-row_scores, kind='stable')[:top_k]
            results[i].extend((ids[rows[j]], float(np.clip(row_scores[j], -1, 1))) for j in order)
            results[i].sort(key=lambda item: -item[1])
            del results[i][top_k:]
    return results
