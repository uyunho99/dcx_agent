from app.context import store as sessions
from app.context.versions import version_dir
from app.known import store as known
from app.persona.store import PersonaStore


def seed(sid, bk='same', items=None, at='2026-01-01T00:00:00+00:00'):
    items = items if items is not None else [{'id': 'I1', 'title': 'Title', 'pain_point': 'Pain'}]
    sessions.update_session(sid, dict(schemaVersion=2, sid=sid, bk=bk,
        insight={'confirmed': [i['id'] for i in items], 'savedAt': at}))
    PersonaStore.open(sid, 'v1').new_revision('insights', items, by='generate', message=None)


def test_suggestions_explicit_add_only(client, monkeypatch):
    monkeypatch.setattr(known, '_embed_many', lambda *a: None)
    seed('previous')
    seed('other', 'different')
    seed('current', items=[])
    known.initialize('current')
    assert client.get('/known/current').json() == {'items': []}
    expected = {'sessionId': 'previous', 'insightId': 'I1', 'title': 'Title', 'painPoint': 'Pain'}
    assert client.get('/known/current/suggestions').json() == {'items': [expected]}
    result = client.post('/known/current', json={'type': 'statement', 'text': 'Title', 'from': 'prev_session'})
    assert result.status_code == 201
    assert result.json()['from'] == 'prev_session'
    assert len(client.get('/known/current').json()['items']) == 1
    assert client.post('/known/current', json={'type': 'doc', 'doc_id': 'x', 'from': 'prev_session'}).status_code == 422


def test_suggestions_limit_recent_20(client):
    seed('current', items=[])
    for i in range(25):
        seed(f's{i:02}', items=[{'id': str(i), 'title': f'Title {i}', 'pain_point': f'Pain {i}'}],
             at=f'2026-01-{i + 1:02}T00:00:00+00:00')
    seed('duplicate', items=[{'id': 'dup', 'title': 'Title 24', 'pain_point': 'Newest'}],
         at='2026-02-01T00:00:00+00:00')
    rows = client.get('/known/current/suggestions').json()['items']
    assert len(rows) == 20
    assert rows[0]['sessionId'] == 'duplicate'
    assert [r['title'] for r in rows] == [f'Title {i}' for i in range(24, 4, -1)]


def test_suggestions_only_confirmed_and_selected_version(client):
    seed('previous')
    sessions.update_session('previous', {'insight': {'confirmed': []}})
    seed('current', items=[])
    assert client.get('/known/current/suggestions').json() == {'items': []}
    assert client.get('/known/missing/suggestions').status_code == 404
    assert client.get('/known/current/suggestions?version=v99').status_code == 404


def test_suggestions_version_bk_and_readonly_add(client, monkeypatch):
    from app.context.versions import create_version
    monkeypatch.setattr(known, '_embed_many', lambda *a: None)
    seed('previous')
    seed('current', items=[])
    create_version('current', 'v1', 'stage8', '')
    sessions.update_session('current', {'bk': 'different'})
    assert client.get('/known/current/suggestions').json() == {'items': []}
    assert len(client.get('/known/current/suggestions?version=v1').json()['items']) == 1
    response = client.post('/known/current?version=v1', json={
        'type': 'statement', 'text': 'Title\nPain', 'from': 'prev_session'})
    assert response.status_code == 409
    assert known.list_known('current', 'v1') == []


def test_suggestions_ignore_stale_and_use_project_bk(client):
    seed('previous')
    seed('current', items=[])
    data = sessions.load_session('previous')
    data['stale'] = {'stage8': 'Changed'}
    sessions.write_json(version_dir('previous', 'v1') / 'session.json', data)
    assert client.get('/known/current/suggestions').json() == {'items': []}
    data.pop('stale')
    data['projectContext'] = {'bk': 'different'}
    sessions.write_json(version_dir('previous', 'v1') / 'session.json', data)
    assert client.get('/known/current/suggestions').json() == {'items': []}
