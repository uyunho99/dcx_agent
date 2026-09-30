"""Regression coverage for T15 review round one."""
import os
from types import SimpleNamespace

import pytest

from app.context import store, versions
from app.work.status import database_path, transaction
from test_api import create


def record_run(sid, run_id, state, *, version='v1', kind='judge', labeler='jev', started=1):
    with transaction(sid) as db:
        db.execute('''INSERT INTO runs
            (run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (run_id, version, kind, labeler, '{}', os.getpid(), state, started, started))


@pytest.mark.parametrize('state', ['interrupted', 'failed'])
@pytest.mark.parametrize('kind,labeler', [('judge', 'jev'), ('train', None)])
def test_completed_replacement_clears_badge(client, state, kind, labeler):
    sid = create(client)
    # Insert out of chronological order to exercise the persisted start ordering.
    record_run(sid, 'replacement', 'done', kind=kind, labeler=labeler, started=2)
    record_run(sid, 'old', state, kind=kind, labeler=labeler)
    assert store.session_activities(sid, store.load_session(sid)) == []
    assert client.get('/sessions').json()['sessions'][0]['activity'] is None


def test_old_version_does_not_badge_active_version(client):
    sid = create(client)
    record_run(sid, 'old', 'interrupted')
    versions.create_version(sid, 'v1', 'stage5', '')
    assert store.session_activities(sid, store.load_session(sid)) == []
    # Even a caller holding old session data must use the active version's runs.
    assert store.session_activities(sid, versions._data(sid, 'v1')) == []
    assert client.get('/sessions').json()['sessions'][0]['activity'] is None


def test_latest_runs_are_independent_by_kind_and_labeler(client):
    sid = create(client)
    record_run(sid, 'jev', 'interrupted')
    record_run(sid, 'gpt', 'done', labeler='gpt', started=2)
    record_run(sid, 'train', 'done', kind='train', labeler=None, started=3)
    assert [a['runId'] for a in store.session_activities(sid, store.load_session(sid))] == ['jev']


def test_sessions_get_does_not_create_runs_database(client):
    sid = create(client)
    path = database_path(sid)
    assert not path.exists()
    assert client.get('/sessions').status_code == 200
    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize('stage', range(6))
def test_restart_invalidates_reports_for_status_compare_and_monitor(client, monkeypatch, stage):
    from app.config import settings
    from app.label.store import LabelStore
    from app.model import export, monitor

    sid = create(client)
    store.update_session(sid, {'prep': {'status': 'done'}, 'training': {'status': 'done'}})
    old = versions.version_dir(sid, 'v1')
    store.write_json(old / 'stage_3.json', {'after': 10})
    store.write_json(old / 'stage_5.json', {'accepted': 8})
    versions.create_version(sid, 'v1', f'stage{stage}', '')
    current = store.session_dir(sid)
    assert not (current / 'stage_5.json').exists()
    assert (current / 'stage_3.json').exists() == (stage > 3)
    assert store.read_json(old / 'stage_5.json') == {'accepted': 8}
    assert store.read_json(old / 'stage_3.json') == {'after': 10}
    response = client.get(f'/train/{sid}/status')
    assert response.status_code == 200
    assert response.json()['stage5'] is None
    assert response.json()['training']['status'] == 'stale'
    compared = versions.compare(sid, 'v1', 'v2', 'stage5')
    assert compared == {'stage_5': {'before': {'accepted': 8}, 'after': None}, 'same': False}
    if stage <= 3:
        compared = versions.compare(sid, 'v1', 'v2', 'stage3')
        assert compared['stage_3'] == {'before': {'after': 10}, 'after': None}
        assert compared['same'] is False

    # A monitor completion must not republish the invalidated report.
    monkeypatch.setattr(settings, 'monitor_rate', .01)
    monkeypatch.setattr(monitor.infer, 'documents', lambda *args: {})
    monkeypatch.setattr(monitor, 'caches_for', lambda *args: {})
    labels = LabelStore(current)
    monitor.infer.prediction_schema(labels)
    monkeypatch.setattr(monitor, 'labels_for', lambda *args: labels)
    writes = []
    monkeypatch.setattr(export, 'write_stage5', lambda *args: writes.append(args))
    monitor.run_worker(SimpleNamespace(sid=sid, version='v2', args={'modelId': 'm'},
        heartbeat=lambda *args: None, should_stop=lambda: False))
    assert writes == []
    assert not (current / 'stage_5.json').exists()


def test_stale_preparation_does_not_fall_back_to_shared_report(client, monkeypatch, tmp_path):
    from app.known import store as known

    sid = create(client)
    shared = tmp_path / 'prepared'
    store.write_json(shared / 'stage_3.json', {'after': 10})
    monkeypatch.setattr(known, 'prepared_root', lambda *args: shared)
    store.update_session(sid, {'prep': {'status': 'done', 'derivedRef': {'kept': True}}})
    versions.create_version(sid, 'v1', 'stage3', '')
    compared = versions.compare(sid, 'v1', 'v2', 'stage3')
    assert compared['stage_3'] == {'before': {'after': 10}, 'after': None}
    assert compared['same'] is False
    # Once preparation confirms reuse, the shared report is valid again.
    store.update_session(sid, {'prep': {'status': 'done'}})
    assert versions.compare(sid, 'v1', 'v2', 'stage3')['stage_3']['after'] == {'after': 10}


def test_stage3_compare_includes_both_reports(client):
    sid = create(client)
    for name, report in [('stage_3', {'after': 10}), ('stage_5', {'accepted': 8})]:
        store.write_json(store.session_dir(sid) / f'{name}.json', report)
    versions.create_version(sid, 'v1', 'stage3', '')
    store.write_json(store.session_dir(sid) / 'stage_3.json', {'after': 20})
    store.write_json(store.session_dir(sid) / 'stage_5.json', {'accepted': 18})
    assert versions.compare(sid, 'v1', 'v2', 'stage3') == {
        'stage_3': {'before': {'after': 10}, 'after': {'after': 20}},
        'stage_5': {'before': {'accepted': 8}, 'after': {'accepted': 18}},
        'same': False}


@pytest.mark.parametrize('predecessor', [None, 'failed', 'interrupted', 'running'])
def test_qa_q8_finished_latest_training_has_no_badge(client, predecessor):
    sid = create(client)
    if predecessor:
        record_run(sid, 'old-train', predecessor, kind='train', labeler=None)
    record_run(sid, 'finished-train', 'done', kind='train', labeler=None, started=2)
    assert store.session_activities(sid, store.load_session(sid)) == []
    assert client.get('/sessions').json()['sessions'][0]['activity'] is None
