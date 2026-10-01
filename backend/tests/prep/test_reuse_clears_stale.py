"""Q4: endpoint cache reuse completes stage three in the active version."""
import socket

import pytest

from app.context import store, versions
from app.prep import pipeline
from app.work import runner
from tests.prep.test_pipeline import Context, doc, setup


@pytest.mark.parametrize('explicit_version', [False, True])
def test_endpoint_reuse_clears_only_stage3(setup, client, monkeypatch, explicit_version):
    def forbidden(*args, **kwargs):
        pytest.fail('Prep reuse must not access the network or start a worker')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    embedder = setup([doc()])
    pipeline.run_prep(Context(), 's', 'v1')
    version = versions.create_version('s', 'v1', 'stage3', '')
    old_path = versions.version_dir('s', 'v1') / 'session.json'
    old_bytes = old_path.read_bytes()
    before = store.load_session('s')
    assert 'stage3' in before['stale']
    expected_stale = {key: value for key, value in before['stale'].items()
                      if key != 'stage3'}
    monkeypatch.setattr(runner, 'start', forbidden)
    calls = len(embedder.calls)
    query = f'?version={version}' if explicit_version else ''

    # A repeated cache hit must remain successful and keep other markers intact.
    for _ in range(2):
        response = client.post('/prep/s/run' + query)
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'done'
        assert result['reused'] is True
        assert result['runId'] is None
        assert result['derivedRef'] == before['prep']['derivedRef']
        assert result['stage3']['after'] == 1
        saved = store.load_session('s')
        assert saved['stale'] == expected_stale
        assert saved['prep']['status'] == 'done'
        assert saved['prep']['reused'] is True
        session = client.get('/session/s' + query)
        assert session.status_code == 200
        assert session.json()['data']['stale'] == expected_stale
        assert old_path.read_bytes() == old_bytes
        assert len(embedder.calls) == calls
