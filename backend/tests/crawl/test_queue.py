import multiprocessing as mp
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

from app.crawl.queue import CrawlQueue, KwMeta, QueueListItem


def add(q, kw, order, urls, source='fixture'):
    q.add_list_tasks([KwMeta(kw, 'axis', 'sub', order)], [source])
    task = q.next_list_task()
    assert task.kw == kw
    q.record_list_page(task, [QueueListItem(url=u, title=u) for u in urls], None)


@pytest.fixture
def queue(tmp_path):
    q = CrawlQueue(tmp_path / 'queue.sqlite')
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
    assert queue.exclude_keywords(snap, ['B']) == 1
    assert queue.lease_urls(snap, 1, 30) == []
    queue.mark_done(row.url_norm, row.source, 1)
    assert queue.counts()['excluded'] == 1


def writer(path, kind, ready, start, results):
    errors = []
    ops = 0
    try:
        q = CrawlQueue(path)
        run = q.register_run('detail' if kind == 'done' else 'list') if kind != 'exclude' else None
        snap = q.connection.execute('SELECT snapshot_id FROM snapshots').fetchone()[0]
        ready.put(True)
        start.wait(10)
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                if kind == 'done':
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
    queue.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 31,))
    assert queue.reclaim_expired_leases() == 1
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
    queue.connection.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 31,))
    other = CrawlQueue(queue.path)
    try:
        second = other.register_run('detail')
        assert first != second
        other.lease_urls(snap, 1, 30)
        queue.mark_done('fixture://aircon/1', 'fixture', 999)
        queue.mark_failed_attempt('fixture://aircon/1', 'fixture', 'old error')
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
    assert queue.next_list_task() == task
