from contextlib import closing
import json
import time

import pytest

from app.config import settings
from app.context import store, versions
from app.work import runner
from app.crawl.queue import CrawlQueue


UNCONNECTED = '임베딩 API가 연결되지 않았습니다. 연결하거나 내부용 설정에서 가짜 임베더로 바꾸세요.'


@pytest.fixture
def collected(client, data_dir, monkeypatch):
    for name, value in {'STORAGE': 'local', 'EMBED_BACKEND': 'fake',
                        'EMBED_MODEL': 'voyage-4', 'EMBED_DIM': '1024',
                        'VOYAGE_API_KEY': ''}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(settings, 'voyage_api_key', '')
    store.update_session('s', {'schemaVersion': 2, 'collectionId': 'c1',
                               'drafts': {'labeling': {'keep': True}},
                               'knownInsights': ['keep']})
    root = data_dir / 'crawl/s/collections/c1'
    store.write_json(root / 'manifest.json', {'parent': None})
    with closing(CrawlQueue(root / 'queue.sqlite')) as queue:
        queue.register_run('detail')
        queue.connection.execute("UPDATE runs SET status='done'")
    store.atomic_write(root / 'docs/shard-0001.jsonl', json.dumps({
        'doc_id': 'd1', 'title': '제목', 'body': '사용 경험이 충분히 긴 본문입니다.',
        'comments': [], 'source': 'naver_cafe', 'url': 'https://example.test/d1',
        'fetch_level': 'full', 'src_meta': {}}) + '\n')
    return client


def configure(client, **values):
    response = client.put('/prep/s/config', json={'embedder': 'fake', **values})
    assert response.status_code == 200, response.text
    return response.json()


def finished(client):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get('/prep/s/status')
        assert response.status_code == 200, response.text
        result = response.json()
        if result['status'] in {'done', 'failed', 'interrupted'}:
            return result
        time.sleep(.05)
    pytest.fail('prep worker did not finish within 30 seconds')


def test_run_then_status_done(collected):
    configure(collected)
    response = collected.post('/prep/s/run')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'running'
    result = finished(collected)
    assert result['status'] == 'done', result
    assert result['stage3']['embedded'] == result['stage3']['after'] == 1
    assert result['progress'] == 1
    session = store.load_session('s')
    assert session['prep']['status'] == 'done'
    assert session['prep']['derivedRef']['prepKey'] == result['stage3']['prepKey']
    assert session['prep']['savedAt']
    assert session['drafts'] == {'labeling': {'keep': True}}
    assert session['knownInsights'] == ['keep']


def test_reuse_returns_done_immediately(collected, monkeypatch):
    configure(collected)
    assert collected.post('/prep/s/run').status_code == 200
    first = finished(collected)
    assert first['status'] == 'done'
    versions.create_version('s', 'v1', 'stage3', '')
    configure(collected)
    def forbidden(*args, **kwargs):
        pytest.fail('reuse must not launch another worker')
    monkeypatch.setattr(runner, 'start', forbidden)
    response = collected.post('/prep/s/run')
    assert response.status_code == 200
    assert response.json()['status'] == 'done'
    assert response.json()['reused'] is True
    assert response.json()['stage3'] == first['stage3']
    assert store.load_session('s')['prep']['status'] == 'done'


def test_embed_unconnected_stops_with_reason(collected, data_dir):
    configure(collected, embedder='voyage')
    assert collected.post('/prep/s/run').status_code == 200
    result = finished(collected)
    assert result['status'] == 'failed', result
    assert result['error'] == {'kind': 'embedder_unconnected', 'message': UNCONNECTED}
    assert result['stage3'] is None
    assert store.load_session('s')['prep']['status'] == 'failed'
    assert runner.status('s')[-1]['state'] == 'failed'
    assert not list((data_dir / 'derived').rglob('*.f16'))


@pytest.mark.parametrize('method,path,body', [
    ('put', 'config', {'embedder': 'fake'}), ('post', 'run', None), ('get', 'status', None)])
