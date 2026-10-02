from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app.config import settings
from app.services import voyage
from app.vectors.embedder import FakeEmbedder, VoyageEmbedder
from app.vectors.search import cosine_topk
from app.vectors.store import VectorStore


@pytest.fixture
def filtered_topk():
    from app.evidence.search import filtered_topk
    return filtered_topk


def test_embed_default_document():
    embedder = FakeEmbedder()
    texts = ['같은 글', '다른 글']
    default = embedder.embed(texts)
    assert default.dtype == np.float32
    assert default.shape == (2, settings.embed_dim)
    np.testing.assert_array_equal(default, embedder.embed(texts, input_type='document'))
    np.testing.assert_array_equal(default, embedder.embed(texts, input_type='query'))
    assert embedder.embed([], input_type='query').shape == (0, settings.embed_dim)


def test_voyage_passes_input_type(monkeypatch):
    monkeypatch.setattr(settings, 'voyage_api_key', 'test-key')
    client = Mock()
    client.embed.side_effect = lambda texts, **kwargs: SimpleNamespace(
        embeddings=[[1.] * settings.embed_dim for _ in texts])
    monkeypatch.setattr(voyage.voyageai, 'Client', Mock(return_value=client))
    embedder = VoyageEmbedder()
    for mode in (None, 'document', 'query'):
        client.reset_mock()
        texts = ['x' * 2001] * 128 + [' ']
        result = embedder.embed(texts) if mode is None else embedder.embed(texts, input_type=mode)
        assert result.shape == (129, settings.embed_dim)
        assert result.dtype == np.float32
        expected = dict(model=settings.embed_model, output_dimension=settings.embed_dim)
        if mode == 'query':
            expected['input_type'] = 'query'
        assert client.embed.call_count == 2
        assert all(call.kwargs == expected for call in client.embed.call_args_list)
        assert client.embed.call_args_list[0].args == (['x' * 2000] * 128,)
        assert client.embed.call_args_list[1].args == (['빈 문서'],)


def test_filtered_topk_requires_allow(tmp_path, filtered_topk):
    with pytest.raises(ValueError, match='^allow set required$'):
        filtered_topk(VectorStore(tmp_path), np.ones((1, 2)), 0, None)


@pytest.mark.parametrize('with_bonus', [False, True])
def test_never_returns_outside_allow(tmp_path, filtered_topk, with_bonus):
    rng = np.random.default_rng(251)
    ids = [f'doc-{i}' for i in range(1000)]
    store = VectorStore(tmp_path)
    store.write_shard(ids, rng.standard_normal((1000, 16)), [False] * 1000)
    bonus = {doc_id: 0.05 for doc_id in ids} if with_bonus else None
    for _ in range(100):
        allow = set(rng.choice(ids, 50, replace=False))
        exclude = set(sorted(allow)[:5])
        results = filtered_topk(store, rng.standard_normal((1, 16)), 15, allow, exclude, bonus)
        assert len(results[0]) == 15
        assert {doc_id for doc_id, _ in results[0]} <= allow - exclude


def test_bonus_reorders(tmp_path, filtered_topk):
    store = VectorStore(tmp_path)
    store.write_shard(['leader', 'excluded'], np.array([[1, 0], [1, 0]]), [False] * 2)
    store.write_shard(['core', 'outside', 'zero', 'failed'],
                      np.array([[0.98, 0.2], [1, 0], [0, 0], [1, 0]]),
                      [False, False, False, True])
    query = np.array([[1., 0.]])
    allow = {'leader', 'core', 'excluded', 'zero', 'failed'}
    assert filtered_topk(store, query, 1, allow, {'excluded'})[0][0][0] == 'leader'
    bonus = {'core': 0.05, 'outside': 100, 'excluded': 100, 'zero': 100, 'failed': 100}
    result = filtered_topk(store, query, 1, allow, {'excluded'}, bonus)
    raw = dict(cosine_topk(store, query, 10, allow, {'excluded'})[0])
    assert result[0][0][0] == 'core'
    assert result[0][0][1] == pytest.approx(raw['core'] + 0.05)
    assert len(filtered_topk(store, query, 10, allow, {'excluded'}, bonus)[0]) == 2


@pytest.mark.parametrize('top_k', [-1, 0, 1, 10])
@pytest.mark.parametrize('bonus', [None, {}])
def test_no_bonus_matches_cosine_topk(tmp_path, filtered_topk, top_k, bonus):
    store = VectorStore(tmp_path)
    store.write_shard(['b', 'a', 'zero'], np.array([[1, 0], [1, 0], [0, 0]]), [False] * 3)
    store.write_shard(['c', 'failed'], np.array([[-1, 0], [1, 0]]), [False, True])
    for queries in (np.array([[1., 0.], [-1., 0.], [0., 0.]]), np.empty((0, 2))):
        for allow in (set(), {'a', 'b', 'c', 'zero', 'failed', 'missing'}):
            for exclude in (set(), {'a'}):
                assert filtered_topk(store, queries, top_k, allow, exclude, bonus) == cosine_topk(
                    store, queries, top_k, allow, exclude)


def test_evidence_never_imports_cosine_topk():
    directory = Path(__file__).resolve().parents[2] / 'app' / 'evidence'
    assert (directory / 'search.py').is_file()
    for path in directory.rglob('*.py'):
        if path != directory / 'search.py':
            assert 'cosine_topk' not in path.read_text(encoding='utf-8'), str(path)
