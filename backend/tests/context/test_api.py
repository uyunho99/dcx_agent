import httpx
from app.context.store import load_session, update_session, session_dir
from app.config import settings
from app.llm import registry
from app.llm.fake import FakeBackend
from app.external import naver_shopping

CTX = dict(bk='에어컨', oneLiner='시원한 공기', researchQuestion={'text': '왜 쓰는가?'},
           projectType={'choice': 'new'}, analysisGoal={'choice': 'needs'}, keyMetrics=['만족'],
           constraints=[], positioning={'price': 'value', 'market': 'new'}, channels=['youtube'],
           productCategory={'l1': '가전', 'source': 'user'})


def create(client):
    response = client.post('/context', json=CTX)
    assert response.status_code == 201
    return response.json()['sid']


def test_post_context_creates_session_and_md(client):
    sid = create(client)
    assert load_session(sid)['schemaVersion'] == 2
    assert load_session(sid)['projectContext']['bk'] == CTX['bk']
    assert '시원한 공기' in (session_dir(sid) / 'project_context.md').read_text()


def test_category_llm_fallback(client, monkeypatch):
    monkeypatch.setattr(settings, 'naver_client_id', 'x')
    backend = FakeBackend({'category_suggest': '{"l1":"가전","l2":"계절","l3":"에어컨"}'})
    monkeypatch.setattr(registry, 'get_backend', lambda _: backend)
    r = client.post('/context/category-suggest', json={'bk': '에어컨', 'oneLiner': '냉방'})
    assert r.status_code == 200
    assert r.json()['source'] == 'llm_estimate'


def test_category_shopping_mode(client, monkeypatch):
    monkeypatch.setattr(settings, 'naver_client_id', 'test')
    monkeypatch.setattr(settings, 'naver_client_secret', 'test')
    items = [dict(category1='디지털/가전', category2='계절가전', category3='에어컨')] * 2 + [dict(category1='생활', category2='기타', category3='기타')]
    monkeypatch.setattr(naver_shopping, 'client_factory', lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'items': items}))))
    r = client.post('/context/category-suggest', json={'bk': '에어컨', 'oneLiner': ''})
    assert r.json() == dict(l1='디지털/가전', l2='계절가전', l3='에어컨', source='shopping')


def test_sessions_legacy_flag(client):
    client.post('/save-session', json={'sid': 'old', 'data': {'bk': 'old'}})
    assert client.get('/sessions').json()['sessions'][0]['legacy'] is True


def test_sessions_sorted_attention_first(client):
    update_session('a', {'schemaVersion': 2, 'keywordRounds': {'2': {'job': {'status': 'interrupted'}}}})
    update_session('z', {'schemaVersion': 2, 'keywordRounds': {'1': {'job': {'status': 'running'}}}})
    assert client.get('/sessions').json()['sessions'][0]['sid'] == 'a'


def test_put_context_after_r1_warns(client):
    sid = create(client)
    update_session(sid, {'keywordRounds': {'1': {'status': 'done'}}})
    r = client.put('/context/' + sid, json={**CTX, 'oneLiner': '새 정의'})
    assert r.json()['warnings'] == ['oneLiner_changed_after_r1']


def test_step_patch_keeps_rounds(client):
    sid = create(client)
    update_session(sid, {'keywordRounds': {'2': {'status': 'done'}}})
    assert client.patch('/session/' + sid, json={'step': 'r3'}).status_code == 200
    assert load_session(sid)['keywordRounds']['2']['status'] == 'done'
    assert client.patch('/session/' + sid, json={'keywords': []}).status_code == 400


def test_draft_roundtrip_per_screen(client):
    sid = create(client)
    client.patch('/session/' + sid, json={'drafts': {'start': {'bk': 'draft'}, 'keywords': {'x': 1}}})
    client.patch('/session/' + sid, json={'drafts': {'start': {'oneLiner': 'draft'}}})
    assert client.get('/context/' + sid).json()['draft'] == {'bk': 'draft', 'oneLiner': 'draft'}


def test_legacy_full_save_merges_but_keeps_server_keys(client):
    sid = create(client)
    update_session(sid, {'keywordRounds': {'2': {'status': 'done'}}, 'coverage': {'x': 1}})
    r = client.post('/save-session', json={'sid': sid, 'data': {'keywordRounds': {}, 'projectContext': {}, 'coverage': {}, 'version': 'v99', 'drafts': {}, 'labeledData': [{'label': 1}]}})
    assert r.json()['status'] == 'saved'
    saved = load_session(sid)
    assert saved['keywordRounds']['2']['status'] == 'done'
    assert saved['version'] == 'v1' and saved['coverage'] == {'x': 1}
    assert saved['labeledData'] == [{'label': 1}]


def test_labeling_save_then_train_reads(client):
    from app.services.training import load_json
    sid = create(client)
    client.post('/save-session', json={'sid': sid, 'data': {'labeledData': [{'text': '합성', 'label': 1}]}})
    assert load_json(f'sessions/{sid}/session.json')['labeledData'] == [{'text': '합성', 'label': 1}]


def test_integrations_no_values(client, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'secret-value')
    r = client.get('/integrations')
    assert 'secret-value' not in r.text
    assert {entry['name'] for entry in r.json()} == {'openai', 'claude'}


def test_new_api_validation_error_envelope(client):
    r = client.post('/context', json={})
    assert r.status_code == 422
    assert r.json()['error']['kind'] == 'validation'
    assert client.get('/context/missing').status_code == 404


def test_legacy_endpoints_versioned_session(client):
    sid = create(client)
    assert client.get('/session/' + sid).json()['data']['schemaVersion'] == 2
    assert client.get('/pipeline-status/' + sid).json()['session']['sid'] == sid
    assert client.delete('/delete-session/' + sid).json()['status'] == 'ok'
    assert client.get('/session/' + sid).json()['status'] == 'not_found'
    assert client.get('/sessions').json()['sessions'] == []


def test_legacy_full_save_still_overwrites(client):
    client.post('/save-session', json={'sid': 'old', 'data': {'a': 1, 'b': 2}})
    client.post('/save-session', json={'sid': 'old', 'data': {'a': 3}})
    assert client.get('/session/old').json()['data'] == {'a': 3}


def test_sessions_recency_includes_new_v2_among_legacy(client):
    import os
    for i in range(21):
        sid = f'slegacy{i:02d}'
        assert client.post('/save-session', json={'sid': sid, 'data': {'bk': sid}}).json()['status'] == 'saved'
        # Reverse ID order and include a tie to check the secondary sort.
        timestamp = 1_600_000_000 - i // 2
        os.utime(session_dir(sid) / 'session.json', (timestamp, timestamp))
    new_sid = create(client)
    response = client.get('/sessions').json()
    assert response['status'] == 'ok'
    ids = [s['sid'] for s in response['sessions']]
    expected_legacy = sorted(range(21), key=lambda i: (-(i // 2), i), reverse=True)
    assert ids == [new_sid] + [f'slegacy{i:02d}' for i in expected_legacy[:19]]
