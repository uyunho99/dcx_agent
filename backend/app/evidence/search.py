"""Evidence search always requires an explicit document allow set."""
import numpy as np

from app.vectors.search import cosine_topk
from app.vectors.store import VectorStore


def filtered_topk(store: VectorStore, queries: np.ndarray, top_k: int,
                  allow: set[str], exclude: set[str] = frozenset(),
                  bonus: dict[str, float] | None = None) -> list[list[tuple[str, float]]]:
    """Rank allowed, non-excluded documents by cosine plus an optional bonus."""
    if allow is None:
        raise ValueError('allow set required')
    if not bonus or top_k <= 0:
        return cosine_topk(store, queries, top_k, allow, exclude)

    # Fetch all eligible scores: a bonus can promote a document below top_k.
    results = cosine_topk(store, queries, len(allow), allow, exclude)
    return [sorted(((doc_id, score + bonus.get(doc_id, 0.0)) for doc_id, score in row),
                   key=lambda item: -item[1])[:top_k] for row in results]
