import json
import math
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.context import store, versions
from app.label import jev
from app.crawl.ratelimit import ChannelLimiter
from tests.fakes.fake_jev import FakeJev


REAL_WAIT_START = ChannelLimiter.wait_start


class Context:
    sid = 'session'
    version = 'v1'
    run_id = 'run'
    def __init__(self, labeler='jev'):
        self.args = {'labeler': labeler}
        self.details = []
        self.stopped = False
        self.checks = 0
    def heartbeat(self, progress, detail):
        self.details.append(json.loads(json.dumps(detail)))
    def should_stop(self):
        self.checks += 1
        return self.stopped


@pytest.fixture
def setup_judge(data_dir, monkeypatch):
    from app.label import judge
    def prepare(n=3, one_liner='사용 경험', version='v1'):
        session = dict(projectContext={'oneLiner': one_liner}, prep={'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}})
        store.write_json(versions.version_dir('session', version) / 'session.json', session)
        root = data_dir / 'derived/session/c1/p_123456789abc/docs'
        root.mkdir(parents=True, exist_ok=True)
        docs = [dict(doc_id=f'd{i:03}', body='본문', title='제목') for i in range(n)]
        (root / '000.jsonl').write_text(''.join(json.dumps(doc) + '\n' for doc in docs))
        return docs
    calls = []
    fake = FakeJev()
    def handle(request):
        calls.append(request.headers['Idempotency-Key'])
        return fake(request)
    real_client = jev.JevClient
    monkeypatch.setattr(judge, 'JevClient', lambda keys, model: real_client(keys, model, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(settings, 'jev_api_keys', ['offline'])
    jev.reset_limiter_pool()
    monkeypatch.setattr(ChannelLimiter, 'wait_start', lambda self: None)
    monkeypatch.setattr(settings, 'codex_bin', str(Path(__file__).resolve().parents[1] / 'fakes/fake_codex.py'))
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(settings, 'codex_timeout_s', 30)
    yield SimpleNamespace(prepare=prepare, calls=calls, judge=judge, root=data_dir)
    jev.reset_limiter_pool()


def cache_for(env, labeler='jev', one_liner='사용 경험'):
    from app.label.votes import VoteCache
    return VoteCache(env.judge.cache_root('session', 'p_123456789abc', labeler, one_liner))


@pytest.mark.parametrize('labeler', ['jev', 'gpt'])
def test_both_labelers_fill_cache(setup_judge, labeler):
    env = setup_judge
    env.prepare()
    env.judge.run_worker(Context(labeler))
    cache = cache_for(env, labeler)
    assert cache.counts() == dict(pending=0, done=3, bad=0)
    if labeler == 'jev':
        key = env.judge.context_key('사용 경험', 'jev')
        assert env.calls == [f'd{i:03}:q1-{key}' for i in range(3)]
    else:
        assert list((env.root / 'llm_runs').glob('*/invocations'))


def test_one_liner_change_new_cache(setup_judge):
    env = setup_judge
    env.prepare()
    env.judge.run_worker(Context())
    env.prepare(one_liner='다른 경험')
    ctx = Context()
    env.judge.run_worker(ctx)
    assert cache_for(env).path != cache_for(env, one_liner='다른 경험').path
    assert cache_for(env, one_liner='다른 경험').counts()['done'] == 3
    assert len(env.calls) == 6
    assert any(d.get('message') == '판정 맥락이 바뀌어 다시 판정합니다' for d in ctx.details)


@pytest.mark.parametrize('labeler', ['jev', 'gpt'])
def test_cache_shared_across_versions(setup_judge, labeler):
    env = setup_judge
    env.prepare()
    env.judge.run_worker(Context(labeler))
    before = {p: p.read_text() for p in (env.root / 'llm_runs').glob('*/invocations')}
    env.prepare(version='v2')
    ctx = Context(labeler)
    ctx.version = 'v2'
    env.judge.run_worker(ctx)
    assert len(env.calls) == (3 if labeler == 'jev' else 0)
    assert cache_for(env, labeler).counts()['done'] == 3
    assert {p: p.read_text() for p in (env.root / 'llm_runs').glob('*/invocations')} == before


def test_rate_limit_respected(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare(125)
    now, starts = [1000.0], []
    monkeypatch.setattr(ChannelLimiter, 'wait_start', REAL_WAIT_START)
    real_wait = ChannelLimiter
    def sleep(delay):
        now[0] += delay
    monkeypatch.setattr(jev, 'ChannelLimiter', lambda concurrency, min_interval_s: real_wait(concurrency, min_interval_s, clock=lambda: now[0], sleep=sleep))
    real_client = jev.JevClient
    fake = FakeJev()
    def handle(request):
        starts.append(now[0])
        return fake(request)
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real_client(keys, model, transport=httpx.MockTransport(handle)))
    ctx = Context()
    env.judge.run_worker(ctx)
    assert len(starts) == 125
    assert all(sum(t <= s < t + 60 for s in starts) <= 120 for t in starts)
    assert ctx.checks < 15


def test_insufficient_credit_pauses(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare()
    real = jev.JevClient
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real(keys, model, transport=httpx.MockTransport(lambda _: httpx.Response(402))))
    reasons = []
    def pause(ctx, reason, detail):
        reasons.append(reason)
        ctx.stopped = True
    monkeypatch.setattr(env.judge, '_pause', pause)
    env.judge.run_worker(Context())
    assert reasons == ['Jev 잔액이 부족합니다']
    assert cache_for(env).counts() == dict(pending=3, done=0, bad=0)


@pytest.mark.parametrize('failure', ['missing', 'paused'])
def test_gpt_failures_bounded_per_document(setup_judge, monkeypatch, failure):
    from app.label.gpt import LabelerPaused
    env = setup_judge
    env.prepare()
    calls = []
    def fail(docs, *args, **kwargs):
        calls.append([d['doc_id'] for d in docs])
        if failure == 'paused':
            raise LabelerPaused('safe reason')
        return {}, [d['doc_id'] for d in docs]
    monkeypatch.setattr(env.judge.gpt, 'judge_batch', fail)
    monkeypatch.setattr(env.judge, '_pause', lambda ctx, *a: setattr(ctx, 'stopped', True))
    for _ in range(4):
        env.judge.run_worker(Context('gpt'))
    assert len(calls) == 3
    assert cache_for(env, 'gpt').counts() == dict(pending=0, done=0, bad=3)


def test_partial_batch_keeps_successes(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare()
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'partial')
    env.judge.run_worker(Context('gpt'))
    assert cache_for(env, 'gpt').counts()['done'] == 3


def test_estimate(setup_judge):
    env = setup_judge
    docs = env.prepare(3)
    result = env.judge.estimate(docs, '사용 경험', 'jev', key_count=2)
    from app.label.questions import jev_questions
    expected = sum(math.ceil(len(json.dumps(dict(model=settings.jev_model, state=jev.build_state(d, '사용 경험')[0], questions=jev_questions('사용 경험')), ensure_ascii=False, separators=(',', ':'))) / 4) for d in docs)
    assert result['jevTokens'] == expected
    assert result['seconds'] == .75


def test_worker_publishes_estimate(setup_judge):
    env = setup_judge
    env.prepare()
    ctx = Context()
    env.judge.run_worker(ctx)
    assert any(d.get('estimate', {}).get('jevTokens', 0) > 0 for d in ctx.details)


def test_unconnected_stops_without_bad_documents(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare()
    real = jev.JevClient
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real([], model))
    monkeypatch.setattr(env.judge, '_pause', lambda *a: pytest.fail('401 must stop'))
    with pytest.raises(jev.JevError, match='연결 키'):
        env.judge.run_worker(Context())
    assert cache_for(env).counts()['pending'] == 3


def test_real_context_pause_resume(setup_judge, monkeypatch):
    import os
    import threading
    import time
    from app.work.worker import Context as RealContext, execute
    from app.work.status import transaction
    from app.work import runner
    from app.label.gpt import LabelerPaused
    env = setup_judge
    env.prepare()
    monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
    original = env.judge.gpt.judge_batch
    calls = []
    def judge(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise LabelerPaused('사용량 한도')
        return original(*args, **kwargs)
    monkeypatch.setattr(env.judge.gpt, 'judge_batch', judge)
    with transaction('session') as db:
        db.execute("INSERT INTO runs(run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at) VALUES ('real','v1','judge','gpt','{}',?,'running',?,?)", (os.getpid(), time.time(), time.time()))
    thread = threading.Thread(target=execute, args=(RealContext('session', 'v1', 'judge', {'labeler': 'gpt'}, 'real'),))
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = runner.status('session')[0]
            if status['state'] == 'paused' and status['detail'].get('reason'):
                break
            time.sleep(.01)
        assert status['state'] == 'paused'
        assert status['detail']['reason'] == '사용량 한도'
        assert cache_for(env, 'gpt').counts()['pending'] == 3
        runner.request('session', 'real', 'resume')
        thread.join(30)
        assert not thread.is_alive()
        assert runner.status('session')[0]['state'] == 'done'
        assert cache_for(env, 'gpt').counts()['done'] == 3
    finally:
        runner.request('session', 'real', 'stop')
        thread.join(30)


def test_model_and_backend_change_context(setup_judge, monkeypatch):
    judge = setup_judge.judge
    old = judge.context_key('context', 'jev')
    monkeypatch.setattr(settings, 'jev_model', 'other-model')
    assert judge.context_key('context', 'jev') != old
    old = judge.context_key('context', 'gpt')
    monkeypatch.setattr(settings, 'label_gpt_backend', 'openai_api')
    assert judge.context_key('context', 'gpt') != old


def pending_rows(cache):
    import sqlite3
    with sqlite3.connect(cache.path) as db:
        return db.execute('SELECT attempts, run_id FROM votes ORDER BY doc_id').fetchall()


def test_transport_outage_releases_backoffs_and_pauses(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare(100)
    calls, sleeps, reasons = [], [], []
    real = jev.JevClient
    def fail(request):
        calls.append(request)
        raise httpx.ConnectError('offline', request=request)
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real(keys, model, transport=httpx.MockTransport(fail)))
    def sleep(delay):
        assert pending_rows(cache_for(env)) == [(0, None)] * 100
        sleeps.append(delay)
    monkeypatch.setattr(env.judge.time, 'sleep', sleep)
    def pause(ctx, reason, detail):
        assert pending_rows(cache_for(env)) == [(0, None)] * 100
        reasons.append(reason)
        ctx.stopped = True
    monkeypatch.setattr(env.judge, '_pause', pause)
    env.judge.run_worker(Context())
    assert len(calls) == 5
    assert sleeps == [1, 2, 4, 8]
    assert reasons == ['Jev 연결이 불안정해 판정을 멈췄습니다']
    assert cache_for(env).counts() == dict(pending=100, done=0, bad=0)


def test_usage_limit_never_consumes_attempts(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare()
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'usage_limit')
    def pause(ctx, reason, detail):
        assert '사용량 한도' in reason
        assert pending_rows(cache_for(env, 'gpt')) == [(0, None)] * 3
        ctx.stopped = True
    monkeypatch.setattr(env.judge, '_pause', pause)
    for _ in range(4):
        env.judge.run_worker(Context('gpt'))
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'normal')
    env.judge.run_worker(Context('gpt'))
    assert cache_for(env, 'gpt').counts() == dict(pending=0, done=3, bad=0)


def test_transient_streak_resets_after_success(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare(2)
    real, fake = jev.JevClient, FakeJev()
    attempts, sleeps = {}, []
    def handle(request):
        key = request.headers['Idempotency-Key']
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] <= 4:
            raise httpx.ReadTimeout('offline', request=request)
        return fake(request)
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real(keys, model, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(env.judge.time, 'sleep', sleeps.append)
    monkeypatch.setattr(env.judge, '_pause', lambda *a: pytest.fail('Successful vote must reset the outage streak'))
    env.judge.run_worker(Context())
    assert sleeps == [1, 2, 4, 8] * 2
    assert cache_for(env).counts() == dict(pending=0, done=2, bad=0)
    assert pending_rows(cache_for(env)) == [(0, None)] * 2


@pytest.mark.parametrize('fault', ['422', 'missing'])
def test_jev_document_faults_still_consume_attempts(setup_judge, monkeypatch, fault):
    env = setup_judge
    env.prepare(2)
    real, calls = jev.JevClient, []
    def handle(request):
        calls.append(request.headers['Idempotency-Key'])
        return httpx.Response(422) if fault == '422' else httpx.Response(200, json={'model': 'test', 'answers': {}})
    monkeypatch.setattr(env.judge, 'JevClient', lambda keys, model: real(keys, model, transport=httpx.MockTransport(handle)))
    env.judge.run_worker(Context())
    assert len(calls) == 6
    assert cache_for(env).counts() == dict(pending=0, done=0, bad=2)
    assert pending_rows(cache_for(env)) == [(3, None)] * 2
