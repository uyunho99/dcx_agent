"""Completion uses local evidence and recovers pending judge publication."""
from contextlib import closing
import socket
import sqlite3
from pathlib import Path

import pytest

from app.context import store, versions
from app.crawl.queue import CrawlQueue
from app.jobs.manager import JobManager
from app.routers import sessions
from app.work.status import database_path, transaction


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Session completion must not access the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(sessions, 'job_manager', JobManager())


def seed():
    store.update_session('display', {'schemaVersion': 2, 'sid': 'display', 'version': 'v1',
        'step': 'crawl-detail', 'collectionId': 'c1',
        'labeling': {'judgeRuns': {'jev': 'j1', 'gpt': 'g1'}}})


def run(labeler, state, version='v1', started=1):
    with transaction('display') as db:
        db.execute('''INSERT INTO runs
            (run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at)
            VALUES (?,?,'judge',?,'{}',0,?,0,?)''',
            (f'{version}-{labeler}-{started}', version, labeler, state, started))


@pytest.mark.parametrize('query', ['', '?version=v1'])
def test_crawl_done_without_polling_is_readonly(client, data_dir, query):
    seed()
    root = data_dir / 'crawl/display/collections/c1'
    root.mkdir(parents=True)
    with closing(CrawlQueue(root / 'queue.sqlite')) as queue:
        rid = queue.register_run('detail')
        queue.finish_run(rid, 'done')
    before = {p: p.read_bytes() for p in data_dir.rglob('*') if p.is_file() and not p.name.endswith(('-wal', '-shm'))}
    payload = client.get('/session/display' + query).json()['data']
    assert payload['step'] == 'crawl-detail'
    assert payload['completion'] == dict(crawlDone=True, prepDone=False,
        labelingDone=False, exportDone=False, clustersDone=False, segmentDone=False, evidenceDone=False)
    assert {p: p.read_bytes() for p in data_dir.rglob('*') if p.is_file() and not p.name.endswith(('-wal', '-shm'))} == before


@pytest.mark.parametrize('other', ['done', 'running', 'paused', 'failed', None])
def test_latest_judge_runs_are_version_local(client, other):
    seed()
    run('jev', 'failed')
    run('jev', 'done', started=2)
    run('gpt', 'done', version='v2')
    if other:
        run('gpt', other)
    payload = client.get('/session/display?version=v1').json()['data']
    assert payload['completion']['labelingDone'] is (other == 'done')


@pytest.mark.parametrize('source', ['persisted', 'job', 'clusters', 'clusters_refined'])
def test_cluster_result_and_session_milestones(client, data_dir, source):
    seed()
    store.update_session('display', {'prep': {'status': 'done'}, 'labeling': {'status': 'done'},
        'training': {'exportRef': 'exports/relevant.jsonl'}})
    if source == 'persisted':
        store.update_session('display', {'clustering': {'status': 'done', 'version': 'v1', 'at': store.now()}})
    elif source == 'job':
        sessions.job_manager.set('cluster', 'display', {'status': 'done', 'clusters': {'0': {'size': 1}}})
    else:
        root = data_dir / source / 'display'
        root.mkdir(parents=True)
        (root / ('cluster_0_123.jsonl' if source == 'clusters' else 'data_123.jsonl')).write_text('{"cluster":0}\n')
    result = client.get('/session/display').json()['data']['completion']
    assert result == dict(crawlDone=False, prepDone=True, labelingDone=True, exportDone=True,
        clustersDone=source == 'persisted', segmentDone=False, evidenceDone=False)


@pytest.mark.parametrize('query', ['', '?version=v1'])
@pytest.mark.parametrize('patch, expected', [
    ({'segment': {'status': 'done'}}, True),
    ({'segment': {'status': 'done'}, 'stale': {'stage6': True}}, False),
    ({}, False),
    ({'segment': {'status': 'running'}}, False),
    ({'segment': {'status': 'done'}, 'stale': {'stage7': True}}, True),
])
def test_segment_completion_uses_durable_status_and_stage6_staleness(client, query, patch, expected):
    seed()
    store.update_session('display', patch)
    result = client.get('/session/display' + query).json()['data']['completion']
    assert result['segmentDone'] is expected
    assert result['clustersDone'] is False


