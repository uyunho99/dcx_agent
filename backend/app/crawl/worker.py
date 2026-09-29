"""P1/P3 processes; only the coordinator thread accesses SQLite or P4 files.

DCX_TEST_ADAPTER_MODULE optionally imports a local registration module. It is
inert by default and intended solely for subprocess tests with fake adapters.
"""
import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

from app.config import settings
from app.context.store import load_session, write_json
from app.crawl.adapters import REGISTRY, available_sources
from app.crawl.adapters.base import AdapterBlocked, FetchedDoc, ListItem, ListPage
from app.crawl.filters import FilterConfig, check_doc, check_list
from app.crawl.hashing import author_hash
from app.crawl.queue import CrawlQueue, HEARTBEAT_INTERVAL, KwMeta, LeaseLost
from app.crawl.ratelimit import ChannelLimiter
from app.crawl.schema import Doc
from app.crawl.urls import doc_id, normalize_url
from app.crawl.writer import DocWriter
from app.utils.text import clean_text

BATCH_SIZE = 200
# Heartbeats fence dead owners; a long lease avoids expiring a healthy slow fetch.
LEASE_SECONDS = 86400


class AdapterParseError(ValueError):
    """Adapters may use this (or ValueError/TypeError) for malformed responses."""


def _load_hook():
    module = os.environ.get('DCX_TEST_ADAPTER_MODULE')
    if module:
        importlib.import_module(module)


def _inputs(sid, collection):
    if collection is not None:
        root = Path(collection)
        session = {}
    else:
        session = load_session(sid) or {}
        cid = session.get('collectionId')
        if not cid:
            raise ValueError(f'Session {sid} has no collectionId; create a collection first')
        if Path(cid).name != cid or cid in ('.', '..'):
            raise ValueError('Invalid collectionId')
        root = Path(settings.local_data_dir) / 'crawl' / sid / 'collections' / cid
    root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').exists() else {}
    config = manifest.get('config', session.get('crawlConfig', {}))
    return root, session, manifest, config


def _keywords(values):
    result = []
    for i, value in enumerate(values):
        if isinstance(value, KwMeta):
            result.append(value)
        elif isinstance(value, str):
            result.append(KwMeta(value, '', '', i))
        else:
            result.append(KwMeta(value.get('text', value.get('kw', '')), value.get('axis', ''),
                                 value.get('sub', ''), i))
    return result


@contextmanager
def _stop_event():
    event = threading.Event()
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, lambda *_: event.set())
    try:
        yield event
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


class _Run:
    def __init__(self, root, sid, kind, sources, limiters, config, snapshot=None):
        self.root, self.sid, self.kind, self.snapshot = root, sid, kind, snapshot
        self.q = CrawlQueue(root / 'queue.sqlite')
        try:
            self.id = self.q.register_run(kind)
        except BaseException:
            self.q.close()
            raise
        self.channels = {s: dict(status='running', attempts=0, parse_errors=0, blocked=0) for s in sources}
        self.limiters = {}
        for s in sources:
            defaults = (2, 0) if s == 'youtube' else ((1, 1) if s in ('clien', 'ppomppu') else (4, 0))
            opts = config.get('channel_limits', {}).get(s, {})
            self.limiters[s] = (limiters or {}).get(s) or ChannelLimiter(
                opts.get('concurrency', defaults[0]), opts.get('min_interval_s', defaults[1]))
        self.pools = {s: ThreadPoolExecutor(max_workers=l.concurrency) for s, l in self.limiters.items()}
        self.last_heartbeat = self.last_reclaim = time.monotonic()
        self.save()

    def save(self):
        write_json(self.root / 'worker_state.json', dict(sid=self.sid, kind=self.kind,
                   run_id=self.id, snapshot_id=self.snapshot, channels=self.channels))

    def tick(self):
        now = time.monotonic()
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self.q.heartbeat(self.id)
            self.last_heartbeat = now
        if now - self.last_reclaim >= 60:
            self.q.reclaim_expired_leases()
            self.last_reclaim = now

    def active(self, source):
        return self.channels[source]['status'] == 'running'

    def outcome(self, source, error):
        c = self.channels[source]
        c['attempts'] += 1
        c['blocked'] = c['blocked'] + 1 if isinstance(error, AdapterBlocked) else 0
        c['parse_errors'] += isinstance(error, (ValueError, TypeError))
        if c['blocked'] >= 20:
            c['status'] = 'paused_blocked'
        elif c['attempts'] >= 10 and c['parse_errors'] / c['attempts'] > 0.3:
            c['status'] = 'paused_parse_error'
        self.save()

    def execute(self, jobs, adapters, method, stop):
        """Route a bounded wave to per-channel pools; never queue a paused channel."""
        pending = {s: deque() for s in self.channels}
        for job in jobs:
            pending[job.source].append(job)
        futures = {}
        running = dict.fromkeys(self.channels, 0)
        def call(source, job):
            with self.limiters[source]:
                adapter = adapters[source]
                if method == 'list':
                    page = adapter.list_page(job.kw, job.cursor)
                    if not isinstance(page, ListPage) or any(not isinstance(i, ListItem) for i in page.items):
                        raise AdapterParseError('Expected ListPage containing ListItem records')
                    return page
                docs = adapter.fetch(ListItem(job.url_norm, job.title, job.snippet, job.date, job.src_meta))
                if not isinstance(docs, list) or any(not isinstance(d, FetchedDoc) for d in docs):
                    raise AdapterParseError('Expected a list of FetchedDoc records')
                return docs
        while futures or any(pending.values()):
            self.tick()
            for s, rows in pending.items():
                if not self.active(s) or stop.is_set():
                    rows.clear()
                while rows and running[s] < self.limiters[s].concurrency:
                    job = rows.popleft()
                    if method == 'detail' and job.exhausted:
                        yield job, None, None
                        continue
                    f = self.pools[s].submit(call, s, job)
                    futures[f] = job
                    running[s] += 1
            if not futures:
                continue
            done, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for f in done:
                job = futures.pop(f)
                running[job.source] -= 1
                try:
                    result, error = f.result(), None
                except Exception as exc:
                    result, error = None, exc
                self.outcome(job.source, error)
                yield job, result, error

    def close(self, status):
        try:
            self.q.finish_run(self.id, status)
            for c in self.channels.values():
                if c['status'] == 'running':
                    c['status'] = status
            self.save()
        finally:
            for pool in self.pools.values():
                pool.shutdown(wait=False, cancel_futures=True)
            self.q.close()


