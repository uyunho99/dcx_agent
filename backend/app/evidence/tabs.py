"""Pure all/new selection; search, tagging and current KI reads are injected."""
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from app.evidence import params
from app.evidence.rerank import Selection, select


@dataclass
class NewTab:
    context_id: str
    selection: Selection
    rounds: int
    exclusions: dict[str, str]
    candidates: list[dict]
    tags: dict[str, dict]
    params: dict = field(default_factory=lambda: {
        name: getattr(params, name) for name in (
            'SELECT_N', 'W_RARITY', 'DPP_SIGMA', 'COVERAGE_MIN', 'COVERAGE_EXTRA',
            'TAG_PROB_ON', 'RARE_MIN', 'DUP_COSINE', 'NEW_EXPAND', 'NEW_EXPAND_MAX',
            'NOVELTY_SHOW', 'NOVELTY_CORE_REPS', 'PROVISIONAL')})

    @property
    def rows(self):
        return self.selection.rows

    @property
    def excluded_known(self):
        return len(self.exclusions)

    @property
    def message(self):
        return f'{self.excluded_known}건이 Known Insight와 같아 빠졌습니다 → 전체 탭에서 보기'


def default_tab(kind: str) -> str:
    return {'context': 'new', 'desire_support': 'all', 'counter': 'all'}[kind]


def _known_snapshot(known_items):
    if known_items is None:
        return None
    items = known_items() if callable(known_items) else known_items
    return [i.model_dump() if hasattr(i, 'model_dump') else dict(i) for i in items]


def _current_tags(tags, known):
    active = None if known is None else {i['id'] for i in known}
    return {i: dict(t, known_match=(t.get('known_match') or 'none')
                    if active is None or t.get('known_match') in active else 'none')
            for i, t in tags.items() if t is not None}


def known_exclusions(candidates, tags, handed_doc_ids: set[str],
                     handed_vectors: np.ndarray, vectors) -> dict[str, str]:
    """Priority: handed document, semantic KI match, cosine duplicate (>= .95).

    handed_vectors must contain only handed original documents, never statement
    embeddings. Missing/zero vectors provide no cosine exclusion evidence.
    """
    # One ULP absorbs normalization rounding at the inclusive .95 boundary.
    handed = np.asarray(handed_vectors, dtype=float)
    if handed.size:
        handed = np.atleast_2d(handed)
        norms = np.linalg.norm(handed, axis=1)
        valid = np.isfinite(handed).all(axis=1) & (norms > 0)
        handed = handed[valid] / norms[valid, None]
    excluded = {}
    for row in candidates:
        doc_id = row['doc_id']
        if doc_id in handed_doc_ids:
            excluded[doc_id] = 'handed'
        elif (tags.get(doc_id) or {}).get('known_match') not in (None, 'none'):
            excluded[doc_id] = 'match'
        elif handed.size and doc_id in vectors:
            vector = np.asarray(vectors[doc_id], dtype=float)
            norm = np.linalg.norm(vector)
            if norm > 0 and np.isfinite(vector).all() and np.any(handed @ (vector / norm) >= np.nextafter(params.DUP_COSINE, -np.inf)):
                excluded[doc_id] = 'dup'
    return excluded



def _handed_inputs(known, vectors):
    ids = {i.get('doc_id') for i in known
           if i.get('origin', i.get('from')) == 'rag' and i.get('type') == 'doc'
           and i.get('doc_id')}
    return ids, [vectors[i] for i in sorted(ids) if i in vectors]


def _decorate(selection, tags):
    selection.rows = [dict(r, known_match=(tags.get(r['doc_id']) or {}).get('known_match', 'none'),
                           novelty=None, novelty_reason=None, show_novelty=False)
                      for r in selection.rows]
    return selection


