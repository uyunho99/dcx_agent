"""Candidate retrieval contracts, using real offline vector search."""
from unittest.mock import Mock

import numpy as np
import pytest

from app.evidence.candidates import search_context, search_persona
from app.evidence.params import QUERY_DIMS
from app.vectors.store import VectorStore


def setup_search(tmp_path, vectors, *, metadata=None, query_vectors=None):
    ids = list(vectors)
    store = VectorStore(tmp_path)
    store.write_shard(ids, np.asarray(list(vectors.values())), [False] * len(ids))
    docs = {doc_id: dict(context_id='ctx', persona_id='persona', band='fringe')
            for doc_id in ids}
    for doc_id, fields in (metadata or {}).items():
        docs[doc_id].update(fields)
    query_vectors = query_vectors or {'Sense': [1., 0.]}
    embedder = Mock()
    embedder.embed.side_effect = lambda texts, **kw: np.asarray([query_vectors[t] for t in texts])
    queries = [dict(dim=dim, text=dim, origin='llm') for dim in query_vectors]
    return queries, dict(docs=docs, store=store, embedder=embedder)


def test_allow_is_context_docs(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'inside': [.8, .6], 'outside': [1., 0.]},
        metadata={'outside': dict(context_id='other', band='core')})
    rows = search_context('ctx', queries, **kwargs)
    assert [r['doc_id'] for r in rows] == ['inside']


def test_counter_no_core_bonus(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'core': [.98, .2], 'fringe': [1., 0.]},
        metadata={'core': dict(band='core')}, query_vectors={'Counter': [1., 0.]})
    rows = search_context('ctx', queries, **kwargs, top_per_query=1, m=1)
    assert rows == [dict(doc_id='fringe', relevance=1., dims_hit=['Counter'], band='fringe')]


def test_core_bonus_applied(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'core': [.98, .2], 'fringe': [1., 0.]},
        metadata={'core': dict(band='core')})
    rows = search_context('ctx', queries, **kwargs, top_per_query=1, m=1)
    assert [r['doc_id'] for r in rows] == ['core']
    assert rows[0]['band'] == 'core'
    assert rows[0]['relevance'] == pytest.approx(.98 / np.hypot(.98, .2), abs=1e-4)


def test_union_dedup_top_m(tmp_path):
    rng = np.random.default_rng(73)
    vectors = {f'doc-{i:03}': rng.normal(size=8) for i in range(160)}
    query_vectors = dict(zip(QUERY_DIMS, np.eye(8)))
    queries, kwargs = setup_search(tmp_path, vectors, query_vectors=query_vectors)
    ids, matrix = kwargs['store'].get(list(vectors))
    scores = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    hits = [sorted(range(len(ids)), key=lambda i: (-scores[i, q], ids[i]))[:15]
            for q in range(8)]
    union = set().union(*map(set, hits))
    assert len(union) > 50
    expected = sorted(union, key=lambda i: (-max(scores[i]), ids[i]))[:50]
    rows = search_context('ctx', queries, **kwargs)
    assert [r['doc_id'] for r in rows] == [ids[i] for i in expected]
    for row, i in zip(rows, expected):
        assert row['relevance'] == pytest.approx(max(scores[i]))
        assert row['dims_hit'] == [dim for dim, hit in zip(QUERY_DIMS, hits) if i in hit]


def test_dims_hit_recorded(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'x': [1., 0.], 'y': [0., 1.]},
        query_vectors={'Sense': [1., 0.], 'Feel': [1., 0.], 'Counter': [0., 1.]})
    rows = search_context('ctx', queries + [queries[0]], **kwargs, top_per_query=1)
    assert rows == [dict(doc_id='x', relevance=1., dims_hit=['Sense', 'Feel'], band='fringe'),
                    dict(doc_id='y', relevance=1., dims_hit=['Counter'], band='fringe')]


