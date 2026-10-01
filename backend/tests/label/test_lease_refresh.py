"""Judge heartbeats keep only their own pending vote leases alive."""
import os
import socket
import sqlite3

import pytest

from app.context import store, versions
from app.label import judge
from app.label.votes import VoteCache
from app.work import worker
from app.work.status import transaction


@pytest.fixture
def lease_env(data_dir, monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError('Network access is forbidden')

    monkeypatch.setattr(socket.socket, 'connect', offline)
    now = [1000.0]
    monkeypatch.setattr(worker.time, 'time', lambda: now[0])
    session = dict(projectContext={'oneLiner': 'context'},
                   prep={'derivedRef': {'collectionId': 'c1', 'prepKey': 'p1'}})
    store.write_json(versions.version_dir('s1', 'v1') / 'session.json', session)
    ctx = worker.Context('s1', 'v1', 'judge', {'labeler': 'gpt'}, 'first')
    with transaction('s1') as db:
        for run_id in ('first', 'other'):
            db.execute('''INSERT INTO runs
                (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at)
                VALUES (?, 'v1', 'judge', '{}', ?, 'running', ?, ?)''',
                       (run_id, os.getpid(), now[0], now[0]))
    cache = VoteCache(judge.cache_root('s1', 'p1', 'gpt', 'context'))
    cache.seed(['a', 'b', 'c', 'd'])
    assert cache.lease(3, 'first') == ['a', 'b', 'c']
    # Retain run_id on terminal rows to verify the status predicate explicitly.
    with cache._db() as db:
        db.execute("UPDATE votes SET status='done' WHERE doc_id='b'")
        db.execute("UPDATE votes SET status='bad' WHERE doc_id='c'")
    assert cache.lease(1, 'other') == ['d']
    # Unit tests install the callback; the real judge wiring is covered in test_judge.
    ctx._heartbeat_callback = lambda: cache.refresh(ctx.run_id)
    return ctx, cache, now


def rows(cache):
    with cache._db() as db:
        return {row['doc_id']: dict(row) for row in db.execute('SELECT * FROM votes')}


@pytest.mark.parametrize('pulse', [True, False], ids=['background', 'checkpoint'])
def test_only_pulse_refreshes_own_pending_lease(lease_env, monkeypatch, pulse):
    ctx, cache, now = lease_env

    def judge_work(context):
        now[0] += 10
        if pulse:
            context._pulse()
        else:
            context.heartbeat(.5, {})
        snapshot = rows(cache)
        assert snapshot['a']['at'] == (now[0] if pulse else 1000.0)
        assert {key: snapshot[key]['at'] for key in ('b', 'c', 'd')} == {
            'b': 1000.0, 'c': 1000.0, 'd': 1000.0}

    monkeypatch.setattr(judge, 'run_worker', judge_work)
    worker._judge(ctx)
    # Registration must end when the judge exits.
    now[0] += 10
    ctx._pulse()
    assert rows(cache)['a']['at'] == (1010.0 if pulse else 1000.0)


@pytest.mark.parametrize('state', ['running', 'paused'])
def test_live_lease_survives_650_seconds(lease_env, monkeypatch, state):
    ctx, cache, now = lease_env
    with transaction(ctx.sid) as db:
        db.execute('UPDATE runs SET state=? WHERE run_id=?', (state, ctx.run_id))

    def judge_work(context):
        for _ in range(65):
            now[0] += 10
            context._pulse()
        competitor = VoteCache(cache.path.parent)
        assert competitor.lease(4, 'other') == ['d']
        assert rows(cache)['a']['run_id'] == 'first'

    monkeypatch.setattr(judge, 'run_worker', judge_work)
    worker._judge(ctx)
    # The original 600-second expiry still applies without more heartbeats.
    now[0] += 601
    with cache._db() as db:
        cache.reclaim(db)
    assert rows(cache)['a']['run_id'] is None


def test_refresh_failure_is_logged_and_retried(lease_env, monkeypatch, caplog):
    ctx, cache, now = lease_env
    original = VoteCache.refresh
    attempts = []

    def flaky_refresh(self, run_id):
        attempts.append(run_id)
        if len(attempts) == 1:
            raise sqlite3.OperationalError('sensitive provider detail')
        return original(self, run_id)

    monkeypatch.setattr(VoteCache, 'refresh', flaky_refresh)

    def judge_work(context):
        now[0] += 10
        context._pulse()
        assert rows(cache)['a']['at'] == 1000.0
        with transaction(ctx.sid) as db:
            assert db.execute('SELECT heartbeat_at FROM runs WHERE run_id=?',
                              (ctx.run_id,)).fetchone()[0] == now[0]
        now[0] += 10
        context._pulse()
        assert rows(cache)['a']['at'] == now[0]

    monkeypatch.setattr(judge, 'run_worker', judge_work)
    worker._judge(ctx)
    assert attempts == ['first', 'first']
    assert 'OperationalError' in caplog.text
    assert 'sensitive provider detail' not in caplog.text


def test_paused_checkpoints_refresh_only_from_pulse(lease_env, monkeypatch):
    ctx, cache, now = lease_env
    refreshes = []
    ctx._heartbeat_callback = lambda: refreshes.append(now[0])
    with transaction(ctx.sid) as db:
        db.execute("UPDATE runs SET action='pause' WHERE run_id=?", (ctx.run_id,))
    sleeps = []
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
        if len(sleeps) == 5:
            ctx._pulse()
        if len(sleeps) == 20:
            with transaction(ctx.sid) as db:
                db.execute("UPDATE runs SET action=NULL WHERE run_id=?", (ctx.run_id,))
    monkeypatch.setattr(worker.time, 'sleep', sleep)
    ctx.heartbeat(.5, {})
    assert len(sleeps) == 20
    assert len(refreshes) == 1
    assert ctx._row()['state'] == 'running'
