import json
from unittest.mock import patch

import numpy as np
import pytest

from app.vectors.store import VectorStore


def test_store_roundtrip_float16(tmp_path):
    ids = [str(i) for i in range(25000)]
    vecs = np.random.default_rng(42).normal(size=(25000, 1024)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store = VectorStore(tmp_path)
    store.write_shard(ids, vecs, [False] * len(ids))
    assert store.count() == 25000
    assert store.done_shards() == 3
    assert len(list((tmp_path / 'vectors').glob('shard-*.f16'))) == 3
    shards = list(store.iter_shards())
    assert [len(s[0]) for s in shards] == [10000, 10000, 5000]
    assert all(s[1].dtype == np.float32 and s[2].dtype == np.bool_ for s in shards)
    found, result = VectorStore(tmp_path).get(['24999', 'missing', '1', '10000', '1'])
    assert found == ['24999', '1', '10000', '1']
    assert np.max(np.abs(result - vecs[[24999, 1, 10000, 1]])) < 1e-3


def test_store_append_failed_and_memmap_cache(tmp_path):
    store = VectorStore(tmp_path)
    store.write_shard(['a', 'bad'], np.ones((2, 4), dtype=np.float32), [False, True])
    with patch('numpy.memmap', wraps=np.memmap) as mmap:
        list(store.iter_shards())
        list(VectorStore(tmp_path).iter_shards())
        assert mmap.call_count == 1
    store.write_shard(['b'], np.ones((1, 4), dtype=np.float32), [False])
    assert VectorStore(tmp_path).count() == 3
    ids, vectors, failed = next(store.iter_shards())
    assert ids == ['a', 'bad']
    assert failed.tolist() == [False, True]
    assert not vectors[1].any()
    records = [json.loads(line) for line in (tmp_path / 'vectors/ids.jsonl').read_text().splitlines()]
    assert records[1] == {'doc_id': 'bad', 'shard': 1, 'row': 1, 'failed': True}


def test_store_empty_and_invalid(tmp_path):
    store = VectorStore(tmp_path)
    assert store.count() == store.done_shards() == 0
    assert list(store.iter_shards()) == []
    assert store.get(['missing'])[0] == []
    with pytest.raises(ValueError):
        store.write_shard(['a'], np.ones((2, 4)), [False])
    store.write_shard(['a'], np.ones((1, 4)), [False])
    with pytest.raises(ValueError):
        store.write_shard(['a'], np.ones((1, 4)), [False])
    with pytest.raises(ValueError):
        store.write_shard(['b'], np.ones((1, 3)), [False])


def test_store_interrupted_index_publication_keeps_previous_shards(tmp_path):
    store = VectorStore(tmp_path)
    store.write_shard(['a'], np.ones((1, 4)), [False])
    with patch('app.vectors.store.os.replace', side_effect=OSError('interrupted')):
        with pytest.raises(OSError):
            store.write_shard(['b'], np.ones((1, 4)), [False])
    reopened = VectorStore(tmp_path)
    assert reopened.count() == 1
    assert reopened.get(['a', 'b'])[0] == ['a']
    reopened.write_shard(['b'], np.ones((1, 4)), [False])
    assert reopened.count() == 2
    assert reopened.done_shards() == 2
