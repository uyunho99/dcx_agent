import numpy as np

from app.vectors.search import cosine_topk
from app.vectors.store import VectorStore


def test_search_skips_zero_vectors(tmp_path):
    store = VectorStore(tmp_path)
    store.write_shard(['zero', 'a', 'b', 'failed'], np.array([[0, 0], [2, 0], [-1, 0], [1, 0]]), [False, False, False, True])
    result = cosine_topk(store, np.array([[1., 0.]]), 10, None, set())
    assert [x[0] for x in result[0]] == ['a', 'b']
    np.testing.assert_allclose([x[1] for x in result[0]], [1, -1])


def test_search_batch_queries(tmp_path):
    store = VectorStore(tmp_path)
    store.write_shard(['a', 'b'], np.array([[1, 0], [0, 2]]), [False, False])
    store.write_shard(['c', 'd'], np.array([[-1, 0], [0, -1]]), [False, False])
    queries = np.array([[3, 0], [0, 2], [-2, 0]])
    results = cosine_topk(store, queries, 1, {'a', 'b', 'c'}, {'b'})
    assert len(results) == 3
    assert [row[0][0] for row in results] == ['a', 'a', 'c']
    assert cosine_topk(store, queries, 2, set(), set()) == [[], [], []]
    assert cosine_topk(store, queries, 0, None, set()) == [[], [], []]
    assert cosine_topk(store, np.zeros((1, 2)), 2, None, set()) == [[]]
    assert cosine_topk(VectorStore(tmp_path / 'absent'), queries, 2, None, set()) == [[], [], []]
