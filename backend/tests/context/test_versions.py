from app.context.store import update_session, load_session, session_dir
from app.context.versions import create_version, compare
from test_api import create


def test_create_version_copies_all_but_collection(client, data_dir):
    sid = create(client)
    update_session(sid, {'collectionId': 'c1'})
    (session_dir(sid) / 'keyword_events.jsonl').write_text('event')
    collection = data_dir / 'crawl' / sid / 'collections' / 'c1'
    collection.mkdir(parents=True)
    (collection / 'manifest.json').write_text('{}')
    assert create_version(sid, 'v1', 'stage1', 'again') == 'v2'
    assert (session_dir(sid) / 'keyword_events.jsonl').read_text() == 'event'
    assert load_session(sid)['collectionId'] == 'c1'
    assert list(collection.parent.iterdir()) == [collection]
    from app.services.training import load_json
    assert load_json(f'sessions/{sid}/session.json')['version'] == 'v2'


def test_restart_marks_downstream_stale(client):
    sid = create(client)
    create_version(sid, 'v1', 'stage1', '')
    assert 'stage2' in load_session(sid)['stale']
    update_session(sid, {'keywords': []})
    assert 'stage1' not in load_session(sid)['stale']
    assert 'stage2' in load_session(sid)['stale']


def test_old_version_readonly(client):
    sid = create(client)
    create_version(sid, 'v1', 'stage1', '')
    assert client.patch(f'/session/{sid}?version=v1', json={'step': 'r2'}).status_code == 409


def test_version_blocked_while_job_running(client):
    sid = create(client)
    update_session(sid, {'keywordRounds': {'1': {'job': {'status': 'running'}}}})
    r = client.post(f'/sessions/{sid}/versions', json={'from': 'v1', 'restartFrom': 'stage1', 'note': ''})
    assert r.status_code == 409
    assert r.json()['error']['kind'] == 'conflict'


def test_compare_stage1_added_removed_moved(client):
    sid = create(client)
    update_session(sid, {'keywords': [{'id': 'a', 'axis': 'x'}, {'id': 'b', 'axis': 'x'}]})
    create_version(sid, 'v1', 'stage1', '')
    update_session(sid, {'keywords': [{'id': 'a', 'axis': 'y'}, {'id': 'c', 'axis': 'y'}]})
    diff = compare(sid, 'v1', 'v2', 'stage1')
    assert [k['id'] for k in diff['added']] == ['c']
    assert [k['id'] for k in diff['removed']] == ['b']
    assert diff['moved'] == [{'id': 'a', 'from': 'x', 'to': 'y'}]
    assert diff['distribution'] == {'x': -2, 'y': 2}


def test_compare_stage2_same_collection(client):
    sid = create(client)
    update_session(sid, {'collectionId': 'c1'})
    create_version(sid, 'v1', 'stage2', '')
    assert compare(sid, 'v1', 'v2', 'stage2') == {'same': True}


def test_active_history_stays_readonly(client):
    sid = create(client)
    create_version(sid, 'v1', 'stage1', '')
    assert client.put(f'/sessions/{sid}/active-version', json={'version': 'v1'}).status_code == 200
    assert client.patch(f'/session/{sid}', json={'step': 'r2'}).status_code == 409
    assert create_version(sid, 'v1', 'stage0', 'restore') == 'v3'
    assert client.patch(f'/session/{sid}', json={'step': 'start'}).status_code == 200


def test_version_activation_failure_keeps_original(client, monkeypatch):
    from app.context import versions
    import pytest
    sid = create(client)
    def fail(*args):
        raise OSError('activation failed')
    monkeypatch.setattr(versions, '_activate_link', fail)
    with pytest.raises(OSError):
        create_version(sid, 'v1', 'stage1', '')
    assert load_session(sid)['version'] == 'v1'
    assert not versions.version_dir(sid, 'v2').exists()


def test_crawl_running_blocks_even_with_failed_round(client, monkeypatch):
    import sys
    from types import ModuleType
    sid = create(client)
    update_session(sid, {'keywordRounds': {'1': {'job': {'status': 'failed'}}}})
    module = ModuleType('app.crawl.control')
    module.activity = lambda _: {'kind': 'crawl', 'status': 'running', 'progress': .5, 'updatedAt': None}
    monkeypatch.setitem(sys.modules, 'app.crawl.control', module)
    assert client.post(f'/sessions/{sid}/versions', json={'from': 'v1', 'restartFrom': 'stage2'}).status_code == 409


def test_compare_stage2_counts(client, data_dir):
    import json
    sid = create(client)
    update_session(sid, {'collectionId': 'c1'})
    create_version(sid, 'v1', 'stage2', '')
    update_session(sid, {'collectionId': 'c2'})
    for cid, count in [('c1', 2), ('c2', 5)]:
        path = data_dir / 'crawl' / sid / 'collections' / cid
        path.mkdir(parents=True)
        (path / 'report.json').write_text(json.dumps({'counts': {'air': {'youtube': count}}}))
    assert compare(sid, 'v1', 'v2', 'stage2')['counts'] == {'air': {'youtube': 3}}