def test_selected_version_does_not_use_active_milestones(client):
    seed()
    store.update_session('display', {'collectionId': None})
    versions.create_version('display', 'v1', 'stage3', '')
    store.update_session('display', {'prep': {'status': 'done'}, 'labeling': {'status': 'done'},
        'training': {'exportRef': 'v2.jsonl'}})
    run('jev', 'done', version='v2')
    run('gpt', 'done', version='v2')
    assert client.get('/session/display').json()['data']['completion']['labelingDone'] is True
    old = client.get('/session/display?version=v1').json()['data']['completion']
    assert not any(old.values())


@pytest.mark.parametrize('query', ['', '?version=v1'])
@pytest.mark.parametrize('failure', ['invalid_collection', 'missing_runs_table'])
def test_completion_failure_is_isolated(client, query, failure):
    seed()
    store.update_session('display', {'prep': {'status': 'done'},
        'training': {'exportRef': 'exports/relevant.jsonl'}})
    sessions.job_manager.set('cluster', 'display', {'status': 'done', 'clusters': {'0': {'size': 1}}})
    store.update_session('display', {'clustering': {'status': 'done', 'version': 'v1', 'at': store.now()}})
    if failure == 'invalid_collection':
        store.update_session('display', {'collectionId': '../invalid'})
        run('jev', 'done')
        run('gpt', 'done')
    else:
        path = database_path('display')
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE unrelated (id INTEGER)')
    response = client.get('/session/display' + query)
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['completion'] == dict(crawlDone=False, prepDone=True,
        labelingDone=failure == 'invalid_collection', exportDone=True, clustersDone=True, segmentDone=False, evidenceDone=False)


@pytest.mark.parametrize('query', ['', '?version=v1'])
def test_missing_cluster_file_is_isolated(client, monkeypatch, query):
    seed()
    store.update_session('display', {'prep': {'status': 'done'},
        'labeling': {'status': 'done'}, 'training': {'exportRef': 'export.jsonl'}})

    def missing_files(*args, **kwargs):
        raise FileNotFoundError('Cluster directory disappeared')

    monkeypatch.setattr(Path, 'glob', missing_files)
    response = client.get('/session/display' + query)
    assert response.status_code == 200
    assert response.json()['data']['completion'] == dict(crawlDone=False, prepDone=True,
        labelingDone=True, exportDone=True, clustersDone=False, segmentDone=False, evidenceDone=False)


@pytest.mark.parametrize('field, completion', [('prep', 'prepDone'),
    ('labeling', 'labelingDone'), ('training', 'exportDone')])
def test_malformed_milestone_is_isolated(field, completion):
    data = {'prep': {'status': 'done'}, 'labeling': {'status': 'done'},
        'training': {'exportRef': 'export.jsonl'}}
    data[field] = None
    result = sessions._completion('display', data)
    assert result[completion] is False
    assert all(result[name] for name in ('prepDone', 'labelingDone', 'exportDone')
        if name != completion)


@pytest.mark.parametrize('status', ['error', 'running', 'not_found'])
@pytest.mark.parametrize('folder', ['clusters', 'clusters_refined'])
def test_partial_cluster_files_never_complete(client, data_dir, status, folder):
    seed()
    root = data_dir / folder / 'display'
    root.mkdir(parents=True)
    filename = 'cluster_0_123.jsonl' if folder == 'clusters' else 'data_123.jsonl'
    (root / filename).write_text('{"cluster":0}\n')
    sessions.job_manager.set('cluster', 'display', {'status': status,
        'clusters': {'0': {'size': 1}}})
    assert client.get('/session/display').json()['data']['completion']['clustersDone'] is False


@pytest.mark.parametrize('restart', ['stage3', 'stage6'])
def test_restarted_version_does_not_inherit_cluster_job(client, restart):
    seed()
    store.update_session('display', {'collectionId': None})
    sessions.job_manager.set('cluster', 'display', {'status': 'done',
        'clusters': {'0': {'size': 1}}})
    store.update_session('display', {'clustering': {'status': 'done', 'version': 'v1', 'at': store.now()}})
    versions.create_version('display', 'v1', restart, '')
    for query in ('', '?version=v2'):
        assert client.get('/session/display' + query).json()['data']['completion']['clustersDone'] is False
    assert client.get('/session/display?version=v1').json()['data']['completion']['clustersDone'] is True