def _error(exc):
    return f'{type(exc).__name__}: {exc}'


def run_list(sid, *, collection=None, keywords=None, sources=None, filters=None, limiters=None):
    _load_hook()
    root, session, manifest, config = _inputs(sid, collection)
    kws = _keywords(keywords if keywords is not None else manifest.get('keywords', session.get('keywords', [])))
    if sources is None:
        sources = manifest.get('channels', config.get('channels'))
    if sources is None:
        sources = available_sources()
    sources = list(dict.fromkeys(sources))
    filters = filters or FilterConfig(**config.get('filters', {}))
    adapters = {s: REGISTRY[s]() for s in sources}
    run = _Run(root, sid, 'list', sources, limiters, config)
    status = 'interrupted'
    try:
        run.q.add_list_tasks(kws, sources)
        with _stop_event() as stop:
            while not stop.is_set():
                jobs = [task for s in sources if run.active(s)
                        for task in run.q.next_list_tasks(s, run.limiters[s].concurrency)]
                if not jobs:
                    break
                for task, page, error in run.execute(jobs, adapters, 'list', stop):
                    if error:
                        run.q.mark_list_failed(task, _error(error))
                        continue
                    run.q.record_list_page(task, page.items, page.next_cursor)
                    for item in page.items:
                        rule = check_list(dict(asdict(item), source=task.source), filters)
                        if rule:
                            # Discovery may encounter a previously filtered/shared URL.
                            row = run.q.connection.execute('SELECT status,attempts FROM urls WHERE url_norm=? AND source=?',
                                (normalize_url(item.url, task.source), task.source)).fetchone()
                            if row['status'] == 'pending' and row['attempts'] == 0:
                                run.q.mark_filtered(normalize_url(item.url, task.source), task.source, rule)
            run.snapshot = run.q.take_snapshot()
            status = 'stopped' if stop.is_set() else 'done'
            if not stop.is_set():
                for row in run.q.connection.execute("SELECT DISTINCT source FROM list_tasks WHERE status='failed'"):
                    if row['source'] in run.channels and run.active(row['source']):
                        run.channels[row['source']]['status'] = 'failed'
            return run.snapshot
    finally:
        run.close(status)


def _clean(text):
    return ' '.join(clean_text(text).split())


def _doc(row, fetched, level):
    return Doc(doc_id=doc_id(row.source, row.url_norm, fetched.thread_key), source=row.source,
        src_meta=fetched.src_meta, kw=row.kw, kw_axis=row.kw_axis, kw_sub=row.kw_sub,
        kw_hits=row.kw_hits, title=_clean(fetched.title), body=_clean(fetched.body),
        comments=[c.model_copy(update={'text': _clean(c.text)}) for c in fetched.comments],
        date=fetched.date or '', url=row.url_norm, fetch_level=level, access=fetched.access,
        snippet=_clean(row.snippet), author_hash=author_hash(row.source, fetched.author_raw) if fetched.author_raw else '',
        crawled_at=datetime.now(timezone.utc).isoformat())


def _remaining(run):
    # Read-only SQL narrows pending work to this snapshot and unpaused sources.
    # Mutations exclusively use CrawlQueue's public API.
    sources = [s for s in run.channels if run.active(s)]
    if not sources:
        return False
    marks = ','.join('?' for _ in sources)
    return run.q.connection.execute(f'''SELECT 1 FROM urls u JOIN snapshot_urls s USING(url_norm,source)
        WHERE s.snapshot_id=? AND u.status='pending' AND u.source IN ({marks}) LIMIT 1''',
        [run.snapshot, *sources]).fetchone() is not None