def test_persona_query_allow_is_persona(tmp_path):
    queries, kwargs = setup_search(tmp_path,
        {'one': [.8, .6], 'two': [.6, .8], 'outside': [1., 0.]},
        metadata={'two': dict(context_id='other'), 'outside': dict(persona_id='other')},
        query_vectors={'desire_check_0': [1., 0.], 'artifact': [0., 1.]})
    assert {r['doc_id'] for r in search_persona('persona', queries, **kwargs)} == {'one', 'two'}
    assert [r['doc_id'] for r in search_persona('persona', queries, **kwargs,
                                               exclude={'one'})] == ['two']


@pytest.mark.parametrize('search,owner', [(search_context, 'ctx'), (search_persona, 'persona')])
def test_queries_embedded_as_query(tmp_path, search, owner):
    queries, kwargs = setup_search(tmp_path, {'a': [1., 0.]},
        query_vectors=dict.fromkeys(QUERY_DIMS, [1., 0.]))
    search(owner, queries, **kwargs)
    kwargs['embedder'].embed.assert_called_once_with(list(QUERY_DIMS), input_type='query')


@pytest.mark.parametrize('n', [3, 23, 49])
def test_small_context_returns_all(tmp_path, n):
    queries, kwargs = setup_search(tmp_path, {f'doc-{i:02}': [1., i / n] for i in range(n)},
        query_vectors=dict.fromkeys(QUERY_DIMS, [1., 0.]))
    rows = search_context('ctx', queries, **kwargs)
    assert len(rows) == n
    assert {r['doc_id'] for r in rows} == set(kwargs['docs'])
    assert all(r['dims_hit'] == (list(QUERY_DIMS) if i < 15 else [])
               for i, r in enumerate(rows))


def test_ties_by_doc_id_at_both_cutoffs(tmp_path):
    queries, kwargs = setup_search(tmp_path,
        {f'doc-{i:03}': [1., 0.] for i in reversed(range(70))})
    rows = search_context('ctx', queries, **kwargs)
    assert [r['doc_id'] for r in rows] == [f'doc-{i:03}' for i in range(15)]
    rows = search_context('ctx', queries, **kwargs, top_per_query=60, m=50)
    assert [r['doc_id'] for r in rows] == [f'doc-{i:03}' for i in range(50)]


def test_relevance_includes_queries_that_did_not_hit(tmp_path):
    queries, kwargs = setup_search(tmp_path,
        {'a': [.6, .8], 'b': [.61, .79]},
        metadata={'b': dict(band='core')},
        query_vectors={'Sense': [1., 0.], 'Counter': [-1., 0.]})
    rows = search_context('ctx', queries, **kwargs, top_per_query=1)
    a = next(row for row in rows if row['doc_id'] == 'a')
    assert a['dims_hit'] == ['Counter']
    _, stored = kwargs['store'].get(['a'])
    assert a['relevance'] == pytest.approx(stored[0, 0] / np.linalg.norm(stored[0]))


def test_exclude_and_unsearchable_documents(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'a': [1., 0.], 'zero': [0., 0.]})
    kwargs['docs']['missing'] = dict(context_id='ctx', persona_id='persona', band='core')
    kwargs['store'].write_shard(['failed'], np.array([[1., 0.]]), [True])
    kwargs['docs']['failed'] = dict(context_id='ctx', persona_id='persona', band='core')
    assert search_context('ctx', queries, **kwargs, exclude={'a'}) == []


@pytest.mark.parametrize('options', [dict(m=0), dict(m=-1), dict(top_per_query=0),
                                     dict(top_per_query=-1)])
def test_nonpositive_limits(tmp_path, options):
    queries, kwargs = setup_search(tmp_path, {'a': [1., 0.]})
    assert search_context('ctx', queries, **kwargs, **options) == []


def test_empty_queries_or_owner(tmp_path):
    queries, kwargs = setup_search(tmp_path, {'a': [1., 0.]})
    assert search_context('ctx', [], **kwargs) == []
    assert search_context('missing', queries, **kwargs) == []
    kwargs['embedder'].embed.assert_not_called()
