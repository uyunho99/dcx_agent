"""Owner-scoped candidate unions with raw cosine relevance."""
from app.evidence.params import CANDIDATES_M, CORE_BONUS, TOP_PER_QUERY
from app.evidence.search import filtered_topk
from app.vectors.embedder import Embedder
from app.vectors.store import VectorStore


def _search(owner_key: str, owner_id: str, queries: list[dict], *,
            docs: dict[str, dict], store: VectorStore, embedder: Embedder,
            exclude: set[str], top_per_query: int, m: int) -> list[dict]:
    allow = {doc_id for doc_id, doc in docs.items() if doc.get(owner_key) == owner_id}
    if not queries or not allow - exclude or top_per_query <= 0 or m <= 0:
        return []

    vectors = embedder.embed([query['text'] for query in queries], input_type='query')
    # Keep all scoped scores: the wrapper's truncated ties follow storage order,
    # and a candidate's best cosine can come from a query it did not hit.
    scores = filtered_topk(store, vectors, len(allow), allow, exclude)
    relevance: dict[str, float] = {}
    dims_hit: dict[str, list[str]] = {}
    for query, row in zip(queries, scores):
        for doc_id, score in row:
            relevance[doc_id] = max(relevance.get(doc_id, float('-inf')), score)
        bonus = 0.0 if query['dim'] == 'Counter' else CORE_BONUS
        ranked = sorted(row, key=lambda item: (
            -(item[1] + (bonus if docs[item[0]]['band'] == 'core' else 0.0)), item[0]))
        for doc_id, _ in ranked[:top_per_query]:
            hits = dims_hit.setdefault(doc_id, [])
            if query['dim'] not in hits:
                hits.append(query['dim'])

    # The brief's small-owner fallback retains all searchable documents; a
    # supplemented document has no dims_hit unless it actually made a top-k.
    candidate_ids = set(dims_hit)
    if len(allow - exclude) < m:
        candidate_ids.update(relevance)
    ordered = sorted(candidate_ids, key=lambda doc_id: (-relevance[doc_id], doc_id))[:m]
    return [dict(doc_id=doc_id, relevance=relevance[doc_id],
                 dims_hit=dims_hit.get(doc_id, []), band=docs[doc_id]['band'])
            for doc_id in ordered]


def search_context(context_id: str, queries: list[dict], *, docs: dict[str, dict],
                   store: VectorStore, embedder: Embedder,
                   exclude: set[str] = frozenset(), top_per_query=TOP_PER_QUERY,
                   m=CANDIDATES_M) -> list[dict]:
    """Search Context documents; Core affects hits, never raw relevance."""
    return _search('context_id', context_id, queries, docs=docs, store=store,
                   embedder=embedder, exclude=exclude, top_per_query=top_per_query, m=m)


def search_persona(persona_id: str, queries: list[dict], *, docs: dict[str, dict],
                   store: VectorStore, embedder: Embedder,
                   exclude: set[str] = frozenset(), top_per_query=TOP_PER_QUERY,
                   m=CANDIDATES_M) -> list[dict]:
    """Search Persona documents across all of its Contexts."""
    return _search('persona_id', persona_id, queries, docs=docs, store=store,
                   embedder=embedder, exclude=exclude, top_per_query=top_per_query, m=m)
