"""Offline T09 contracts, including real threaded concurrency."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.context import store
from app.keywords import rounds
from app.keywords.events import load_events
from app.llm import registry
from app.llm.fake import FakeBackend
from app.main import app


THREADED_EXECUTE = rounds.execute


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'local_data_dir', str(tmp_path))
    monkeypatch.setattr(settings, 'searchad_api_key', '')
    monkeypatch.setattr(rounds, 'execute', lambda fn: fn())
    store.update_session('test', {'schemaVersion': 2, 'keywords': []})
    (store.session_dir('test') / 'project_context.md').write_text('원문 맥락\n- 리서치 질문: 냉방 경험은?')
    return tmp_path


@pytest.fixture
def backend(monkeypatch):
    class RecordingFake(FakeBackend):
        calls = []
        def run(self, task):
            self.calls.append(task)
            count = len(self.calls)
            self.responses = {task.task: json.dumps({'keywords': [
                {'kw': f'냉방{count}단어{i}', 'axis': 'physical', 'sub': 'space', 'why': '상황'}
                for i in range(42)]})}
            return super().run(task)
    fake = RecordingFake()
    monkeypatch.setattr(registry, 'get_backend', lambda task: fake)
    return fake


@pytest.fixture
def client(data_dir, backend):
    return TestClient(app)


def start(client, n):
    response = client.post(f'/keywords/test/rounds/{n}')
    assert response.status_code == 200, response.text
    return client.get(f'/keywords/test/rounds/{n}').json()


def commit(client, n, state=None):
    state = state or client.get(f'/keywords/test/rounds/{n}').json()
    return client.post(f'/keywords/test/rounds/{n}/commit', json={
        'gen': state['gen'], 'decisions': [{'id': k['id'], 'status': 'approved'} for k in state['keywords']]})


def through(client, n):
    for number in range(1, n + 1):
        assert commit(client, number, start(client, number)).status_code == 200


def test_rounds_must_follow_order(client):
    assert client.post('/keywords/test/rounds/2').status_code == 409
    start(client, 1)
    assert client.post('/keywords/test/rounds/2').status_code == 409


def test_start_is_idempotent_while_running(client, backend, monkeypatch):
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    a = client.post('/keywords/test/rounds/1').json()
    b = client.post('/keywords/test/rounds/1').json()
    assert a['jobId'] == b['jobId'] and a['status'] == 'running'
    assert len(queued) == 1
    queued[0]()
    assert len(backend.calls) == 1


def test_job_survives_refresh(client):
    state = start(client, 1)
    assert state['status'] == 'done'
    assert len(state['keywords']) == 42
    assert all(k['status'] == 'pending' for k in state['keywords'])
    with TestClient(app) as refreshed:
        assert refreshed.get('/keywords/test/rounds/1').json() == state


def test_interrupted_on_restart(client):
    store.update_session('test', {'keywordRounds': {'1': {'job': {'jobId': 'lost', 'status': 'running'}}}})
    rounds.recover_interrupted()
    job = client.get('/keywords/test/rounds/1').json()
    assert job['status'] == 'failed' and job['error']['kind'] == 'interrupted'


def test_partial_count_flag(client):
    assert start(client, 1)['below_min'] == {'got': 42, 'min': 70}


def test_r2_commit_triggers_coverage(client):
    through(client, 2)
    assert store.load_session('test')['coverage'] == {'status': 'unconnected'}


def test_r3_inputs_recorded(client, backend):
    through(client, 2)
    start(client, 3)
    inputs = store.load_session('test')['keywordRounds']['3']['inputs']
    assert inputs == {'rejection': 'empty:no_rejections', 'coverage': 'empty:searchad_unconnected',
                      'prior_session': 'empty:no_prior_session', 'promptVersion': 'r3.v1'}
    assert [a.title for a in backend.calls[-1].attachments] == ['project_context.md', 'keyword_feedback.md']
    assert backend.calls[-1].attachments[0].body.startswith('원문 맥락')


def test_old_endpoints_removed(client):
    for path in ('/generate-keywords', '/score-keywords', '/suggest-words'):
        assert client.post(path, json={}).status_code == 404


def test_manual_add_scores_volume(client):
    response = client.post('/keywords/test/manual', json={'kw': '저소음', 'axis': 'physical', 'sub': 'sense'})
    assert response.status_code == 200
    kw = response.json()
    assert kw['origin'] == 'manual' and kw['volume']['source'] == 'unconnected'
    assert load_events('test')[-1].type == 'add'


def test_manual_add_duplicate_409(client):
    body = {'kw': '저 소음', 'axis': 'physical', 'sub': 'sense'}
    first = client.post('/keywords/test/manual', json=body).json()
    response = client.post('/keywords/test/manual', json={**body, 'kw': '저소음'})
    assert response.status_code == 409
    assert response.json()['duplicateOf'] == first['id']


def test_suggested_word_origin_recorded(client):
    response = client.post('/keywords/test/manual', json={
        'kw': '견디다', 'axis': 'behavioral', 'sub': 'coping', 'origin': 'suggested'})
    assert response.json()['origin'] == 'suggested'


def test_custom_sub_requires_axis(client):
    assert client.post('/keywords/test/manual', json={'kw': '창문', 'sub': 'custom:설치환경'}).status_code == 422


def test_r4_regen_gen_ids_unique(client):
    through(client, 3)
    first = start(client, 4)
    assert commit(client, 4, first).status_code == 200
    second = start(client, 4)
    assert first['gen'] == 1 and second['gen'] == 2
    assert all('g1' in k['id'] for k in first['keywords'])
    assert all('g2' in k['id'] for k in second['keywords'])
    assert not ({k['id'] for k in first['keywords']} & {k['id'] for k in second['keywords']})
    assert commit(client, 4, first).status_code == 409
    assert commit(client, 4, second).status_code == 200


def test_concurrent_round_start_single_job(client, backend, monkeypatch):
    through(client, 1)
    entered, release = Event(), Event()
    original = backend.run
    def blocked(task):
        entered.set()
        assert release.wait(5)
        return original(task)
    monkeypatch.setattr(backend, 'run', blocked)
    workers = []
    def threaded(fn):
        workers.append(THREADED_EXECUTE(fn))
    monkeypatch.setattr(rounds, 'execute', threaded)
    barrier = Barrier(2)
    def request():
        barrier.wait()
        return client.post('/keywords/test/rounds/2').json()
    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: request(), range(2)))
        assert entered.wait(2)
        assert len({r['jobId'] for r in results}) == 1
    finally:
        release.set()
        for thread in workers:
            thread.join(5)
    assert len(backend.calls) == 2


def test_llm_failure_is_persisted(client, backend, monkeypatch):
    from app.llm.base import failure
    monkeypatch.setattr(backend, 'run', lambda task: failure('timeout', 'Timed out'))
    state = start(client, 1)
    assert state['status'] == 'failed'
    assert state['error']['kind'] == 'timeout'
    assert state['keywords'] == []


def test_past_version_writes_are_409(client):
    from app.context.versions import create_version, version_dir
    create_version('test', 'v1', 'stage1', '')
    before = (version_dir('test', 'v1') / 'session.json').read_bytes()
    for path, body in [('/rounds/1', {}), ('/manual', {'kw': '소음', 'axis': 'physical', 'sub': 'sense'}),
                       ('/coverage', {}), ('/events', {'round': 1, 'type': 'direction', 'text': '방향'}),
                       ('/suggest-words', {'axis': 'physical', 'sub': 'sense'}),
                       ('/rounds/1/commit', {'gen': 1, 'decisions': []})]:
        assert client.post('/keywords/test' + path + '?version=v1', json=body).status_code == 409
    assert (version_dir('test', 'v1') / 'session.json').read_bytes() == before
    assert client.get('/keywords/test?version=v1').status_code == 200


def test_running_job_blocks_version_creation(client, monkeypatch):
    monkeypatch.setattr(rounds, 'execute', lambda fn: None)
    start(client, 1)
    response = client.post('/sessions/test/versions', json={'from': 'v1', 'restartFrom': 'stage1', 'note': ''})
    assert response.status_code == 409
    assert store.session_activity('test', store.load_session('test'))['kind'] == 'keyword_round_1'


def test_direction_move_reject_feedback(client, backend):
    assert client.post('/keywords/test/events', json={'round': 1, 'type': 'direction', 'text': '조용한 환경'}).status_code == 200
    state = start(client, 1)
    assert '조용한 환경' in backend.calls[-1].attachments[1].body
    kw = state['keywords'][0]
    moved = client.post('/keywords/test/events', json={'round': 1, 'type': 'move', 'kwId': kw['id'],
                                                     'to': {'axis': 'psychological', 'sub': 'emotion'}})
    assert moved.status_code == 200
    decisions = [{'id': k['id'], 'status': 'approved'} for k in state['keywords']]
    decisions[0].update(status='rejected', reject={'tags': ['common'], 'note': '범위 넓음'})
    response = client.post('/keywords/test/rounds/1/commit', json={'gen': 1, 'decisions': decisions})
    assert response.status_code == 200
    saved = client.get('/keywords/test').json()
    assert saved['keywords'][0]['axis'] == 'psychological'
    assert '범위 넓음' in saved['feedback_md']
    start(client, 2)
    assert '범위 넓음' in backend.calls[-1].attachments[1].body


def test_connected_coverage_and_inputs(client, backend, monkeypatch):
    original = backend.run
    def classified(task):
        if task.task == 'kw_axis_classify':
            return FakeBackend({task.task: json.dumps({'axes': {'냉방1단어0': 'physical', '누수': 'physical'}})}).run(task)
        return original(task)
    monkeypatch.setattr(backend, 'run', classified)
    calls = []
    def related(hints):
        calls.append(hints)
        return [('냉방1단어0', 100), ('누수', 20)]
    through(client, 1)
    monkeypatch.setattr(rounds.naver_searchad, 'related_queries', related)
    state = start(client, 2)
    assert commit(client, 2, state).status_code == 200
    saved = store.load_session('test')['coverage']
    assert saved['status'] == 'connected' and saved['m1'] == pytest.approx(100 / 120)
    assert saved['m6'] == 0
    assert saved['m7'] is None
    count = len(calls)
    assert client.post('/keywords/test/coverage').status_code == 200
    assert len(calls) == count
    start(client, 3)
    assert store.load_session('test')['keywordRounds']['3']['inputs']['coverage'] == 'ok'


def test_suggest_words_uses_server_context(client, monkeypatch):
    fake = FakeBackend({'kw_suggest_words': json.dumps({'words': [{'word': '견디다', 'type': '동사'}]})})
    monkeypatch.setattr(registry, 'get_backend', lambda task: fake)
    response = client.post('/keywords/test/suggest-words', json={'axis': 'behavioral', 'sub': 'coping'})
    assert response.status_code == 200 and response.json()['words'][0]['word'] == '견디다'


def test_invalid_commit_is_atomic(client):
    state = start(client, 1)
    before = store.load_session('test')
    response = client.post('/keywords/test/rounds/1/commit', json={'gen': 1, 'decisions': [
        {'id': state['keywords'][0]['id'], 'status': 'rejected', 'reject': {'tags': ['invalid']}}]})
    assert response.status_code == 422
    assert store.load_session('test') == before
    assert not load_events('test')


def test_startup_recovers_interrupted(client):
    store.update_session('test', {'keywordRounds': {'1': {'job': {'jobId': 'lost', 'status': 'running'}}}})
    with TestClient(app) as restarted:
        assert restarted.get('/keywords/test/rounds/1').json()['error']['kind'] == 'interrupted'


def test_unconnected_coverage_replaces_old_failure(client):
    store.update_session('test', {'coverage': {'status': 'failed', 'error': {'kind': 'request_failed'}}})
    assert client.post('/keywords/test/coverage').json() == {'status': 'unconnected'}
    assert store.load_session('test')['coverage'] == {'status': 'unconnected'}