@pytest.fixture
def cluster_service(monkeypatch, data_dir):
    import numpy as np
    from app.services import clustering

    monkeypatch.setattr(clustering, 'job_manager', sessions.job_manager)
    monkeypatch.setattr(clustering, 'read_export', lambda *args: [
        {'doc_id': 'a', 'title': 'alpha'}, {'doc_id': 'b', 'title': 'beta'}])
    monkeypatch.setattr(clustering, 'prepared_root', lambda *args: data_dir)
    monkeypatch.setattr(clustering.VectorStore, 'get',
        lambda self, ids: (ids, np.asarray([[1., 0.], [0., 1.]])))
    return clustering


@pytest.mark.parametrize('restart', ['stage3', 'stage6'])
def test_clustering_publishes_version_local_completion_surviving_restart(
        client, monkeypatch, cluster_service, restart):
    seed()
    store.update_session('display', {'collectionId': None})
    versions.create_version('display', 'v1', restart, '')
    old_path = versions.version_dir('display', 'v1') / 'session.json'
    old_bytes = old_path.read_bytes()
    before_stale = versions._data('display', 'v2')['stale']
    assert not client.get('/session/display').json()['data']['completion']['clustersDone']

    cluster_service.run_clustering({'sid': 'display', 'num_clusters': 1})
    assert sessions.job_manager.get('cluster', 'display')['status'] == 'done'
    saved = versions._data('display', 'v2')
    assert saved['clustering']['status'] == 'done'
    assert saved['clustering']['version'] == 'v2'
    from datetime import datetime
    assert datetime.fromisoformat(saved['clustering']['at'])
    assert saved['stale'] == {k: v for k, v in before_stale.items() if k != 'stage6'}
    for query in ('', '?version=v2'):
        assert client.get('/session/display' + query).json()['data']['completion']['clustersDone']
    monkeypatch.setattr(sessions, 'job_manager', JobManager())
    monkeypatch.setattr(cluster_service, 'job_manager', sessions.job_manager)
    assert client.get('/session/display').json()['data']['completion']['clustersDone']
    assert not client.get('/session/display?version=v1').json()['data']['completion']['clustersDone']
    assert old_path.read_bytes() == old_bytes


def test_failed_cluster_publication_preserves_stale(client, monkeypatch, cluster_service):
    seed()
    store.update_session('display', {'collectionId': None})
    versions.create_version('display', 'v1', 'stage3', '')
    before = versions._data('display', 'v2')
    def fail(*args):
        raise OSError('publication failed')
    monkeypatch.setattr(cluster_service, 'save_jsonl', fail)
    cluster_service.run_clustering({'sid': 'display', 'num_clusters': 1})
    assert sessions.job_manager.get('cluster', 'display')['status'] == 'error'
    assert versions._data('display', 'v2') == before
    assert not client.get('/session/display').json()['data']['completion']['clustersDone']


def test_cluster_cannot_complete_a_different_active_version(client, monkeypatch, cluster_service):
    seed()
    store.update_session('display', {'collectionId': None})
    before = versions._data('display', 'v1')
    monkeypatch.setattr(cluster_service, 'save_jsonl',
        lambda *args: versions.create_version('display', 'v1', 'stage3', ''))
    cluster_service.run_clustering({'sid': 'display', 'num_clusters': 1})
    assert sessions.job_manager.get('cluster', 'display')['status'] == 'error'
    assert versions._data('display', 'v1') == before
    assert 'stage6' in versions._data('display', 'v2')['stale']
    assert 'clustering' not in versions._data('display', 'v2')


def test_session_save_cannot_overwrite_cluster_publication(client):
    seed()
    saved = {'status': 'done', 'version': 'v1', 'at': store.now()}
    store.update_session('display', {'clustering': saved})
    response = client.post('/save-session', json={'sid': 'display',
        'data': {'clustering': {'status': 'running', 'version': 'v2'}}})
    assert response.json()['status'] == 'saved'
    assert versions._data('display', 'v1')['clustering'] == saved