def test_legacy_session_rejected(client, method, path, body):
    store.update_session('legacy', {'step': 'preprocess'})
    response = getattr(client, method)(f'/prep/legacy/{path}', **({'json': body} if body else {}))
    assert response.status_code == 409
    assert response.json()['status'] == 'error'
    assert response.json()['error']['kind'] == 'legacy_session'


def test_config_validation_and_stale_version(collected):
    response = collected.put('/prep/s/config', json={'minBodyChars': -1})
    assert response.status_code == 422
    assert response.json()['error']['kind'] == 'validation'
    response = collected.put('/prep/s/config?version=v2', json={'embedder': 'fake'})
    assert response.status_code == 409
    assert 'prep' not in store.load_session('s')


def test_config_replaces_removed_boilerplate(collected):
    configure(collected, boilerplate={'naver_cafe': ['remove me']})
    configure(collected, boilerplate={})
    assert store.load_session('s')['prep']['config']['boilerplate'] == {}


def test_qa_q1_server_default_exposed_and_first_run_succeeds(collected, monkeypatch):
    from app.config import Settings
    monkeypatch.setattr(settings, 'embed_backend', Settings(_env_file=None).embed_backend)
    assert collected.get('/prep/s/status').json()['config']['embedder'] == 'fake'
    assert collected.post('/prep/s/run').status_code == 200
    assert finished(collected)['status'] == 'done'
    assert store.load_session('s')['prep']['config']['embedder'] == 'fake'


def test_qa_q5_prep_reports_actual_embedder(collected, data_dir):
    configure(collected)
    assert collected.post('/prep/s/run').status_code == 200
    result = finished(collected)
    assert result['stage3']['embedder'] == 'fake'
    ref = result['derivedRef']
    manifest = store.read_json(data_dir / 'derived/s' / ref['collectionId'] / ref['prepKey'] / 'manifest.json')
    assert manifest['embedder']['name'] == 'fake'
    assert manifest['embedderName'] == 'fake'


def test_qa_q6_partial_embedding_failure_is_not_reuse(collected, data_dir):
    from types import SimpleNamespace
    from app.prep.pipeline import run_prep
    from app.vectors.embedder import EmbedderUnconnected
    configure(collected, embedder='voyage')
    ctx = SimpleNamespace(args={}, heartbeat=lambda *a: None, should_stop=lambda: False)
    with pytest.raises(EmbedderUnconnected):
        run_prep(ctx, 's', 'v1')
    assert list((data_dir / 'derived/s').rglob('docs/*.jsonl'))
    assert list((data_dir / 'derived/s').rglob('tokens/*.jsonl'))
    configure(collected, embedder='fake')
    first = collected.post('/prep/s/run').json()
    assert first['reused'] is False
    result = finished(collected)
    assert result['status'] == 'done'
    assert result['reused'] is False
    assert collected.post('/prep/s/run').json()['reused'] is True
    assert collected.get('/prep/s/status').json()['reused'] is True
    configure(collected, minBodyChars=11)
    assert collected.get('/prep/s/status').json()['reused'] is False


def test_qa_q5_reused_old_report_uses_manifest_backend(collected, data_dir):
    configure(collected)
    collected.post('/prep/s/run')
    result = finished(collected)
    assert result['status'] == 'done'
    ref = result['derivedRef']
    root = data_dir / 'derived/s' / ref['collectionId'] / ref['prepKey']
    report = store.read_json(root / 'stage_3.json')
    report['embedder'] = 'voyage-4'  # Artifact written before R-112.
    store.write_json(root / 'stage_3.json', report)
    manifest = store.read_json(root / 'manifest.json')
    manifest.pop('embedderName')
    store.write_json(root / 'manifest.json', manifest)
    reused = collected.post('/prep/s/run').json()
    assert reused['reused'] is True
    assert reused['stage3']['embedder'] == 'fake'
    assert collected.get('/prep/s/status').json()['stage3']['embedder'] == 'fake'
    assert store.read_json(root / 'stage_3.json') == report  # No mutation of historical artifacts.
