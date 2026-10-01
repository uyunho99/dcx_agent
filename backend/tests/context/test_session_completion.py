"""Completion is a local, read-only projection for active and selected versions."""
from contextlib import closing
import socket

import pytest

from app.context import store, versions
from app.crawl.queue import CrawlQueue
from app.jobs.manager import JobManager
from app.routers import sessions
from app.work.status import transaction


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
        labelingDone=False, exportDone=False, clustersDone=False)
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


@pytest.mark.parametrize('source', ['job', 'clusters', 'clusters_refined'])
def test_cluster_result_and_session_milestones(client, data_dir, source):
    seed()
    store.update_session('display', {'prep': {'status': 'done'}, 'labeling': {'status': 'done'},
        'training': {'exportRef': 'exports/relevant.jsonl'}})
    if source == 'job':
        sessions.job_manager.set('cluster', 'display', {'status': 'done', 'clusters': {'0': {'size': 1}}})
    else:
        root = data_dir / source / 'display'
        root.mkdir(parents=True)
        (root / ('cluster_0_123.jsonl' if source == 'clusters' else 'data_123.jsonl')).write_text('{"cluster":0}\n')
    result = client.get('/session/display').json()['data']['completion']
    assert result == dict(crawlDone=False, prepDone=True, labelingDone=True, exportDone=True, clustersDone=True)


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
