from collections import Counter
import os
import threading
import time

import pytest

from app.config import settings
from app.label import gpt
from app.label.rule import SEM
from app.label.votes import VoteCache
from app.work.status import transaction
from tests.label.test_judge import Context, cache_for, setup_judge


@pytest.fixture
def concurrent_judge(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare(8)
    monkeypatch.setattr(settings, 'label_batch_size', 2)
    monkeypatch.setattr(settings, 'label_concurrency', 4)
    monkeypatch.setattr(settings, 'jev_backend', 'fake')
    env.puts = []
    env.fails = []
    owner = threading.get_ident()
    put, fail = VoteCache.put, VoteCache.fail

    def record_put(cache, doc_id, payload):
        assert threading.get_ident() == owner
        env.puts.append(doc_id)
        put(cache, doc_id, payload)

    def record_fail(cache, doc_id, reason):
        assert threading.get_ident() == owner
        env.fails.append((doc_id, reason))
        fail(cache, doc_id, reason)

    monkeypatch.setattr(VoteCache, 'put', record_put)
    monkeypatch.setattr(VoteCache, 'fail', record_fail)
    return env


def votes(docs):
    return {d['doc_id']: gpt.GptVote(anchor=False, sem=dict.fromkeys(SEM, 0),
            situation=False, reason_code='no_needs', signal=None) for d in docs}, []


def rows(env):
    with cache_for(env, 'gpt')._db() as db:
        return {r['doc_id']: dict(r) for r in db.execute('SELECT * FROM votes')}


@pytest.mark.parametrize('concurrency', [4, 1, 0])
def test_batches_overlap_and_put_once(concurrent_judge, monkeypatch, concurrency):
    env = concurrent_judge
    monkeypatch.setattr(settings, 'label_concurrency', concurrency)
    barrier = threading.Barrier(4, timeout=5) if concurrency == 4 else None
    lock = threading.Lock()
    calls = []
    active = maximum = 0

    def judge(docs, *args, **kwargs):
        nonlocal active, maximum
        with lock:
            calls.append([d['doc_id'] for d in docs])
            active += 1
            maximum = max(maximum, active)
        try:
            if barrier:
                barrier.wait()
            else:
                time.sleep(.01)
            return votes(docs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(gpt, 'judge_batch', judge)
    env.judge.run_worker(Context('gpt'))
    assert maximum == max(1, concurrency)
    assert sorted(calls) == [[f'd{i:03}', f'd{i+1:03}'] for i in range(0, 8, 2)]
    assert Counter(env.puts) == Counter(f'd{i:03}' for i in range(8))
    assert cache_for(env, 'gpt').counts() == dict(pending=0, done=8, bad=0)


@pytest.mark.parametrize('failure', ['limit', 'backend', 'missing', 'error', 'mixed'])
@pytest.mark.parametrize('attempts', [0, 2])
def test_chunk_failures_preserve_peers(concurrent_judge, monkeypatch, failure, attempts):
    env = concurrent_judge
    cache = cache_for(env, 'gpt')
    cache.seed(f'd{i:03}' for i in range(8))
    with cache._db() as db:
        db.execute('UPDATE votes SET attempts=?', (attempts,))
    barrier = threading.Barrier(4, timeout=5)
    seen = set()
    lock = threading.Lock()
    error = ValueError('unexpected failure')

    def judge(docs, *args, **kwargs):
        ids = [d['doc_id'] for d in docs]
        with lock:
            first = ids[0] not in seen
            seen.update(ids)
        if first:
            barrier.wait()
        if ids[0] == 'd000':
            if failure in ('limit', 'mixed'):
                raise gpt.LabelerPaused('usage limit', usage_limit=True)
            if failure == 'backend':
                raise gpt.LabelerPaused('backend failed')
            if failure == 'error':
                raise error
            result, _ = votes(docs[1:])
            return result, ids[:1]
        if failure == 'mixed' and ids[0] == 'd002':
            raise gpt.LabelerPaused('backend failed')
        return votes(docs)

    ctx = Context('gpt')
    with transaction(ctx.sid) as db:
        db.execute("INSERT INTO runs(run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES ('run','v1','judge','{}',?,'running',?,?)", (os.getpid(), time.time(), time.time()))
    heartbeat = ctx.heartbeat

    def stop_on_pause(progress, detail):
        heartbeat(progress, detail)
        if detail.get('reason'):
            ctx.stopped = True

    ctx.heartbeat = stop_on_pause
    monkeypatch.setattr(gpt, 'judge_batch', judge)
    if failure == 'error':
        with pytest.raises(ValueError) as caught:
            env.judge.run_worker(ctx)
        assert caught.value is error
    else:
        env.judge.run_worker(ctx)
    result = rows(env)
    failed = {'d000'} if failure == 'missing' else {'d000', 'd001'}
    if failure == 'mixed':
        failed |= {'d002', 'd003'}
    successful = set(result) - failed
    assert Counter(env.puts) == Counter(successful)
    assert all(result[i]['status'] == 'done' for i in successful)
    assert all(r['run_id'] is None for r in result.values())
    for doc_id in failed:
        row = result[doc_id]
        retry = failure in ('backend', 'missing') or (failure == 'mixed' and doc_id >= 'd002')
        assert row['status'] == ('bad' if retry and (attempts == 2 or failure == 'missing') else 'pending')
        assert row['last_error'] == (('invalid_or_missing_vote' if failure == 'missing' else 'gpt_backend_failed') if retry else None)
        assert row['attempts'] == (3 if failure == 'missing' else attempts + int(retry))
    if failure in ('limit', 'backend', 'mixed'):
        with transaction(ctx.sid) as db:
            assert db.execute("SELECT state FROM runs WHERE run_id='run'").fetchone()[0] == 'paused'
        assert [d['reason'] for d in ctx.details if 'reason' in d] == [
            'backend failed' if failure == 'backend' else 'usage limit']


def test_finished_slot_is_refilled_while_a_slow_batch_runs(concurrent_judge, monkeypatch):
    env = concurrent_judge
    monkeypatch.setattr(settings, 'label_concurrency', 2)
    third_started = threading.Event()
    order = []
    lock = threading.Lock()

    def judge(docs, *args, **kwargs):
        with lock:
            order.append(docs[0]['doc_id'])
            position = len(order)
        if position == 1:
            # The slow first batch only finishes once a refilled batch has started.
            assert third_started.wait(5), 'slot was not refilled while the slow batch ran'
        elif position == 3:
            third_started.set()
        return votes(docs)

    monkeypatch.setattr(gpt, 'judge_batch', judge)
    env.judge.run_worker(Context('gpt'))
    assert third_started.is_set() and sorted(env.puts) == sorted(rows(env))
