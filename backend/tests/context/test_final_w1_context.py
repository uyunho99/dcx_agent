import pytest
from app.context import store, versions
from app.config import settings
from app.external.base import integration_status
from test_api import create, CTX

@pytest.mark.parametrize('patch', [{'keywords': []}, {'keywordRounds': {}}, {'crawlConfig': {}}, {'collectionId': None}, {'stageResults': {'stage1': {}}}])
def test_only_explicit_confirmation_clears(client, patch):
    sid = create(client)
    store.update_session(sid, {'stale': {'stage0': 'old', 'stage1': 'old', 'stage2': 'old'}})
    store.update_session(sid, patch)
    assert len(store.load_session(sid)['stale']) == 3
    store.update_session(sid, {}, confirm_stage='stage2')
    assert 'stage2' not in store.load_session(sid)['stale']
    assert client.put(f'/context/{sid}', json=CTX).status_code == 200
    assert store.load_session(sid)['stale'] == {'stage1': 'old'}

@pytest.mark.parametrize('phase', ['unfinished', 'done', 'running'])
def test_fork_collection_phase(client, monkeypatch, phase):
    from app.crawl import control
    sid = create(client)
    store.update_session(sid, {'collectionId': 'c1'})
    monkeypatch.setattr(control, 'phase_state', lambda sid, collection_id=None: phase, raising=False)
    if phase in ('running', 'unfinished'):
        with pytest.raises(store.StoreError, match='크롤링 수집을 끝낸 뒤 새 버전을 만드세요.') as error:
            versions.create_version(sid, 'v1', 'stage3', '')
        assert error.value.status == 409
        assert not versions.version_dir(sid, 'v2').exists()
        return
    versions.create_version(sid, 'v1', 'stage3', '')
    assert versions._data(sid, 'v1')['collectionId'] == 'c1'
    assert store.load_session(sid)['collectionId'] == 'c1'

def test_unreadable_session_isolated(client):
    sid = create(client)
    bad = store.root_dir('broken')
    bad.mkdir()
    (bad / 'session.json').write_text('{broken')
    rows = client.get('/sessions').json()['sessions']
    assert {r['sid'] for r in rows} == {sid, 'broken'}
    assert next(r for r in rows if r['sid'] == 'broken') == {'sid': 'broken', 'status': 'unreadable'}

def test_legacy_keys_dropped(client):
    sid = create(client)
    keys = ['bk', 'pd', 'problemDef', 'allKw', '_pendingKw', 'ages', 'ar', 'gens']
    client.post('/save-session', json={'sid': sid, 'data': dict.fromkeys(keys, 'old')})
    assert not set(keys) & store.load_session(sid).keys()

def test_openai_needs_model(monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test')
    monkeypatch.setattr(settings, 'openai_model', '')
    assert not next(x for x in integration_status() if x.name == 'openai').connected

def test_session_errors_generic(client, monkeypatch):
    from app.routers import sessions
    def fail(*args):
        raise OSError('private secret path')
    monkeypatch.setattr(sessions.store, 'load_session', fail)
    assert 'private secret' not in client.post('/save-session', json={'sid': 'test', 'data': {}}).text
    monkeypatch.setattr(sessions.store, 'root_dir', fail)
    assert 'private secret' not in client.delete('/delete-session/test').text

@pytest.mark.parametrize('action', ['version', 'active', 'save', 'delete'])
def test_session_mutations_guard_displayed_version(client, action):
    sid = create(client)
    versions.create_version(sid, 'v1', 'stage1', '')
    before = store.load_session(sid)
    if action == 'version':
        response = client.post(f'/sessions/{sid}/versions?version=v1', json={'from': 'v1', 'restartFrom': 'stage1'})
    elif action == 'active':
        response = client.put(f'/sessions/{sid}/active-version?version=v1', json={'version': 'v2'})
    elif action == 'save':
        response = client.post('/save-session?version=v1', json={'sid': sid, 'data': {'step': 'old'}})
    else:
        response = client.delete(f'/delete-session/{sid}?version=v1')
    assert response.status_code == 409
    assert store.load_session(sid) == before

@pytest.mark.parametrize('source_collection,phase,allowed', [
    ('c1', 'unfinished', False), ('c1', 'running', False),
    ('c1', 'done', True), (None, 'unfinished', True),
])
def test_fork_checks_history_source_not_active_collection(client, monkeypatch, source_collection, phase, allowed):
    from app.crawl import control
    sid = create(client)
    versions.create_version(sid, 'v1', 'stage3', '')
    source = versions._data(sid, 'v1')
    source['collectionId'] = source_collection
    store.write_json(versions.version_dir(sid, 'v1') / 'session.json', source)
    store.update_session(sid, {'collectionId': 'c2'})
    checked = []
    def source_phase(session_id, collection_id=None):
        checked.append((session_id, collection_id))
        return phase if collection_id == 'c1' else 'done'
    monkeypatch.setattr(control, 'phase_state', source_phase)
    monkeypatch.setattr(control, 'activity', lambda _: None)
    response = client.post(f'/sessions/{sid}/versions', json={'from': 'v1', 'restartFrom': 'stage3'})
    assert response.status_code == (201 if allowed else 409)
    assert checked == ([(sid, 'c1')] if source_collection else [])
    if allowed:
        assert store.load_session(sid).get('collectionId') == source_collection
    else:
        assert response.json()['error']['code'] == 'crawl_unfinished'
        assert store.load_session(sid)['version'] == 'v2'
        assert not versions.version_dir(sid, 'v3').exists()
