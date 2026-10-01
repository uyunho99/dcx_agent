"""Offline T09 contracts, including real threaded concurrency."""
import json
import socket
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.context import store
from app.external import naver_autocomplete
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
    monkeypatch.setattr(settings, 'autocomplete_backend', 'fake')
    def no_network(*args, **kwargs):
        raise AssertionError('Network access is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
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
    assert store.load_session('test')['coverage']['source'] == 'autocomplete'


def test_r3_inputs_recorded(client, backend):
    through(client, 2)
    start(client, 3)
    inputs = store.load_session('test')['keywordRounds']['3']['inputs']
    assert inputs == {'rejection': 'empty:no_rejections', 'coverage': 'ok',
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
    assert [k['id'] for k in first['keywords']] == [f'k_r4g1_{i:04d}' for i in range(1, 43)]
    assert [k['id'] for k in second['keywords']] == [f'k_r4g2_{i:04d}' for i in range(1, 43)]
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


def test_unconnected_coverage_replaces_old_failure(client, autocomplete_calls):
    store.update_session('test', {'coverage': {'status': 'failed', 'error': {'kind': 'request_failed'}}})
    assert client.post('/keywords/test/coverage').status_code == 200
    assert store.load_session('test')['coverage']['status'] == 'connected'


@pytest.fixture
def threaded(monkeypatch):
    workers = []
    def execute(fn):
        workers.append(THREADED_EXECUTE(fn))
    monkeypatch.setattr(rounds, 'execute', execute)
    yield workers
    for worker in workers:
        worker.join(5)
        assert not worker.is_alive()


def finish_threaded(client, workers):
    response = client.post('/keywords/test/rounds/1')
    assert response.status_code == 200
    workers[-1].join(5)
    assert not workers[-1].is_alive()
    return client.get('/keywords/test/rounds/1').json()


@pytest.mark.parametrize('source', ['_inputs', 'attach_volumes'])
def test_threaded_store_error_fails_job(client, threaded, monkeypatch, source):
    original = getattr(rounds, source)
    def fail(*args):
        raise store.StoreError('private store detail')
    monkeypatch.setattr(rounds, source, fail)
    failed = finish_threaded(client, threaded)
    assert failed['status'] == 'failed'
    assert failed['error']['kind'] == 'backend'
    assert 'private store detail' not in json.dumps(failed)
    monkeypatch.setattr(rounds, source, original)
    retried = finish_threaded(client, threaded)
    assert retried['jobId'] != failed['jobId']
    assert retried['status'] == 'done'


@pytest.mark.parametrize('bad_sid', ['legacy.old', 'corrupt'])
def test_threaded_round_skips_bad_prior_session(client, data_dir, threaded, bad_sid):
    # Write minimal context directly to avoid unrelated ProjectContext validation.
    path = store.session_dir('test') / 'session.json'
    data = store.load_session('test')
    data['projectContext'] = {'bk': '냉방'}
    store.write_json(path, data)
    bad = data_dir / 'sessions' / bad_sid
    bad.mkdir()
    (bad / 'session.json').write_text('{private broken contents')
    assert finish_threaded(client, threaded)['status'] == 'done'


@pytest.mark.parametrize('bad_sid', ['legacy.old', 'corrupt'])
def test_startup_skips_bad_sessions(client, data_dir, caplog, bad_sid):
    bad = data_dir / 'sessions' / bad_sid
    bad.mkdir()
    (bad / 'session.json').write_text('{private broken contents')
    for sid in ['test', 'valid']:
        store.update_session(sid, {'schemaVersion': 2, 'keywordRounds': {
            '1': {'job': {'jobId': 'lost', 'status': 'running'}}}})
    with TestClient(app) as restarted:
        for sid in ['test', 'valid']:
            state = restarted.get(f'/keywords/{sid}/rounds/1').json()
            assert state['status'] == 'failed'
            assert state['error']['kind'] == 'interrupted'
    assert bad_sid in caplog.text
    assert 'private broken contents' not in caplog.text


@pytest.mark.parametrize('coverage,signal,status', [
    ({'status': 'connected', 'missing_top': []}, '부족 축 없음', 'ok'),
    ({'status': 'ok', 'missing_top': []}, '부족 축 없음', 'ok'),
    ({'status': 'failed'}, '커버리지 계산 실패 — 축 분포 균형에 집중', 'ok'),
    ({'status': 'unconnected'}, '커버리지 정보 없음', 'empty:searchad_unconnected'),
    ({}, '커버리지 정보 없음', 'empty:searchad_unconnected'),
])
def test_r3_coverage_signal_truth(client, backend, monkeypatch, coverage, signal, status):
    through(client, 2)
    store.update_session('test', {'coverage': rounds._Replacement(coverage)})
    for key in ['searchad_api_key', 'searchad_secret', 'searchad_customer_id']:
        monkeypatch.setattr(settings, key, 'configured')
    monkeypatch.setattr(rounds, 'attach_volumes', lambda kws: kws)
    state = start(client, 3)
    assert state['status'] == 'done'
    assert state['inputs']['coverage'] == status
    assert signal in backend.calls[-1].instructions
    if coverage.get('status') not in ('connected', 'ok'):
        assert '부족 축 없음' not in backend.calls[-1].instructions


def test_commit_explicit_generation(client):
    state = start(client, 1)
    assert state['keywords'][0]['id'] == 'k_r1g1_0001'
    decisions = [{'id': k['id'], 'status': 'approved'} for k in state['keywords']]
    with pytest.raises(store.StoreError) as exc:
        rounds.commit_round('test', 1, decisions, gen=2)
    assert exc.value.status == 409
    rounds.commit_round('test', 1, decisions, gen=1)


def test_empty_commit_stale_generation(client, backend, monkeypatch):
    monkeypatch.setattr(backend, 'run', FakeBackend({'kw_r1': '{"keywords": []}'}).run)
    # Empty successful drafts still require the explicit generation check.
    start(client, 1)
    store.update_session('test', {'keywordRounds': {'1': {'keywords': [], 'job': {'status': 'done'}}}})
    assert client.post('/keywords/test/rounds/1/commit', json={'gen': 2, 'decisions': []}).status_code == 409
    assert client.post('/keywords/test/rounds/1/commit', json={'gen': 1, 'decisions': []}).status_code == 200


@pytest.mark.parametrize('replacement', [{'jobId': 'replacement'}, {'status': 'done'}])
def test_threaded_failure_preserves_superseding_job(client, threaded, monkeypatch, replacement):
    def superseded(*args):
        store.update_session('test', {'keywordRounds': {'1': {'job': replacement}}})
        raise store.StoreError('old worker failed')
    monkeypatch.setattr(rounds, '_inputs', superseded)
    state = finish_threaded(client, threaded)
    for key, value in replacement.items():
        assert state[key] == value
    assert state['error'] is None


@pytest.mark.parametrize('n', [1, 2, 3, 4])
def test_regenerate_uncommitted_round(client, monkeypatch, n):
    through(client, n - 1)
    first = start(client, n)
    before_committed = store.load_session('test')['keywords']
    assert client.post(f'/keywords/test/rounds/{n}').status_code == 409
    assert client.post(f'/keywords/test/rounds/{n}?regenerate=false').status_code == 409
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    response = client.post(f'/keywords/test/rounds/{n}?regenerate=true')
    assert response.status_code == 200, response.text
    running = response.json()
    assert running['jobId'] != first['jobId']
    assert running['gen'] == first['gen'] + 1
    assert client.get(f'/keywords/test/rounds/{n}').json()['keywords'] == first['keywords']
    assert client.post(f'/keywords/test/rounds/{n}?regenerate=true').json()['jobId'] == running['jobId']
    assert len(queued) == 1
    # A replacement may legitimately return the same words under fresh IDs.
    generated = [{**{key: k[key] for key in ('kw', 'axis', 'sub')}, 'why': '상황'}
                 for k in first['keywords']]
    fake = FakeBackend({f'kw_round_{n}': json.dumps({'keywords': generated})})
    monkeypatch.setattr(registry, 'get_backend', lambda task: fake)
    queued[0]()
    second = client.get(f'/keywords/test/rounds/{n}').json()
    assert second['status'] == 'done'
    assert [k['id'] for k in second['keywords']] == [f'k_r{n}g2_{i:04d}' for i in range(1, 43)]
    assert store.load_session('test')['keywords'] == before_committed
    assert commit(client, n, first).status_code == 409
    assert commit(client, n, second).status_code == 200


@pytest.mark.parametrize('n', [1, 2, 3])
def test_regenerate_committed_round_rejected(client, n):
    through(client, n)
    before = client.get(f'/keywords/test/rounds/{n}').json()
    assert client.post(f'/keywords/test/rounds/{n}?regenerate=true').status_code == 409
    assert client.get(f'/keywords/test/rounds/{n}').json() == before


def test_regenerate_enforces_order(client):
    assert client.post('/keywords/test/rounds/2?regenerate=true').status_code == 409
    start(client, 1)
    assert client.post('/keywords/test/rounds/2?regenerate=true').status_code == 409


def test_regenerate_failed_round(client, backend, monkeypatch):
    from app.llm.base import failure
    through(client, 1)
    original = backend.run
    monkeypatch.setattr(backend, 'run', lambda task: failure('timeout', 'Timed out'))
    first = start(client, 2)
    assert first['status'] == 'failed'
    monkeypatch.setattr(backend, 'run', original)
    response = client.post('/keywords/test/rounds/2?regenerate=true')
    assert response.status_code == 200
    second = client.get('/keywords/test/rounds/2').json()
    assert second['jobId'] != first['jobId'] and second['gen'] == first['gen'] + 1
    assert second['status'] == 'done'


def test_r4_explicit_regenerate_preserves_committed_keywords(client):
    through(client, 4)
    before = store.load_session('test')['keywords']
    response = client.post('/keywords/test/rounds/4?regenerate=true')
    assert response.status_code == 200 and response.json()['gen'] == 2
    assert client.get('/keywords/test/rounds/4').json()['status'] == 'done'
    assert store.load_session('test')['keywords'] == before


@pytest.fixture
def autocomplete_calls(monkeypatch):
    calls = []
    def suggestions(seeds, on_progress=None):
        calls.append(seeds)
        return naver_autocomplete.AutocompleteResult(
            [('냉방1단어0', 1), ('누락상위', 2), ('누락하위', 8)], 3, len(seeds))
    monkeypatch.setattr(naver_autocomplete, 'suggestions', suggestions)
    return calls


def test_coverage_uses_searchad_when_connected(client, monkeypatch, autocomplete_calls):
    monkeypatch.setattr(rounds.naver_searchad, 'related_queries',
                        lambda hints: [('냉방1단어0', 100), ('누락', 20)])
    through(client, 2)
    saved = client.get('/keywords/test').json()['coverage']
    assert saved['source'] == 'searchad' and saved['weighting'] == 'volume'
    assert saved['m1'] == pytest.approx(100 / 120)
    assert saved['m2_bands'] is None and saved['m7_reason'] is None
    assert not autocomplete_calls


def test_coverage_falls_back_to_autocomplete_when_unconnected(client, autocomplete_calls):
    through(client, 1)
    # Seed order follows displayed generation order, excluding manual/rejected items.
    data = store.load_session('test')
    kws = data['keywords']
    kws[0]['status'] = 'rejected'
    kws[1]['origin'] = 'manual'
    data.update(keywords=kws, projectContext={'bk': '에어컨'})
    store.write_json(store.session_dir('test') / 'session.json', data)
    state = start(client, 2)
    assert commit(client, 2, state).status_code == 200
    saved = client.get('/keywords/test').json()['coverage']
    expected = [k['kw'] for k in kws if k['status'] == 'approved' and k['origin'] == 'llm'][:20]
    assert autocomplete_calls == [['에어컨'] + expected]
    assert saved['source'] == 'autocomplete' and saved['weighting'] == 'rank'
    assert saved['seeds'] == 21 and saved['failedSeeds'] == 3
    assert saved['humanQueries'] == [['냉방1단어0', 1], ['누락상위', 2], ['누락하위', 8]]
    assert saved['m2'] is None and len(saved['m2_bands']) == 3
    assert saved['m7'] is None and saved['m7_reason'] == 'no_volume'


def test_coverage_autocomplete_unavailable_status(client, monkeypatch):
    def unavailable(seeds, on_progress=None):
        raise naver_autocomplete.AutocompleteUnavailable('private failure detail')
    monkeypatch.setattr(naver_autocomplete, 'suggestions', unavailable)
    through(client, 2)
    saved = client.get('/keywords/test').json()['coverage']
    assert saved['status'] == 'unavailable'
    assert saved['source'] == 'autocomplete' and saved['weighting'] == 'rank'
    assert saved['failedSeeds'] == saved['seeds'] == 20
    assert 'private failure detail' not in json.dumps(saved)
    assert start(client, 3)['status'] == 'done'
    assert commit(client, 3).status_code == 200


def test_coverage_cached_once_refresh_refetches(client, autocomplete_calls):
    through(client, 2)
    before = client.get('/keywords/test').json()['coverage']
    for _ in range(2):
        assert client.post('/keywords/test/coverage').json() == before
    assert len(autocomplete_calls) == 1
    assert client.post('/keywords/test/coverage?refresh=true').status_code == 200
    assert len(autocomplete_calls) == 2


def test_missing_top_feeds_r3_inputs(client, backend, monkeypatch):
    human = [(f'누락검색어{i:02}', 10 - i % 10) for i in range(25)]
    monkeypatch.setattr(naver_autocomplete, 'suggestions', lambda seeds, on_progress=None:
                        naver_autocomplete.AutocompleteResult(human, 0, len(seeds)))
    through(client, 2)
    missing = sorted(human, key=lambda row: row[1])[:20]
    assert client.get('/keywords/test').json()['coverage']['missing_top'] == [list(row) for row in missing]
    assert start(client, 3)['inputs']['coverage'] == 'ok'
    assert json.dumps(missing, ensure_ascii=False) in backend.calls[-1].instructions


def test_r2_commit_returns_before_autocomplete_finishes(client, monkeypatch, autocomplete_calls):
    through(client, 1)
    state = start(client, 2)
    queued = []
    def execute(fn):
        saved = store.load_session('test')
        assert saved['keywordRounds']['2']['committed']
        assert saved['coverage']['status'] == 'loading'
        assert saved['coverage']['startedAt']
        queued.append(fn)
    monkeypatch.setattr(rounds, 'execute', execute)
    assert commit(client, 2, state).status_code == 200
    assert not autocomplete_calls
    assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
    assert len(queued) == 1
    queued[0]()
    assert client.get('/keywords/test').json()['coverage']['status'] == 'connected'


@pytest.mark.parametrize('age,status', [(119, 'loading'), (121, 'unavailable')])
def test_stale_loading_over_2min_reads_unavailable(client, monkeypatch, autocomplete_calls, age, status):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    saved = {'status': 'loading', 'startedAt': (now - timedelta(seconds=age)).isoformat()}
    store.update_session('test', {'coverage': saved})
    assert client.get('/keywords/test').json()['coverage']['status'] == status
    assert client.post('/keywords/test/coverage').json()['status'] == status
    assert not autocomplete_calls


def test_refresh_param_refetches_only_when_true(client, monkeypatch, autocomplete_calls):
    through(client, 2)
    before = client.get('/keywords/test').json()['coverage']
    assert client.post('/keywords/test/coverage?refresh=false').json() == before
    assert client.post('/keywords/test/coverage?refresh=invalid').status_code == 422
    assert len(autocomplete_calls) == 1
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    refreshed = client.post('/keywords/test/coverage?refresh=true').json()
    assert refreshed['status'] == 'loading' and refreshed['startedAt']
    assert len(queued) == 1 and len(autocomplete_calls) == 1
    assert client.post('/keywords/test/coverage').json()['status'] == 'loading'
    assert len(queued) == 1
    queued[0]()
    assert len(autocomplete_calls) == 2



def test_coverage_real_worker_does_not_block_commit(client, monkeypatch):
    through(client, 1)
    state = start(client, 2)
    entered, release = Event(), Event()
    workers = []
    def suggestions(seeds, on_progress=None):
        entered.set()
        assert release.wait(5)
        return naver_autocomplete.AutocompleteResult([('누락', 1)], 0, len(seeds))
    def execute(fn):
        workers.append(THREADED_EXECUTE(fn))
    monkeypatch.setattr(naver_autocomplete, 'suggestions', suggestions)
    monkeypatch.setattr(rounds, 'execute', execute)
    try:
        assert commit(client, 2, state).status_code == 200
        assert entered.wait(2)
        assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
    finally:
        release.set()
        for worker in workers:
            worker.join(5)
            assert not worker.is_alive()
    assert client.get('/keywords/test').json()['coverage']['status'] == 'connected'


def test_coverage_refresh_discards_queries_and_axes(client, backend, monkeypatch, autocomplete_calls):
    through(client, 2)
    classified = []
    original = backend.run
    def classify(task):
        if task.task == 'kw_axis_classify':
            classified.append(task.instructions)
            return FakeBackend({task.task: json.dumps({'axes': {'새검색어': 'physical'}})}).run(task)
        return original(task)
    monkeypatch.setattr(backend, 'run', classify)
    monkeypatch.setattr(naver_autocomplete, 'suggestions', lambda seeds, on_progress=None:
                        naver_autocomplete.AutocompleteResult([('새검색어', 4)], 0, len(seeds)))
    client.post('/keywords/test/coverage?refresh=true')
    saved = client.get('/keywords/test').json()['coverage']
    assert saved['humanQueries'] == [['새검색어', 4]]
    assert saved['humanAxes'] == {'새검색어': 'physical'}
    assert len(classified) == 1 and '새검색어' in classified[0]


def test_loading_coverage_deduplicates_refresh(client, monkeypatch, autocomplete_calls):
    through(client, 2)
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    first = client.post('/keywords/test/coverage?refresh=true').json()
    assert client.post('/keywords/test/coverage?refresh=true').json() == first
    assert len(queued) == 1 and len(autocomplete_calls) == 1
    queued[0]()
    assert len(autocomplete_calls) == 2


def test_superseded_coverage_worker_preserves_new_result(client, monkeypatch, autocomplete_calls):
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    client.post('/keywords/test/coverage')
    replacement = {'status': 'connected', 'source': 'searchad', 'humanQueries': [['replacement', 10]]}
    store.update_session('test', {'coverage': rounds._Replacement(replacement)})
    queued[0]()
    assert client.get('/keywords/test').json()['coverage'] == replacement


@pytest.mark.parametrize('source', ['autocomplete', 'searchad'])
def test_r2_recommit_recomputes_cached_queries(client, monkeypatch, source):
    human = [('냉방2단어0', 2), ('새승인', 4)]
    if source == 'searchad':
        monkeypatch.setattr(rounds.naver_searchad, 'related_queries', lambda hints: human)
    else:
        monkeypatch.setattr(naver_autocomplete, 'suggestions', lambda seeds, on_progress=None:
                            naver_autocomplete.AutocompleteResult(human, 0, len(seeds)))
    through(client, 2)
    before = store.load_session('test')['coverage']
    assert before['missing_top'] == [['새승인', 4]]
    def forbidden(*args):
        pytest.fail('Cached coverage must not fetch or classify')
    monkeypatch.setattr(rounds.naver_searchad, 'related_queries', forbidden)
    monkeypatch.setattr(naver_autocomplete, 'suggestions', forbidden)
    monkeypatch.setattr(rounds, 'run_task', forbidden)
    replacement = {**store.load_session('test')['keywords'][-1], 'id': 'replacement', 'kw': '새승인', 'status': 'pending'}
    store.update_session('test', {'keywordRounds': {'2': {'committed': False, 'replacing': True,
        'gen': 2, 'job': {'gen': 2}, 'keywords': [replacement]}}})
    assert commit(client, 2).status_code == 200
    after = store.load_session('test')['coverage']
    assert after['missing_top'] == [['냉방2단어0', 2]]
    assert after['m1'] != before['m1']
    assert after['humanQueries'] == before['humanQueries']
    assert after['humanAxes'] == before['humanAxes']
    assert after['m2_bands' if source == 'autocomplete' else 'm2'] != before['m2_bands' if source == 'autocomplete' else 'm2']


def test_classifying_persists_queries_and_uses_recent_update(client, monkeypatch):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    def suggestions(seeds, on_progress=None):
        nonlocal now
        now += timedelta(seconds=121)
        return naver_autocomplete.AutocompleteResult([('검색어', 1)], 0, len(seeds))
    monkeypatch.setattr(naver_autocomplete, 'suggestions', suggestions)
    def classify(task):
        saved = store.load_session('test')['coverage']
        assert saved['humanQueries'] == [['검색어', 1]]
        assert saved['phase'] == 'classifying'
        assert saved['updatedAt'] == now.isoformat()
        assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
        return FakeBackend().run(task)
    monkeypatch.setattr(rounds, 'run_task', classify)
    client.post('/keywords/test/coverage')
    assert store.load_session('test')['coverage']['status'] == 'connected'


def test_empty_bk_not_sent_to_autocomplete(client, autocomplete_calls):
    through(client, 2)
    assert '' not in autocomplete_calls[0]


@pytest.mark.parametrize('source,label', [('autocomplete', '자동완성 순위'), ('searchad', '월간 검색수')])
def test_r3_coverage_numbers_have_source_label(client, source, label):
    store.update_session('test', {'coverage': {'status': 'connected', 'source': source, 'missing_top': [['누락', 3]]}})
    assert label in rounds._inputs('test', store.load_session('test'), 3).coverage_signals


def test_slow_classification_heartbeat_keeps_loading(client, monkeypatch):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    monkeypatch.setattr(naver_autocomplete, 'suggestions', lambda seeds, on_progress=None:
                        naver_autocomplete.AutocompleteResult([('검색어', 1)], 0, len(seeds)))
    callbacks = []
    class ControlledThread:
        def __init__(self, target, **kwargs):
            callbacks.append(target)
        def start(self):
            pass
        def join(self):
            pass
    class ControlledEvent:
        ticks = 0
        def wait(self, seconds):
            nonlocal now
            self.ticks += 1
            if self.ticks > 5:
                return True
            now += timedelta(seconds=seconds)
            assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
            return False
        def set(self):
            pass
    monkeypatch.setattr(rounds, 'Thread', ControlledThread)
    monkeypatch.setattr(rounds, 'Event', ControlledEvent)
    def classify(task):
        callbacks[0]()
        saved = store.load_session('test')['coverage']
        assert saved['phase'] == 'classifying'
        assert saved['humanQueries'] == [['검색어', 1]]
        assert (now - datetime.fromisoformat(saved['startedAt'])).total_seconds() == 150
        assert saved['updatedAt'] == now.isoformat()
        assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
        return FakeBackend().run(task)
    monkeypatch.setattr(rounds, 'run_task', classify)
    client.post('/keywords/test/coverage')
    assert store.load_session('test')['coverage']['status'] == 'connected'


@pytest.mark.parametrize('regenerate', [False, True])
def test_review_r3_loading_gate(client, monkeypatch, regenerate):
    through(client, 2)
    if regenerate:
        start(client, 3)
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    client.post('/keywords/test/coverage?refresh=true')
    response = client.post(f'/keywords/test/rounds/3?regenerate={str(regenerate).lower()}')
    assert response.status_code == 409
    assert '커버리지를 받는 중입니다. 끝나면 R3를 만들 수 있습니다.' in response.text
    assert len(queued) == 1


@pytest.mark.parametrize('status', ['connected', 'unavailable', 'unconnected', 'stale'])
@pytest.mark.parametrize('regenerate', [False, True])
def test_review_r3_terminal_snapshot(client, monkeypatch, status, regenerate):
    through(client, 2)
    if regenerate:
        start(client, 3)
    cov = {'status': status, 'source': 'autocomplete', 'missing_top': [['admitted', 1]]}
    if status == 'stale':
        cov.update(status='loading', updatedAt='2000-01-01T00:00:00+00:00')
    store.update_session('test', {'coverage': rounds._Replacement(cov)})
    input_data = store.load_session('test')
    input_data.get('keywordRounds', {}).get('3', {}).pop('coverageSnapshot', None)
    expected = rounds._inputs('test', input_data, 3).coverage_signals
    queued, captured = [], []
    original = rounds._inputs
    def capture(sid, data, n):
        state = original(sid, data, n)
        captured.append(state.coverage_signals)
        return state
    monkeypatch.setattr(rounds, '_inputs', capture)
    monkeypatch.setattr(rounds, 'execute', queued.append)
    assert client.post(f'/keywords/test/rounds/3?regenerate={str(regenerate).lower()}').status_code == 200
    store.update_session('test', {'coverage': rounds._Replacement(
        {'status': 'connected', 'missing_top': [['later refresh', 9]]})})
    queued[0]()
    assert captured == [expected]


def test_review_stale_refresh_recommit_never_reuses_previous(client, monkeypatch):
    through(client, 2)
    old = store.load_session('test')['coverage']
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    loading = client.post('/keywords/test/coverage?refresh=true').json()
    fields = {'humanQueries', 'humanAxes', 'source', 'weighting', *rounds.coverage.CoverageReport.__dataclass_fields__}
    assert not fields.intersection(loading)
    assert loading['previous'] == {key: old[key] for key in fields if key in old}
    now = datetime.fromisoformat(loading['updatedAt']) + timedelta(seconds=121)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    store.update_session('test', {'keywordRounds': {'2': {'committed': False}}})
    assert commit(client, 2).status_code == 200
    assert client.get('/keywords/test').json()['coverage']['status'] == 'unavailable'
    assert len(queued) == 1
    queued[0]()
    assert client.get('/keywords/test').json()['coverage']['status'] == 'connected'


def test_review_slow_autocomplete_fetch_keeps_loading(client, monkeypatch):
    import httpx
    through(client, 2)
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    data = store.load_session('test')
    data['projectContext'] = {'bk': 'product'}
    store.write_json(store.session_dir('test') / 'session.json', data)
    monkeypatch.setattr(settings, 'autocomplete_backend', 'http')
    observed = []
    def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)
        observed.append(client.get('/keywords/test').json()['coverage']['status'])
    def response(request):
        advance(9)
        return httpx.Response(200, json={'items': [[['query']]]})
    original = naver_autocomplete.suggestions
    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        monkeypatch.setattr(naver_autocomplete, 'suggestions',
            lambda seeds, **kwargs: original(seeds, client=http, sleep=advance, **kwargs))
        client.post('/keywords/test/coverage?refresh=true')
    assert len(observed) == 41  # 21 seeds and 20 one-second delays
    assert set(observed) == {'loading'}
    assert client.get('/keywords/test').json()['coverage']['status'] == 'connected'


def test_review_searchad_fetch_heartbeat(client, monkeypatch):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, 'now', lambda: now.isoformat())
    callbacks, stopped = [], []
    class ControlledThread:
        def __init__(self, target, **kwargs):
            callbacks.append(target)
        def start(self):
            pass
        def join(self):
            pass
    class ControlledEvent:
        ticks = 0
        def wait(self, seconds):
            nonlocal now
            assert seconds == 30
            self.ticks += 1
            if self.ticks > 5:
                return True
            now += timedelta(seconds=seconds)
            assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
            return False
        def set(self):
            stopped.append(True)
    monkeypatch.setattr(rounds, 'Thread', ControlledThread)
    monkeypatch.setattr(rounds, 'Event', ControlledEvent)
    def fetch(hints):
        assert callbacks, 'heartbeat must start before SearchAd fetch'
        callbacks[0]()
        assert store.load_session('test')['coverage']['updatedAt'] == now.isoformat()
        return []
    monkeypatch.setattr(rounds.naver_searchad, 'related_queries', fetch)
    client.post('/keywords/test/coverage')
    assert stopped
    assert store.load_session('test')['coverage']['status'] == 'connected'
