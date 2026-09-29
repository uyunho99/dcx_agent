from app.context.store import update_session, load_session, session_dir
from app.context.versions import create_version, compare
from test_api import create


def test_create_version_copies_all_but_collection(client, data_dir, monkeypatch):
    from app.crawl import control
    monkeypatch.setattr(control, 'phase_state', lambda sid, collection_id=None: 'done')
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
    update_session(sid, {'keywords': []}, confirm_stage='stage1')
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


def test_compare_stage2_same_collection(client, monkeypatch):
    from app.crawl import control
    monkeypatch.setattr(control, 'phase_state', lambda sid, collection_id=None: 'done')
    sid = create(client)
    update_session(sid, {'collectionId': 'c1'})
    create_version(sid, 'v1', 'stage2', '')
    assert compare(sid, 'v1', 'v2', 'stage2') == {'same': True}


def test_readonly_history_cannot_be_activated(client):
    import pytest
    from app.context.store import StoreError, read_json, root_dir
    from app.context.versions import set_active
    sid = create(client)
    create_version(sid, 'v1', 'stage1', '')
    before = read_json(root_dir(sid) / 'meta.json')
    with pytest.raises(StoreError, match='읽기 전용') as error:
        set_active(sid, 'v1')
    assert error.value.status == 409
    response = client.put(f'/sessions/{sid}/active-version', json={'version': 'v1'})
    assert response.status_code == 409
    assert response.json()['error']['kind'] == 'conflict'
    assert '읽기 전용' in response.json()['error']['message']
    assert read_json(root_dir(sid) / 'meta.json') == before
    assert (root_dir(sid) / 'active').resolve() == session_dir(sid)
    assert client.get(f'/context/{sid}?version=v1').status_code == 200
    assert client.get(f'/session/{sid}?version=v1').json()['data']['version'] == 'v1'
    assert client.patch(f'/session/{sid}?version=v1', json={'step': 'r2'}).status_code == 409
    assert create_version(sid, 'v1', 'stage0', 'restore') == 'v3'
    assert client.patch(f'/session/{sid}', json={'step': 'start'}).status_code == 200


def test_version_operations_keep_legacy_full_saves_writable(client):
    sid = create(client)
    operations = [
        ('activate', 'v1'), ('create', 'v1'), ('activate', 'v1'),
        ('activate', 'v2'), ('create', 'v1'), ('activate', 'v2'),
        ('create', 'v2'), ('activate', 'v3'), ('activate', 'v4'),
    ]
    for i, (operation, version) in enumerate(operations):
        if operation == 'create':
            assert client.post(f'/sessions/{sid}/versions', json={
                'from': version, 'restartFrom': 'stage1', 'note': 'restore',
            }).status_code == 201
        else:
            client.put(f'/sessions/{sid}/active-version', json={'version': version})
        before = load_session(sid)
        response = client.post('/save-session', json={'sid': sid, 'data': {
            'keywordRounds': {}, 'projectContext': {}, 'version': 'v0',
            'labeledData': [{'label': i}], 'stageResults': {'stage3': {'iteration': i}},
        }})
        assert response.status_code == 200
        assert response.json()['status'] == 'saved'
        saved = load_session(sid)
        assert saved['labeledData'] == [{'label': i}]
        assert saved['stageResults']['stage3'] == {'iteration': i}
        assert saved['projectContext'] == before['projectContext']
        assert saved['version'] == before['version']


def test_version_operations_allow_null_job(client):
    sid = create(client)
    update_session(sid, {'keywordRounds': {'1': {'job': None}}})
    assert client.put(f'/sessions/{sid}/active-version', json={'version': 'v1'}).status_code == 200
    assert client.post(f'/sessions/{sid}/versions', json={
        'from': 'v1', 'restartFrom': 'stage1',
    }).status_code == 201


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
