"""Stage 3–5 version boundaries and durable snapshot contracts."""
import sqlite3
from threading import Event, Thread

import pytest

from app.context import store, versions
from app.label.store import LabelStore
from app.work import runner
from test_api import create


def test_save_session_keeps_stage3_5_keys(client):
    sid = create(client)
    owned = {key: {'status': 'done', 'marker': key} for key in ('prep', 'labeling', 'training')}
    store.update_session(sid, owned)
    response = client.post('/save-session', json={'sid': sid, 'data': {
        **{key: {'status': 'none'} for key in owned}, 'step': 'training'}})
    assert response.json()['status'] == 'saved'
    assert {key: store.load_session(sid)[key] for key in owned} == owned


@pytest.mark.parametrize('kind', ['prep', 'judge', 'train', 'infer'])
def test_running_worker_blocks_version(client, monkeypatch, kind):
    sid = create(client)
    monkeypatch.setattr(runner, 'status', lambda _: [dict(kind=kind, state='running', progress=.62, runId='r')])
    response = client.post(f'/sessions/{sid}/versions', json={'from': 'v1', 'restartFrom': 'stage4'})
    assert response.status_code == 409
    assert not versions.version_dir(sid, 'v2').exists()


def test_paused_judge_allows_version(client, monkeypatch):
    sid = create(client)
    monkeypatch.setattr(runner, 'status', lambda _: [dict(kind='judge', state='paused', progress=.62, runId='r')])
    assert versions.create_version(sid, 'v1', 'stage4', '') == 'v2'


@pytest.mark.parametrize('kind,state,label', [('judge', 'running', '판정 62%'),
    ('train', 'running', '학습 중'), ('judge', 'interrupted', '중단됨 · 이어서 진행')])
def test_worker_activity_badge(client, monkeypatch, kind, state, label):
    sid = create(client)
    monkeypatch.setattr(runner, 'status', lambda _: [dict(kind=kind, state=state, progress=.62, runId='r')])
    activity = store.session_activity(sid, store.load_session(sid))
    assert activity and activity['label'] == label
    assert activity['status'] == state
    assert client.get('/sessions').json()['sessions'][0]['activity'] == activity


@pytest.mark.parametrize('stage', [3, 4, 5])
def test_restart_stage_state(client, stage):
    sid = create(client)
    ref = dict(collectionId='c1', prepKey='p_123456789abc')
    store.update_session(sid, {'prep': {'status': 'done', 'derivedRef': ref},
        'labeling': {'started': True, 'judgeRefs': {'jev': 'shared/cache'}, 'judgeRuns': {'jev': 'old'}},
        'training': {'status': 'done', 'modelId': 'old', 'exportRef': 'old/export'}})
    labels = LabelStore(store.session_dir(sid))
    with labels._db() as db:
        db.execute("INSERT INTO queue VALUES ('d', 'labeler_failed', 0, 'open')")
        db.execute("INSERT INTO human VALUES ('d','alice','escalate','{}',NULL,NULL,1)")
    versions.create_version(sid, 'v1', f'stage{stage}', '')
    data = store.load_session(sid)
    assert data['prep']['derivedRef'] == ref
    assert data['prep']['status'] == ('stale' if stage == 3 else 'done')
    assert data['training']['status'] == 'stale'
    assert 'exportRef' not in data['training']
    if stage <= 4:
        assert data['labeling']['started'] is False
        assert data['labeling']['judgeRefs'] == {'jev': 'shared/cache'}
        assert 'judgeRuns' not in data['labeling']
        with LabelStore(store.session_dir(sid))._db() as db:
            assert db.execute('SELECT count(*) FROM human').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM queue').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM stale_queue').fetchone()[0] == 1
    else:
        assert data['labeling']['started'] is True


@pytest.mark.parametrize('stage', ['stage3', 'stage4', 'stage5'])
def test_compare_stage_metrics(client, stage):
    sid = create(client)
    store.write_json(store.session_dir(sid) / 'stage_3.json', {'after': 10})
    store.write_json(store.session_dir(sid) / 'stage_5.json', {'accepted': 8})
    versions.create_version(sid, 'v1', 'stage5', '')
    store.write_json(store.session_dir(sid) / 'stage_3.json', {'after': 20})
    store.write_json(store.session_dir(sid) / 'stage_5.json', {'accepted': 18})
    name = 'stage_3' if stage == 'stage3' else 'stage_5'
    key = 'after' if stage == 'stage3' else 'accepted'
    assert versions.compare(sid, 'v1', 'v2', stage)[name] == {
        'before': {key: 10 if stage == 'stage3' else 8},
        'after': {key: 20 if stage == 'stage3' else 18}}


def test_version_copy_sqlite_consistent(client, monkeypatch):
    sid = create(client)
    labels = LabelStore(store.session_dir(sid))
    source = sqlite3.connect(labels.path)
    source.execute('PRAGMA journal_mode=WAL')
    source.execute("INSERT INTO human VALUES ('before','alice','escalate','{}',NULL,NULL,1)")
    source.commit()
    copied, submitted = Event(), Event()
    snapshots = []
    real_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        def backup(self, target, **kwargs):
            super().backup(target, **kwargs)
            snapshots.append(target.execute('SELECT count(*) FROM human').fetchone()[0])
            copied.set()
            assert submitted.wait(5)

    def connect(path, *args, **kwargs):
        if str(path).split('?')[0].endswith('v1/labels.sqlite'):
            kwargs['factory'] = Connection
        return real_connect(path, *args, **kwargs)

    def submit():
        if copied.wait(5):
            labels.submit('during', 'alice', 'escalate', {
                'anchor': True, 'situation': True,
                'sem': dict.fromkeys(('sense', 'feel', 'think', 'act', 'relate', 'outcome'), 1)})
            submitted.set()

    monkeypatch.setattr(sqlite3, 'connect', connect)
    thread = Thread(target=submit)
    thread.start()
    try:
        versions.create_version(sid, 'v1', 'stage5', '')
        assert snapshots == [1], 'SQLite backup API must define the snapshot'
        with real_connect(store.session_dir(sid) / 'labels.sqlite') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute('SELECT count(*) FROM human').fetchone()[0] == snapshots[0]
        assert source.execute('SELECT count(*) FROM human').fetchone()[0] == 2
    finally:
        copied.set()
        thread.join(6)
        source.close()