def _detail_wave(run, buffers, stop):
    """Global queue claims, then fair channel routing into <=200 fetched URLs.

    The queue has no source selector. Scan past a dense source when necessary
    so it cannot starve another channel. Buffered claims never enter a pool
    until their bounded wave, and paused claims are left for public reclaim.
    """
    for source, rows in buffers.items():
        if not run.active(source):
            rows.clear()
    ready = {r[0] for r in run.q.connection.execute(
        """SELECT DISTINCT u.source FROM urls u JOIN snapshot_urls s USING(url_norm,source)
        WHERE s.snapshot_id=? AND u.status='pending' AND (u.retry_at IS NULL OR u.retry_at<=?)""",
        (run.snapshot, time.time())) if run.active(r[0])}
    while any(not buffers[s] for s in ready) and not stop.is_set():
        run.tick()
        rows = run.q.lease_urls(run.snapshot, BATCH_SIZE, LEASE_SECONDS)
        if not rows:
            break
        for row in rows:
            if run.active(row.source):
                buffers[row.source].append(row)
    jobs = []
    while len(jobs) < BATCH_SIZE and any(buffers.values()) and not stop.is_set():
        for rows in buffers.values():
            if rows and len(jobs) < BATCH_SIZE:
                jobs.append(rows.popleft())
    return jobs


def run_detail(sid, snapshot_id, *, collection=None, filters=None, limiters=None, backoff_s=1):
    _load_hook()
    root, _, _, config = _inputs(sid, collection)
    filters = filters or FilterConfig(**config.get('filters', {}))
    q = CrawlQueue(root / 'queue.sqlite')
    try:
        sources = [r[0] for r in q.connection.execute('SELECT DISTINCT source FROM snapshot_urls WHERE snapshot_id=?', (snapshot_id,))]
    finally:
        q.close()
    adapters = {s: REGISTRY[s]() for s in sources}
    run = _Run(root, sid, 'detail', sources, limiters, config, snapshot_id)
    writer = None
    status = 'interrupted'
    batch = {}
    written = 0
    buffers = {s: deque() for s in sources}
    def commit():
        nonlocal written
        if batch:
            writer.flush_and_fsync()
            run.q.mark_done_many(list(batch.values()))
            batch.clear()  # Completion is NOT idempotent; never replay a committed batch.
            written = 0
    try:
        writer = DocWriter(root / 'docs', shard_size=5000)
        run.q.lease_urls(snapshot_id, 0, LEASE_SECONDS)  # Validate snapshot, apply exclusions.
        with _stop_event() as stop:
            while not stop.is_set():
                run.tick()
                jobs = _detail_wave(run, buffers, stop)
                if not jobs:
                    if not _remaining(run):
                        break
                    stop.wait(0.05)
                    continue
                for row, fetched, error in run.execute(jobs, adapters, 'detail', stop):
                    last_error = row.last_error
                    if error:
                        last_error = _error(error)
                        result = run.q.mark_failed_attempt(row.url_norm, row.source, last_error,
                                                          max_attempts=3, backoff_s=backoff_s)
                        if result != 'exhausted':
                            continue
                    fallback = row.exhausted or error is not None
                    if fallback:
                        fetched = [FetchedDoc(row.title, row.snippet, [], row.date, row.src_meta, 'public', None)]
                    docs, rules = [], []
                    for item in fetched:
                        rule = check_doc(item, filters)
                        if rule:
                            rules.append(rule)
                        else:
                            docs.append(_doc(row, item, 'snippet' if fallback or item.access == 'restricted' else 'full'))
                    if not docs and rules:
                        run.q.mark_filtered(row.url_norm, row.source, rules[0])
                        continue
                    docs = list({d.doc_id: d for d in docs}.values())
                    for doc in docs:
                        writer.write(doc)
                        written += 1
                        if written >= BATCH_SIZE:
                            # A URL can contain >200 threads. Its completion waits for all.
                            writer.flush_and_fsync()
                            commit()
                            written = 0
                    level = 'snippet' if fallback or any(d.fetch_level == 'snippet' for d in docs) else 'full'
                    access = 'restricted' if any(d.access == 'restricted' for d in docs) else 'public'
                    batch[(row.url_norm, row.source)] = (row.url_norm, row.source, len(docs), last_error, level, access)
                    if len(batch) >= BATCH_SIZE:
                        commit()
                commit()
                if not any(buffers[s] for s in sources if run.active(s)) and not _remaining(run):
                    break
            status = 'stopped' if stop.is_set() else 'done'
    finally:
        # Never complete pending writes after fencing or another exception.
        try:
            if writer is not None:
                writer.close()
        finally:
            run.close(status)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['list', 'detail'])
    parser.add_argument('--sid', required=True)
    parser.add_argument('--snapshot')
    parser.add_argument('--collection', type=Path)
    args = parser.parse_args(argv)
    if args.kind == 'detail' and not args.snapshot:
        parser.error('detail requires --snapshot')
    try:
        if args.kind == 'list':
            print(run_list(args.sid, collection=args.collection))
        else:
            run_detail(args.sid, args.snapshot, collection=args.collection)
    except Exception as exc:
        print(f'Worker error: {_error(exc)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