def all_tab(candidates, tags, vectors, docs, *, known_items=None, supplement=None) -> Selection:
    """Known badges never penalize all-tab ranking; inputs remain untouched."""
    result = select(candidates, tags, vectors, docs, supplement=supplement)
    return _decorate(result, _current_tags(tags, _known_snapshot(known_items)))


def new_tab(context_id, candidates, tags, vectors, docs, *,
            handed_doc_ids=frozenset(), handed_vectors=(), known_items=None,
            expand: Callable[[int], list[dict]] | None = None,
            prepare: Callable[[list[dict]], dict[str, dict]] | None = None,
            supplement: Callable[[list[str], int], list[dict]] | None = None) -> NewTab:
    """Reapply 4.4 after exclusions, then fetch next 50 at most three times.

    expand(50) owns a relevance cursor and the Context allow set. prepare(rows)
    tags AND judges fetched documents and returns tags keyed by stable doc ID;
    it also makes their vectors/docs available before returning. Both expansion
    and coverage supplements pass through prepare and exclusions. Duplicates
    are deduplicated before prepare. At most one coverage supplement is fetched
    for this tab computation; its candidates persist through expansion rounds.

    known_items may be a current-list callback, read after injected work and
    before publication. Stable matches to deleted IDs disappear immediately.
    When supplied, it is authoritative for handed rag/doc IDs and their vectors
    (pass original-document vectors, not known_vectors' statement embeddings).
    With no known_items, the explicit handed inputs and projected tags are used.
    """
    pool = {r['doc_id']: dict(r) for r in candidates}
    working_tags = {i: dict(t) for i, t in tags.items() if t is not None}
    rounds, supplemented = 0, False

    def ingest(rows):
        fresh = {}
        for row in rows:
            if row['doc_id'] not in pool:
                fresh.setdefault(row['doc_id'], dict(row))
        if fresh and prepare is not None:
            prepared = prepare(list(fresh.values()))
            working_tags.update({i: dict(t) for i, t in prepared.items() if i in fresh and t is not None})
        pool.update(fresh)

    def eligible():
        known = _known_snapshot(known_items)
        current = _current_tags(working_tags, known)
        handed_ids, handed = handed_doc_ids, handed_vectors
        if known is not None:
            handed_ids, handed = _handed_inputs(known, vectors)
        excluded = known_exclusions(list(pool.values()), current, handed_ids, handed, vectors)
        return [r for i, r in pool.items() if i not in excluded], current, excluded

    def choose():
        nonlocal supplemented
        rows, current, excluded = eligible()
        result = select(rows, current, vectors, docs)
        if result.coverage < params.COVERAGE_MIN and supplement is not None and not supplemented:
            # Re-enter selection after preparation, so a KI deleted during that
            # work can restore even a previously excluded initial candidate.
            supplemented = True
            ingest(supplement(result.missing_dims, params.COVERAGE_EXTRA))
            rows, current, excluded = eligible()
            result = select(rows, current, vectors, docs)
        result.coverage_supplements = int(supplemented)
        return _decorate(result, current), excluded, current

    result, excluded, current = choose()
    while len(result.rows) < params.SELECT_N and expand is not None and rounds < params.NEW_EXPAND_MAX:
        fetched = expand(params.NEW_EXPAND)
        rounds += 1
        ingest(fetched)
        result, excluded, current = choose()
        if not fetched:
            break
    return NewTab(context_id, result, rounds, excluded, list(pool.values()), current)


def refresh_new(context_id, candidates, tags, vectors, docs, *, known_items,
                cached_expand=None, cached_supplement=None) -> NewTab:
    """Recompute one Context from cached tags, without any tagging/novelty call.

    Optional callbacks are cache-only searches; tags/vectors/docs must already
    contain fetched IDs. Missing tags remain unselected. Persist only this
    Context's new tab; all-tab rows and other Contexts belong to the caller.
    """
    return new_tab(context_id, candidates, tags, vectors, docs, known_items=known_items,
                   expand=cached_expand, supplement=cached_supplement)
