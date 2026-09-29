"""Final W1 offline regression contracts."""
import json
from pathlib import Path
import runpy
import pytest
from app.config import settings
from app.context import store, versions
from app.keywords import rounds
from app.keywords.events import load_events
from app.keywords.prompts import MIN_COUNT

@pytest.fixture
def fake_session(client, monkeypatch):
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    monkeypatch.setattr(settings, 'searchad_api_key', '')
    monkeypatch.setattr(rounds, 'execute', lambda fn: fn())
    store.update_session('w1', {'schemaVersion': 2, 'keywords': []})
    (store.session_dir('w1') / 'project_context.md').write_text('에어컨 사용 경험')
    return client

def generate(client, n, suffix=''):
    response = client.post(f'/keywords/w1/rounds/{n}{suffix}')
    assert response.status_code == 200, response.text
    state = client.get(f'/keywords/w1/rounds/{n}').json()
    assert state['status'] == 'done', state
    assert not state['below_min']
    assert len(state['keywords']) >= MIN_COUNT[n]
    return state

def commit(client, n, state):
    return client.post(f'/keywords/w1/rounds/{n}/commit', json={'gen': state['gen'], 'decisions': [
        {'id': k['id'], 'status': 'approved'} for k in state['keywords']]})

def test_shipped_fake_rounds_and_corpus(fake_session, tmp_path):
    words = []
    for n in range(1, 5):
        state = generate(fake_session, n)
        words.extend(k['kw'] for k in state['keywords'])
        assert commit(fake_session, n, state).status_code == 200
    assert len(words) == len(set(words))
    assert fake_session.post('/keywords/w1/suggest-words', json={'axis': 'physical', 'sub': 'space'}).status_code == 200
    path = tmp_path / 'corpus.csv'
    runpy.run_path('tests/fixtures/make_corpus.py')['write_corpus'](path)
    rows = path.read_text().splitlines()[1:]
    assert all(sum(word in row for row in rows) >= 3 for word in words)
    assert all(word in path.read_text() for word in ['소음', '냄새', '실외기', '리모컨', '결로', '필터', '전기세'])

@pytest.mark.parametrize('regenerate', ['', '?regenerate=true'])
def test_restart_round_order_and_replacement(fake_session, regenerate):
    for n in range(1, 5):
        assert commit(fake_session, n, generate(fake_session, n)).status_code == 200
    versions.create_version('w1', 'v1', 'stage0', '')
    assert fake_session.post('/keywords/w1/rounds/2').status_code == 409
    for n in range(1, 5):
        state = generate(fake_session, n, regenerate)
        assert state['gen'] == 2
        assert commit(fake_session, n, state).status_code == 200
        data = store.load_session('w1')
        assert 'stage1' not in data['stale']
        assert all(not data['keywordRounds'][str(i)]['committed'] for i in range(n + 1, 5))
    assert all('g2_' in k['id'] for k in store.load_session('w1')['keywords'])

@pytest.mark.parametrize('endpoint,body', [
    ('rounds/1', None), ('rounds/1/commit', {'gen': 1, 'decisions': []}),
    ('events', {'round': 1, 'type': 'direction', 'text': 'hello'}),
    ('manual', {'kw': '새단어', 'axis': 'physical', 'sub': 'space'}),
    ('suggest-words', {'axis': 'physical', 'sub': 'space'}), ('coverage', None),
])
def test_stale_version_does_not_write(fake_session, endpoint, body):
    versions.create_version('w1', 'v1', 'stage1', '')
    root = store.root_dir('w1')
    def snapshot():
        return {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    before = snapshot()
    response = fake_session.post(f'/keywords/w1/{endpoint}?version=v1', json=body)
    assert response.status_code == 409
    assert response.json()['error']['message'] == '다른 버전이 활성화되었습니다'
    assert snapshot() == before

def test_commit_crash_retries_events_once(fake_session, monkeypatch):
    state = generate(fake_session, 1)
    original = store._update_locked
    def crash(sid, patch, *args, **kwargs):
        if patch.get('keywordRounds', {}).get('1', {}).get('committed'):
            raise OSError('simulated crash')
        return original(sid, patch, *args, **kwargs)
    monkeypatch.setattr(store, '_update_locked', crash)
    assert commit(fake_session, 1, state).status_code == 500
    events = load_events('w1')
    assert len(events) == len(state['keywords'])
    assert not store.load_session('w1')['keywordRounds']['1']['committed']
    monkeypatch.setattr(store, '_update_locked', original)
    assert commit(fake_session, 1, state).status_code == 200
    assert len(load_events('w1')) == len(events)
    assert all(e.id.startswith('commit:1:1:') for e in load_events('w1'))

def test_background_paths_preserve_stale(fake_session, monkeypatch):
    store.update_session('w1', {'stale': {'stage1': 'old', 'stage2': 'old'}})
    rounds.compute_coverage('w1')
    assert store.load_session('w1')['stale']['stage1'] == 'old'
    monkeypatch.setattr(rounds, 'execute', lambda fn: None)
    rounds.start_round('w1', 1)
    rounds.recover_interrupted()
    assert store.load_session('w1')['stale'] == {'stage1': 'old', 'stage2': 'old'}

@pytest.mark.parametrize('endpoint,body', [('manual', {'kw': '새단어', 'axis': 'physical', 'sub': 'space'}), ('events', {'round': 1, 'type': 'direction', 'text': 'hello'})])
def test_hitl_confirms_stage1(fake_session, endpoint, body):
    store.update_session('w1', {'stale': {'stage1': 'old', 'stage2': 'old'}})
    assert fake_session.post(f'/keywords/w1/{endpoint}', json=body).status_code == 200
    assert store.load_session('w1')['stale'] == {'stage2': 'old'}

@pytest.mark.parametrize('endpoint,body', [
    ('rounds/1', None), ('rounds/1/commit', {'gen': 1, 'decisions': []}),
    ('events', {'round': 1, 'type': 'direction', 'text': 'hello'}),
    ('manual', {'kw': '새단어', 'axis': 'physical', 'sub': 'space'}),
    ('suggest-words', {'axis': 'physical', 'sub': 'space'}), ('coverage', None),
])
def test_version_checked_after_lock_acquired(fake_session, monkeypatch, endpoint, body):
    from contextlib import contextmanager
    original = store.locked
    switched = False
    @contextmanager
    def switch_before_lock(sid):
        nonlocal switched
        if not switched:
            switched = True
            versions.create_version(sid, 'v1', 'stage1', '')
        with original(sid) as root:
            yield root
    monkeypatch.setattr(store, 'locked', switch_before_lock)
    response = fake_session.post(f'/keywords/w1/{endpoint}?version=v1', json=body)
    assert response.status_code == 409
    assert response.json()['error']['message'] == '다른 버전이 활성화되었습니다'
    assert store.load_session('w1').get('keywords') == []
    assert not (store.session_dir('w1') / 'keyword_events.jsonl').exists()

def test_restart_r4_then_extra_generation_preserves_committed(fake_session):
    for n in range(1, 5):
        assert commit(fake_session, n, generate(fake_session, n)).status_code == 200
    versions.create_version('w1', 'v1', 'stage1', '')
    for n in range(1, 5):
        assert commit(fake_session, n, generate(fake_session, n)).status_code == 200
    before = store.load_session('w1')['keywords']
    assert fake_session.post('/keywords/w1/rounds/4').status_code == 200
    state = fake_session.get('/keywords/w1/rounds/4').json()
    assert commit(fake_session, 4, state).status_code == 200
    assert store.load_session('w1')['keywords'] == before
