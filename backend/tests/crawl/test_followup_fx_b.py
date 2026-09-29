from contextlib import closing
from types import SimpleNamespace
import time

import pytest
from app.context import store, versions
from app.crawl import control, worker
from app.crawl.queue import CrawlQueue
from tests.crawl.test_crawl_api import env, prepared


@pytest.mark.parametrize('source_done', [False, True])
def test_fork_uses_source_collection(env, source_done):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET kind='detail',status=?", ('done' if source_done else 'stopped',))
        q.connection.execute("UPDATE urls SET status='done'")
    versions.create_version('S', 'v1', 'stage3', '')
    if source_done:
        control.start_list('S')
        with closing(CrawlQueue(control.collection_dir('S') / 'queue.sqlite')) as q:
            q.connection.execute("UPDATE runs SET status='stopped'")
    versions.create_version('S', 'v1', 'stage3', '')
    assert store.load_session('S')['collectionId'] == ('c1' if source_done else None)
    assert versions._data('S', 'v1')['collectionId'] == 'c1'


@pytest.mark.parametrize('new_run', [False, True])
def test_fenced_worker_cannot_save(tmp_path, new_run):
    old = worker._Run(tmp_path, 'S', 'list', ['fixture'], None, {})
    try:
        old.q.connection.execute("UPDATE runs SET status='interrupted' WHERE run_id=?", (old.id,))
        if new_run:
            old.q.register_run('list')
        reset = {'channels': {'fixture': {'status': 'running'}}, 'paused_channels': []}
        store.write_json(tmp_path / 'worker_state.json', reset)
        old.channels['fixture']['status'] = 'paused_blocked'
        old.save()
        assert store.read_json(tmp_path / 'worker_state.json') == reset
        old.close('stopped')
        assert store.read_json(tmp_path / 'worker_state.json') == reset
    finally:
        old.q.close()


def test_stale_worker_fenced_and_polled(env, monkeypatch):
    control.start_list('S')
    root = control.collection_dir('S')
    monkeypatch.setattr(control.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='python -m app.crawl.worker'))
    events = []
    monkeypatch.setattr(control.os, 'kill', lambda *a: events.append('term'))
    monkeypatch.setattr(control, 'pid_alive', lambda pid: len(events) < 3)
    monkeypatch.setattr(control.time, 'sleep', lambda seconds: events.append('poll'))
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time()-120,))
        assert control._live(q) is None
        assert control.latest_run(q)['status'] == 'interrupted'
    assert events == ['term', 'poll', 'poll']


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_delete_unreadable_versioned_session(env, damage):
    path = versions.version_dir('S', 'v1') / 'session.json'
    if damage == 'missing':
        path.unlink()
    else:
        path.write_text('{broken')
    response = env.client.delete('/delete-session/S')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert not (store.root_dir('S') / 'meta.json').exists()


@pytest.mark.parametrize('message,code', [
    ('Sources are unavailable', 'sources_unavailable'),
    ('Worker is already running', 'worker_running'),
    ('Unknown resume channel', 'unknown_resume_channel'),
    ('Finish list collection before starting detail', 'p1_unfinished'),
    ('Finished collections are immutable', 'finished_collection'),
    ('읽기 전용 버전입니다', 'readonly_version'),
    ('다른 버전이 활성화되었습니다', 'version_conflict'),
])
def test_crawl_error_codes(env, monkeypatch, message, code):
    def fail(*a, **k):
        raise store.StoreError(message)
    monkeypatch.setattr(control, 'resume', fail)
    error = env.client.post('/crawl/S/resume').json()['error']
    assert error['message'] == message
    assert error['code'] == code


def test_invalid_request_code(env):
    error = env.client.post('/crawl/S/resume', json={'min_interval_s': {'fixture': -1}}).json()['error']
    assert error['code'] == 'invalid_request'


def test_new_reservation_fences_still_running_worker(tmp_path):
    old = worker._Run(tmp_path, 'S', 'list', ['fixture'], None, {})
    try:
        now = time.time() + 1
        old.q.connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
            ('new', str(tmp_path), 'list', 123, 'starting', now, now, '{}'))
        reset = {'paused_channels': [], 'run_id': 'new'}
        store.write_json(tmp_path / 'worker_state.json', reset)
        old.save()
        assert store.read_json(tmp_path / 'worker_state.json') == reset
    finally:
        old.close('stopped')


def test_stale_worker_wait_is_bounded(env, monkeypatch):
    control.start_list('S')
    monkeypatch.setattr(control.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='python -m app.crawl.worker'))
    monkeypatch.setattr(control.os, 'kill', lambda *a: None)
    elapsed = [0.0]
    monkeypatch.setattr(control.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(control.time, 'sleep', lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    with closing(CrawlQueue(control.collection_dir('S') / 'queue.sqlite')) as q:
        q.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time()-120,))
        assert control._live(q) is None
    assert elapsed[0] == pytest.approx(5)


def test_delete_keeps_path_validation(env):
    from app.routers.sessions import delete_session
    response = delete_session('../S')
    assert response.status_code == 400
    assert store.load_session('S') is not None


def test_storage_error_code(env, monkeypatch):
    def fail(*a, **k):
        raise OSError('private path')
    monkeypatch.setattr(control, 'status', fail)
    response = env.client.get('/crawl/S/status')
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'storage_error'
    assert 'private path' not in response.text
