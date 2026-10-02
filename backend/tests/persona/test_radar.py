import numpy as np
import pytest

from app.persona.radar import embed_axes, radar, session_percentiles
from app.persona.params import RADAR_AXES


def test_weighted_absolute_cosine():
    result = radar({'a': np.array([-2., 0., 0.]), 'b': np.array([0., 5., 0.])},
                   {'a': 1, 'b': 3}, np.eye(3))
    assert result['raw'] == pytest.approx(dict(Computed=.25, Connected=.75, Shared=0))
    assert result['percentile'] == dict(Computed=50, Connected=50, Shared=50)


def test_session_percentiles_and_ties():
    assert session_percentiles([0, .5, .5, 1]) == [12.5, 50, 50, 87.5]
    assert session_percentiles([.3]) == [50]


@pytest.mark.parametrize('query', [True, False])
def test_axis_embedding_compatibility(query):
    calls = []
    class Query:
        def embed(self, texts, *, input_type=None):
            calls.append((texts, input_type))
            return np.eye(3)
    class Legacy:
        def embed(self, texts):
            calls.append((texts, None))
            return np.eye(3)
    assert np.array_equal(embed_axes(Query() if query else Legacy()), np.eye(3))
    assert calls == [(list(RADAR_AXES.values()), 'query' if query else None)]


def test_embedder_internal_typeerror_not_retried():
    class Broken:
        def embed(self, texts, input_type=None):
            raise TypeError('internal failure')
    with pytest.raises(TypeError, match='internal failure'):
        embed_axes(Broken())


def test_zero_vector_is_finite():
    result = radar({'a': np.zeros(3)}, {'a': 1}, np.eye(3))
    assert list(result['raw'].values()) == [0, 0, 0]
