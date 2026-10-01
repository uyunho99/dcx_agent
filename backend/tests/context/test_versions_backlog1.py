"""Retire workers only after their active version becomes read-only."""
import os
import socket
import time

import pytest

from app.context import store, versions
from app.work.status import transaction
from app.work.worker import Context
from test_api import create


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Network access is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def add_run(sid, kind, state, version='v1'):
    run_id = f'{version}-{kind}-{state}'
    with transaction(sid) as db:
        db.execute('''INSERT INTO runs
            (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at,action)
            VALUES (?,?,?,'{}',?,?,?,?,?)''',
            (run_id, version, kind, os.getpid(), state, time.time(), time.time(),
             'pause' if state == 'paused' else None))
    return Context(sid, version, kind, {}, run_id)


@pytest.mark.parametrize('kind', ['judge', 'infer'])
def test_paused_worker_is_interrupted_after_version_creation(client, kind):
    sid = create(client)
    context = add_run(sid, kind, 'paused')
    assert versions.create_version(sid, 'v1', 'stage4', '') == 'v2'
    row = context._row()
    assert row['state'] == 'interrupted'
    assert row['action'] == 'stop'
    assert context.should_stop()


def test_running_monitor_allows_creation_and_receives_stop(client):
    sid = create(client)
    context = add_run(sid, 'monitor', 'running')
    response = client.post(f'/sessions/{sid}/versions', json={
        'from': 'v1', 'restartFrom': 'stage5'})
    assert response.status_code == 201
    assert store.load_session(sid)['version'] == 'v2'
    assert context._row()['action'] == 'stop'
    assert context.should_stop()


@pytest.mark.parametrize('kind', ['judge', 'prep', 'train', 'infer'])
def test_running_worker_still_blocks_creation_with_monitor(client, kind):
    sid = create(client)
    worker = add_run(sid, kind, 'running')
    monitor = add_run(sid, 'monitor', 'running')
    response = client.post(f'/sessions/{sid}/versions', json={
        'from': 'v1', 'restartFrom': 'stage4'})
    assert response.status_code == 409
    assert not versions.version_dir(sid, 'v2').exists()
    assert not worker.should_stop()
    assert not monitor.should_stop()


@pytest.mark.parametrize('state', ['done', 'failed', 'interrupted'])
def test_finished_runs_are_unchanged(client, state):
    sid = create(client)
    contexts = [add_run(sid, kind, state) for kind in ('judge', 'infer', 'monitor')]
    before = [dict(context._row()) for context in contexts]
    versions.create_version(sid, 'v1', 'stage4', '')
    assert [dict(context._row()) for context in contexts] == before


def test_restoring_history_stops_previous_active_workers_only(client):
    sid = create(client)
    versions.create_version(sid, 'v1', 'stage4', '')
    previous = add_run(sid, 'judge', 'paused', 'v2')
    unrelated = add_run(sid, 'infer', 'paused', 'v1')
    versions.create_version(sid, 'v1', 'stage4', '')
    assert previous._row()['state'] == 'interrupted'
    assert previous.should_stop()
    assert not unrelated.should_stop()


def test_failed_creation_does_not_stop_workers(client, monkeypatch):
    sid = create(client)
    contexts = [add_run(sid, 'judge', 'paused'), add_run(sid, 'monitor', 'running')]
    before = [dict(context._row()) for context in contexts]
    write_json = versions.write_json

    def fail_meta(path, data):
        if path.name == 'meta.json':
            raise OSError('metadata write failed')
        write_json(path, data)

    monkeypatch.setattr(versions, 'write_json', fail_meta)
    with pytest.raises(OSError, match='metadata write failed'):
        versions.create_version(sid, 'v1', 'stage4', '')
    assert store.load_session(sid)['version'] == 'v1'
    assert not versions.version_dir(sid, 'v2').exists()
    assert [dict(context._row()) for context in contexts] == before


def test_worker_stop_failure_does_not_fail_committed_version(client, monkeypatch, caplog):
    import sqlite3
    sid = create(client)
    ctx = add_run(sid, 'judge', 'paused')
    def fail_stop(*args):
        raise sqlite3.OperationalError('sensitive detail')
    monkeypatch.setattr(versions, '_stop_readonly_workers', fail_stop)
    response = client.post(f'/sessions/{sid}/versions', json={
        'from': 'v1', 'restartFrom': 'stage4'})
    assert response.status_code == 201
    assert store.load_session(sid)['version'] == 'v2'
    assert versions._meta(sid)['activeVersion'] == 'v2'
    assert versions._meta(sid)['versions'][0]['readonly']
    assert ctx._row()['state'] == 'paused'
    assert 'OperationalError' in caplog.text
    assert 'sensitive detail' not in caplog.text
