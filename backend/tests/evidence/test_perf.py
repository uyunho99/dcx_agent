"""Opt-in stage-seven CPU measurements; no timing acceptance threshold."""
from time import perf_counter

import numpy as np
import pytest

from app.evidence import rerank, tabs


@pytest.mark.perf
def test_rerank_and_tabs_31_contexts_50_candidates(record_property):
    rng = np.random.default_rng(42)
    pools = []
    for c in range(31):
        ids = [f'c{c}-d{i}' for i in range(50)]
        candidates = [dict(doc_id=d, relevance=1 - i / 100,
                           band='edge' if i % 5 == 0 else 'core') for i, d in enumerate(ids)]
        tags = {d: dict(relevant=True, known_match='none', unmet_need='quiet cooling') for d in ids}
        matrix = rng.normal(size=(50, 1024))
        matrix /= np.linalg.norm(matrix, axis=1)[:, None]
        vectors = dict(zip(ids, matrix))
        docs = {d: dict(combo_rarity=float(rng.random()), tagProbs=dict.fromkeys(
            ('sense', 'feel', 'think', 'act', 'relate', 'outcome'), .8)) for d in ids}
        pools.append((candidates, tags, vectors, docs))

    start = perf_counter()
    selections = [rerank.select(*pool) for pool in pools]
    rerank_s = perf_counter() - start
    start = perf_counter()
    results = []
    for c, pool in enumerate(pools):
        known = [dict(id=f'ki-{c}', type='doc', doc_id=pool[0][0]['doc_id'], **{'from': 'rag'})]
        results.append((tabs.all_tab(*pool, known_items=known),
                        tabs.new_tab(f'c{c}', *pool, known_items=known)))
    tabs_s = perf_counter() - start
    assert all(len(s.rows) == 10 for s in selections)
    assert all(len(a.rows) == len(n.rows) == 10 and n.excluded_known == 1 for a, n in results)
    for name, seconds in [('rerank', rerank_s), ('tabs_all_and_new', tabs_s)]:
        record_property(name + '_seconds', seconds)
        print(f'{name} contexts=31 candidates_per_context=50 dimensions=1024 '
              f'total={seconds:.6f}s per_context={seconds / 31:.6f}s')
