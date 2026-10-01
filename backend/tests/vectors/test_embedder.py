from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app.config import settings
from app.services import voyage
from app.vectors.embedder import EmbedderUnconnected, FakeEmbedder, VoyageEmbedder, get_embedder


def test_fake_embedder_deterministic():
    embedder = FakeEmbedder()
    vectors = embedder.embed(['같은 글', '다른 글', '같은 글'])
    assert vectors.shape == (3, 1024)
    assert vectors.dtype == np.float32
    np.testing.assert_array_equal(vectors[0], vectors[2])
    np.testing.assert_array_equal(vectors[:1], FakeEmbedder().embed(['같은 글']))
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
    assert not np.array_equal(vectors[0], vectors[1])
    assert embedder.embed([]).shape == (0, 1024)


def test_voyage_request_model(monkeypatch):
    monkeypatch.setattr(settings, 'voyage_api_key', 'test-key')
    client = Mock()
    client.embed.side_effect = lambda texts, **kwargs: SimpleNamespace(embeddings=[[1.] * 1024 for _ in texts])
    monkeypatch.setattr(voyage.voyageai, 'Client', Mock(return_value=client))
    result = VoyageEmbedder().embed(['x' * 2001] * 128 + [' '])
    assert result.shape == (129, 1024)
    assert result.dtype == np.float32
    assert client.embed.call_count == 2
    args, kwargs = client.embed.call_args_list[0]
    assert args[0] == ['x' * 2000] * 128
    assert kwargs == {'model': 'voyage-4', 'output_dimension': 1024}
    assert client.embed.call_args_list[1].args[0] == ['빈 문서']


def test_voyage_failure_is_zero_and_does_not_leak_key(monkeypatch, capsys):
    monkeypatch.setattr(settings, 'voyage_api_key', 'secret-test-key')
    client = Mock()
    client.embed.side_effect = [RuntimeError('secret-test-key'), SimpleNamespace(embeddings=[[1.] * 1024])]
    monkeypatch.setattr(voyage.voyageai, 'Client', Mock(return_value=client))
    result = VoyageEmbedder().embed(['text'] * 129)
    assert not result[:128].any()
    assert result[128].all()
    assert 'secret-test-key' not in str(capsys.readouterr())


@pytest.mark.parametrize('key', ['', ' ', 'x'])
def test_voyage_unconnected(monkeypatch, key):
    monkeypatch.setattr(settings, 'voyage_api_key', key)
    with pytest.raises(EmbedderUnconnected):
        VoyageEmbedder()


def test_get_embedder_fake(monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    assert isinstance(get_embedder(), FakeEmbedder)


def test_voyage_invalid_response_rows_are_zero(monkeypatch):
    monkeypatch.setattr(settings, 'voyage_api_key', 'test-key')
    client = Mock()
    client.embed.return_value = SimpleNamespace(embeddings=[[1.] * 1024, [2.], [float('nan')] * 1024])
    monkeypatch.setattr(voyage.voyageai, 'Client', Mock(return_value=client))
    result = VoyageEmbedder().embed(['ok', 'wrong dimension', 'nonfinite', 'missing'])
    assert result.shape == (4, 1024)
    assert result[0].all()
    assert not result[1:].any()
