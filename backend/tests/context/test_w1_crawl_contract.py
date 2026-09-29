"""W1's store/version contracts exercised against W2's public crawl API."""
from contextlib import closing
import pytest
from app.context import store, versions
from app.crawl import control
from app.crawl.queue import CrawlQueue
from tests.crawl.test_crawl_api import env, prepared


def test_crawl_confirm_and_nonconfirm_paths(env):
    store.update_session('S', {'stale': {'stage1': 'old', 'stage2': 'old'}})
    root, _ = prepared(env)
    assert store.load_session('S')['stale'] == {'stage1': 'old'}
    store.update_session('S', {'stale': {'stage2': 'old'}})
    assert env.client.put('/crawl/S/config', json={'channels': ['fixture']}).status_code == 200
    assert env.client.put('/crawl/S/gate', json={'exclusions': ['alpha']}).status_code == 200
    assert store.load_session('S')['stale'] == {'stage1': 'old', 'stage2': 'old'}


@pytest.mark.parametrize('status', ['running', 'stopped', 'interrupted', 'paused', 'done'])
def test_fork_refuses_actual_unfinished_queue_before_copy(env, status, monkeypatch):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as queue:
        queue.connection.execute('UPDATE runs SET status=?', (status,))
    assert control.phase_state('S') == ('running' if status == 'running' else 'unfinished')
    before = store.load_session('S')
    meta = versions.list_versions('S')
    copied = []
    monkeypatch.setattr(versions.shutil, 'copytree', lambda *args: copied.append(args))
    response = env.client.post('/sessions/S/versions', json={'from': 'v1', 'restartFrom': 'stage3'})
    assert response.status_code == 409
    assert response.json()['error'] == {
        'kind': 'conflict', 'code': 'crawl_unfinished',
        'message': '크롤링 수집을 끝낸 뒤 새 버전을 만드세요.',
    }
    assert copied == []
    assert store.load_session('S') == before
    assert versions.list_versions('S') == meta
    assert not versions.version_dir('S', 'v2').exists()


def test_fork_without_collection(env):
    assert versions.create_version('S', 'v1', 'stage3', '') == 'v2'
    assert store.load_session('S').get('collectionId') is None
    assert 'stage2' not in store.load_session('S')['stale']
