"""T10: only a successfully recompleted stage loses its stale banner."""
import os
import socket
import time

import pytest

from app.config import settings
from app.context import store, versions
from app.model import export
from app.prep import pipeline
from app.work.status import transaction
from app.work.worker import Context, execute
from tests.prep.test_pipeline import setup, doc, Context as PrepContext
from tests.label.test_judge import setup_judge
from tests.model.test_model_mode import prepared
from tests.model.test_export import seed


STALE = {f'stage{n}': 'stage3 changed in v2' for n in range(3, 7)}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('T10 tests must not access the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def mark(sid, version):
    path = versions.version_dir(sid, version) / 'session.json'
    data = store.read_json(path)
    data['stale'] = dict(STALE)
    store.write_json(path, data)


def assert_stale(sid, version, cleared=None):
    assert versions._data(sid, version)['stale'] == {
        key: value for key, value in STALE.items() if key != cleared}


@pytest.mark.parametrize('reuse', [False, True])
def test_prep_completion_clears_only_stage3(setup, reuse):
    setup([doc()])
    if reuse:
        pipeline.run_prep(PrepContext(), 's', 'v1')
    version = versions.create_version('s', 'v1', 'stage3', '')
    mark('s', version)
    pipeline.run_prep(PrepContext(), 's', version)
    assert versions._data('s', version)['prep']['reused'] is reuse
    assert_stale('s', version, 'stage3')
    assert 'stale' not in versions._data('s', 'v1')


def test_interrupted_prep_keeps_stale(setup):
    setup([doc()])
    version = versions.create_version('s', 'v1', 'stage3', '')
    mark('s', version)
    pipeline.run_prep(PrepContext(stop_after=0), 's', version)
    assert_stale('s', version)


def add_run(labeler, state='running', version='v2', run_id=None, started=None):
    run_id = run_id or labeler
    now = time.time()
    with transaction('session') as db:
        db.execute('''INSERT INTO runs
            (run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at)
            VALUES (?,?,'judge',?,'{}',?,?,?,?)''',
            (run_id, version, labeler, os.getpid(), state, now, started or now))
    return Context('session', version, 'judge', {'labeler': labeler}, run_id)


@pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
    setup_judge.prepare(version='v2')
    monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
    mark('session', 'v2')
    # A completed worker in another version cannot satisfy this version.
    add_run('gpt', 'done', 'v1', 'old-version')
    if other_state != 'missing':
        add_run('gpt', other_state)
    execute(add_run('jev'))
    assert_stale('session', 'v2')
    assert versions._data('session', 'v2').get('labeling', {}).get('status') != 'done'
    execute(add_run('gpt', run_id='gpt-retry'))
    assert_stale('session', 'v2', 'stage4')
    assert versions._data('session', 'v2')['labeling']['status'] == 'done'
    with transaction('session') as db:
        assert db.execute("SELECT state FROM runs WHERE run_id='gpt-retry'").fetchone()[0] == 'done'


@pytest.mark.parametrize('action', ['stop', 'pause'])
def test_stopped_judge_preserves_stale(setup_judge, monkeypatch, action):
    setup_judge.prepare(version='v2')
    monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
    mark('session', 'v2')
    add_run('jev', 'done')
    ctx = add_run('gpt')
    with transaction('session') as db:
        db.execute("UPDATE runs SET action=? WHERE run_id='gpt'", (action,))
    from app.context.stale import judge_done
    judge_done(ctx)
    assert_stale('session', 'v2')
    assert versions._data('session', 'v2').get('labeling', {}).get('status') != 'done'


def test_export_clears_only_stage5(data_dir):
    sid, _ = prepared(data_dir)
    version = versions.create_version(sid, 'v1', 'stage5', '')
    seed(sid)
    mark(sid, version)
    result = export.write(sid, version, without_model=True)
    assert (data_dir / result['exportRef']).exists()
    assert_stale(sid, version, 'stage5')
    assert 'stale' not in versions._data(sid, 'v1')


def test_failed_export_preserves_stale(data_dir):
    sid, _ = prepared(data_dir)
    version = versions.create_version(sid, 'v1', 'stage5', '')
    mark(sid, version)
    with pytest.raises(store.StoreError):
        export.write(sid, version, without_model=True)
    assert_stale(sid, version)


def test_clear_is_idempotent_and_version_local(data_dir):
    from app.context.stale import clear_stale
    sid, _ = prepared(data_dir)
    version = versions.create_version(sid, 'v1', 'stage3', '')
    mark(sid, 'v1')
    mark(sid, version)
    clear_stale(sid, version, 'stage3')
    clear_stale(sid, version, 'stage3')
    assert_stale(sid, version, 'stage3')
    assert_stale(sid, 'v1')


@pytest.mark.parametrize('recovery', ['replay', 'active_read', 'selected_read'])
def test_judge_publication_recovers_after_write_failure(client, monkeypatch, recovery):
    from app.context.stale import judge_done

    store.update_session('session', {'schemaVersion': 2, 'sid': 'session',
        'version': 'v1', 'labeling': {'status': 'stale'}})
    mark('session', 'v1')
    add_run('jev', 'done', version='v1')
    ctx = add_run('gpt', version='v1')
    original_write = store.write_json
    attempts = []

    def failed_write(path, data):
        attempts.append(path)
        raise OSError('injected publication failure')

    monkeypatch.setattr(store, 'write_json', failed_write)
    with pytest.raises(OSError, match='injected publication failure'):
        judge_done(ctx)
    with transaction('session') as db:
        assert [r['state'] for r in db.execute('SELECT state FROM runs')] == ['done', 'done']
    assert_stale('session', 'v1')
    # Read recovery is fail-soft while publication is still unavailable.
    response = client.get('/session/session?version=v1')
    assert response.status_code == 200
    assert 'stage4' in response.json()['data']['stale']
    assert_stale('session', 'v1')

    writes = []
    def restored_write(path, data):
        writes.append(path)
        original_write(path, data)

    monkeypatch.setattr(store, 'write_json', restored_write)
    for _ in range(2):
        if recovery == 'replay':
            judge_done(ctx)
        else:
            query = '?version=v1' if recovery == 'selected_read' else ''
            response = client.get('/session/session' + query)
            assert response.status_code == 200
            assert 'stage4' not in response.json()['data']['stale']
            assert response.json()['data']['labeling']['status'] == 'done'
    assert_stale('session', 'v1', 'stage4')
    assert versions._data('session', 'v1')['labeling']['status'] == 'done'
    assert len(writes) == 1
    assert len(attempts) == 2


@pytest.mark.parametrize('explicit_version', [False, True])
def test_reconcile_judge_done_skips_readonly_version(client, monkeypatch, explicit_version):
    from app.context.stale import reconcile_judge_done

    store.update_session('session', {'schemaVersion': 2, 'sid': 'session',
        'version': 'v1', 'labeling': {'status': 'stale'}})
    mark('session', 'v1')
    add_run('jev', 'done', version='v1')
    add_run('gpt', 'done', version='v1')
    versions.create_version('session', 'v1', 'stage3', '')
    old_path = versions.version_dir('session', 'v1') / 'session.json'
    before = old_path.read_bytes()
    old_data = versions._data('session', 'v1')
    writes = []
    original_write = store.write_json
    def record_write(path, data):
        writes.append(path)
        original_write(path, data)
    monkeypatch.setattr(store, 'write_json', record_write)
    result = reconcile_judge_done('session', old_data, 'v1' if explicit_version else None)
    assert result == old_data
    assert client.get('/session/session?version=v1').status_code == 200
    assert writes == []
    assert old_path.read_bytes() == before
    assert versions._data('session', 'v2')['labeling']['status'] == 'stale'
