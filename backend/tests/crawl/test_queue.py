from concurrent.futures import ThreadPoolExecutor
import threading
import multiprocessing as mp
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

from app.crawl import queue as queue_module
from app.crawl.queue import CrawlQueue, KwMeta, QueueListItem


def add(q, kw, order, urls, source='fixture'):
    q.add_list_tasks([KwMeta(kw, 'axis', 'sub', order)], [source])
    task = q.next_list_task()
    assert task.kw == kw
    q.record_list_page(task, [QueueListItem(url=u, title=u) for u in urls], None)


@pytest.fixture
def queue(tmp_path):
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    q.register_run('list')
    yield q
    q.close()


def test_unique_url_records_hits(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    add(queue, 'B', 1, ['fixture://aircon/1'])
    with queue.open_readonly(queue.path) as db:
        assert db.execute('SELECT count(*) FROM urls').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM url_hits').fetchone()[0] == 2


def test_lease_order_deterministic(queue):
    add(queue, 'B', 1, ['fixture://aircon/3', 'fixture://aircon/2'])
    add(queue, 'A', 0, ['fixture://aircon/9'], 'z')
    add(queue, 'A', 0, ['fixture://aircon/8'], 'a')
    snap = queue.take_snapshot()
    add(queue, 'C', 2, ['fixture://aircon/0'])
    rows = queue.lease_urls(snap, 10, 30)
    assert [(r.kw_order, r.source, r.url_norm) for r in rows] == [
        (0, 'a', 'fixture://aircon/8'), (0, 'z', 'fixture://aircon/9'),
        (1, 'fixture', 'fixture://aircon/2'), (1, 'fixture', 'fixture://aircon/3')]


def test_reclaim_expired(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    queue.lease_urls(queue.take_snapshot(), 1, 30)
    queue.connection.execute('UPDATE urls SET lease_until=?', (time.time() - 1,))
    assert queue.reclaim_expired_leases() == 1
    assert queue.counts()['pending'] == 1


def test_exclude_keywords(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    assert queue.exclude_keywords(snap, ['A']) == 1
    assert queue.exclude_keywords(snap, ['A']) == 0
    assert queue.counts()['excluded'] == 1
    assert queue.lease_urls(snap, 10, 30) == []


def test_dead_run_leases_reclaimed(queue, monkeypatch):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    run = queue.register_run('detail')
    queue.lease_urls(queue.take_snapshot(), 1, 3600)
    def dead(pid, sig):
        raise ProcessLookupError
    monkeypatch.setattr(os, 'kill', dead)
    assert queue.reclaim_expired_leases() == 1
    assert queue.counts()['pending'] == 1
    assert run


def test_shared_url_excluded_only_if_all_hits_excluded(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    add(queue, 'B', 1, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    assert queue.exclude_keywords(snap, ['A']) == 0
    row = queue.lease_urls(snap, 1, 30)[0]
    assert row.kw == 'B' and row.kw_order == 1
    assert row.kw_hits == ['A', 'B']
    queue.mark_failed_attempt(row.url_norm, row.source, 'retry', backoff_s=0)
    assert queue.exclude_keywords(snap, ['B']) == 1
    assert queue.lease_urls(snap, 1, 30) == []
    with pytest.raises(queue_module.LeaseLost):
        queue.mark_done(row.url_norm, row.source, 1)
    assert queue.counts()['excluded'] == 1


def writer(path, kind, ready, start, results):
    errors = []
    ops = 0
    try:
        q = CrawlQueue(path)
        run = q.register_run('detail' if kind == 'done' else 'list') if kind != 'exclude' else None
        snap = q.connection.execute('SELECT snapshot_id FROM snapshots').fetchone()[0]
        if kind == 'done':
            q.lease_urls(snap, 1, 30)
        ready.put(True)
        start.wait(10)
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                if kind == 'done':
                    if ops:
                        q.add_urls([QueueListItem(url=f'fixture://aircon/write{ops}', kw='A', source='fixture')])
                        snap = q.take_snapshot()
                        row = q.lease_urls(snap, 1, 30)[0]
                        q.mark_done(row.url_norm, row.source, 1)
                    else:
                        q.mark_done('fixture://aircon/1', 'fixture', 1)
                elif kind == 'exclude':
                    q.exclude_keywords(snap, ['B'])
                else:
                    q.heartbeat(run)
                ops += 1
            except sqlite3.OperationalError as exc:
                errors.append(str(exc))
            time.sleep(0.003)
        q.close()
    except Exception as exc:
        errors.append(repr(exc))
    results.put((errors, ops))


def test_concurrent_writers_no_locked_error(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    add(queue, 'B', 1, ['fixture://aircon/2'])
    queue.take_snapshot()
    queue.finish_run(queue.run_id, 'done')
    ctx = mp.get_context('spawn')
    ready, results, start = ctx.Queue(), ctx.Queue(), ctx.Event()
    procs = [ctx.Process(target=writer, args=(queue.path, k, ready, start, results))
             for k in ('done', 'exclude', 'heartbeat')]
    began = time.monotonic()
    try:
        for p in procs:
            p.start()
        for _ in procs:
            assert ready.get(timeout=3)
        start.set()
        for _ in procs:
            errors, ops = results.get(timeout=7)
            assert errors == []
            assert ops > 10
        for p in procs:
            p.join(1)
            assert p.exitcode == 0
        assert time.monotonic() - began < 10
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join()


def test_pragmas_and_readonly_counts(queue):
    for db in (queue.connection, queue.open_readonly(queue.path)):
        try:
            assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
            assert db.execute('PRAGMA busy_timeout').fetchone()[0] == 10000
            assert db.execute('PRAGMA synchronous').fetchone()[0] == 1
            if db is not queue.connection:
                with pytest.raises(sqlite3.OperationalError):
                    db.execute('DELETE FROM urls')
        finally:
            if db is not queue.connection:
                db.close()
    queue.connection.execute('BEGIN IMMEDIATE')
    try:
        assert queue.counts()['total'] == 0
    finally:
        queue.connection.rollback()


def test_stale_heartbeat_and_registration(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    run = queue.register_run('detail')
    with pytest.raises(RuntimeError):
        queue.register_run('detail')
    queue.lease_urls(queue.take_snapshot(), 1, 3600)
    queue.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 61,))
    assert queue.reclaim_expired_leases() == 1
    with pytest.raises(queue_module.LeaseLost):
        queue.heartbeat(run)
    queue.finish_run(run, 'done')
    assert queue.register_run('detail') != run


def test_attempts_and_completion_aggregates(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    for i in range(3):
        row = queue.lease_urls(snap, 1, 30)[0]
        assert row.attempts == i + 1
        if i < 2:
            queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0)
    queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0)
    assert queue.lease_urls(snap, 1, 30) == []
    queue.mark_done(row.url_norm, row.source, 2, 'timeout', 'snippet', 'restricted')
    counts = queue.counts()
    assert counts['done'] == 1 and counts['doc_count'] == 2
    assert counts['fetch_level'] == {'snippet': 1}
    assert counts['access'] == {'restricted': 1}


def test_pagination_duck_types_and_atomicity(queue):
    queue.add_list_tasks([KwMeta('A', 'x', 'y', 0)], ['fixture'])
    task = queue.next_list_task()
    item = SimpleNamespace(url='fixture://aircon/1', title='t', snippet='s', date=None, src_meta={})
    queue.record_list_page(task, [item], 'page2')
    task2 = queue.next_list_task()
    assert task2.cursor == 'page2'
    queue.record_list_page(task2, [item], None)
    assert queue.next_list_task() is None
    assert queue.counts()['total'] == 1
    assert queue.add_urls([dict(url='fixture://aircon/1', source='fixture', kw='B', kw_order=1)]) == 0
    assert queue.lease_urls(queue.take_snapshot(), 1, 30)[0].kw_hits == ['A', 'B']


def test_filtered_and_snapshot_hash(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    first = queue.take_snapshot()
    second = queue.take_snapshot()
    hashes = queue.connection.execute('SELECT hash FROM snapshots').fetchall()
    assert hashes[0][0] == hashes[1][0]
    queue.mark_filtered('fixture://aircon/1', 'fixture', '②')
    assert queue.lease_urls(first, 10, 30) == []
    assert queue.counts()['filter_rules'] == {'②': 1}
    assert first != second


def test_reclaimed_lease_rejects_previous_worker_completion(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    first = queue.register_run('detail')
    snap = queue.take_snapshot()
    queue.lease_urls(snap, 1, 30)
    queue.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 61,))
    other = CrawlQueue(queue.path)
    try:
        second = other.register_run('detail')
        assert first != second
        other.lease_urls(snap, 1, 30)
        with pytest.raises(queue_module.LeaseLost):
            queue.mark_done('fixture://aircon/1', 'fixture', 999)
        with pytest.raises(queue_module.LeaseLost):
            queue.mark_failed_attempt('fixture://aircon/1', 'fixture', 'old error')
        with pytest.raises(queue_module.LeaseLost):
            queue.mark_filtered('fixture://aircon/1', 'fixture', '②')
        assert queue.counts()['leased'] == 1
        other.mark_done('fixture://aircon/1', 'fixture', 1)
        assert queue.counts()['doc_count'] == 1
    finally:
        other.close()


def test_exclusions_stay_with_snapshot_membership(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    queue.add_urls([QueueListItem(url='fixture://aircon/2', kw='A', source='fixture')])
    assert queue.exclude_keywords(snap, ['A']) == 1
    assert queue.counts()['pending'] == 1


def test_bad_page_has_no_partial_writes(queue):
    queue.add_list_tasks([KwMeta('A', 'x', 'y', 0)], ['fixture'])
    task = queue.next_list_task()
    with pytest.raises(TypeError):
        queue.record_list_page(task, [QueueListItem(url='fixture://aircon/1'),
                                     QueueListItem(url='fixture://aircon/2', src_meta={'bad': object()})], None)
    assert queue.counts()['total'] == 0
    assert queue.next_list_task() is None
    assert queue.connection.execute('SELECT status FROM list_tasks').fetchone()[0] == 'running'
    queue.record_list_page(task, [], None)


def test_exclusions_preserve_completed_filtered_and_leased(queue):
    urls = [f'fixture://aircon/{i}' for i in range(3)]
    add(queue, 'A', 0, urls)
    add(queue, 'B', 1, urls)
    snap = queue.take_snapshot()
    rows = queue.lease_urls(snap, 3, 30)
    queue.mark_done(rows[0].url_norm, 'fixture', 2, fetch_level='full', access='public')
    queue.mark_filtered(rows[1].url_norm, 'fixture', '②')
    before = queue.counts()
    for kws in (['A'], ['B']):
        assert queue.exclude_keywords(snap, kws) == 0
        assert queue.counts() == before
        assert [r[0] for r in queue.connection.execute('SELECT kw FROM urls')] == ['A'] * 3


@pytest.mark.parametrize('recover', [False, True])
@pytest.mark.parametrize('max_attempts', [2, 3, 4])
def test_exhausted_snippet_survives_crash(queue, recover, max_attempts):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    for attempt in range(max_attempts):
        row = queue.lease_urls(snap, 1, 3600)[0]
        assert not row.exhausted
        result = queue.mark_failed_attempt(row.url_norm, row.source, 'timeout',
                                           max_attempts=max_attempts, backoff_s=0)
        assert result == ('exhausted' if attempt == max_attempts - 1 else 'pending')
    state = queue.connection.execute('SELECT status,lease_run_id FROM urls').fetchone()
    assert tuple(state) == ('leased', queue.run_id)
    if recover:
        queue.connection.execute("UPDATE runs SET status='interrupted' WHERE run_id=?", (queue.run_id,))
        queue.register_run('list')
        row = queue.lease_urls(snap, 1, 30)[0]
        assert row.exhausted and row.attempts == max_attempts
        assert row.last_error == 'timeout'
    queue.mark_done(row.url_norm, row.source, 1, 'timeout', 'snippet', 'restricted')
    assert queue.counts()['done'] == 1
    assert queue.counts()['fetch_level'] == {'snippet': 1}


def test_crash_on_last_attempt_goes_to_snippet(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    for _ in range(2):
        row = queue.lease_urls(snap, 1, 30)[0]
        queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0)
    queue.lease_urls(snap, 1, 30)
    queue.connection.execute('UPDATE urls SET lease_until=0')
    assert queue.reclaim_expired_leases() == 1
    row = queue.lease_urls(snap, 1, 30)[0]
    assert row.exhausted and row.attempts == 3


def test_list_tasks_concurrent_claims_and_source(queue):
    queue.add_list_tasks([KwMeta(str(i), '', '', i) for i in range(10)], ['a', 'b'])
    barrier = threading.Barrier(2)
    run = queue.run_id
    def claim():
        q = CrawlQueue(queue.path)
        try:
            q.run_id = run
            barrier.wait(timeout=5)
            return q.next_list_tasks('a', 10)
        finally:
            q.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        tasks = [t for f in futures for t in f.result()]
    assert len(tasks) == 10
    assert len({(t.kw, t.source, t.cursor) for t in tasks}) == 10
    assert all(t.source == 'a' and t.lease_run_id == run for t in tasks)
    assert len(queue.next_list_tasks(None, 20)) == 10
    assert queue.next_list_task() is None


def test_list_failure_retry_limit(queue):
    queue.add_list_tasks([KwMeta('A', '', '', 0)], ['a'])
    for i in range(3):
        task = queue.next_list_task()
        assert task.attempts == i
        queue.mark_list_failed(task, 'page timeout')
        row = queue.connection.execute('SELECT * FROM list_tasks').fetchone()
        assert row['attempts'] == i + 1 and row['last_error'] == 'page timeout'
        assert row['status'] == ('failed' if i == 2 else 'pending')
        assert row['lease_run_id'] is None
    assert queue.next_list_task() is None


@pytest.mark.parametrize('dead', [True, False])
def test_list_reclaim_and_fencing(queue, monkeypatch, dead):
    queue.add_list_tasks([KwMeta('A', '', '', 0)], ['a'])
    task = queue.next_list_task()
    if dead:
        monkeypatch.setattr(queue_module, '_alive', lambda pid: False)
    else:
        queue.connection.execute('UPDATE runs SET heartbeat_at=0')
    assert queue.reclaim_expired_leases() == 1
    with pytest.raises(queue_module.LeaseLost):
        queue.record_list_page(task, [], None)
    with pytest.raises(queue_module.LeaseLost):
        queue.mark_list_failed(task, 'late')
    monkeypatch.setattr(queue_module, '_alive', lambda pid: True)
    queue.register_run('list')
    assert queue.next_list_task().kw == 'A'


def test_stale_window_is_sixty_seconds(queue, monkeypatch):
    assert queue_module.STALE_AFTER_S == 60
    assert queue_module.HEARTBEAT_INTERVAL == 10
    add(queue, 'A', 0, ['fixture://aircon/1'])
    queue.lease_urls(queue.take_snapshot(), 1, 3600)
    queue.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 40,))
    assert queue.reclaim_expired_leases() == 0
    with pytest.raises(RuntimeError):
        queue.register_run('list')
    monkeypatch.setattr(queue_module, 'STALE_AFTER_S', 30)
    assert queue.reclaim_expired_leases() == 1
    with pytest.raises(queue_module.LeaseLost):
        queue.heartbeat(queue.run_id)


def test_leasing_requires_registered_running_run(tmp_path):
    q = CrawlQueue(tmp_path / 'unregistered.sqlite')
    try:
        snap = q.take_snapshot()
        with pytest.raises(RuntimeError):
            q.lease_urls(snap, 1, 30)
        with pytest.raises(RuntimeError):
            q.next_list_tasks(None, 1)
        run = q.register_run('detail')
        q.connection.execute("UPDATE runs SET status='interrupted'")
        with pytest.raises(queue_module.LeaseLost):
            q.lease_urls(snap, 1, 30)
        with pytest.raises(queue_module.LeaseLost):
            q.heartbeat(run)
    finally:
        q.close()


def test_done_many_one_transaction_and_atomic_fencing(queue):
    add(queue, 'A', 0, ['fixture://aircon/1', 'fixture://aircon/2'])
    rows = queue.lease_urls(queue.take_snapshot(), 2, 30)
    batch = [(r.url_norm, r.source, 1, 'timeout', 'snippet', 'restricted') for r in rows]
    queue.connection.execute('UPDATE urls SET lease_run_id=? WHERE url_norm=?', ('other', rows[1].url_norm))
    with pytest.raises(queue_module.LeaseLost):
        queue.mark_done_many(batch)
    assert queue.counts()['leased'] == 2 and queue.counts()['doc_count'] == 0
    queue.connection.execute('UPDATE urls SET lease_run_id=?', (queue.run_id,))
    trace = []
    queue.connection.set_trace_callback(trace.append)
    try:
        queue.mark_done_many(batch)
    finally:
        queue.connection.set_trace_callback(None)
    assert trace.count('BEGIN IMMEDIATE') == trace.count('COMMIT') == 1
    assert queue.counts()['done'] == queue.counts()['doc_count'] == 2
    assert queue.counts()['fetch_level'] == {'snippet': 2}
    assert queue.counts()['access'] == {'restricted': 2}
    assert [r[0] for r in queue.connection.execute('SELECT last_error FROM urls')] == ['timeout'] * 2


@pytest.mark.parametrize('method', ['mark_done', 'mark_filtered', 'mark_failed_attempt'])
def test_reclaimed_unowned_url_raises(queue, method):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    queue.lease_urls(queue.take_snapshot(), 1, 30)
    queue.connection.execute('UPDATE urls SET lease_until=0')
    queue.reclaim_expired_leases()
    with pytest.raises(queue_module.LeaseLost):
        getattr(queue, method)('fixture://aircon/1', 'fixture', 1 if method == 'mark_done' else 'error')



def test_upgrade_existing_list_schema(tmp_path):
    path = tmp_path / 'old.sqlite'
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE list_tasks (
            kw TEXT NOT NULL, source TEXT NOT NULL, cursor TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','failed')),
            fetched INTEGER NOT NULL DEFAULT 0, total_hint INTEGER,
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
            PRIMARY KEY(kw,source,cursor))""")
        db.execute("INSERT INTO list_tasks(kw,source,attempts,last_error) VALUES ('A','a',1,'timeout')")
    q = CrawlQueue(path)
    try:
        q.register_run('list')
        q.add_list_tasks([KwMeta('A', '', '', 0)], ['a'])
        task = q.next_list_task()
        assert task.attempts == 1 and task.last_error == 'timeout'
        assert task.lease_run_id == q.run_id
        q.record_list_page(task, [], None)
    finally:
        q.close()


@pytest.mark.parametrize('recover', [False, True])
@pytest.mark.parametrize('exclude_all', [False, True])
def test_mid_lease_exclusion_rechecked_on_pending(queue, recover, exclude_all):
    url = 'fixture://aircon/1'
    add(queue, 'A', 0, [url])
    add(queue, 'C', 2, [url])
    add(queue, 'B', 1, [url])
    snap = queue.take_snapshot()
    row = queue.lease_urls(snap, 1, 30)[0]
    assert queue.exclude_keywords(snap, ['A', 'B', 'C'] if exclude_all else ['A']) == 0
    if recover:
        queue.connection.execute('UPDATE urls SET lease_until=0')
        # Recovery must retain the snapshot even through a new connection.
        with_queue = CrawlQueue(queue.path)
        try:
            assert with_queue.reclaim_expired_leases() == 1
        finally:
            with_queue.close()
    else:
        assert queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0) == 'pending'
    state = queue.connection.execute('SELECT status,kw,lease_run_id FROM urls').fetchone()
    assert tuple(state) == ('excluded' if exclude_all else 'pending', 'A' if exclude_all else 'B', None)
    assert queue.counts()['pending'] == (0 if exclude_all else 1)
    rows = queue.lease_urls(snap, 1, 30)
    if exclude_all:
        assert rows == []
    else:
        assert [(r.kw, r.kw_order) for r in rows] == [('B', 1)]


def test_lease_cleans_stranded_pending_in_snapshot(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    queue.exclude_keywords(snap, ['A'])
    # Simulate a pending row stranded by the previous implementation, in backoff.
    queue.connection.execute("UPDATE urls SET status='pending',retry_at=?", (time.time() + 3600,))
    add(queue, 'B', 1, ['fixture://aircon/outside'])
    assert queue.lease_urls(snap, 10, 30) == []
    assert queue.counts()['excluded'] == 1
    assert queue.counts()['pending'] == 1  # Outside-snapshot work is untouched.


@pytest.mark.parametrize('recover', [False, True])
def test_full_run_finishes_after_mid_lease_exclusions(queue, recover):
    urls = [f'fixture://aircon/{i}' for i in range(3)]
    add(queue, 'A', 0, urls)
    add(queue, 'B', 1, urls[1:])
    snap = queue.take_snapshot()
    rows = queue.lease_urls(snap, 3, 30)
    queue.mark_done(rows[2].url_norm, rows[2].source, 1)
    assert queue.exclude_keywords(snap, ['A']) == 0
    if recover:
        queue.connection.execute("UPDATE urls SET lease_until=0 WHERE status='leased'")
        assert queue.reclaim_expired_leases() == 2
    else:
        for row in rows[:2]:
            queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0)
    for row in queue.lease_urls(snap, 10, 30):
        assert row.kw == 'B'
        queue.mark_done(row.url_norm, row.source, 1)
    assert queue.lease_urls(snap, 10, 30) == []
    counts = queue.counts()
    assert (counts['pending'], counts['leased'], counts['excluded'], counts['done']) == (0, 0, 1, 2)


@pytest.mark.parametrize('recover', [False, True])
def test_pending_recheck_uses_lease_snapshot(queue, recover):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    row = queue.lease_urls(snap, 1, 30)[0]
    other_snap = queue.take_snapshot()
    assert queue.exclude_keywords(other_snap, ['A']) == 0
    if recover:
        queue.connection.execute('UPDATE urls SET lease_until=0')
        queue.reclaim_expired_leases()
    else:
        queue.mark_failed_attempt(row.url_norm, row.source, 'timeout', backoff_s=0)
    assert queue.counts()['pending'] == 1
    assert len(queue.lease_urls(snap, 1, 30)) == 1


def exclusion_updates(statements):
    return [sql for sql in statements if sql.lstrip().startswith((
        "UPDATE urls SET status='excluded'", 'UPDATE urls SET (kw,kw_axis,kw_sub)'))]


def test_unchanged_exclusions_do_not_write_during_leasing(queue):
    add(queue, 'A', 0, [f'fixture://aircon/{i}' for i in range(5000)])
    snap = queue.take_snapshot()
    statements = []
    queue.connection.set_trace_callback(statements.append)
    try:
        before = queue.connection.total_changes
        for _ in range(10):
            assert len(queue.lease_urls(snap, 200, 30)) == 200
        assert queue.connection.total_changes - before == 2000  # Only lease writes.
        assert exclusion_updates(statements) == []
    finally:
        queue.connection.set_trace_callback(None)


def test_exclusion_sweep_once_per_changed_snapshot_across_connections(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    other_snap = queue.take_snapshot()
    with_queue = CrawlQueue(queue.path)
    try:
        assert with_queue.exclude_keywords(snap, ['A']) == 1
        # A legacy stranded pending row, including retry backoff, is repaired.
        queue.connection.execute("UPDATE urls SET status='pending',retry_at=?", (time.time() + 3600,))
        statements = []
        queue.connection.set_trace_callback(statements.append)
        assert queue.lease_urls(other_snap, 1, 30) == []
        assert exclusion_updates(statements) == []
        assert queue.lease_urls(snap, 1, 30) == []
        updates = exclusion_updates(statements)
        assert len(updates) == 1
        assert "SET status='excluded'" in updates[0]
        assert queue.counts()['excluded'] == 1
        queue.connection.set_trace_callback(None)
        assert with_queue.exclude_keywords(snap, ['A']) == 0  # No version bump.
        with_queue.run_id = queue.run_id
        statements.clear()
        with_queue.connection.set_trace_callback(statements.append)
        before = with_queue.connection.total_changes
        for _ in range(10):
            assert with_queue.lease_urls(snap, 1, 30) == []
        assert exclusion_updates(statements) == []
        assert with_queue.connection.total_changes == before
    finally:
        queue.connection.set_trace_callback(None)
        with_queue.close()


def test_reassignment_writes_only_changed_metadata(queue):
    add(queue, 'A', 0, ['fixture://aircon/1', 'fixture://aircon/2'])
    snap = queue.take_snapshot()
    queue.connection.execute("UPDATE urls SET kw_axis='old',kw_sub='old' WHERE url_norm='fixture://aircon/1'")
    before = queue.connection.total_changes
    assert queue.exclude_keywords(snap, []) == 0
    assert queue.connection.total_changes - before == 1
    assert [tuple(r) for r in queue.connection.execute('SELECT kw,kw_axis,kw_sub FROM urls')] == [
        ('A', 'axis', 'sub'), ('A', 'axis', 'sub')]
    before = queue.connection.total_changes
    assert queue.exclude_keywords(snap, []) == 0
    assert queue.connection.total_changes == before


def test_legacy_snapshot_gets_one_initial_sweep(queue):
    add(queue, 'A', 0, ['fixture://aircon/1'])
    snap = queue.take_snapshot()
    queue.exclude_keywords(snap, ['A'])
    queue.connection.execute("UPDATE urls SET status='pending'")
    # Recreate the pre-version snapshot schema without touching membership.
    queue.connection.executescript('''
        ALTER TABLE snapshots RENAME TO old_snapshots;
        CREATE TABLE snapshots (
            snapshot_id TEXT PRIMARY KEY, created_at REAL NOT NULL,
            url_count INTEGER NOT NULL, hash TEXT NOT NULL);
        INSERT INTO snapshots SELECT snapshot_id,created_at,url_count,hash FROM old_snapshots;
        DROP TABLE old_snapshots;
    ''')
    reopened = CrawlQueue(queue.path)
    try:
        reopened.run_id = queue.run_id
        assert reopened.lease_urls(snap, 1, 30) == []
        assert reopened.counts()['excluded'] == 1
        statements = []
        reopened.connection.set_trace_callback(statements.append)
        assert reopened.lease_urls(snap, 1, 30) == []
        assert exclusion_updates(statements) == []
    finally:
        reopened.close()
