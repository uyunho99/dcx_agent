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


@pytest.mark.parametrize('status', ['stopped', 'interrupted', 'paused'])
def test_fork_detaches_actual_unfinished_queue(env, status):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as queue:
        queue.connection.execute('UPDATE runs SET status=?', (status,))
    assert control.phase_state('S') == 'unfinished'
    cid = store.load_session('S')['collectionId']
    versions.create_version('S', 'v1', 'stage3', '')
    assert versions._data('S', 'v1')['collectionId'] == cid
    assert store.load_session('S')['collectionId'] is None
    assert 'stage2' in store.load_session('S')['stale']
